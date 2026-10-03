from __future__ import annotations

import json
from pathlib import Path

from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.zombie_killer_integration import (
    _process_create_time,
    _read_watch_pid_file,
    _verify_watch_process,
    build_zombie_killer_status,
)


def _make_config(tmp_path: Path) -> MaintenanceConfig:
    codex_home = tmp_path / ".codex"
    return MaintenanceConfig(database_path=str(codex_home / "logs_2.sqlite"))


def test_read_watch_pid_file_with_non_dict_json(tmp_path: Path) -> None:
    # watch.pid containing valid JSON that is not a dictionary (e.g. list, string, int)
    pid_file = tmp_path / "watch.pid"
    for non_dict in ["[12345]", '"just a string"', "12345", "true", "null"]:
        pid_file.write_text(non_dict, encoding="utf-8")
        assert _read_watch_pid_file(tmp_path) is None


def test_read_watch_pid_file_missing_pid_field(tmp_path: Path) -> None:
    pid_file = tmp_path / "watch.pid"
    pid_file.write_text(json.dumps({"create_time": 1234.5}), encoding="utf-8")
    assert _read_watch_pid_file(tmp_path) is None


def test_verify_watch_process_with_negative_or_zero_pid() -> None:
    assert _verify_watch_process(-1, None) is False
    assert _verify_watch_process(0, None) is False
    assert _verify_watch_process(-999, 12345.0) is False


def test_process_create_time_with_negative_or_zero_pid() -> None:
    assert _process_create_time(-1) is None
    assert _process_create_time(0) is None
    assert _process_create_time(-999) is None


def test_build_zombie_killer_status_with_none_event_values(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    state_dir = config.zombie_killer_state_dir
    state_dir.mkdir(parents=True, exist_ok=True)
    events_file = state_dir / "zombie_events.jsonl"
    events_file.write_text(
        json.dumps({"cycle_at": None, "count": None}) + "\n",
        encoding="utf-8",
    )

    status = build_zombie_killer_status(config)
    assert status.last_cycle_at is None
    assert status.last_cycle_count is None


def test_build_zombie_killer_status_with_invalid_string_values(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    state_dir = config.zombie_killer_state_dir
    state_dir.mkdir(parents=True, exist_ok=True)
    events_file = state_dir / "zombie_events.jsonl"
    events_file.write_text(
        json.dumps({"cycle_at": "invalid-timestamp", "count": "not-a-number"}) + "\n",
        encoding="utf-8",
    )

    status = build_zombie_killer_status(config)
    assert status.last_cycle_at is None
    assert status.last_cycle_count is None
