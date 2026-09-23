"""01 · E2B 沙箱快速上手

本示例演示 E2B「代码解释器沙箱」最核心的能力：

    1. 创建一个云端隔离沙箱
    2. 在沙箱里执行 Python 代码（run_code）
    3. 读取执行结果：返回值(text) / 标准输出(logs.stdout) / 错误(error)
    4. 沙箱是「有状态」的：后一次执行能引用前一次定义的变量

运行：
    python tutorials/e2b_sandbox/01_quickstart.py

无 E2B_API_KEY 时会自动回退到本地模拟沙箱（仅用于离线学习，无隔离性）。

对照真实 E2B 用法（有 key 时本示例内部就是这样调用的）：
    from e2b_code_interpreter import Sandbox
    with Sandbox.create(timeout=300) as sandbox:
        execution = sandbox.run_code("x = 21; x * 2")
        print(execution.text)   # -> "42"
"""

from dotenv import load_dotenv

from _local_sandbox import open_sandbox

load_dotenv()


def main() -> None:
    sandbox, backend = open_sandbox(timeout=300)
    print(f"== 使用的沙箱后端：{backend}（sandbox_id={sandbox.sandbox_id}）==\n")

    with sandbox:
        # 1) 执行代码并拿到「最后一个表达式」的值
        execution = sandbox.run_code("x = 21\nx * 2")
        print("[1] 表达式返回值 execution.text =", execution.text)

        # 2) 沙箱是有状态的：这里可以直接用上面定义的 x
        execution = sandbox.run_code("print(f'x 现在是 {x}')")
        print("[2] 标准输出 execution.logs.stdout =", "".join(execution.logs.stdout).strip())

        # 3) 执行一段更真实的数据处理代码
        code = """
import statistics
data = [3, 1, 4, 1, 5, 9, 2, 6]
print("原始数据:", data)
print("平均值:", statistics.mean(data))
print("标准差:", round(statistics.pstdev(data), 3))
sorted(data)
"""
        execution = sandbox.run_code(code)
        print("\n[3] stdout:\n" + "".join(execution.logs.stdout).rstrip())
        print("[3] 返回值(排序结果):", execution.text)

        # 4) 错误处理：沙箱内的异常不会让你的程序崩溃，而是通过 error 返回
        execution = sandbox.run_code("1 / 0")
        if execution.error:
            print(f"\n[4] 捕获到沙箱内异常: {execution.error.name}: {execution.error.value}")

    print("\n== 沙箱已关闭并清理 ==")


if __name__ == "__main__":
    main()
