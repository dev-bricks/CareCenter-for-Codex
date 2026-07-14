"""Static guards for the source launch scripts."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_start_bat_uses_pythonw_without_normal_pause() -> None:
    text = (PROJECT_ROOT / "start.bat").read_text(encoding="utf-8")
    assert 'where pythonw >nul 2>&1' in text
    assert 'start "" pythonw -m codex_logdatenbank_wartung.cli tray' in text
    assert text.rstrip().endswith("exit /b 0")


def test_debug_bat_keeps_console_output_available() -> None:
    text = (PROJECT_ROOT / "debug.bat").read_text(encoding="utf-8")
    assert 'python -m codex_logdatenbank_wartung.cli tray' in text
    assert "pause" in text
    assert "EXIT_CODE" in text

