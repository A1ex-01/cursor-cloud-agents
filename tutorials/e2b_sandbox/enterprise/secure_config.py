"""企业级 · 沙箱安全加固配置

生产环境里，沙箱不是「创建出来能跑代码」就够了，还要回答安全团队的问题：
它能访问哪些网络？密钥怎么进去又不泄露？超时怎么办？怎么区分不同租户？

E2B 的 `Sandbox.create()` 提供了一整套企业级参数，本模块把它们整理成一个
「加固配置构造器」，并解释每个参数对应的安全含义。

运行（离线演示，会打印脱敏后的配置并用本地沙箱走一遍流程）：
    python tutorials/e2b_sandbox/enterprise/secure_config.py
"""

import os
import sys

from dotenv import load_dotenv

# 让本文件既能被直接运行，也能被其它脚本导入时找到 _local_sandbox
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _local_sandbox import open_sandbox  # noqa: E402

load_dotenv()


def build_enterprise_sandbox_config(
    *,
    tenant_id: str,
    user_id: str,
    session_id: str,
    allowed_domains: list[str] | None = None,
    timeout: int = 300,
) -> dict:
    """构造一套「企业级加固」的 Sandbox.create() 关键字参数。

    返回的 dict 可直接展开传给真实的 e2b：``Sandbox.create(**config)``。
    """
    # 1) 密钥：只从进程环境读取，绝不硬编码；再作为环境变量注入沙箱。
    #    这样密钥只在运行期存在于沙箱内存，代码仓库 / 日志里都看不到明文。
    injected_envs = {}
    for name in ("OPENAI_API_KEY", "DATABASE_URL", "INTERNAL_API_TOKEN"):
        if os.getenv(name):
            injected_envs[name] = os.environ[name]

    # 2) 网络出口白名单：默认拒绝所有外网，只放行明确允许的域名 / 网段。
    #    这是防数据外泄（exfiltration）的关键——即使模型被诱导，也出不去。
    network = None
    allow_internet_access = True
    if allowed_domains is not None:
        # allow_out 为空列表 = 除显式规则外全部拒绝；这里只放行白名单域名。
        network = {"allow_out": allowed_domains}
        allow_internet_access = False  # 与白名单配合，未列出的目标一律拒绝

    config = {
        # 自定义模板：预装公司内部依赖 / 工具的镜像（见 enterprise/README.md）
        "template": os.getenv("E2B_TEMPLATE_ID", "base"),
        # 会话最长存活时间（秒）。Pro 最长 24h，Hobby 最长 1h。
        "timeout": timeout,
        # secure=True：envd 需要访问令牌，别人拿到沙箱地址也无法直接操作。
        "secure": True,
        # 内网访问策略
        "allow_internet_access": allow_internet_access,
        # 生命周期：超时不销毁，而是「暂停」（保存快照），下次按需自动恢复，省钱又保状态。
        "lifecycle": {"on_timeout": "pause", "auto_resume": True},
        # 元数据：给每个沙箱打上租户 / 用户 / 会话标签，便于审计、计费、按租户清理。
        "metadata": {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "session_id": session_id,
            "env": os.getenv("APP_ENV", "dev"),
        },
        # 注入的密钥（运行期环境变量）
        "envs": injected_envs,
    }
    if network is not None:
        config["network"] = network
    return config


def _redacted(config: dict) -> dict:
    """打印前对密钥做脱敏，避免把明文写进日志。"""
    safe = dict(config)
    safe["envs"] = {k: "***REDACTED***" for k in config.get("envs", {})}
    return safe


def create_enterprise_sandbox(**kwargs):
    """按加固配置创建沙箱：有 E2B_API_KEY 用真实云沙箱，否则回退本地（忽略安全参数，仅演示流程）。"""
    config = build_enterprise_sandbox_config(**kwargs)
    print("== 加固后的 Sandbox.create() 配置（已脱敏）==")
    import json

    print(json.dumps(_redacted(config), ensure_ascii=False, indent=2))

    if os.getenv("E2B_API_KEY"):
        from e2b_code_interpreter import Sandbox

        return Sandbox.create(**config), "e2b"
    print("\n[提示] 未检测到 E2B_API_KEY，回退本地沙箱（安全参数在本地不生效，仅演示流程）。")
    return open_sandbox(timeout=config["timeout"])


def main() -> None:
    sandbox, backend = create_enterprise_sandbox(
        tenant_id="acme-corp",
        user_id="u-1001",
        session_id="sess-abc",
        # 只允许沙箱访问公司内网 API 和 PyPI 镜像，其它一律拒绝
        allowed_domains=["api.internal.acme-corp.com", "pypi.org", "files.pythonhosted.org"],
        timeout=600,
    )
    print(f"\n== 沙箱已创建，后端：{backend} ==")
    with sandbox:
        execution = sandbox.run_code("import os; print('沙箱内可见的注入密钥数量:', "
                                     "len([k for k in os.environ if k.endswith('_KEY') or k.endswith('_URL') or k.endswith('_TOKEN')]))")
        print("沙箱内执行:", "".join(execution.logs.stdout).strip())
    print("\n== 完成 ==")


if __name__ == "__main__":
    main()
