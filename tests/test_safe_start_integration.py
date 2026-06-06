from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.safe_start_integration import (
    build_safe_start_status,
    detect_safe_start_storm,
    install_safe_start_package,
    safe_start_install_target,
    should_defer_for_safe_start,
)


def make_config(tmp_path: Path) -> MaintenanceConfig:
    codex_home = tmp_path / ".codex"
    return MaintenanceConfig(
        database_path=str(codex_home / "logs_2.sqlite"),
        safe_start_config_path=str(codex_home / "automation-safe-start" / "config.json"),
        safe_start_storm_window_minutes=10,
        safe_start_storm_release_threshold=2,
    )


def write_event(path: Path, *, event: str, stamp: datetime, automation_id: str = "job") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "ts": stamp.isoformat(timespec="seconds"),
                    "event": event,
                    "automation_id": automation_id,
                },
                ensure_ascii=False,
            )
            + "\n"
        )


def test_detect_safe_start_storm_counts_recent_release_events(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    now = datetime.now().astimezone()
    events = config.safe_start_state_dir / "events.jsonl"
    write_event(events, event="release", stamp=now - timedelta(minutes=2), automation_id="a")
    write_event(events, event="release", stamp=now - timedelta(minutes=4), automation_id="b")
    write_event(events, event="release", stamp=now - timedelta(minutes=20), automation_id="old")

    storm = detect_safe_start_storm(config, now=now)

    assert storm.status == "release_burst"
    assert storm.release_count == 2
    assert should_defer_for_safe_start(config) is True


def test_should_defer_when_latest_snapshot_has_active_gate(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.safe_start_state_dir.mkdir(parents=True)
    (config.safe_start_state_dir / "latest.json").write_text(
        json.dumps(
            {
                "phase": "release-queue",
                "tool_paused_ids": ["weekly"],
                "released_ids": [],
                "delayed_release_ids": ["weekly"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert should_defer_for_safe_start(config) is True


def test_build_safe_start_status_uses_snapshot_fallback(tmp_path: Path, monkeypatch) -> None:
    from codex_logdatenbank_wartung import safe_start_integration

    monkeypatch.setattr(safe_start_integration, "_safe_start_cli", lambda: None)
    config = make_config(tmp_path)
    config.safe_start_state_dir.mkdir(parents=True)
    (config.safe_start_state_dir / "latest-catchup-plan.json").write_text(
        json.dumps(
            {
                "eligible_ids": ["weekly"],
                "candidates": [{"automation_id": "weekly"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    status = build_safe_start_status(config)

    assert status.available is False
    assert status.eligible_ids == ["weekly"]
    assert status.candidate_count == 1


def test_safe_start_install_target_prefers_local_source(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "safe-start-for-codex"
    source.mkdir()
    (source / "pyproject.toml").write_text("[project]\nname='safe-start-for-codex'\n", encoding="utf-8")
    monkeypatch.setenv("CARECENTER_SAFE_START_SOURCE", str(source))

    assert safe_start_install_target() == str(source)


def test_install_safe_start_package_runs_pip_upgrade(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "safe-start-for-codex"
    source.mkdir()
    (source / "pyproject.toml").write_text("[project]\nname='safe-start-for-codex'\n", encoding="utf-8")
    monkeypatch.setenv("CARECENTER_SAFE_START_SOURCE", str(source))
    calls: list[list[str]] = []

    def fake_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="installed\n", stderr="")

    result = install_safe_start_package(runner=fake_runner)

    assert result.status == "ok"
    assert calls
    assert calls[0][-3:] == ["install", "--upgrade", str(source)]
