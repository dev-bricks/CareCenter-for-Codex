from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import tomlkit

from codex_logdatenbank_wartung import automation_control
from codex_logdatenbank_wartung.automation_control import (
    activate_all_automations,
    activate_carecenter_paused_automations,
    control_state_dir,
    control_state_path,
    find_automation_anomalies,
    load_automations,
    load_carecenter_paused_ids,
    pause_active_automations,
    run_automation_action,
    scan_automations,
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


# --- Unlesbare Definitionen duerfen nicht still verschwinden (T-20261101-844031160) ---------------

# Das Fehlerbild vom 2026-10-31: doppelte Schluessel, die tomlkit als ParseError ablehnt.
DUPLICATE_KEYS_TOML = (
    'id = "{id}"\nname = "Broken {id}"\nkind = "cron"\nstatus = "ACTIVE"\n'
    'model = "gpt-a"\nreasoning_effort = "high"\nmodel = "gpt-a"\nreasoning_effort = "high"\n'
)


def write_broken(codex_home: Path, rel_parts: tuple[str, ...], automation_id: str) -> Path:
    folder = codex_home.joinpath("automations", *rel_parts)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "automation.toml"
    path.write_text(DUPLICATE_KEYS_TOML.format(id=automation_id), encoding="utf-8", newline="")
    return path


def test_scan_reports_unparseable_with_path_and_error(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    good = write_automation(config.codex_home, "good-job", "ACTIVE")
    broken = write_broken(config.codex_home, ("broken-job",), "broken-job")

    records, unparseable = scan_automations(config)

    assert [record.path for record in records] == [good]
    assert [(item.id, item.path) for item in unparseable] == [("broken-job", broken)]
    assert "model" in unparseable[0].error
    # Bestehende API bleibt: load_automations liefert weiter nur die lesbaren Definitionen.
    assert [record.id for record in load_automations(config)] == ["good-job"]


def test_find_anomalies_reports_unparseable_instead_of_skipping(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    write_automation(config.codex_home, "good-job", "ACTIVE")
    top = write_broken(config.codex_home, ("broken-top",), "broken-top")
    nested = write_broken(config.codex_home, ("outer", "inner"), "inner")

    report = find_automation_anomalies(config)

    assert sorted(item.path for item in report.unparseable) == sorted([top, nested])
    assert all(item.error for item in report.unparseable)
    assert report.has_anomalies is True


def test_pause_active_does_not_claim_success_with_unreadable_definitions(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    good = write_automation(config.codex_home, "good-job", "ACTIVE")
    broken = write_broken(config.codex_home, ("broken-job",), "broken-job")
    before = broken.read_bytes()

    result = pause_active_automations(config)

    assert read_status(good) == "PAUSED"
    assert result.status == "partial"
    assert result.unparseable_ids == ["broken-job"]
    assert result.unparseable_count == 1
    assert any("broken-job" in error and str(broken) in error for error in result.errors)
    assert broken.read_bytes() == before
    events = (control_state_dir(config) / "events.jsonl").read_text(encoding="utf-8")
    assert json.loads(events.splitlines()[-1])["unparseable_ids"] == ["broken-job"]


def test_pause_active_with_only_unreadable_definitions_is_not_ok(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    write_broken(config.codex_home, ("broken-a",), "broken-a")
    write_broken(config.codex_home, ("broken-b",), "broken-b")

    result = pause_active_automations(config)

    assert result.status == "failed"
    assert result.unparseable_count == 2
    assert result.changed_count == 0


def test_restore_ccc_keeps_ids_of_unreadable_definitions_remembered(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    good = write_automation(config.codex_home, "good-job", "PAUSED")
    write_broken(config.codex_home, ("broken-job",), "broken-job")
    write_carecenter_state(config, ["good-job", "broken-job"])

    result = activate_carecenter_paused_automations(config)

    assert read_status(good) == "ACTIVE"
    assert result.status == "partial"
    assert result.unparseable_ids == ["broken-job"]
    assert "broken-job" not in result.missing_ids
    assert load_carecenter_paused_ids(config) == ["broken-job"]


def test_restore_ccc_does_not_adopt_an_unrelated_unreadable_definition(tmp_path: Path) -> None:
    """Sonst wuerde ein spaeterer Restore die nach der Reparatur lesbare Datei aktivieren,
    obwohl der Nutzer sie selbst pausiert hatte."""
    config = make_config(tmp_path)
    write_automation(config.codex_home, "good-job", "PAUSED")
    write_broken(config.codex_home, ("users-own-job",), "users-own-job")
    write_carecenter_state(config, ["good-job"])

    result = activate_carecenter_paused_automations(config)

    assert result.unparseable_ids == ["users-own-job"]
    assert result.status == "partial"
    assert load_carecenter_paused_ids(config) == []


def test_activate_all_does_not_forget_paused_ids_while_definitions_are_unreadable(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    write_automation(config.codex_home, "good-job", "PAUSED")
    write_broken(config.codex_home, ("broken-job",), "broken-job")
    write_carecenter_state(config, ["good-job", "broken-job"])

    result = activate_all_automations(config)

    assert result.status == "partial"
    assert result.unparseable_count == 1
    assert "broken-job" in load_carecenter_paused_ids(config)


def test_clean_run_still_reports_ok_without_unreadable_definitions(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    write_automation(config.codex_home, "good-job", "ACTIVE")

    result = pause_active_automations(config)

    assert result.status == "ok"
    assert result.unparseable_ids == []
    assert result.unparseable_count == 0


# --- Atomares Schreiben (T-20261101-844031160) ---------------------------------------------------


def test_write_toml_interrupted_before_replace_leaves_the_original_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = make_config(tmp_path)
    path = write_automation(config.codex_home, "job", "ACTIVE")
    before = path.read_bytes()

    def crash(src: object, dst: object) -> None:
        raise OSError("simulated crash between tmp and replace")

    monkeypatch.setattr(automation_control.os, "replace", crash)
    result = pause_active_automations(config)

    assert path.read_bytes() == before
    assert result.status == "failed"
    assert any("simulated crash" in error for error in result.errors)
    assert sorted(item.name for item in path.parent.iterdir()) == ["automation.toml"]


def test_write_toml_syncs_a_temp_file_in_the_same_folder_before_replacing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = make_config(tmp_path)
    path = write_automation(config.codex_home, "job", "ACTIVE")
    events: list[tuple[str, object]] = []
    real_fsync, real_replace = os.fsync, os.replace

    def spy_fsync(fd: int) -> None:
        events.append(("fsync", fd))
        real_fsync(fd)

    def spy_replace(src: object, dst: object) -> None:
        events.append(("replace", (Path(str(src)).parent, Path(str(dst)))))
        real_replace(src, dst)

    monkeypatch.setattr(automation_control.os, "fsync", spy_fsync)
    monkeypatch.setattr(automation_control.os, "replace", spy_replace)

    pause_active_automations(config)

    assert [name for name, _ in events] == ["fsync", "replace"]
    assert events[1][1] == (path.parent, path)
    assert read_status(path) == "PAUSED"


def test_status_change_preserves_crlf_utf8_without_bom(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    folder = config.codex_home / "automations" / "umlaut-job"
    folder.mkdir(parents=True)
    path = folder / "automation.toml"
    original = 'id = "umlaut-job"\r\nname = "Überprüfung läuft"\r\nstatus = "ACTIVE"\r\n'
    path.write_bytes(original.encode("utf-8"))

    pause_active_automations(config)

    raw = path.read_bytes()
    assert raw == original.replace('"ACTIVE"', '"PAUSED"').encode("utf-8")
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.count(b"\n") == raw.count(b"\r\n")


def test_undecodable_bytes_are_reported_not_silently_rewritten(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    folder = config.codex_home / "automations" / "latin1-job"
    folder.mkdir(parents=True)
    path = folder / "automation.toml"
    path.write_bytes(b'id = "latin1-job"\nname = "caf\xe9"\nstatus = "ACTIVE"\n')
    before = path.read_bytes()

    result = pause_active_automations(config)

    assert result.unparseable_ids == ["latin1-job"]
    assert result.status == "failed"
    assert path.read_bytes() == before
