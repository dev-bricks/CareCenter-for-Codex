from __future__ import annotations

import sqlite3
from pathlib import Path

from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.maintenance import MaintenanceRunner
from codex_logdatenbank_wartung.processes import ProcessInfo


def make_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE logs (id INTEGER PRIMARY KEY, message TEXT)")
        connection.execute("INSERT INTO logs (message) VALUES ('ok')")


def make_config(tmp_path: Path, db_path: Path) -> MaintenanceConfig:
    return MaintenanceConfig(
        database_path=str(db_path),
        backup_dir=str(tmp_path / "backups"),
        log_dir=str(tmp_path / "logs"),
        maintenance_lock_path=str(tmp_path / "maintenance.lock"),
    )


def test_dry_run_blocks_when_codex_is_running(tmp_path: Path) -> None:
    db_path = tmp_path / "logs_2.sqlite"
    make_db(db_path)
    config = make_config(tmp_path, db_path)
    provider = lambda: [ProcessInfo(123, "Codex", r"C:\Program Files\Codex\Codex.exe", "")]

    result = MaintenanceRunner(config, provider).run(dry_run=True)

    assert result.status == "blocked"
    assert not (tmp_path / "backups").exists()


def test_execute_creates_backup_and_log_when_safe(tmp_path: Path) -> None:
    db_path = tmp_path / "logs_2.sqlite"
    make_db(db_path)
    config = make_config(tmp_path, db_path)

    result = MaintenanceRunner(config, lambda: []).run(dry_run=False)

    assert result.status == "ok"
    assert result.backup_dir is not None
    assert (Path(result.backup_dir) / "logs_2.sqlite").exists()
    assert list((tmp_path / "logs").glob("maintenance-*.json"))


def test_execute_blocks_if_maintenance_lock_exists(tmp_path: Path) -> None:
    db_path = tmp_path / "logs_2.sqlite"
    make_db(db_path)
    config = make_config(tmp_path, db_path)
    Path(config.maintenance_lock_path).write_text("running\n", encoding="utf-8")

    result = MaintenanceRunner(config, lambda: []).run(dry_run=False)

    assert result.status == "blocked"
    assert not (tmp_path / "backups").exists()
