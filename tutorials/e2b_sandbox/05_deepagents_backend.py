"""05 · 给 DeepAgents 写一个 E2B「沙箱后端」（Sandbox Backend）

DeepAgents 的文件工具（read_file/write_file/ls...）和代码执行工具（execute）都由一个
「后端（backend）」提供。只要后端实现了 `SandboxBackendProtocol`，create_deep_agent
就会自动给智能体加上 `execute` 工具，让它能在隔离环境里跑 shell 命令、装依赖、跑脚本。

DeepAgents 自带 LangSmithSandbox 等后端；这里我们演示**如何自己接入 E2B**：
只要继承 `BaseSandbox` 并实现 4 个方法（execute / upload_files / download_files / id），
其余文件操作 BaseSandbox 会基于 execute 自动帮我们实现。

本示例可离线运行：直接调用 backend.execute(...) 验证「后端 -> 沙箱」链路；
配置了大模型 key 时，会用 create_deep_agent 跑一个真正会写代码、跑代码的智能体。

运行：
    python tutorials/e2b_sandbox/05_deepagents_backend.py
"""

import os

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox
from dotenv import load_dotenv

from _local_sandbox import open_sandbox

load_dotenv()


class E2BBackend(BaseSandbox):
    """把 E2B 沙箱（或离线本地沙箱）接入 DeepAgents 的自定义后端。

    只需实现 4 个原语，BaseSandbox 会用它们拼出 read/write/ls/grep/glob 等全部文件工具。
    """

    def __init__(self, sandbox) -> None:
        self._sandbox = sandbox

    @property
    def id(self) -> str:
        return self._sandbox.sandbox_id

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        try:
            res = self._sandbox.commands.run(command, timeout=timeout or 120)
            stdout, stderr, exit_code = res.stdout, res.stderr, res.exit_code
        except Exception as exc:  # noqa: BLE001
            # E2B 在命令非零退出时会抛 CommandExitException，异常对象自带 stdout/stderr/exit_code
            stdout = getattr(exc, "stdout", "") or ""
            stderr = getattr(exc, "stderr", None) or str(exc)
            exit_code = getattr(exc, "exit_code", 1)
        return ExecuteResponse(output=(stdout or "") + (stderr or ""), exit_code=exit_code)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        responses: list[FileUploadResponse] = []
        for path, content in files:
            try:
                self._sandbox.files.write(path, content)
                responses.append(FileUploadResponse(path=path, error=None))
            except Exception as exc:  # noqa: BLE001
                responses.append(FileUploadResponse(path=path, error=str(exc)))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        for path in paths:
            try:
                data = self._sandbox.files.read(path)
                content = data.encode() if isinstance(data, str) else data
                responses.append(FileDownloadResponse(path=path, content=content, error=None))
            except Exception:  # noqa: BLE001
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="file_not_found")
                )
        return responses


def main() -> None:
    sandbox, backend_name = open_sandbox()
    print(f"== 使用的沙箱后端：{backend_name} ==\n")

    with sandbox:
        backend = E2BBackend(sandbox)
        print(f"[1] 自定义后端已创建，backend.id = {backend.id}")

        # 离线可验证：直接调用后端的 execute（这正是 deepagents 的 execute 工具底层做的事）
        resp = backend.execute("echo 'hello from sandbox' && python3 -c 'print(6*7)'")
        print(f"[2] backend.execute 输出:\n{resp.output.strip()}\n    exit_code={resp.exit_code}")

        # 验证文件上传/下载原语（BaseSandbox 的高层文件工具都建立在它们之上）
        backend.upload_files([("/home/user/hello.txt", b"content from deepagents backend\n")])
        downloaded = backend.download_files(["/home/user/hello.txt"])[0]
        print(f"[3] 上传后再下载读回: {downloaded.content!r} (error={downloaded.error})")

        # 有大模型 key 时：跑一个真正的 deepagent
        if os.getenv("OPENAI_API_KEY"):
            from deepagents import create_deep_agent

            print("\n[4] 检测到 OPENAI_API_KEY，用 create_deep_agent 运行智能体:")
            agent = create_deep_agent(
                model="openai:gpt-4o-mini",
                backend=backend,
                system_prompt="你是一个编程助手。可以用 execute 工具在沙箱里写并运行代码。",
            )
            result = agent.invoke(
                {"messages": [{"role": "user",
                               "content": "写一个 Python 脚本判断 2027 是不是质数，运行它并告诉我结果。"}]}
            )
            print("[智能体最终回答]", result["messages"][-1].content)
        else:
            print("\n[4] 未检测到 OPENAI_API_KEY，跳过完整 deepagent 演示。")
            print("    配置 .env 里的模型 key 后，create_deep_agent 会自动带上 execute 工具。")

    print("\n== 完成 ==")


if __name__ == "__main__":
    main()
