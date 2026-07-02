from __future__ import annotations

import json
from pathlib import Path

import tomlkit

from codex_logdatenbank_wartung.automation_control import (
    activate_all_automations,
    activate_carecenter_paused_automations,
    control_state_path,
    find_automation_anomalies,
    load_automations,
    load_carecenter_paused_ids,
    pause_active_automations,
    run_automation_action,
)
from codex_logdatenbank_wartung.config import MaintenanceConfig


def make_config(tmp_path: Path) -> MaintenanceConfig:
    codex_home = tmp_path / ".codex"
    return MaintenanceConfig(database_path=str(codex_home / "logs_2.sqlite"))


def write_automation(codex_home: Path, automation_id: str, status: str) -> Path:
    folder = codex_home / "automations" / automation_id
    folder.mkdir(parents=True)
    path = folder / "automation.toml"
    doc = tomlkit.document()
    doc["id"] = automation_id
    doc["name"] = f"Automation {automation_id}"
    doc["kind"] = "cron"
    doc["rrule"] = "FREQ=HOURLY;INTERVAL=1"
    doc["status"] = status
    doc["updated_at"] = 1
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    return path


def write_automation_at(
    codex_home: Path, rel_parts: tuple[str, ...], automation_id: str, status: str = "ACTIVE"
) -> Path:
    """Schreibt eine automation.toml an einem beliebigen relativen Pfad unter automations/."""
    folder = codex_home.joinpath("automations", *rel_parts)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "automation.toml"
    doc = tomlkit.document()
    doc["id"] = automation_id
    doc["name"] = f"Automation {automation_id}"
    doc["kind"] = "cron"
    doc["status"] = status
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    return path


def read_status(path: Path) -> str:
    return str(tomlkit.parse(path.read_text(encoding="utf-8"))["status"])


def write_carecenter_state(config: MaintenanceConfig, ids: list[str]) -> None:
    path = control_state_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"paused_by_carecenter_ids": ids}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_pause_active_remembers_only_carecenter_paused_ids(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    active = write_automation(config.codex_home, "active-job", "ACTIVE")
    prepaused = write_automation(config.codex_home, "manual-job", "PAUSED")

    result = pause_active_automations(config)

    assert result.status == "ok"
    assert result.changed_ids == ["active-job"]
    assert read_status(active) == "PAUSED"
    assert read_status(prepaused) == "PAUSED"
    assert load_carecenter_paused_ids(config) == ["active-job"]


def test_restore_carecenter_paused_leaves_manual_pauses_off(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    ccc_paused = write_automation(config.codex_home, "ccc-job", "PAUSED")
    manual_paused = write_automation(config.codex_home, "manual-job", "PAUSED")
    write_carecenter_state(config, ["ccc-job"])

    result = activate_carecenter_paused_automations(config)

    assert result.changed_ids == ["ccc-job"]
    assert read_status(ccc_paused) == "ACTIVE"
    assert read_status(manual_paused) == "PAUSED"
    assert load_carecenter_paused_ids(config) == []


def test_staggered_restore_waits_between_changed_automations(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    write_automation(config.codex_home, "a", "PAUSED")
    write_automation(config.codex_home, "b", "PAUSED")
    write_carecenter_state(config, ["a", "b"])
    sleeps: list[float] = []
    progress: list[tuple[int, int, str]] = []

    result = activate_carecenter_paused_automations(
        config,
        staggered=True,
        delay_seconds=60,
        sleeper=sleeps.append,
        progress=lambda current, total, automation_id: progress.append(
            (current, total, automation_id)
        ),
    )

    assert result.changed_ids == ["a", "b"]
    assert result.delay_seconds == 60
    assert sleeps == [60.0]
    assert progress == [(1, 2, "a"), (2, 2, "b")]
    assert load_carecenter_paused_ids(config) == []


def test_activate_all_turns_manual_pauses_on_and_clears_ccc_state(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    first = write_automation(config.codex_home, "first", "PAUSED")
    second = write_automation(config.codex_home, "second", "PAUSED")
    write_carecenter_state(config, ["first"])

    result = activate_all_automations(config)

    assert result.changed_ids == ["first", "second"]
    assert read_status(first) == "ACTIVE"
    assert read_status(second) == "ACTIVE"
    assert load_carecenter_paused_ids(config) == []


def test_run_automation_action_dispatches_staggered_all(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    write_automation(config.codex_home, "first", "PAUSED")
    write_automation(config.codex_home, "second", "PAUSED")
    sleeps: list[float] = []

    result = run_automation_action(
        config,
        "activate-all-staggered",
        sleeper=sleeps.append,
        stagger_delay_seconds=60,
    )

    assert result.changed_ids == ["first", "second"]
    assert sleeps == [60.0]


def test_find_anomalies_detects_nested_automation(tmp_path: Path) -> None:
    # (a) Nest-Fall: verwaister Duplikat-Ordner mit identischer id im Eltern-Ordner.
    config = make_config(tmp_path)
    write_automation_at(config.codex_home, ("sync-check",), "sync-check")
    nested = write_automation_at(config.codex_home, ("sync-check", "sync-check"), "sync-check")

    report = find_automation_anomalies(config)

    assert [item.path for item in report.nested] == [nested]
    assert report.nested[0].id == "sync-check"
    assert report.nested[0].depth == 2
    assert report.has_anomalies is True
    # Tiefe-1-Scan bleibt unberührt (sieht nur den Eltern-Ordner).
    assert [record.id for record in load_automations(config)] == ["sync-check"]


def test_find_anomalies_detects_duplicate_id_without_nesting(tmp_path: Path) -> None:
    # (b) Doppel-id-Fall, unabhängig von Verschachtelung: zwei Tiefe-1-Ordner mit
    # verschiedenen Ordnernamen, aber identischem id-Feld.
    config = make_config(tmp_path)
    first = write_automation_at(config.codex_home, ("folder-a",), "dupe")
    second = write_automation_at(config.codex_home, ("folder-b",), "dupe")

    report = find_automation_anomalies(config)

    assert report.nested == []
    assert len(report.duplicate_ids) == 1
    assert report.duplicate_ids[0].id == "dupe"
    assert report.duplicate_ids[0].paths == sorted([first, second])
    assert report.has_anomalies is True


def test_find_anomalies_clean_when_flat_and_unique(tmp_path: Path) -> None:
    # (c) Sauberer Fall: nur Tiefe-1-Ordner mit eindeutigen ids.
    config = make_config(tmp_path)
    write_automation_at(config.codex_home, ("job-a",), "job-a")
    write_automation_at(config.codex_home, ("job-b",), "job-b")

    report = find_automation_anomalies(config)

    assert report.nested == []
    assert report.duplicate_ids == []
    assert report.has_anomalies is False
