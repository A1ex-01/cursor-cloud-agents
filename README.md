# LangGraph / LangChain / DeepAgents 教学库

面向工程师的**智能体（Agent）实战教学库**，聚焦如何用 LangChain、LangGraph 与 DeepAgents 构建可以「写代码、跑代码」的智能体，并把它们安全地跑在生产 / 企业环境里。

每个章节都遵循同一风格：

- 一篇**中文教程**（`README.md`）讲清「是什么 / 为什么 / 怎么用」；
- 若干**可直接运行的示例脚本**（`*.py`），每个脚本聚焦一个知识点；
- 尽量做到**没有云端密钥也能离线跑通**（用本地回退实现体会流程），有密钥后一行不改切到真实云服务。

---

## 章节目录

| 章节 | 主题 | 说明 |
| --- | --- | --- |
| [`tutorials/e2b_sandbox`](tutorials/e2b_sandbox/) | **E2B 沙箱：从入门到企业级** | 为什么智能体需要沙箱；E2B 基础用法；与 LangChain / LangGraph / DeepAgents 集成；企业级（沙箱池、网络隔离、密钥管理、可观测性、自定义模板、自托管）。 |

> 更多章节持续补充中。

---

## 快速开始

```bash
# 1. 克隆后进入项目
cd cursor-cloud-agents

# 2. 创建虚拟环境并安装依赖
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. 配置密钥（复制模板后填入自己的 key）
cp .env.example .env
#   然后编辑 .env，至少填 E2B_API_KEY；用到大模型的示例再填对应的 *_API_KEY

# 4. 运行第一个示例
python tutorials/e2b_sandbox/01_quickstart.py
```

### 关于「离线也能跑」

大部分示例在**检测不到 `E2B_API_KEY`** 时，会自动回退到一个 **本地模拟沙箱**（`tutorials/e2b_sandbox/_local_sandbox.py`），让你在没有云端账号时也能体会完整流程与代码结构。

⚠️ **本地模拟沙箱只用于离线教学，它在你本机进程内执行代码，没有任何隔离性，绝不能用于运行不可信代码或用于生产。** 真实隔离必须用 E2B 云沙箱（或自托管集群）。

---

## 目录结构

```
.
├── README.md                 # 本文件：教学库总览
├── requirements.txt          # 统一依赖
├── .env.example              # 环境变量模板（复制为 .env 使用）
├── .gitignore
└── tutorials/
    └── e2b_sandbox/          # 第 1 个章节：E2B 沙箱
        ├── README.md         # 章节主教程
        ├── _local_sandbox.py # 离线回退用的本地模拟沙箱（仅教学）
        ├── 01_quickstart.py
        ├── 02_files_and_commands.py
        ├── 03_langchain_tool.py
        ├── 04_langgraph_agent.py
        ├── 05_deepagents_backend.py
        └── enterprise/       # 企业级用法
            ├── README.md
            ├── sandbox_pool.py
            ├── secure_config.py
            └── observability.py
```
