# E2B 沙箱：企业级落地指南

把「能跑」变成「敢在生产跑」。本节聚焦企业真正关心的四类问题：**隔离与安全、并发与成本、持久化、可观测与合规**，并给出可运行的参考实现。

---

## 1. 隔离模型：为什么安全团队会签字

E2B 的每个沙箱会话运行在独立的 **Firecracker microVM** 中，拥有**自己的 guest 内核**，跑在 KVM 上：

- 沙箱里的内核漏洞，还需要再突破一次 Firecracker 才能碰到宿主机；
- 每个 microVM 有独立内存，支持 **pause / snapshot / fork**；
- 相比共享内核的容器，隔离强度更高，适合运行**不可信的、模型生成的代码**。

配套的安全控制：

| 能力 | 说明 | SDK 入口 |
| --- | --- | --- |
| 访问令牌 | envd 需要令牌，拿到沙箱地址也无法直接操作 | `Sandbox.create(secure=True)`（默认开启） |
| 出口网络控制 | 按 IP / CIDR / 域名放行或拒绝出站流量，防数据外泄 | `network={"allow_out": [...], "deny_out": [...]}` / `allow_internet_access=False` |
| 断网运行 | 完全禁止外网 | `allow_internet_access=False` |
| 密钥外置 | 密钥不进镜像、不进代码，运行期注入 | `envs={...}`（从宿主环境读取） |
| 公网 URL 令牌 | 暴露沙箱端口时用令牌保护 | 公开 URL 携带 access token |

参考实现见 [`secure_config.py`](secure_config.py)。核心原则：

- **默认拒绝外网**，只放行明确需要的域名（公司 API、包镜像）；
- **密钥只从环境变量读取**，注入沙箱后只存在于运行期内存，绝不硬编码、不打日志；
- 用 **metadata** 给每个沙箱打上 `tenant_id / user_id / session_id` 标签，用于审计、计费、按租户批量清理。

---

## 2. 并发与成本：沙箱池

E2B 按**沙箱运行时长 × 规格**计费（暂停的沙箱不计费）。生产要点：

1. **复用而非每次新建**：用沙箱池减少冷启动，见 [`sandbox_pool.py`](sandbox_pool.py)。
2. **限制并发上限**：`max_size` 防止打爆配额和账单。
3. **务必回收**：用 `with` / `lease()` / 池的 `close()` 确保沙箱不泄漏（泄漏 = 一直计费）。
4. **合理设置 `timeout`**：给一个兜底超时，避免僵尸沙箱长期存活。

```python
pool = SandboxPool(max_size=8, timeout=600)
with pool.lease() as sandbox:
    sandbox.run_code("...")   # 用完自动归还，供下个请求复用
pool.close()                   # 服务下线时统一回收
```

---

## 3. 持久化：暂停、快照与卷

长会话智能体常需要「关掉再回来还在」。E2B 提供多层持久化：

| 方式 | 恢复速度 | 恢复内容 | 适用 |
| --- | --- | --- | --- |
| **全量暂停/恢复**（默认 pause） | 极快（~内存恢复） | 文件系统 + 内存 + 运行中进程 | 长会话、有状态服务 |
| **仅文件系统快照**（`keep_memory=False`） | 相当于重启 | 只有磁盘文件 | 只关心产出文件、检查点 |
| **持久卷 / 云存储桶（FUSE）** | 挂载即用 | 独立于沙箱生命周期的数据 | 跨会话共享数据、大数据集 |

结合 `lifecycle` 可以让沙箱**超时自动暂停而非销毁**，下次请求到来时自动恢复：

```python
Sandbox.create(
    lifecycle={"on_timeout": "pause", "auto_resume": True},  # 超时暂停并可被流量唤醒
)
```

> 注意：仅文件系统快照不能与 `auto_resume` 同用（没有内存镜像可恢复），需显式 `connect()` 恢复。

---

## 4. 自定义模板：预装依赖，加速冷启动

不要在每次会话里 `pip install`，而是把依赖固化进**自定义模板**（本质就是一个 Dockerfile）：

- 预装公司内部库、CLI、字体、数据集；
- 冷启动更快（E2B 会对模板做快照，可 ~80ms 载入）；
- 用 `Sandbox.create(template="<你的模板ID>")` 使用。

构建流程：写 Dockerfile → 用 E2B CLI/SDK 构建模板 → 拿到模板 ID → 在代码里引用。示例配置里的 `E2B_TEMPLATE_ID` 环境变量就是留给它的。

---

## 5. 可观测性、审计与合规

见 [`observability.py`](observability.py)。生产必须能回答「谁、何时、在哪个沙箱、跑了什么、多久、多少钱、成功否」：

- **结构化日志**：每次执行输出一行 JSON，直接采集到 ELK / Loki；
- **指标**：执行次数、错误率、总时长，推送 Prometheus；
- **审计轨迹**：记录每次执行的代码（可按合规做哈希 / 截断 / 脱敏）与租户/用户；
- **成本估算**：按运行时长估算费用，做预算与告警；
- **LangSmith**：开启 `LANGSMITH_TRACING` 后，可把每次智能体+沙箱执行作为一条 trace 追踪。

---

## 6. 部署形态：Cloud / BYOC / 自托管

| 形态 | 数据边界 | 适用 |
| --- | --- | --- |
| **E2B Cloud** | 托管在 E2B | 起步最快，按用量计费 |
| **BYOC（Bring Your Own Cloud）** | 沙箱模板/快照/日志都在**你自己的 AWS/GCP VPC** 内；敏感流量不经过 E2B Cloud，仅匿名指标上报 | 受监管数据、企业合规；企业版 |
| **自托管 / 开源单节点** | 全部在你自己账户，用 Terraform 一键部署 | 想完全自控、不出网 |

BYOC 与自托管时，把 `E2B_DOMAIN` 指向你自己的集群域名即可（见 `.env.example`）。

---

## 7. 生产 checklist

- [ ] 出口网络默认拒绝，按需白名单放行
- [ ] 密钥全部走环境变量注入，代码/镜像/日志零明文
- [ ] 每个沙箱带 `tenant_id/user_id/session_id` 元数据
- [ ] 用沙箱池限制并发上限，用完必回收
- [ ] 设置兜底 `timeout`，超时暂停或销毁
- [ ] 依赖固化进自定义模板，别在会话里现装
- [ ] 结构化日志 + 指标 + 审计 + 成本告警接入
- [ ] 受监管数据评估 BYOC / 自托管

---

## 运行参考实现

```bash
python tutorials/e2b_sandbox/enterprise/secure_config.py     # 安全加固配置
python tutorials/e2b_sandbox/enterprise/sandbox_pool.py      # 沙箱池与复用
python tutorials/e2b_sandbox/enterprise/observability.py     # 日志/指标/审计/成本
```

> 以上脚本在无 `E2B_API_KEY` 时会回退到本地模拟沙箱以便离线体会流程；真实隔离与安全参数仅在连接真实 E2B（Cloud 或自托管）时生效。
