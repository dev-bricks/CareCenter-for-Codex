"""Reproduzierbare Store-/README-Screenshots fuer CareCenter for Codex."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from .tray import StatusWindow


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCREENSHOT_PATH = PROJECT_ROOT / "README" / "screenshots" / "main.png"


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
    window.set_zombie_count(4)
    window.set_state("Bereit für Windows-Store-Preflight")
    window.set_progress(
        68,
        "Store-Materialien geprüft · nächster Schritt: EXE, MSIX und WACK.",
        False,
    )
    window.set_result(
        "Offline · keine Telemetrie\n"
        "Safe-Modus schützt laufende Automationen\n"
        "Store-Reparatur und Neuinstallation direkt erreichbar"
    )
    window.set_audit_settings("notify", "auto")
    window.resize(max(window.minimumWidth(), 760), window.sizeHint().height() + 24)
    window.show()
    app.processEvents()

    pixmap = window.grab()
    saved = pixmap.save(str(output_path))
    window.close()
    app.processEvents()

    if owns_app:
        app.quit()

    if not saved or not output_path.exists():
        raise RuntimeError(f"Screenshot konnte nicht geschrieben werden: {output_path}")
    return output_path
