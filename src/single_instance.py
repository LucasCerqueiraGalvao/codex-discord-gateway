from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import TextIO

if os.name == "nt":
    import ctypes
    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
else:
    import fcntl


class SingleInstanceLock:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._handle: TextIO | None = None
        self._mutex_handle: int | None = None
        digest = hashlib.sha1(str(self._path.resolve()).encode("utf-8")).hexdigest()
        self._mutex_name = f"Local\\codex-discord-gateway-{digest}"

    def acquire(self) -> bool:
        if self._mutex_handle is not None or self._handle is not None:
            return True

        if os.name == "nt":
            handle = _KERNEL32.CreateMutexW(None, False, self._mutex_name)
            if not handle:
                return False

            error_code = ctypes.get_last_error()
            if error_code == 183:  # ERROR_ALREADY_EXISTS
                _KERNEL32.CloseHandle(handle)
                return False

            self._mutex_handle = handle
            return True

        handle = self._path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False

        handle.seek(0)
        handle.write(f"{os.getpid()}\n")
        handle.truncate()
        handle.flush()
        self._handle = handle
        return True

    def release(self) -> None:
        if self._mutex_handle is not None:
            _KERNEL32.CloseHandle(self._mutex_handle)
            self._mutex_handle = None
            return

        handle = self._handle
        if handle is None:
            return

        try:
            handle.seek(0)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            self._handle = None

    def __enter__(self) -> "SingleInstanceLock":
        if not self.acquire():
            raise RuntimeError(f"Could not acquire single-instance lock at {self._path}")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
