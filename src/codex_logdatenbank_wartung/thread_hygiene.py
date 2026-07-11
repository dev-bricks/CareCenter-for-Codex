"""Sichere Altersregeln für Codex-Desktop-Threads.

Die aktuelle Codex-App speichert Thread-Alter und Archivstatus in ``state_5.sqlite``;
Ungelesen-IDs liegen ergänzend in ``.codex-global-state.json``. Änderungen erfolgen
nur bei geschlossenem Codex, nach Backups und mit SQLite-Transaktion.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .config import MaintenanceConfig
from .mark_runs_read import ATOM_STATE_KEY, UNREAD_KEY, _atomic_write_json, global_state_path
from .processes import ProcessProvider, find_codex_processes_by_executable


@dataclass(slots=True)
class ThreadHygieneResult:
    status: str
    marked_read: int = 0
    archived: int = 0
    message: str = ""
    state_backup: str | None = None
    database_backup: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_text(self) -> str:
        return (
            f"Status: {self.status}\n{self.message}\n"
            f"Als gelesen markiert: {self.marked_read}\nArchiviert: {self.archived}"
        )


def _backup_path(path: Path, suffix: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return path.with_name(f"{path.name}.carecenter-{suffix}-{stamp}")


def maintain_threads(
    config: MaintenanceConfig,
    *,
    mark_read_days: int = 0,
    archive_days: int = 0,
    archive_thread_ids: set[str] | None = None,
    mark_all_read: bool = False,
    process_provider: ProcessProvider | None = None,
    now: int | None = None,
) -> ThreadHygieneResult:
    """Markiert alte ungelesene Threads und/oder archiviert alte Threads.

    ``0`` deaktiviert die jeweilige Altersregel. ``mark_all_read`` leert unabhängig
    vom Alter alle lokalen Ungelesen-IDs. Unbekannte IDs bleiben bei Altersfiltern erhalten.
    """
    if find_codex_processes_by_executable(config, provider=process_provider):
        return ThreadHygieneResult("blocked", message="Codex läuft; Ausführung vorgemerkt/übersprungen.")
    explicit_archive_ids = set(archive_thread_ids or ())
    if not mark_all_read and mark_read_days <= 0 and archive_days <= 0 and not explicit_archive_ids:
        return ThreadHygieneResult("nothing", message="Keine Thread-Regel aktiviert.")

    db_path = config.state_db_path
    state_path = global_state_path(config)
    if not db_path.exists():
        return ThreadHygieneResult("failed", message=f"Thread-Datenbank fehlt: {db_path}")

    try:
        state_raw = state_path.read_text(encoding="utf-8") if state_path.exists() else "{}"
        state = json.loads(state_raw)
    except (OSError, ValueError) as exc:
        return ThreadHygieneResult("failed", message=f"Globaler Zustand unlesbar: {exc}")

    current = int(time.time() if now is None else now)
    read_cutoff = current - max(0, int(mark_read_days)) * 86400
    archive_cutoff = current - max(0, int(archive_days)) * 86400
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    moved: list[tuple[Path, Path]] = []
    state_backup: Path | None = None
    db_backup: Path | None = None
    try:
        rows = {row["id"]: row for row in conn.execute(
            "SELECT id, rollout_path, updated_at, archived FROM threads"
        )}
        atom = state.setdefault(ATOM_STATE_KEY, {}) if isinstance(state, dict) else {}
        unread_by_host = atom.get(UNREAD_KEY, {}) if isinstance(atom, dict) else {}
        if not isinstance(unread_by_host, dict):
            unread_by_host = {}

        marked = 0
        for host, ids in list(unread_by_host.items()):
            if not isinstance(ids, list):
                continue
            kept: list[object] = []
            for thread_id in ids:
                row = rows.get(str(thread_id))
                should_read = mark_all_read or (
                    mark_read_days > 0 and row is not None and int(row["updated_at"]) < read_cutoff
                )
                if should_read:
                    marked += 1
                else:
                    kept.append(thread_id)
            unread_by_host[host] = kept
        if isinstance(atom, dict):
            atom[UNREAD_KEY] = unread_by_host

        candidates = [
            row for row in rows.values()
            if not int(row["archived"]) and (
                row["id"] in explicit_archive_ids
                or (archive_days > 0 and int(row["updated_at"]) < archive_cutoff)
            )
        ]

        if not marked and not candidates:
            return ThreadHygieneResult("nothing", message="Keine passenden Threads gefunden.")

        config.backup_path.mkdir(parents=True, exist_ok=True)
        db_backup = config.backup_path / _backup_path(db_path, "thread-db-bak").name
        backup_conn = sqlite3.connect(db_backup)
        try:
            conn.backup(backup_conn)
        finally:
            backup_conn.close()
        if marked and state_path.exists():
            state_backup = _backup_path(state_path, "thread-state-bak")
            state_backup.write_text(state_raw, encoding="utf-8")

        archive_root = config.codex_home / "archived_sessions"
        archive_root.mkdir(parents=True, exist_ok=True)
        conn.execute("BEGIN IMMEDIATE")
        archived = 0
        for row in candidates:
            source = Path(str(row["rollout_path"]))
            target = archive_root / source.name
            if source.exists() and source.resolve() != target.resolve():
                if target.exists():
                    raise FileExistsError(f"Archivziel existiert bereits: {target}")
                shutil.move(str(source), str(target))
                moved.append((source, target))
            conn.execute(
                "UPDATE threads SET archived=1, archived_at=?, rollout_path=? WHERE id=?",
                (current, str(target), row["id"]),
            )
            archived += 1
            for host, ids in unread_by_host.items():
                if isinstance(ids, list) and row["id"] in ids:
                    unread_by_host[host] = [item for item in ids if item != row["id"]]
                    marked += 1
        conn.commit()
        if marked or archived:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(state_path, state)
        return ThreadHygieneResult(
            "ok", marked_read=marked, archived=archived,
            message=f"{marked} Thread(s) als gelesen markiert, {archived} archiviert.",
            state_backup=str(state_backup) if state_backup else None,
            database_backup=str(db_backup),
        )
    except Exception as exc:
        conn.rollback()
        for source, target in reversed(moved):
            if target.exists() and not source.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(source))
        return ThreadHygieneResult("failed", message=f"Keine vollständige Änderung: {exc}")
    finally:
        conn.close()


def run_configured_thread_hygiene(config: MaintenanceConfig) -> ThreadHygieneResult:
    return maintain_threads(
        config,
        mark_read_days=max(0, int(config.auto_mark_threads_read_days)),
        archive_days=max(0, int(config.auto_archive_threads_days)),
    )
