"""Tests fuer das Markieren der Automations-Ergebnisse als gelesen (mark_runs_read)."""

from __future__ import annotations

import json
from pathlib import Path

from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.mark_runs_read import (
    global_state_path,
    mark_all_automation_runs_read,
)
from codex_logdatenbank_wartung.processes import ProcessInfo


def make_config(tmp_path: Path) -> MaintenanceConfig:
    codex_home = tmp_path / ".codex"
    codex_home.mkdir(parents=True, exist_ok=True)
    return MaintenanceConfig(database_path=str(codex_home / "logs_2.sqlite"))


def write_state(config: MaintenanceConfig, payload: object) -> Path:
    path = global_state_path(config)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def no_codex() -> list[ProcessInfo]:
    """Provider ohne Codex-Prozesse (Codex geschlossen)."""
    return []


def codex_running(config: MaintenanceConfig) -> list[ProcessInfo]:
    """Provider mit einem Codex-Prozess am EXAKTEN konfigurierten Exe-Pfad.

    matches_codex_executable vergleicht den exakten ``codex_executable``-Pfad, nicht den
    Prozessnamen -- der Provider muss daher ``executable=config.codex_executable`` liefern.
    """
    return [
        ProcessInfo(
            pid=4242,
            name="Codex",
            executable=config.codex_executable,
        )
    ]


def test_blocked_when_codex_running_leaves_file_untouched(tmp_path: Path) -> None:
    # (a) Codex laeuft -> status blocked, Datei UNVERAENDERT.
    config = make_config(tmp_path)
    payload = {
        "electron-persisted-atom-state": {
            "unread-thread-ids-by-host-v1": {"local": ["t1", "t2", "t3"]},
        },
        "other-key": {"keep": True},
    }
    path = write_state(config, payload)
    original = path.read_text(encoding="utf-8")

    result = mark_all_automation_runs_read(
        config, process_provider=lambda: codex_running(config)
    )

    assert result.status == "blocked"
    assert result.cleared_count == 0
    assert path.read_text(encoding="utf-8") == original
    # Kein Backup angelegt.
    assert list(path.parent.glob("*.carecenter-bak-*")) == []


def test_clears_lists_and_backs_up_when_codex_closed(tmp_path: Path) -> None:
    # (b) Codex zu, Liste mit N IDs -> geleert, cleared_count==N, Backup da, Rest unveraendert.
    config = make_config(tmp_path)
    payload = {
        "electron-persisted-atom-state": {
            "unread-thread-ids-by-host-v1": {"local": ["a", "b", "c"], "remote": ["d"]},
            "some-other-atom": [1, 2, 3],
        },
        "top-level-untouched": {"nested": "value"},
    }
    path = write_state(config, payload)

    result = mark_all_automation_runs_read(config, process_provider=no_codex)

    assert result.status == "ok"
    assert result.cleared_count == 4
    assert result.backup_path is not None

    backups = list(path.parent.glob("*.carecenter-bak-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == json.dumps(payload, ensure_ascii=False, indent=2)

    written = json.loads(path.read_text(encoding="utf-8"))
    atom = written["electron-persisted-atom-state"]
    assert atom["unread-thread-ids-by-host-v1"] == {"local": [], "remote": []}
    # Alles andere unveraendert.
    assert atom["some-other-atom"] == [1, 2, 3]
    assert written["top-level-untouched"] == {"nested": "value"}


def test_clears_all_unread_thread_chat_conversation_states(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    payload = {
        "electron-persisted-atom-state": {
            "unread-thread-ids-by-host-v1": {"local": ["t1"]},
            "unread-chat-ids-by-host-v1": {"local": ["c1", "c2"]},
            "nested-view-state": {
                "unread-conversation-ids-by-host-v1": {"remote": ["v1"]},
            },
            "unread-notification-count": 99,
            "some-other-atom": [1, 2, 3],
        },
    }
    path = write_state(config, payload)

    result = mark_all_automation_runs_read(config, process_provider=no_codex)

    assert result.status == "ok"
    assert result.cleared_count == 4
    written = json.loads(path.read_text(encoding="utf-8"))
    atom = written["electron-persisted-atom-state"]
    assert atom["unread-thread-ids-by-host-v1"] == {"local": []}
    assert atom["unread-chat-ids-by-host-v1"] == {"local": []}
    assert atom["nested-view-state"]["unread-conversation-ids-by-host-v1"] == {"remote": []}
    assert atom["unread-notification-count"] == 99
    assert atom["some-other-atom"] == [1, 2, 3]


def test_nothing_to_do_when_lists_already_empty(tmp_path: Path) -> None:
    # (c) Listen bereits leer -> status nothing, kein Fehler, kein Backup.
    config = make_config(tmp_path)
    payload = {
        "electron-persisted-atom-state": {
            "unread-thread-ids-by-host-v1": {"local": [], "remote": []},
        },
    }
    path = write_state(config, payload)

    result = mark_all_automation_runs_read(config, process_provider=no_codex)

    assert result.status == "nothing"
    assert result.cleared_count == 0
    assert list(path.parent.glob("*.carecenter-bak-*")) == []


def test_nothing_to_do_when_key_missing(tmp_path: Path) -> None:
    # (c) Key fehlt -> status nothing, kein Fehler.
    config = make_config(tmp_path)
    write_state(config, {"electron-persisted-atom-state": {"unrelated": 1}})

    result = mark_all_automation_runs_read(config, process_provider=no_codex)

    assert result.status == "nothing"
    assert result.cleared_count == 0


def test_nothing_to_do_when_file_missing(tmp_path: Path) -> None:
    # (c) Datei fehlt -> status nothing, kein Fehler.
    config = make_config(tmp_path)
    assert not global_state_path(config).exists()

    result = mark_all_automation_runs_read(config, process_provider=no_codex)

    assert result.status == "nothing"


def test_corrupt_json_aborts_and_leaves_file_untouched(tmp_path: Path) -> None:
    # (d) korruptes JSON -> failed, Originaldatei UNVERAENDERT, kein Backup.
    config = make_config(tmp_path)
    path = global_state_path(config)
    path.write_text("{ this is : not valid json", encoding="utf-8")
    original = path.read_text(encoding="utf-8")

    result = mark_all_automation_runs_read(config, process_provider=no_codex)

    assert result.status == "failed"
    assert result.cleared_count == 0
    assert path.read_text(encoding="utf-8") == original
    assert list(path.parent.glob("*.carecenter-bak-*")) == []


def test_dry_run_counts_without_writing(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    payload = {
        "electron-persisted-atom-state": {
            "unread-thread-ids-by-host-v1": {"local": ["x", "y"]},
        },
    }
    path = write_state(config, payload)
    original = path.read_text(encoding="utf-8")

    result = mark_all_automation_runs_read(
        config, process_provider=no_codex, dry_run=True
    )

    assert result.status == "ok"
    assert result.dry_run is True
    assert result.cleared_count == 2
    assert path.read_text(encoding="utf-8") == original
    assert list(path.parent.glob("*.carecenter-bak-*")) == []
