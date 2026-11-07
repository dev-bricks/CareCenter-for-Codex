from __future__ import annotations

import json
import os
import stat
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


# --- Leere und id-lose Definitionen sind keine lesbaren Datensaetze (T-20261107-490692877) ---------
# Eine leere (etwa abgeschnittene) automation.toml parst als leeres TOML. Ohne diese Pruefung galt sie als
# Datensatz mit Status UNKNOWN, und activate-all haette ``status = "ACTIVE"`` hineingeschrieben: eine kaputte
# Definition waere mit einem Status "repariert" worden.

BAD_DEFINITIONS = [
    pytest.param(b"", "empty", id="leere-datei"),
    pytest.param(b"# abgeschnitten, nur ein Kommentar\n", "empty", id="nur-kommentar"),
    pytest.param(b" \r\n\t\n  \n", "empty", id="nur-leerraum"),
    pytest.param(b'name = "x"\nstatus = "ACTIVE"\n', "missing id", id="id-fehlt"),
    pytest.param(b'id = ""\nname = "x"\nstatus = "ACTIVE"\n', "missing id", id="id-leer"),
    pytest.param(b'id = "   "\nname = "x"\nstatus = "ACTIVE"\n', "missing id", id="id-nur-leerraum"),
    pytest.param(b'id = 5\nname = "x"\nstatus = "ACTIVE"\n', "missing id", id="id-keine-zeichenkette"),
    pytest.param(b'[section]\nstatus = "ACTIVE"\n', "missing id", id="nur-tabelle"),
    pytest.param(b'id = "other-job"\nname = "x"\nstatus = "ACTIVE"\n', "id mismatch", id="id-weicht-vom-ordner-ab"),
]


def write_bad(codex_home: Path, folder_name: str, payload: bytes) -> Path:
    folder = codex_home / "automations" / folder_name
    folder.mkdir(parents=True)
    path = folder / "automation.toml"
    path.write_bytes(payload)
    return path


@pytest.mark.parametrize(("payload", "token"), BAD_DEFINITIONS)
def test_empty_or_id_less_definition_is_unparseable_with_its_own_message(
    tmp_path: Path, payload: bytes, token: str
) -> None:
    config = make_config(tmp_path)
    good = write_automation(config.codex_home, "good-job", "PAUSED")
    bad = write_bad(config.codex_home, "bad-job", payload)

    records, unparseable = scan_automations(config)

    assert [record.path for record in records] == [good], "nicht als lesbarer Datensatz (UNKNOWN) fuehren"
    assert [(item.id, item.path) for item in unparseable] == [("bad-job", bad)]
    assert token in unparseable[0].error
    assert [record.id for record in load_automations(config)] == ["good-job"]


@pytest.mark.parametrize(("payload", "token"), BAD_DEFINITIONS)
@pytest.mark.parametrize("action", ["pause-active", "activate-all", "restore-ccc"])
def test_no_action_ever_writes_into_an_empty_or_id_less_definition(
    tmp_path: Path, payload: bytes, token: str, action: str
) -> None:
    config = make_config(tmp_path)
    bad = write_bad(config.codex_home, "bad-job", payload)
    write_carecenter_state(config, ["bad-job"])

    result = run_automation_action(config, action)  # type: ignore[arg-type]

    assert bad.read_bytes() == payload, "die kaputte Definition darf nie ueberschrieben werden"
    assert result.unparseable_ids == ["bad-job"]
    assert result.status != "ok"
    assert any("bad-job" in error and token in error for error in result.errors)
    assert [item.name for item in bad.parent.iterdir()] == ["automation.toml"], "keine tmp-Datei"


def test_status_change_revalidates_the_file_right_before_writing(tmp_path: Path) -> None:
    """Zwischen Scan und Schreiben abgeschnittene Datei: weder ueberschreiben noch als lesbar behandeln."""
    config = make_config(tmp_path)
    path = write_automation(config.codex_home, "job", "PAUSED")
    record = scan_automations(config)[0][0]
    path.write_bytes(b"")

    with pytest.raises(automation_control._UNREADABLE):
        automation_control._set_status(record, "ACTIVE")

    assert path.read_bytes() == b""


