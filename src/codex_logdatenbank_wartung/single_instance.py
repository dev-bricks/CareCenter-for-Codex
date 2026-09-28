"""Single-Instance-Guard für die Tray-App."""

from __future__ import annotations

import contextlib
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
            if handle:
                if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
                    kernel32.CloseHandle(handle)
                    self.already_running = True
                    return False
                self._handle = handle
                return True

            # CreateMutexW failed (e.g. Access Denied on Global\ namespace without elevation)
            if self.name.startswith("Global\\"):
                local_name = "Local\\" + self.name[7:]
                handle = kernel32.CreateMutexW(None, False, local_name)
                if handle:
                    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
                        kernel32.CloseHandle(handle)
                        self.already_running = True
                        return False
                    self._handle = handle
                    return True

        # Lockfile-Fallback (non-Windows oder wenn Mutex-Erzeugung fehlgeschlagen ist)
        self.fallback_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._lock_fd = os.open(
                self.fallback_path,
                os.O_CREAT | os.O_EXCL | os.O_RDWR,
            )
        except FileExistsError:
            self.already_running = True
            return False
        except OSError:
            self.already_running = True
            return False
        return True

    def release(self) -> None:
        if os.name == "nt" and self._handle:
            ctypes.windll.kernel32.ReleaseMutex(self._handle)
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None

        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None
            with contextlib.suppress(FileNotFoundError, OSError):
                self.fallback_path.unlink()

    def __enter__(self) -> SingleInstanceGuard:
        self.acquire()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()
