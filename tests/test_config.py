"""Tests fuer die Konfigurations-Persistenz."""

from __future__ import annotations

import json
from pathlib import Path

import codex_logdatenbank_wartung.config as config_module
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


def test_load_accepts_int_for_float_field(tmp_path: Path) -> None:
    """Regression: JSON-Integer (z.B. 25) darf fuer ein float-Feld nicht verworfen werden."""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"idle_cpu_percent": 25}),
        encoding="utf-8",
    )
    config = MaintenanceConfig.load(config_path)
    assert isinstance(config, MaintenanceConfig)
    assert config.idle_cpu_percent == 25.0, (
        f"idle_cpu_percent sollte 25.0 sein, ist {config.idle_cpu_percent!r}"
    )


def test_load_persists_fast_loop_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({
            "fast_loop_enabled": True,
            "fast_loop_interval_hours": 7,
            "fast_loop_close_retry_attempts": 2,
            "fast_loop_close_retry_delay_seconds": 5,
            "fast_loop_safe_fallback_enabled": True,
        }),
        encoding="utf-8",
    )

    config = MaintenanceConfig.load(config_path)

    assert config.fast_loop_enabled is True
    assert config.fast_loop_interval_hours == 7
    assert config.fast_loop_close_retry_attempts == 2
    assert config.fast_loop_close_retry_delay_seconds == 5
    assert config.fast_loop_safe_fallback_enabled is True


def test_load_rejects_bool_for_int_field(tmp_path: Path) -> None:
    """bool darf nicht als gueltiger int-Wert durchgehen (bool ist int-Unterklasse).

    Szenario: config.json enthaelt ``backup_keep: true`` (z. B. Tipp-Fehler).
    Ohne den bool-Guard wuerde ``isinstance(True, type(3))`` == True gelten und
    backup_keep=True (=1) speichern -- prune_backups() wuerde danach nur 1 Backup halten.
    """
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"backup_keep": True}),
        encoding="utf-8",
    )
    config = MaintenanceConfig.load(config_path)
    assert isinstance(config, MaintenanceConfig)
    assert isinstance(config.backup_keep, int) and not isinstance(config.backup_keep, bool), (
        f"backup_keep sollte int-Default sein, ist {config.backup_keep!r} ({type(config.backup_keep).__name__})"
    )
    assert config.backup_keep == 3  # Default-Wert


def test_load_returns_defaults_on_wrong_field_type(tmp_path: Path) -> None:
    """Bug-Fix: Config mit bekanntem Feld in falschem Typ -> Defaults, kein Crash.

    Scenario: Nutzer editiert config.json manuell und schreibt z.B.
    backup_keep: "drei" statt 3 (gueltiges JSON, dict, aber falscher Typ fuer das Feld).
    cls(**filtered) wuerde das speichern; spaeter crasht prune_backups() bei keep <= 0.
    """
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"backup_keep": "drei", "watcher_enabled": True}),
        encoding="utf-8",
    )
    config = MaintenanceConfig.load(config_path)
    assert isinstance(config, MaintenanceConfig)
    assert isinstance(config.backup_keep, int), (
        f"backup_keep sollte int sein (Defaults), ist {type(config.backup_keep).__name__!r}"
    )


def test_ccc_data_root_env_var(tmp_path: Path, monkeypatch) -> None:
    """CCC_DATA_ROOT überschreibt den Daten-Root für backup_dir, log_dir und maintenance_lock_path."""
    monkeypatch.setenv("CCC_DATA_ROOT", str(tmp_path))

    config = MaintenanceConfig()
    assert config.backup_dir == str(tmp_path / "backups")
    assert config.log_dir == str(tmp_path / "logs")
    assert config.maintenance_lock_path == str(tmp_path / "maintenance.lock")

    loaded = MaintenanceConfig.load()
    assert loaded.backup_dir == str(tmp_path / "backups")
    assert (tmp_path / "config.json").exists()  # load() legte config.json unter redirected root an


def test_local_root_defaults_to_localappdata_for_new_installations(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("CCC_DATA_ROOT", raising=False)
    legacy_root = tmp_path / "legacy-root"
    local_appdata = tmp_path / "LocalAppData"
    monkeypatch.setattr(config_module, "LEGACY_LOCAL_ROOT", legacy_root)
    monkeypatch.setattr(config_module, "_local_appdata", lambda: local_appdata)

    assert config_module.local_root() == local_appdata / config_module.DEFAULT_DATA_DIR_NAME


def test_local_root_prefers_existing_legacy_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("CCC_DATA_ROOT", raising=False)
    legacy_root = tmp_path / "legacy-root"
    legacy_root.mkdir()
    local_appdata = tmp_path / "LocalAppData"
    monkeypatch.setattr(config_module, "LEGACY_LOCAL_ROOT", legacy_root)
    monkeypatch.setattr(config_module, "_local_appdata", lambda: local_appdata)

    assert config_module.local_root() == legacy_root
