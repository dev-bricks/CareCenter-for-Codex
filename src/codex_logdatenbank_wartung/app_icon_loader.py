"""App-Icon-Loader für CareCenter for Codex.

Lädt das Anwendungs-Icon mit robuster Multi-Pfad-Auflösung (PyInstaller-Bundle,
assets/CareCenterForCodex.ico, assets/app_icon.ico, Root-ICOs und PNG-Fallback)
sowohl als PIL-Image (für System-Tray / Bildbearbeitung) als auch optional als QIcon.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PIL import Image


def get_project_root() -> Path:
    """Liefert das Basisverzeichnis für Ressourcen im Repo oder gefrorenen Bundle."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    # src-Layout: parents[2] von src/codex_logdatenbank_wartung/app_icon_loader.py ist Repo-Root
    return Path(__file__).resolve().parents[2]


def get_app_icon_path() -> Path | None:
    """Findet den besten verfügbaren Pfad zur Icon-Datei."""
    root = get_project_root()
    candidates = [
        root / "CareCenterForCodex.ico",
        root / "assets" / "CareCenterForCodex.ico",
        root / "assets" / "app_icon.ico",
        root / "assets" / "DesktopIcon.ico",
        root / "assets" / "icon.ico",
        root / "assets" / "CareCenter.ico",
        root / "DesktopIcon.ico",
        root / "icon.ico",
        root / "ICO.ico",
        root / "CareCenter.ico",
        root / "CareCenterForCodex.png",
        root / "assets" / "CareCenterForCodex.png",
        root / "assets" / "DesktopIcon.png",
        root / "assets" / "icon.png",
        root / "assets" / "CareCenter.png",
        root / "DesktopIcon.png",
        root / "icon.png",
        root / "CareCenter.png",
    ]
    for cand in candidates:
        if cand.is_file():
            return cand
    return None


def load_app_icon_pil(size: int = 64) -> Image.Image:
    """Lädt das Anwendungs-Icon als PIL Image mit Fallback."""
    from PIL import Image, ImageDraw

    icon_path = get_app_icon_path()
    if icon_path is not None:
        try:
            with Image.open(icon_path) as img:
                return img.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
        except Exception:
            pass

    # Deterministischer Fallback falls Datei nicht lesbar
    image = Image.new("RGBA", (size, size), (15, 23, 42, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((3, 3, size - 4, size - 4), radius=max(2, size // 5), fill=(15, 23, 42, 255))
    draw.ellipse((size * 0.2, size * 0.2, size * 0.8, size * 0.8), fill=(2, 132, 199, 255))
    draw.rounded_rectangle(
        (size * 0.35, size * 0.45, size * 0.65, size * 0.55),
        radius=max(1, size // 16),
        fill=(255, 255, 255, 255),
    )
    draw.rounded_rectangle(
        (size * 0.45, size * 0.35, size * 0.55, size * 0.65),
        radius=max(1, size // 16),
        fill=(255, 255, 255, 255),
    )
    return image


def load_app_icon() -> Any:
    """Lädt ein valides QIcon falls eine Qt Application aktiv ist und PySide6/PyQt verfügbar ist, sonst None."""
    try:
        from PySide6.QtGui import QGuiApplication, QIcon
    except ImportError:
        try:
            from PyQt6.QtGui import QGuiApplication, QIcon
        except ImportError:
            return None

    app = QGuiApplication.instance()
    if app is None:
        return None

    icon_path = get_app_icon_path()
    if icon_path is not None:
        icon = QIcon(str(icon_path))
        if not icon.isNull():
            return icon

    return None


def get_app_icon() -> Any:
    """Alias für load_app_icon."""
    return load_app_icon()
