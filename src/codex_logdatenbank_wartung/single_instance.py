"""Single-Instance-Guard für die Tray-App."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path


ERROR_ALREADY_EXISTS = 183


class SingleInstanceGuard:
    """Windows-Mutex mit Lockfile-Fallback."""

    def __init__(self, name: str, fallback_path: Path) -> None:
        self.name = name
        self.fallback_path = fallback_path
        self._handle: int | None = None
        self._lock_fd: int | None = None
        self.already_running = False

    def acquire(self) -> bool:
        if os.name == "nt":
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.CreateMutexW(None, False, self.name)
            self._handle = handle
            if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
                self.already_running = True
                return False
            return True

        self.fallback_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._lock_fd = os.open(
                self.fallback_path,
                os.O_CREAT | os.O_EXCL | os.O_RDWR,
            )
        except FileExistsError:
            self.already_running = True
            return False
        return True

    def release(self) -> None:
        if os.name == "nt" and self._handle:
            ctypes.windll.kernel32.ReleaseMutex(self._handle)
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None
            return

        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None
            try:
                self.fallback_path.unlink()
            except FileNotFoundError:
                pass

    def __enter__(self) -> "SingleInstanceGuard":
        self.acquire()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()