def test_anomaly_scan_reports_empty_and_id_less_files_but_keeps_duplicate_detection(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    empty = write_bad(config.codex_home, "empty-job", b"")
    no_id = write_bad(config.codex_home, "no-id-job", b'name = "x"\n')
    first = write_automation_at(config.codex_home, ("folder-a",), "dupe")
    second = write_automation_at(config.codex_home, ("folder-b",), "dupe")

    report = find_automation_anomalies(config)

    assert sorted(item.path for item in report.unparseable) == sorted([empty, no_id])
    assert any("empty" in item.error for item in report.unparseable)
    assert any("missing id" in item.error for item in report.unparseable)
    # id und Ordnername duerfen hier abweichen: sonst waere die Doppel-id-Erkennung nicht mehr moeglich.
    assert [item.paths for item in report.duplicate_ids] == [sorted([first, second])]


# --- Rechte und Symlinks beim atomaren Schreiben ---------------------------------------------------


@pytest.mark.skipif(os.name == "nt", reason="POSIX-Dateirechte")
@pytest.mark.parametrize("mode", [0o644, 0o664, 0o640, 0o600])
def test_status_change_keeps_the_permissions_of_the_original(tmp_path: Path, mode: int) -> None:
    config = make_config(tmp_path)
    path = write_automation(config.codex_home, "job", "ACTIVE")
    path.chmod(mode)

    pause_active_automations(config)

    assert stat.S_IMODE(path.stat().st_mode) == mode, "mkstemp macht 0600; die Rechte des Originals uebernehmen"
    assert read_status(path) == "PAUSED"


def test_status_change_applies_the_mode_of_the_original_to_the_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plattformunabhaengig: der Aufruf muss vor dem os.replace auf der tmp-Datei erfolgen."""
    config = make_config(tmp_path)
    path = write_automation(config.codex_home, "job", "ACTIVE")
    original_mode = stat.S_IMODE(path.stat().st_mode)
    calls: list[tuple[str, int, bool]] = []
    real_chmod, real_replace = os.chmod, os.replace

    def spy_chmod(target: object, mode: int, *args: object, **kwargs: object) -> None:
        calls.append(("chmod", mode, str(target).endswith(".tmp")))
        real_chmod(target, mode, *args, **kwargs)  # type: ignore[arg-type]

    def spy_replace(src: object, dst: object) -> None:
        calls.append(("replace", 0, False))
        real_replace(src, dst)  # type: ignore[arg-type]

    monkeypatch.setattr(automation_control.os, "chmod", spy_chmod)
    monkeypatch.setattr(automation_control.os, "replace", spy_replace)

    pause_active_automations(config)

    assert calls == [("chmod", original_mode, True), ("replace", 0, False)]


@pytest.mark.skipif(os.name != "nt", reason="nur unter Windows scheitert os.replace an einer schreibgeschuetzten Datei")
def test_read_only_original_fails_cleanly_without_leftovers(tmp_path: Path) -> None:
    """r1-Befund PR #10: die tmp-Datei erbte das Nur-Lesen-Attribut, das Aufraeumen scheiterte ebenfalls,
    es blieb ``automation.toml.<x>.tmp`` liegen und die Meldung nannte nur diese tmp-Datei."""
    config = make_config(tmp_path)
    path = write_automation(config.codex_home, "job", "ACTIVE")
    path.chmod(stat.S_IREAD)
    try:
        result = pause_active_automations(config)
    finally:
        path.chmod(stat.S_IWRITE | stat.S_IREAD)

    assert result.status == "failed"
    assert read_status(path) == "ACTIVE", "das Original bleibt unveraendert"
    assert list(path.parent.glob("*.tmp")) == [], "keine tmp-Reste"
    (error,) = result.errors
    # Fehlertext von os.replace(tmp -> Ziel) endet mit dem Zielpfad; der des Aufraeumens (unlink) nennt nur die tmp-Datei.
    assert error.endswith("automation.toml'"), error


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks sind hier nicht erlaubt (unter Windows: Entwicklermodus oder Administrator)")


def test_status_change_writes_through_a_symlink_and_keeps_the_link(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    real_dir = tmp_path / "synced"
    real_dir.mkdir()
    target = write_automation(tmp_path / "elsewhere", "job", "ACTIVE")
    target.replace(real_dir / "job.toml")
    target = real_dir / "job.toml"
    folder = config.codex_home / "automations" / "job"
    folder.mkdir(parents=True)
    link = folder / "automation.toml"
    _symlink_or_skip(link, target)

    result = pause_active_automations(config)

    assert result.status == "ok"
    assert link.is_symlink(), "der Link darf nicht durch eine normale Datei ersetzt werden"
    assert link.resolve() == target.resolve() and os.path.samefile(link, target)  # readlink liefert unter Windows ein Praefix
    assert read_status(target) == "PAUSED"
    assert sorted(item.name for item in real_dir.iterdir()) == ["job.toml"], "keine tmp-Datei zurueckgelassen"


def test_write_toml_writes_to_the_resolved_target_of_a_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Auch ohne Symlink-Recht pruefbar: aufgeloest wird der Pfad wie bei einem Symlink, geschrieben wird dort."""
    config = make_config(tmp_path)
    link_path = write_automation(config.codex_home, "job", "ACTIVE")
    real_dir = tmp_path / "synced"
    real_dir.mkdir()
    target = real_dir / "job.toml"
    target.write_bytes(link_path.read_bytes())
    link_before = link_path.read_bytes()
    real_realpath = os.path.realpath

    def fake_realpath(value: object, *args: object, **kwargs: object) -> str:
        if Path(str(value)) == link_path:
            return str(target)
        return real_realpath(value, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(automation_control.os.path, "realpath", fake_realpath)

    document = tomlkit.parse(target.read_text(encoding="utf-8"))
    document["status"] = "PAUSED"
    automation_control._write_toml(link_path, document)

    assert read_status(target) == "PAUSED"
    assert link_path.read_bytes() == link_before, "der Link-Pfad selbst bleibt unberuehrt"
    assert sorted(item.name for item in real_dir.iterdir()) == ["job.toml"]
