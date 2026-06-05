"""Tests fuer die Konfigurations-Persistenz."""

from __future__ import annotations

import json
from pathlib import Path

from codex_logdatenbank_wartung.config import MaintenanceConfig


def test_load_returns_defaults_on_corrupt_json(tmp_path: Path) -> None:
    """Bug-Fix: beschaedigte Config (leere Datei, ungueltig JSON, non-dict) -> Defaults, kein Crash."""
    for bad_content in ("", "{bad json", "null", "[]", "42"):
        path = tmp_path / f"config_{bad_content[:4].strip() or 'empty'}.json"
        path.write_text(bad_content, encoding="utf-8")
        config = MaintenanceConfig.load(path)
        assert isinstance(config, MaintenanceConfig), f"Erwartet Defaults fuer: {bad_content!r}"
        assert config.watcher_enabled is True  # Sentinel: Default-Wert


def test_load_returns_defaults_on_unreadable_file(tmp_path: Path) -> None:
    """Bug-Fix: nicht lesbare Config (OSError) -> Defaults, kein Crash."""
    from unittest.mock import patch

    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")
    with patch("pathlib.Path.read_text", side_effect=OSError("Lesefehler")):
        config = MaintenanceConfig.load(path)
    assert isinstance(config, MaintenanceConfig)


def test_load_returns_defaults_on_invalid_utf8(tmp_path: Path) -> None:
    """Bug-Fix: Datei mit ungueltigem UTF-8 (abgebrochener Multibyte-Schreibvorgang) -> Defaults, kein Crash."""
    path = tmp_path / "config.json"
    path.write_bytes(b"\xff\xfe{bad")
    config = MaintenanceConfig.load(path)
    assert isinstance(config, MaintenanceConfig)
    assert config.watcher_enabled is True  # Sentinel: Default-Wert


def test_load_drops_legacy_watcher_terminate_user_starts_and_does_not_reemit(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "watcher_enabled": True,
                "watcher_terminate_user_starts": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    config = MaintenanceConfig.load(config_path)

    assert not hasattr(config, "watcher_terminate_user_starts")

    config.save(config_path)
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert "watcher_terminate_user_starts" not in saved
    assert saved["watcher_enabled"] is True
