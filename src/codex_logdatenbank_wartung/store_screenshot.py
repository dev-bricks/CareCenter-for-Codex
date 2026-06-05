"""Reproduzierbare Store-/README-Screenshots für CareCenter for Codex."""

from __future__ import annotations

from pathlib import Path
from sys import platform as sys_platform
from time import sleep

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from .tray import StatusWindow

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCREENSHOT_PATH = PROJECT_ROOT / "README" / "screenshots" / "main.png"


def _windows_extended_frame_bounds(window: StatusWindow) -> tuple[int, int, int, int] | None:
    """Liefert unter Windows die sichtbaren Fenstergrenzen ohne DWM-Schatten."""
    if sys_platform != "win32":
        return None

    try:
        from ctypes import byref, c_int, sizeof, windll, wintypes
    except (AttributeError, ImportError):
        return None

    rect = wintypes.RECT()
    result = windll.dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(int(window.winId())),
        c_int(9),  # DWMWA_EXTENDED_FRAME_BOUNDS
        byref(rect),
        sizeof(rect),
    )
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if result != 0 or width <= 0 or height <= 0:
        return None
    return rect.left, rect.top, width, height


def _save_window_capture(window: StatusWindow, output_path: Path) -> bool:
    """Speichert nach Möglichkeit das native Fenster inklusive Titelleiste."""
    platform_name = QApplication.platformName().lower()
    if platform_name not in {"minimal", "offscreen"}:
        screen = window.screen() or QApplication.primaryScreen()
        capture_rect = _windows_extended_frame_bounds(window)
        if capture_rect is None:
            frame = window.frameGeometry()
            if frame.isValid():
                capture_rect = (frame.x(), frame.y(), frame.width(), frame.height())
        if screen is not None and capture_rect is not None:
            x, y, width, height = capture_rect
            pixmap = screen.grabWindow(0, x, y, width, height)
            if not pixmap.isNull() and pixmap.save(str(output_path)):
                return True

    pixmap = window.grab()
    return not pixmap.isNull() and pixmap.save(str(output_path))


def render_store_screenshot(output_path: Path = DEFAULT_SCREENSHOT_PATH) -> Path:
    """Rendert einen reproduzierbaren Screenshot des Statusfensters."""
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication(["carecenter-store-screenshot"])
        app.setQuitOnLastWindowClosed(False)

    window = StatusWindow()
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    window.set_zombie_count(0)
    window.set_state("Bereit.")
    window.set_progress(0, "", False)
    window.set_result("")
    window.set_audit_settings("auto", "auto")
    window.resize(window.minimumWidth(), window.sizeHint().height())
    window.show()
    window.raise_()
    window.activateWindow()
    for _ in range(4):
        app.processEvents()
        if QApplication.platformName().lower() not in {"minimal", "offscreen"}:
            sleep(0.05)

    saved = _save_window_capture(window, output_path)
    window.close()
    app.processEvents()

    if owns_app:
        app.quit()

    if not saved or not output_path.exists():
        raise RuntimeError(f"Screenshot konnte nicht geschrieben werden: {output_path}")
    return output_path
