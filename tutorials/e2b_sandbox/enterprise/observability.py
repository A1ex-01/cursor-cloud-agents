"""企业级 · 可观测性、审计与成本追踪

生产里你必须能回答：谁在什么时候、在哪个沙箱里、跑了什么代码、花了多长时间、花了多少钱、成功还是失败。
本模块用一个「可观测沙箱包装器」拦截每次 run_code，输出结构化日志、累积指标、审计轨迹和成本估算。

这套东西可以直接对接你的日志系统（如 ELK / Loki）、指标系统（Prometheus）和
LangSmith（把每次沙箱执行作为一次 trace）。

运行（离线演示）：
    python tutorials/e2b_sandbox/enterprise/observability.py
"""

import json
import os
import sys
import time
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _local_sandbox import open_sandbox  # noqa: E402

# E2B 大致按「沙箱运行时长 × 规格」计费；这里用一个可配置的每秒单价做示意。
# 真实单价请以 https://e2b.dev/pricing 为准，并按 vCPU / 内存规格调整。
COST_PER_SECOND_USD = float(os.getenv("E2B_COST_PER_SECOND_USD", "0.0001"))


@dataclass
class Metrics:
    executions: int = 0
    errors: int = 0
    total_seconds: float = 0.0
    audit_log: list[dict] = field(default_factory=list)

    @property
    def estimated_cost_usd(self) -> float:
        return round(self.total_seconds * COST_PER_SECOND_USD, 6)

    def summary(self) -> dict:
        return {
            "executions": self.executions,
            "errors": self.errors,
            "success_rate": round(1 - self.errors / self.executions, 3) if self.executions else None,
            "total_seconds": round(self.total_seconds, 4),
            "estimated_cost_usd": self.estimated_cost_usd,
        }


class ObservableSandbox:
    """包装一个沙箱，为每次 run_code 增加结构化日志 / 指标 / 审计 / 成本。"""

    def __init__(self, sandbox, *, tenant_id: str, user_id: str) -> None:
        self._sandbox = sandbox
        self._tenant_id = tenant_id
        self._user_id = user_id
        self.metrics = Metrics()

    @property
    def sandbox_id(self) -> str:
        return self._sandbox.sandbox_id

    def _emit(self, event: dict) -> None:
        # 结构化 JSON 日志：直接采集到日志平台即可检索 / 告警。
        print(json.dumps(event, ensure_ascii=False))

    def run_code(self, code: str, **kwargs):
        started = time.time()
        execution = self._sandbox.run_code(code, **kwargs)
        elapsed = time.time() - started

        failed = execution.error is not None
        self.metrics.executions += 1
        self.metrics.errors += int(failed)
        self.metrics.total_seconds += elapsed

        record = {
            "ts": round(started, 3),
            "level": "error" if failed else "info",
            "event": "sandbox.run_code",
            "sandbox_id": self.sandbox_id,
            "tenant_id": self._tenant_id,
            "user_id": self._user_id,
            "elapsed_s": round(elapsed, 4),
            "ok": not failed,
            "error": execution.error.name if failed else None,
            # 审计：记录执行了什么代码（生产中可按合规要求做哈希 / 截断 / 脱敏）
            "code_preview": code.strip().splitlines()[0][:80] if code.strip() else "",
        }
        self._emit(record)
        self.metrics.audit_log.append(record)
        return execution

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._sandbox.kill()


def main() -> None:
    sandbox, backend = open_sandbox()
    print(f"== 使用的沙箱后端：{backend}；下面每行 JSON 就是一条可采集的结构化日志 ==\n")

    obs = ObservableSandbox(sandbox, tenant_id="acme-corp", user_id="u-1001")
    with obs:
        obs.run_code("sum(range(100))")
        obs.run_code("import time; time.sleep(0.05); print('done')")
        obs.run_code("open('/nonexistent/really').read()")  # 故意失败，演示错误统计

    print("\n== 指标汇总（可推送到 Prometheus / 计费系统）==")
    print(json.dumps(obs.metrics.summary(), ensure_ascii=False, indent=2))
    print(f"\n== 审计轨迹共 {len(obs.metrics.audit_log)} 条 ==")


if __name__ == "__main__":
    main()
