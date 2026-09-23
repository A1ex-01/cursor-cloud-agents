"""04 · 在 LangGraph 智能体里使用 E2B 沙箱工具

把上一节的「执行代码」工具挂到一个 LangGraph 的 ReAct 智能体上，
智能体就能「思考 -> 决定写代码 -> 在沙箱里执行 -> 根据结果继续」循环推理。

本示例分两种运行方式：
    - 有大模型 key：用 create_react_agent 跑完整智能体，看它自己写代码、跑代码、给结论；
    - 无大模型 key：用 ToolNode 手动喂一个「工具调用」，离线验证「工具节点 -> 沙箱执行」这条链路是通的。

运行：
    python tutorials/e2b_sandbox/04_langgraph_agent.py
"""

import os

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, create_react_agent

from _local_sandbox import open_sandbox

# 复用上一节封装好的工具工厂
import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location(
    "tool03", pathlib.Path(__file__).with_name("03_langchain_tool.py")
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
make_python_tool = _mod.make_python_tool

load_dotenv()


def run_full_agent(sandbox) -> None:
    """有大模型 key 时：完整的 ReAct 智能体。"""
    from langchain_openai import ChatOpenAI

    run_python = make_python_tool(sandbox)
    agent = create_react_agent(
        model=ChatOpenAI(model="gpt-4o-mini"),
        tools=[run_python],
        prompt="你是一个数据分析助手。需要计算或处理数据时，必须写 Python 代码并用 run_python 工具执行，不要自己心算。",
    )
    question = "有一组销售额 [120, 85, 300, 45, 210, 95]，帮我算出总和、平均值和最大值。"
    print(f"[用户] {question}\n")
    result = agent.invoke({"messages": [HumanMessage(content=question)]})
    print("[智能体最终回答]", result["messages"][-1].content)


def run_offline_toolnode(sandbox) -> None:
    """无大模型 key 时：搭一个最小 LangGraph 图，用 ToolNode 在沙箱里执行工具调用。

    这样即使没有大模型，也能真实验证「LangGraph 图 -> ToolNode -> 沙箱执行」这条链路。
    ToolNode 需要在编译后的图的运行时上下文中调用，所以这里用 StateGraph 包一层。
    """
    run_python = make_python_tool(sandbox)

    graph = StateGraph(MessagesState)
    graph.add_node("tools", ToolNode([run_python]))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    app = graph.compile()

    # 模拟「模型已经决定调用 run_python」这一步，作为图的输入
    fake_ai_message = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "run_python",
                "args": {"code": "vals=[120,85,300,45,210,95]\n"
                                  "print('总和', sum(vals))\n"
                                  "print('平均', sum(vals)/len(vals))\n"
                                  "print('最大', max(vals))"},
                "id": "call_1",
                "type": "tool_call",
            }
        ],
    )
    out = app.invoke({"messages": [fake_ai_message]})
    tool_message = out["messages"][-1]
    print("[LangGraph 图里的 ToolNode 在沙箱中执行工具调用，返回给模型的内容]:")
    print(tool_message.content)


def main() -> None:
    sandbox, backend = open_sandbox()
    print(f"== 使用的沙箱后端：{backend} ==\n")

    with sandbox:
        if os.getenv("OPENAI_API_KEY"):
            print(">> 检测到 OPENAI_API_KEY，运行完整 ReAct 智能体\n")
            run_full_agent(sandbox)
        else:
            print(">> 未检测到大模型 key，运行离线 ToolNode 演示\n")
            run_offline_toolnode(sandbox)

    print("\n== 完成 ==")


if __name__ == "__main__":
    main()
