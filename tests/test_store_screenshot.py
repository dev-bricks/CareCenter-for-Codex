"""Tests fuer die reproduzierbare Store-Screenshot-Erzeugung."""

from __future__ import annotations

from pathlib import Path

from codex_logdatenbank_wartung.store_screenshot import render_store_screenshot


def test_render_store_screenshot_writes_png(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    output = tmp_path / "main.png"

    result = render_store_screenshot(output)

    assert result == output.resolve()
    assert output.exists()
    data = output.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(data) > 1024
