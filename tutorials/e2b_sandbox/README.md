# E2B 沙箱：从入门到企业级

> 让你的智能体安全地「写代码、跑代码」。

本章讲清楚三件事：

1. **为什么** 智能体需要一个隔离沙箱；
2. **怎么用** E2B 沙箱（创建、执行代码、读写文件、跑命令）；
3. **怎么接** 到 LangChain / LangGraph / DeepAgents，以及**企业级**该怎么落地。

每个知识点都配了一个可直接运行的脚本，且**没有云端密钥也能离线跑通**（自动回退到本地模拟沙箱）。

---

## 1. 为什么需要沙箱？

大模型智能体强大的地方在于能生成并执行代码来解决问题（算数据、画图、调 API、跑测试……）。但「让 AI 生成的代码在你的服务器上直接跑」是巨大的安全风险：

- 代码可能删文件、读密钥、发起网络请求、挖矿、横向渗透；
- 就算模型没恶意，也可能因为幻觉写出破坏性命令；
- 多用户 / 多租户场景下，一个用户的代码不能影响另一个用户。

**沙箱（Sandbox）** 就是答案：把代码放进一个**隔离、可丢弃、受限**的环境里执行。

[E2B](https://e2b.dev) 提供的正是这样的云沙箱——每个会话跑在独立的 **Firecracker microVM**（各自独立的内核）里，具备强隔离、可控出口网络、秒级启动、可暂停/快照等特性，专为 AI 智能体设计。

---

## 2. 安装与准备

```bash
pip install -r requirements.txt         # 项目根目录
cp .env.example .env                     # 填入 E2B_API_KEY（在 https://e2b.dev Dashboard 获取）
```

两个相关的包：

| 包 | 作用 |
| --- | --- |
| `e2b` | 底层 SDK：`Sandbox`、文件系统、命令执行、网络/生命周期配置 |
| `e2b-code-interpreter` | 在其上封装的「代码解释器」沙箱，提供有状态的 `run_code()` |

> **离线也能学**：所有示例在检测不到 `E2B_API_KEY` 时，会自动回退到 [`_local_sandbox.py`](_local_sandbox.py) 里的本地模拟沙箱。它接口一致但**在本机进程内执行、毫无隔离**，⚠️ **仅供离线学习，绝不能用于不可信代码或生产**。

---

## 3. 基础用法

### 3.1 执行代码 —— [`01_quickstart.py`](01_quickstart.py)

```python
from e2b_code_interpreter import Sandbox

with Sandbox.create(timeout=300) as sandbox:
    execution = sandbox.run_code("x = 21; x * 2")
    print(execution.text)              # -> "42"（最后一个表达式的值）
    print(execution.logs.stdout)       # print 出来的内容
    if execution.error:                # 沙箱内异常不会让你的程序崩溃
        print(execution.error.name)
```

要点：
- 沙箱是**有状态**的，后一次 `run_code` 能引用前一次定义的变量；
- 返回的 `Execution` 里，`text` 是最后表达式的值，`logs.stdout/stderr` 是输出，`error` 是异常信息；
- `with` 语句退出时沙箱自动关闭（停止计费）。

### 3.2 文件与命令 —— [`02_files_and_commands.py`](02_files_and_commands.py)

沙箱本质是一台完整 Linux 机器：

```python
sandbox.files.write("/home/user/data.csv", "a,b\n1,2\n")   # 写文件
content = sandbox.files.read("/home/user/data.csv")          # 读文件
sandbox.files.list("/home/user")                             # 列目录
result = sandbox.commands.run("python analyze.py")           # 跑命令
print(result.stdout, result.exit_code)
```

这就是「智能体工作台」的雏形：把数据放进去，让智能体写脚本、跑脚本、取结果。

> 命令默认工作目录是 `/home/user`，脚本里用相对路径最省心。

---

## 4. 接入 LangChain / LangGraph / DeepAgents

### 4.1 封装成 LangChain 工具 —— [`03_langchain_tool.py`](03_langchain_tool.py)

把 `run_code` 包成标准 `@tool`，任何 LangChain 模型都能通过 tool calling 调用它：

```python
@tool
def run_python(code: str) -> str:
    """在隔离沙箱中执行 Python 代码并返回结果。"""
    execution = sandbox.run_code(code)
    ...
model = ChatOpenAI(model="gpt-4o-mini").bind_tools([run_python])
```

### 4.2 LangGraph 智能体 —— [`04_langgraph_agent.py`](04_langgraph_agent.py)

把工具挂到 `create_react_agent` 上，智能体就能「思考→写代码→执行→看结果→继续」：

```python
from langgraph.prebuilt import create_react_agent
agent = create_react_agent(model=ChatOpenAI(...), tools=[run_python], prompt="...")
agent.invoke({"messages": [HumanMessage(content="算出这组数的总和与平均值")]})
```

（无大模型 key 时，脚本会搭一个最小 `StateGraph`，用 `ToolNode` 离线验证「图→沙箱执行」链路。）

### 4.3 DeepAgents 自定义沙箱后端 —— [`05_deepagents_backend.py`](05_deepagents_backend.py)

DeepAgents 的文件工具与 `execute` 工具都由「后端（backend）」提供。只要实现
`SandboxBackendProtocol`（核心是 `execute()`），`create_deep_agent` 就会自动给智能体加上 `execute` 工具：

```python
from deepagents.backends.sandbox import BaseSandbox

class E2BBackend(BaseSandbox):
    def __init__(self, sandbox): self._sandbox = sandbox
    @property
    def id(self): return self._sandbox.sandbox_id
    def execute(self, command, *, timeout=None):
        res = self._sandbox.commands.run(command, timeout=timeout or 120)
        return ExecuteResponse(output=res.stdout + res.stderr, exit_code=res.exit_code)
    def upload_files(self, files): ...
    def download_files(self, paths): ...

agent = create_deep_agent(model="openai:gpt-4o-mini", backend=E2BBackend(sandbox))
```

只实现 4 个原语，`BaseSandbox` 就会用它们自动拼出 `read/write/ls/grep/glob` 等全部文件工具。

---

## 5. 企业级用法

真正上生产，需要考虑并发、安全、成本、审计。详见 [`enterprise/`](enterprise/README.md)：

| 主题 | 脚本 | 解决的问题 |
| --- | --- | --- |
| 沙箱池与生命周期 | [`enterprise/sandbox_pool.py`](enterprise/sandbox_pool.py) | 复用沙箱、限制并发上限、避免冷启动和资源泄漏 |
| 安全加固配置 | [`enterprise/secure_config.py`](enterprise/secure_config.py) | 出口网络白名单、密钥注入、访问令牌、超时暂停、租户标签 |
| 可观测性与成本 | [`enterprise/observability.py`](enterprise/observability.py) | 结构化日志、指标、审计轨迹、成本估算 |

---

## 6. 常见问题

- **沙箱最长能活多久？** `timeout` 以秒计，默认 300s；Pro 最长 24h，Hobby 最长 1h。用 `lifecycle` 可让超时后「暂停」而非销毁。
- **忘了关沙箱会怎样？** 会持续计费直到超时。生产中务必用 `with` 或沙箱池统一回收。
- **能装第三方库吗？** 能。`sandbox.commands.run("pip install pandas")`，或做成自定义模板预装（更快）。
- **代码执行结果怎么拿图片？** `run_code` 的 `Execution.results` 会带上图表等富结果（png/svg 等）。

---

## 运行本章全部示例

```bash
python tutorials/e2b_sandbox/01_quickstart.py
python tutorials/e2b_sandbox/02_files_and_commands.py
python tutorials/e2b_sandbox/03_langchain_tool.py
python tutorials/e2b_sandbox/04_langgraph_agent.py
python tutorials/e2b_sandbox/05_deepagents_backend.py
python tutorials/e2b_sandbox/enterprise/sandbox_pool.py
python tutorials/e2b_sandbox/enterprise/secure_config.py
python tutorials/e2b_sandbox/enterprise/observability.py
```
