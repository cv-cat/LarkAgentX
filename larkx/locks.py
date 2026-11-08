"""系统文件锁。进程退出(包括崩溃)时自动释放,不会留下要手动删的锁。"""
import os
import time
from pathlib import Path


class FileLock:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.fh = None

    def acquire(self) -> bool:
        """拿不到立刻返回 False。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, 'a+')
        try:
            if os.name == 'nt':
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        self.fh = fh
        return True

    def wait(self, timeout: float = 10) -> bool:
        """最多等 timeout 秒。"""
        deadline = time.monotonic() + timeout
        while not self.acquire():
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)
        return True

    def release(self):
        if not self.fh:
            return
        try:
            if os.name == 'nt':
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self.fh.close()
        self.fh = None

    def __enter__(self):
        if not self.wait():
            raise TimeoutError(f'等待文件锁超时: {self.path}')
        return self

    def __exit__(self, *exc):
        self.release()
