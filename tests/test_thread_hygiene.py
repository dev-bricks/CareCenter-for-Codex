from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.mark_runs_read import global_state_path
from codex_logdatenbank_wartung.processes import ProcessInfo
from codex_logdatenbank_wartung.thread_hygiene import maintain_threads

NOW = 2_000_000_000


def make_config(tmp_path: Path) -> MaintenanceConfig:
    home = tmp_path / ".codex"
    home.mkdir()
    config = MaintenanceConfig(
        database_path=str(home / "logs_2.sqlite"),
        backup_dir=str(tmp_path / "backups"),
    )
    with sqlite3.connect(config.state_db_path) as conn:
        conn.execute(
            "CREATE TABLE threads (id TEXT PRIMARY KEY, rollout_path TEXT NOT NULL, "
            "updated_at INTEGER NOT NULL, archived INTEGER NOT NULL DEFAULT 0, archived_at INTEGER)"
        )
    return config


def add_thread(config: MaintenanceConfig, thread_id: str, age_days: int) -> Path:
    path = config.codex_home / "sessions" / f"{thread_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")
    with sqlite3.connect(config.state_db_path) as conn:
        conn.execute(
            "INSERT INTO threads(id, rollout_path, updated_at, archived) VALUES (?, ?, ?, 0)",
            (thread_id, str(path), NOW - age_days * 86400),
        )
    return path


def write_unread(config: MaintenanceConfig, ids: list[str]) -> None:
    global_state_path(config).write_text(
        json.dumps({"electron-persisted-atom-state": {
            "unread-thread-ids-by-host-v1": {"local": ids}, "keep": True
        }}), encoding="utf-8"
    )


def test_marks_only_unread_threads_older_than_cutoff(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    add_thread(config, "old", 5)
    add_thread(config, "new", 1)
    write_unread(config, ["old", "new", "unknown"])

    result = maintain_threads(
        config, mark_read_days=2, process_provider=lambda: [], now=NOW
    )

    assert result.status == "ok"
    assert result.marked_read == 1
    state = json.loads(global_state_path(config).read_text(encoding="utf-8"))
    assert state["electron-persisted-atom-state"]["unread-thread-ids-by-host-v1"]["local"] == ["new", "unknown"]


def test_mark_all_read_clears_every_known_and_unknown_id(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    add_thread(config, "new", 0)
    write_unread(config, ["new", "unknown"])

    result = maintain_threads(config, mark_all_read=True, process_provider=lambda: [], now=NOW)

    assert result.marked_read == 2
    state = json.loads(global_state_path(config).read_text(encoding="utf-8"))
    assert state["electron-persisted-atom-state"]["unread-thread-ids-by-host-v1"]["local"] == []


def test_archives_only_old_threads_and_moves_rollout(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    old_path = add_thread(config, "old", 20)
    new_path = add_thread(config, "new", 3)
    write_unread(config, ["old", "new"])

    result = maintain_threads(config, archive_days=10, process_provider=lambda: [], now=NOW)

    assert result.status == "ok"
    assert result.archived == 1
    assert not old_path.exists()
    assert (config.codex_home / "archived_sessions" / old_path.name).exists()
    assert new_path.exists()
    with sqlite3.connect(config.state_db_path) as conn:
        assert conn.execute("SELECT archived FROM threads WHERE id='old'").fetchone()[0] == 1
        assert conn.execute("SELECT archived FROM threads WHERE id='new'").fetchone()[0] == 0


def test_blocks_while_codex_is_running(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    write_unread(config, ["old"])
    result = maintain_threads(
        config,
        mark_all_read=True,
        process_provider=lambda: [
            ProcessInfo(pid=42, name="Codex", executable=config.codex_executable)
        ],
    )
    assert result.status == "blocked"
