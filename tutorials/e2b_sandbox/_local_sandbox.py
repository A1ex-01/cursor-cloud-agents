"""离线回退用的「本地模拟沙箱」。

本模块的目的：让**没有 E2B_API_KEY** 的学习者也能把本章的示例跑通，
从而理解代码结构与调用流程。它刻意模仿了 `e2b_code_interpreter.Sandbox`
的一小部分接口：

    - Sandbox.create(...)             创建沙箱（这里是本地对象）
    - sandbox.run_code(code)          执行一段代码，返回 Execution（含 .text/.logs/.error）
    - sandbox.commands.run(cmd)       执行一条 shell 命令
    - sandbox.files.write/read/list   读写沙箱文件系统
    - with Sandbox.create() as sbx:   支持上下文管理器，自动清理

============================  重要安全警告  ============================
LocalSandbox 直接在**当前 Python 进程 / 本机**里执行代码和命令，
它没有任何隔离（no VM, no container, no network isolation）。

它只适合离线学习时体会流程，**绝不能用来运行不可信代码，也绝不能用于生产。**
真正的隔离请使用 E2B 云沙箱（配置 E2B_API_KEY）或自托管的 E2B 集群。
======================================================================
"""

from __future__ import annotations

import ast
import io
import os
import subprocess
import tempfile
import traceback
import uuid
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field


@dataclass
class _Logs:
    stdout: list[str] = field(default_factory=list)
    stderr: list[str] = field(default_factory=list)


@dataclass
class _ExecutionError:
    name: str
    value: str
    traceback: str


@dataclass
class _Execution:
    """对应 e2b 的 Execution：run_code 的返回值。"""

    text: str | None = None
    logs: _Logs = field(default_factory=_Logs)
    error: _ExecutionError | None = None
    results: list = field(default_factory=list)


@dataclass
class _CommandResult:
    """对应 e2b 的 CommandResult：commands.run 的返回值。"""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


class _LocalFilesystem:
    """把「沙箱内路径」映射到本机临时目录，模拟 sandbox.files.*。"""

    def __init__(self, root: str) -> None:
        self._root = root

    def _resolve(self, path: str) -> str:
        # e2b 沙箱默认工作目录是 /home/user；这里把绝对路径挂到临时根目录下。
        return os.path.join(self._root, path.lstrip("/"))

    def write(self, path: str, data: str | bytes) -> None:
        full = self._resolve(path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
        with open(full, mode) as f:
            f.write(data)

    def read(self, path: str) -> str:
        with open(self._resolve(path), "r") as f:
            return f.read()

    def list(self, path: str = "/home/user") -> list[str]:
        full = self._resolve(path)
        if not os.path.isdir(full):
            return []
        return sorted(os.listdir(full))


class _LocalCommands:
    """模拟 sandbox.commands.run。"""

    def __init__(self, home: str) -> None:
        self._home = home

    def run(self, cmd: str, timeout: float | None = 60, **_: object) -> _CommandResult:
        # 本地沙箱把 /home/user 挂到临时目录，因此命令里出现的该绝对前缀也要一并改写，
        # 这样 `wc -l /home/user/x` 之类命令才能找到沙箱内的真实文件。
        cmd = cmd.replace("/home/user", self._home)
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=self._home,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return _CommandResult(
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
        )


class LocalSandbox:
    """一个「本地假沙箱」，接口对齐 e2b_code_interpreter.Sandbox 的常用部分。"""

    def __init__(self, timeout: int = 300, **_: object) -> None:
        self.sandbox_id = f"local-{uuid.uuid4().hex[:8]}"
        self._timeout = timeout
        self._namespace: dict[str, object] = {"__name__": "__sandbox__"}
        self._root = tempfile.mkdtemp(prefix="local_sandbox_")
        home = os.path.join(self._root, "home", "user")
        os.makedirs(home, exist_ok=True)
        self.files = _LocalFilesystem(self._root)
        self.commands = _LocalCommands(home)
        self._home = home

    @classmethod
    def create(cls, *args: object, **kwargs: object) -> "LocalSandbox":
        return cls(**{k: v for k, v in kwargs.items() if k == "timeout"})

    def run_code(self, code: str, language: str | None = None, **_: object) -> _Execution:
        if language not in (None, "python", "py"):
            return _Execution(
                error=_ExecutionError(
                    name="UnsupportedLanguage",
                    value=f"LocalSandbox 仅支持 python，收到 language={language!r}",
                    traceback="",
                )
            )

        stdout_buf, stderr_buf = io.StringIO(), io.StringIO()
        text: str | None = None
        err: _ExecutionError | None = None

        try:
            tree = ast.parse(code)
            last = tree.body[-1] if tree.body else None
            eval_expr = None
            if isinstance(last, ast.Expr):
                eval_expr = ast.Expression(body=last.value)
                tree = ast.Module(body=tree.body[:-1], type_ignores=[])

            with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                exec(compile(tree, "<sandbox>", "exec"), self._namespace)
                if eval_expr is not None:
                    value = eval(compile(eval_expr, "<sandbox>", "eval"), self._namespace)
                    if value is not None:
                        text = repr(value)
        except Exception as exc:  # noqa: BLE001 - 教学演示需要捕获所有异常
            err = _ExecutionError(
                name=type(exc).__name__,
                value=str(exc),
                traceback=traceback.format_exc(),
            )

        logs = _Logs(
            stdout=stdout_buf.getvalue().splitlines(keepends=True),
            stderr=stderr_buf.getvalue().splitlines(keepends=True),
        )
        return _Execution(text=text, logs=logs, error=err)

    def set_timeout(self, timeout: int) -> None:
        self._timeout = timeout

    def kill(self) -> None:
        import shutil

        shutil.rmtree(self._root, ignore_errors=True)

    def __enter__(self) -> "LocalSandbox":
        return self

    def __exit__(self, *exc: object) -> None:
        self.kill()


def open_sandbox(timeout: int = 300, **kwargs: object):
    """统一入口：有 E2B_API_KEY 就用真实 E2B 云沙箱，否则回退到本地模拟沙箱。

    返回 ``(sandbox, backend_name)``，backend_name 为 ``"e2b"`` 或 ``"local"``，
    方便示例脚本打印当前用的是哪种后端。
    """
    if os.getenv("E2B_API_KEY"):
        try:
            from e2b_code_interpreter import Sandbox

            return Sandbox.create(timeout=timeout, **kwargs), "e2b"
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] 创建 E2B 云沙箱失败，回退到本地模拟沙箱：{exc}")

    return LocalSandbox.create(timeout=timeout), "local"
