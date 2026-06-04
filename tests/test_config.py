"""Tests fuer die Konfigurations-Persistenz."""

from __future__ import annotations

import json
from pathlib import Path

from codex_logdatenbank_wartung.config import MaintenanceConfig


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
