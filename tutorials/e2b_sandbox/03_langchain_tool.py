"""03 · 把 E2B 沙箱封装成一个 LangChain 工具（Tool）

智能体本身只会「说」，要让它真正「做」——比如算一道数学题、跑一段数据分析——
就得给它一个能执行代码的工具。这里我们把 E2B 沙箱的 run_code 封装成标准的
LangChain `@tool`，之后就能挂到任何 LangChain / LangGraph 智能体上。

本示例可离线运行：直接调用工具（tool.invoke）验证它能在沙箱里跑代码；
如果配置了大模型 key，最后还会演示把工具绑定到模型上让模型自己决定调用。

运行：
    python tutorials/e2b_sandbox/03_langchain_tool.py
"""

import os

from dotenv import load_dotenv
from langchain_core.tools import tool

from _local_sandbox import open_sandbox

load_dotenv()


def make_python_tool(sandbox):
    """基于一个已打开的沙箱，构造一个「执行 Python 代码」的 LangChain 工具。"""

    @tool
    def run_python(code: str) -> str:
        """在隔离沙箱中执行 Python 代码并返回结果。

        适合做计算、数据处理、画图等。传入完整、可独立运行的 Python 代码；
        需要输出结果时请用 print()。
        """
        execution = sandbox.run_code(code)
        if execution.error:
            return f"执行出错 {execution.error.name}: {execution.error.value}"
        stdout = "".join(execution.logs.stdout).strip()
        parts = []
        if stdout:
            parts.append(f"stdout:\n{stdout}")
        if execution.text:
            parts.append(f"返回值: {execution.text}")
        return "\n".join(parts) or "（无输出）"

    return run_python


def main() -> None:
    sandbox, backend = open_sandbox()
    print(f"== 使用的沙箱后端：{backend} ==\n")

    with sandbox:
        run_python = make_python_tool(sandbox)

        # 1) 离线可验证：像智能体那样「调用工具」
        print("[1] 直接调用工具计算斐波那契数列:")
        result = run_python.invoke(
            {"code": "def fib(n):\n"
                     "    a, b = 0, 1\n"
                     "    for _ in range(n):\n"
                     "        a, b = b, a + b\n"
                     "    return a\n"
                     "print([fib(i) for i in range(10)])"}
        )
        print(result)

        # 2) 工具的元信息（模型正是靠这些描述决定何时调用它）
        print(f"\n[2] 工具名: {run_python.name}")
        print(f"    工具描述: {run_python.description.splitlines()[0]}")

        # 3) 有大模型 key 时，演示模型自己决定调用工具（tool calling）
        if os.getenv("OPENAI_API_KEY"):
            from langchain_openai import ChatOpenAI

            print("\n[3] 检测到 OPENAI_API_KEY，演示模型自主调用工具:")
            model = ChatOpenAI(model="gpt-4o-mini").bind_tools([run_python])
            ai_msg = model.invoke("用代码计算 1 到 100 的和，并告诉我结果")
            if ai_msg.tool_calls:
                call = ai_msg.tool_calls[0]
                print(f"    模型决定调用工具 {call['name']}，参数 code=\n{call['args']['code']}")
                print("    工具执行结果:", run_python.invoke(call["args"]))
            else:
                print("    模型这次没有调用工具，直接回答:", ai_msg.content)
        else:
            print("\n[3] 未检测到 OPENAI_API_KEY，跳过「模型自主调用」演示。")
            print("    配置 .env 里的 OPENAI_API_KEY 后可看到模型自己决定调用该工具。")

    print("\n== 完成 ==")


if __name__ == "__main__":
    main()
