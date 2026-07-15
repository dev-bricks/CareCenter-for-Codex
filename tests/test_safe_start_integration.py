from __future__ import annotations

import json
import re
import subprocess
import tomllib
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import tomlkit

from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.safe_start_integration import (
    CARECENTER_SAFE_START_DEFAULT_INTERVAL_MINUTES,
    SAFE_START_PACKAGE_SPEC,
    build_safe_start_status,
    detect_safe_start_storm,
    install_safe_start_package,
    launch_safe_start_tray,
    restore_safe_start_latest,
    safe_start_gate_active,
    safe_start_install_target,
    safe_start_launch_arguments,
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


def write_automation(codex_home: Path, automation_id: str, status: str) -> Path:
    folder = codex_home / "automations" / automation_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "automation.toml"
    doc = tomlkit.document()
    doc["id"] = automation_id
    doc["name"] = automation_id
    doc["kind"] = "cron"
    doc["rrule"] = "FREQ=DAILY"
    doc["status"] = status
    doc["updated_at"] = 1
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    return path


def read_status(path: Path) -> str:
    return str(tomlkit.parse(path.read_text(encoding="utf-8"))["status"])


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


def test_should_defer_when_latest_snapshot_is_paused_phase(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.safe_start_state_dir.mkdir(parents=True)
    (config.safe_start_state_dir / "latest.json").write_text(
        json.dumps(
            {
                "phase": "paused",
                "tool_paused_ids": ["weekly"],
                "released_ids": [],
                "items": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert safe_start_gate_active(config) is True
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


def test_safe_start_fallback_is_commit_pinned_and_matches_build_extra(monkeypatch) -> None:
    from codex_logdatenbank_wartung import safe_start_integration

    monkeypatch.setattr(safe_start_integration, "_local_safe_start_source", lambda: None)

    target = safe_start_install_target()
    assert target == SAFE_START_PACKAGE_SPEC
    assert re.fullmatch(
        r"safe-start-for-codex @ git\+https://github\.com/dev-bricks/"
        r"safe-start-for-codex\.git@[0-9a-f]{40}",
        target,
    )

    project_root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
    assert target in metadata["project"]["optional-dependencies"]["build"]
    assert metadata["tool"]["hatch"]["metadata"]["allow-direct-references"] is True
    assert not any(
        dependency.startswith("safe-start-for-codex")
        for dependency in metadata["project"]["dependencies"]
    )


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


def test_safe_start_launch_arguments_use_config_when_present(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.safe_start_config_file.parent.mkdir(parents=True)
    config.safe_start_config_file.write_text("{}", encoding="utf-8")

    args, exists = safe_start_launch_arguments(config)

    assert exists is True
    assert args == ["tray", "--config", str(config.safe_start_config_file)]


def test_safe_start_launch_arguments_fallback_to_one_minute(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    args, exists = safe_start_launch_arguments(config)

    assert exists is False
    assert args[-2:] == [
        "--interval-minutes",
        str(CARECENTER_SAFE_START_DEFAULT_INTERVAL_MINUTES),
    ]


def test_launch_safe_start_tray_uses_codex_home_and_fallback_interval(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from codex_logdatenbank_wartung import safe_start_integration

    config = make_config(tmp_path)
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(safe_start_integration, "_python_command_candidates", lambda: [["python"]])
    monkeypatch.setattr(safe_start_integration, "_local_safe_start_source", lambda: None)

    def fake_popen(command: list[str], **kwargs: object) -> object:
        calls.append((command, kwargs))
        return SimpleNamespace(pid=123)

    result = launch_safe_start_tray(config, popen=fake_popen)

    assert result.status == "ok"
    assert result.pid == 123
    assert result.fallback_interval_minutes == CARECENTER_SAFE_START_DEFAULT_INTERVAL_MINUTES
    assert calls[0][0] == [
        "python",
        "-m",
        "safe_start_for_codex",
        "tray",
        "--config",
        str(config.safe_start_config_file),
        "--interval-minutes",
        "1",
    ]
    env = calls[0][1]["env"]
    assert isinstance(env, dict)
    assert env["CODEX_HOME"] == str(config.codex_home)


def test_launch_safe_start_tray_noops_when_gate_is_active(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.safe_start_state_dir.mkdir(parents=True)
    (config.safe_start_state_dir / "latest.json").write_text(
        json.dumps(
            {
                "phase": "release-queue",
                "tool_paused_ids": ["weekly"],
                "released_ids": [],
                "delayed_release_ids": ["weekly"],
                "items": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def fail_popen(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("Safe Start darf nicht erneut gestartet werden")

    result = launch_safe_start_tray(config, popen=fail_popen)

    assert result.status == "already-running"
    assert result.command == []


def test_restore_safe_start_latest_reactivates_tool_paused_items(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    weekly = write_automation(config.codex_home, "weekly", "PAUSED")
    manual = write_automation(config.codex_home, "manual", "PAUSED")
    config.safe_start_state_dir.mkdir(parents=True)
    (config.safe_start_state_dir / "latest.json").write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "phase": "paused",
                "tool_paused_ids": ["weekly"],
                "released_ids": [],
                "delayed_release_ids": ["weekly"],
                "items": [
                    {
                        "id": "weekly",
                        "name": "weekly",
                        "path": str(weekly),
                        "original_status": "ACTIVE",
                        "status": "PAUSED",
                        "kind": "cron",
                        "rrule": "FREQ=DAILY",
                        "created_at": 1,
                        "updated_at": 1,
                        "tool_paused": True,
                        "released": False,
                    },
                    {
                        "id": "manual",
                        "name": "manual",
                        "path": str(manual),
                        "original_status": "PAUSED",
                        "status": "PAUSED",
                        "kind": "cron",
                        "rrule": "FREQ=DAILY",
                        "created_at": 1,
                        "updated_at": 1,
                        "tool_paused": False,
                        "released": False,
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = restore_safe_start_latest(config)

    assert result.status == "ok"
    assert result.restored_ids == ["weekly"]
    assert read_status(weekly) == "ACTIVE"
    assert read_status(manual) == "PAUSED"
    assert safe_start_gate_active(config) is False
    latest = json.loads((config.safe_start_state_dir / "latest.json").read_text(encoding="utf-8"))
    assert latest["phase"] == "restored"
    assert latest["delayed_release_ids"] == []
    assert latest["carecenter_restore"]["restored_ids"] == ["weekly"]
