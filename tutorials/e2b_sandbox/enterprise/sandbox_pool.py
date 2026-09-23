"""企业级 · 沙箱池（Sandbox Pool）与生命周期管理

在高并发的智能体服务里，每来一个请求就 `create` 一个沙箱、用完 `kill`，会带来：
    - 创建延迟（冷启动）叠加到每次请求；
    - 沙箱数量不受控，容易打爆配额 / 成本。

常见做法是维护一个「沙箱池」：预创建、复用、限制上限、回收空闲。本模块实现了一个
线程安全的最小可用池，演示 acquire / release / 复用 / 上限阻塞 / 优雅关闭。

运行（离线演示，多线程借还沙箱）：
    python tutorials/e2b_sandbox/enterprise/sandbox_pool.py
"""

import os
import queue
import sys
import threading
import time
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _local_sandbox import open_sandbox  # noqa: E402


class SandboxPool:
    """线程安全的沙箱池。

    - max_size: 池内沙箱数量上限；达到上限时 acquire 会阻塞等待空闲；
    - idle 沙箱放在队列里复用，避免重复冷启动；
    - close() 统一回收，防止沙箱泄漏（继续计费）。
    """

    def __init__(self, max_size: int = 4, timeout: int = 300) -> None:
        self._max_size = max_size
        self._timeout = timeout
        self._idle: queue.Queue = queue.Queue()
        self._created = 0
        self._lock = threading.Lock()
        self._closed = False

    def _new_sandbox(self):
        sandbox, backend = open_sandbox(timeout=self._timeout)
        return sandbox

    def acquire(self, wait: float | None = 30):
        """借一个沙箱：优先复用空闲的；没有且未达上限则新建；已达上限则等待。"""
        if self._closed:
            raise RuntimeError("SandboxPool 已关闭")
        try:
            return self._idle.get_nowait()
        except queue.Empty:
            pass
        with self._lock:
            if self._created < self._max_size:
                self._created += 1
                return self._new_sandbox()
        # 已达上限，阻塞等待别人归还
        return self._idle.get(timeout=wait)

    def release(self, sandbox) -> None:
        """归还沙箱到空闲队列，供下次复用。"""
        if self._closed:
            sandbox.kill()
            return
        self._idle.put(sandbox)

    @contextmanager
    def lease(self):
        """with 语法糖：自动 acquire + release。"""
        sandbox = self.acquire()
        try:
            yield sandbox
        finally:
            self.release(sandbox)

    def close(self) -> None:
        """关闭池：销毁所有沙箱，释放云端资源。"""
        self._closed = True
        while True:
            try:
                self._idle.get_nowait().kill()
            except queue.Empty:
                break


def main() -> None:
    print("== 创建一个 max_size=2 的沙箱池，用 4 个线程并发借还 ==\n")
    pool = SandboxPool(max_size=2)
    seen_ids: list[str] = []
    lock = threading.Lock()

    def worker(n: int) -> None:
        with pool.lease() as sandbox:
            with lock:
                seen_ids.append(sandbox.sandbox_id)
            execution = sandbox.run_code(f"result = {n} ** 2\nresult")
            print(f"[线程 {n}] 用沙箱 {sandbox.sandbox_id} 算出 {n}^2 = {execution.text}")
            time.sleep(0.05)  # 模拟一点工作量，制造并发竞争

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(1, 5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    unique = set(seen_ids)
    print(f"\n== 4 次任务实际只用了 {len(unique)} 个沙箱（max_size=2），说明发生了复用 ==")
    print("   用到的沙箱 id:", unique)

    pool.close()
    print("== 池已关闭，所有沙箱被回收 ==")


if __name__ == "__main__":
    main()
