"""02 · 在沙箱里读写文件、执行 Shell 命令

除了执行 Python 代码，E2B 沙箱本质上是一台完整的 Linux 机器，你可以：

    - 用 sandbox.files.write / read / list 读写文件系统
    - 用 sandbox.commands.run 执行任意 shell 命令（pip 安装、运行脚本、调用 CLI...）

这让它非常适合作为「智能体的工作台」：把数据写进去，让智能体写脚本、跑脚本、看结果。

运行：
    python tutorials/e2b_sandbox/02_files_and_commands.py

对照真实 E2B 用法：
    from e2b_code_interpreter import Sandbox
    with Sandbox.create() as sandbox:
        sandbox.files.write("/home/user/data.csv", "a,b\\n1,2\\n")
        result = sandbox.commands.run("wc -l /home/user/data.csv")
        print(result.stdout, result.exit_code)
"""

from dotenv import load_dotenv

from _local_sandbox import open_sandbox

load_dotenv()


def main() -> None:
    sandbox, backend = open_sandbox()
    print(f"== 使用的沙箱后端：{backend} ==\n")

    with sandbox:
        # 1) 写入一个 CSV 文件到沙箱
        csv_content = "name,score\nAlice,90\nBob,75\nCarol,88\n"
        sandbox.files.write("/home/user/scores.csv", csv_content)
        print("[1] 已写入 /home/user/scores.csv")

        # 2) 列出目录，确认文件存在
        print("[2] /home/user 下的文件:", sandbox.files.list("/home/user"))

        # 3) 用 shell 命令统计行数
        result = sandbox.commands.run("wc -l /home/user/scores.csv")
        print(f"[3] wc -l 输出: {result.stdout.strip()} (exit_code={result.exit_code})")

        # 4) 让沙箱写一个脚本并运行它 —— 这正是智能体常见的用法
        #    命令默认工作目录是 /home/user，所以脚本里用相对路径 'scores.csv' 即可。
        script = """
import csv
with open('scores.csv') as f:
    rows = list(csv.DictReader(f))
avg = sum(int(r['score']) for r in rows) / len(rows)
print(f'共 {len(rows)} 条记录，平均分 {avg:.1f}')
"""
        sandbox.files.write("/home/user/analyze.py", script)
        result = sandbox.commands.run("python analyze.py")
        print(f"[4] 运行 analyze.py 输出: {result.stdout.strip()}")

        # 5) 把文件从沙箱读回本地
        content = sandbox.files.read("/home/user/scores.csv")
        print(f"[5] 读回文件内容首行: {content.splitlines()[0]}")

    print("\n== 完成 ==")


if __name__ == "__main__":
    main()
