"""Sichere Offline-Wartung der Codex-Logdatenbank."""

from __future__ import annotations

import contextlib
import json
import shutil
import sqlite3
import time
import traceback
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from .config import MaintenanceConfig
from .i18n import t
from .processes import (
    ProcessProvider,
    find_codex_processes_by_executable,
    windows_processes,
)

ResultStatus = Literal["ok", "blocked", "failed", "dry-run"]
StepStatus = Literal["ok", "blocked", "failed", "skipped", "planned"]


@dataclass(slots=True)
class ProgressUpdate:
    """Eine Fortschrittsmeldung fuer die UI (Tray-Statusfenster, Tooltip)."""

    phase: str
    message: str
    percent: int
    indeterminate: bool = False


# Wird (ggf. aus einem Worker-Thread) bei jedem Fortschritt aufgerufen.
ProgressCallback = Callable[[ProgressUpdate], None]

# Backup-Copy in Bloecken, damit der Fortschritt der 1,9-GB-Kopie messbar ist.
_COPY_CHUNK = 4 * 1024 * 1024


@dataclass(slots=True)
class MaintenanceStep:
    name: str
    status: StepStatus
    message: str


@dataclass(slots=True)
class MaintenanceResult:
    status: ResultStatus
    dry_run: bool
    started_at: str
    ended_at: str
    database_path: str
    backup_dir: str | None = None
    trigger: str = "manual"
    steps: list[MaintenanceStep] = field(default_factory=list)
    codex_processes: list[dict[str, object]] = field(default_factory=list)
    error: str | None = None

    def add(self, name: str, status: StepStatus, message: str) -> None:
        self.steps.append(MaintenanceStep(name, status, message))

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_text(self) -> str:
        lines = [
            f"{t('report_status')}: {self.status}",
            f"{t('report_dry_run')}: {self.dry_run}",
            f"{t('report_database')}: {self.database_path}",
        ]
        if self.backup_dir:
            lines.append(f"{t('report_backup')}: {self.backup_dir}")
        if self.codex_processes:
            lines.append(f"{t('report_codex_processes')}:")
            for process in self.codex_processes:
                lines.append(
                    f"  - {process.get('pid')} {process.get('name')} "
                    f"{process.get('executable') or process.get('command_line') or ''}".rstrip()
                )
        lines.append(f"{t('report_steps')}:")
        for step in self.steps:
            lines.append(f"  - [{step.status}] {step.name}: {step.message}")
        if self.error:
            lines.append(f"{t('report_error')}: {self.error}")
        return "\n".join(lines)


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def is_onedrive_path(path: Path) -> bool:
    return any("onedrive" in part.lower() for part in path.resolve().parts)


def database_sidecars(db_path: Path) -> list[Path]:
    return [db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")]


# Timestamp-Spalten werden nach Name erkannt (Groß-/Kleinschreibung ignoriert).
# "ts" ist der echte Spaltenname in logs_2.sqlite (verifiziert 2026-06-28).
_TS_COLUMN_NAMES = frozenset(
    ("timestamp", "created_at", "created", "started_at", "ended_at", "time", "date", "ts")
)


def _table_names(conn: sqlite3.Connection) -> list[str]:
    """Alle Nutztabellen aus sqlite_master (ohne SQLite-interne Tabellen)."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return [row[0] for row in rows]


def _column_info(conn: sqlite3.Connection, table: str) -> list[tuple[str, str]]:
    """Name und Typ aller Spalten einer Tabelle via PRAGMA table_info."""
    # PRAGMA table_info liefert: cid, name, type, notnull, dflt_value, pk
    rows = conn.execute(f"PRAGMA table_info([{table}])").fetchall()
    return [(row[1], row[2]) for row in rows]


def _detect_ts_column(columns: list[tuple[str, str]]) -> tuple[str, str] | None:
    """Erste Timestamp-Spalte nach Name, oder None wenn keine gefunden."""
    for name, col_type in columns:
        if name.lower() in _TS_COLUMN_NAMES:
            return name, col_type
    return None


def _cutoff_value(col_type: str, archive_days: int) -> int | str:
    """Cutoff-Wert passend zum Spaltentyp.

    INTEGER/BIGINT: Unix-Timestamp in Sekunden (wie logs_2.sqlite ts-Spalte).
    Alle anderen Typen (TEXT, TIMESTAMP, REAL): ISO-String ohne Zeitzone,
    lexikografisch vergleichbar (YYYY-MM-DDTHH:MM:SS).
    """
    cutoff_dt = datetime.now() - timedelta(days=archive_days)
    upper = col_type.upper()
    if upper.startswith("INT") or upper in ("BIGINT", "INTEGER"):
        return int(cutoff_dt.timestamp())
    return cutoff_dt.isoformat(timespec="seconds")


def _archive_table(
    conn: sqlite3.Connection,
    table: str,
    ts_col: str,
    cutoff: object,
    archive_file: Path,
    *,
    dry_run: bool = False,
) -> int:
    """Archiviert ältere Zeilen einer Tabelle in eine JSONL-Datei.

    Write-then-delete: JSONL-Schreiben vor dem DELETE, damit kein Datenverlust
    möglich ist, wenn das DELETE fehlschlägt oder die Verbindung abbricht.
    Committet pro Tabelle — ein Fehler in Tabelle B rollt Tabelle A nicht zurück.
    Im Dry-Run-Modus werden Zeilen nur gezählt, nichts verändert.
    """
    cur = conn.execute(f"SELECT * FROM [{table}] WHERE [{ts_col}] < ?", (cutoff,))
    col_names = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    if not rows or dry_run:
        return len(rows)
    archive_file.parent.mkdir(parents=True, exist_ok=True)
    with archive_file.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(
                json.dumps(dict(zip(col_names, row)), ensure_ascii=False, default=str) + "\n"
            )
    conn.execute(f"DELETE FROM [{table}] WHERE [{ts_col}] < ?", (cutoff,))
    conn.commit()  # pro Tabelle committen — Fehler in anderer Tabelle rollt dies nicht zurück
    return len(rows)


class MaintenanceLock:
    """Kleiner Laufzeit-Lock, damit Wartung nicht parallel startet."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.acquired = False

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("x", encoding="utf-8") as handle:
                handle.write(f"started_at={iso_now()}\n")
        except FileExistsError:
            return False
        self.acquired = True
        return True

    def release(self) -> None:
        if self.acquired:
            with contextlib.suppress(FileNotFoundError):
                self.path.unlink()
            self.acquired = False

    def __enter__(self) -> MaintenanceLock:
        self.acquire()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


class MaintenanceRunner:
    """Führt die Wartung bewusst konservativ aus."""

    def __init__(
        self,
        config: MaintenanceConfig,
        process_provider: ProcessProvider | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.config = config
        self.process_provider = process_provider
        self.progress_callback = progress_callback

    def _emit(self, phase: str, message: str, percent: int, *, indeterminate: bool = False) -> None:
        if self.progress_callback is not None:
            self.progress_callback(
                ProgressUpdate(phase, message, max(0, min(100, percent)), indeterminate)
            )

    def run(self, *, dry_run: bool = True, trigger: str = "manual") -> MaintenanceResult:
        started = iso_now()
        result = MaintenanceResult(
            status="dry-run" if dry_run else "ok",
            dry_run=dry_run,
            started_at=started,
            ended_at=started,
            database_path=str(self.config.db_path),
            trigger=trigger,
        )

        self._emit("start", t("maintenance_progress_start"), 0)
        try:
            self._run_inner(result)
        except Exception as exc:  # pragma: no cover - Schutznetz für Protokollierung
            result.status = "failed"
            result.error = f"{type(exc).__name__}: {exc}"
            result.add(t("step_exception"), "failed", traceback.format_exc())
        finally:
            result.ended_at = iso_now()
            if not dry_run:
                self.write_log(result)
        terminal = {
            "ok": t("maintenance_done_ok"),
            "blocked": t("maintenance_terminal_blocked"),
            "failed": t("maintenance_terminal_failed"),
            "dry-run": t("maintenance_terminal_dry_run"),
        }.get(result.status, t("maintenance_terminal_other", status=result.status))
        self._emit(result.status, terminal, 100)
        return result

    def _run_inner(self, result: MaintenanceResult) -> None:
        db_path = self.config.db_path
        sidecars = database_sidecars(db_path)
        existing_sidecars = [path for path in sidecars if path.exists()]

        if not db_path.exists():
            result.status = "failed"
            result.add(t("step_database"), "failed", t("database_missing", path=db_path))
            return

        result.add(
            t("step_database"),
            "ok",
            t("database_found", path=db_path, count=len(existing_sidecars)),
        )

        if self.process_provider is None:
            all_processes = windows_processes()
            if not all_processes:
                result.status = "blocked"
                result.add(
                    t("process_check_step"),
                    "blocked",
                    t("process_check_fail_closed"),
                )
                return
            def provider():
                return all_processes
        else:
            provider = self.process_provider

        codex_processes = find_codex_processes_by_executable(self.config, provider)
        result.codex_processes = [asdict(process) for process in codex_processes]
        if codex_processes:
            result.status = "blocked"
            result.add(t("process_check_step"), "blocked", t("process_check_blocked"))
            return
        result.add(t("process_check_step"), "ok", t("process_check_ok"))

        if is_onedrive_path(db_path) and not self.config.allow_onedrive_control:
            result.status = "blocked"
            result.add(
                t("step_onedrive"),
                "blocked",
                t("onedrive_blocked"),
            )
            return
        result.add(t("step_onedrive"), "ok", t("onedrive_ok"))

        if result.dry_run:
            result.add(t("step_backup"), "planned", t("backup_planned"))
            if self.config.backup_state_db:
                result.add(t("step_state_backup"), "planned", t("state_backup_planned"))
            result.add(t("step_integrity"), "planned", t("integrity_planned"))
            self.archive_old_logs(result)  # erkennt result.dry_run, liest DB read-only
            if self.config.allow_optimize:
                result.add(t("step_optimize"), "planned", t("optimize_planned"))
            if self.config.allow_vacuum:
                result.add(t("step_vacuum"), "planned", t("vacuum_planned"))
            return

        with MaintenanceLock(self.config.lock_path) as lock:
            if not lock.acquired:
                result.status = "blocked"
                result.add(t("step_lock"), "blocked", t("lock_running"))
                return
            result.add(t("step_lock"), "ok", t("lock_set", path=self.config.lock_path))

            self._emit("backup", t("backup_progress_start"), 5)
            backup_dir = self.create_backup(existing_sidecars)
            result.backup_dir = str(backup_dir)
            result.add(t("step_backup"), "ok", t("backup_created", path=backup_dir))

            if self.config.backup_state_db:
                self._backup_state_db(backup_dir, result)

            self.prune_backups(result)

            self._emit("integrity", t("integrity_progress"), 58, indeterminate=True)
            backup_db = backup_dir / db_path.name
            integrity = self.integrity_check(backup_db)
            if integrity != "ok":
                result.status = "failed"
                result.add(t("step_integrity"), "failed", integrity)
                return
            result.add(t("step_integrity"), "ok", t("integrity_ok"))

            self.archive_old_logs(result)
            self.optimize_and_vacuum(db_path, result)

    def _backup_state_db(self, backup_dir: Path, result: MaintenanceResult) -> None:
        """Sichert state_5.sqlite (+ WAL/SHM) ins Backup-Verzeichnis. Kein VACUUM (#21750)."""
        state_files = database_sidecars(self.config.state_db_path)
        existing = [f for f in state_files if f.exists()]
        if not existing:
            result.add(t("step_state_backup"), "skipped", t("state_backup_missing"))
            return
        try:
            for source in existing:
                shutil.copy2(source, backup_dir / source.name)
            total_mb = sum(f.stat().st_size for f in existing) / (1024 * 1024)
            result.add(
                t("step_state_backup"),
                "ok",
                t("state_backup_ok", mb=total_mb, count=len(existing)),
            )
        except OSError as exc:
            result.add(t("step_state_backup"), "failed", t("backup_failed", error=exc))

    def create_backup(self, files: list[Path]) -> Path:
        backup_dir = self.config.backup_path / f"logs_2-{timestamp()}"
        backup_dir.mkdir(parents=True, exist_ok=False)
        total = sum(self._safe_size(source) for source in files) or 1
        copied = 0
        # Fortschritt der Sicherung belegt den Bereich 5..55 %.
        for source in files:
            target = backup_dir / source.name
            copied = self._copy_with_progress(source, target, copied, total)
        return backup_dir

    @staticmethod
    def _safe_size(path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return 0

    def _copy_with_progress(self, source: Path, target: Path, copied: int, total: int) -> int:
        """Kopiere blockweise und melde Byte-Fortschritt (mappt auf 5..55 %)."""
        last_mb = -1
        with source.open("rb") as src, target.open("wb") as dst:
            while True:
                chunk = src.read(_COPY_CHUNK)
                if not chunk:
                    break
                dst.write(chunk)
                copied += len(chunk)
                percent = 5 + int(50 * copied / total)
                done_mb = copied // (1024 * 1024)
                if done_mb != last_mb:
                    last_mb = done_mb
                    self._emit(
                        "backup",
                        t("backup_progress", done=done_mb, total=total // (1024 * 1024)),
                        percent,
                    )
        shutil.copystat(source, target)
        return copied

    def prune_backups(self, result: MaintenanceResult) -> None:
        """Begrenze die Zahl der DB-Backups (Lektion: unbegrenzte Backups fuellten 123 GB)."""
        keep = self.config.backup_keep
        if keep <= 0:
            result.add(t("step_backup_retention"), "skipped", t("retention_unlimited"))
            return
        backups = sorted(
            (path for path in self.config.backup_path.glob("logs_2-*") if path.is_dir()),
            key=lambda path: path.name,
        )
        excess = backups[:-keep]
        removed = []
        for directory in excess:
            shutil.rmtree(directory, ignore_errors=True)
            removed.append(directory.name)
        removed.extend(self._prune_loose_backups(keep))
        if removed:
            result.add(
                t("step_backup_retention"),
                "ok",
                t("retention_removed", removed=len(removed), keep=keep),
            )
        else:
            result.add(
                t("step_backup_retention"),
                "ok",
                t("retention_ok", keep=keep),
            )

    def _prune_loose_backups(self, keep: int) -> list[str]:
        """Begrenze lose Backup-Dateien, die flach im Backup-Verzeichnis liegen.

        `thread_hygiene` legt seine Sicherungen als einzelne Dateien direkt in
        `backup_path` ab (`<db>.carecenter-thread-db-bak-<stamp>`), nicht in ein
        `logs_2-*`-Verzeichnis. Der bisherige Verzeichnis-Glob hat sie deshalb nie
        erfasst: 122 Dateien / 2,5 GB waren so unbemerkt aufgelaufen -- dieselbe
        Bugklasse, gegen die `prune_backups` ursprünglich gebaut wurde.

        Es wird pro Backup-Art (Präfix vor `-bak-`) getrennt aufbewahrt, damit
        verschiedene Sicherungstypen sich nicht gegenseitig verdrängen.
        """
        groups: dict[str, list[Path]] = {}
        for path in self.config.backup_path.glob("*-bak-*"):
            if not path.is_file():
                continue
            prefix = path.name.split("-bak-", 1)[0]
            groups.setdefault(prefix, []).append(path)

        removed: list[str] = []
        for paths in groups.values():
            ordered = sorted(paths, key=lambda item: item.name)
            for path in ordered[:-keep]:
                try:
                    path.unlink()
                except OSError:
                    continue
                removed.append(path.name)
        return removed

    def integrity_check(self, db_path: Path) -> str:
        uri = f"file:{db_path.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=30) as connection:
            rows = connection.execute("PRAGMA integrity_check;").fetchall()
        if rows == [("ok",)]:
            return "ok"
        return "; ".join(str(row[0]) for row in rows)

    def archive_old_logs(self, result: MaintenanceResult) -> None:
        if not self.config.allow_archive_old_logs:
            result.add(t("step_archive"), "skipped", t("archive_disabled"))
            return
        if self.config.archive_days <= 0:
            result.add(t("step_archive"), "skipped", t("archive_no_days"))
            return

        self._emit("archive", t("archive_progress"), 63, indeterminate=True)
        archive_dir = self.config.archive_path
        db_path = self.config.db_path

        if result.dry_run:
            # Nur zählen, nichts schreiben (read-only Verbindung).
            uri = f"file:{db_path.as_posix()}?mode=ro"
            total_count = 0
            with sqlite3.connect(uri, uri=True, timeout=30) as conn:
                for table in _table_names(conn):
                    cols = _column_info(conn, table)
                    ts_hit = _detect_ts_column(cols)
                    if ts_hit is None:
                        continue
                    ts_col, col_type = ts_hit
                    cutoff = _cutoff_value(col_type, self.config.archive_days)
                    total_count += _archive_table(
                        conn, table, ts_col, cutoff,
                        archive_dir / f"{table}.jsonl", dry_run=True,
                    )
            msg = (
                t("archive_dry_run", count=total_count) if total_count else t("archive_nothing")
            )
            result.add(t("step_archive"), "planned", msg)
            return

        # Live-Lauf: erst JSONL schreiben, dann aus DB löschen (Write-then-delete).
        archived_total = 0
        archived_tables = 0
        errors: list[str] = []
        conn = sqlite3.connect(str(db_path), timeout=60)
        try:
            for table in _table_names(conn):
                cols = _column_info(conn, table)
                ts_hit = _detect_ts_column(cols)
                if ts_hit is None:
                    continue
                ts_col, col_type = ts_hit
                cutoff = _cutoff_value(col_type, self.config.archive_days)
                archive_file = archive_dir / f"{table}.jsonl"
                try:
                    count = _archive_table(conn, table, ts_col, cutoff, archive_file)
                    if count:
                        archived_total += count
                        archived_tables += 1
                except Exception as exc:
                    with contextlib.suppress(Exception):
                        conn.rollback()
                    errors.append(t("archive_table_error", table=table, error=exc))
        finally:
            conn.close()

        if errors:
            result.add(t("step_archive"), "failed", "; ".join(errors))
        elif archived_total:
            result.add(
                t("step_archive"), "ok",
                t("archive_result", archived=archived_total, tables=archived_tables),
            )
        else:
            result.add(t("step_archive"), "ok", t("archive_nothing"))

    def optimize_and_vacuum(self, db_path: Path, result: MaintenanceResult) -> None:
        with sqlite3.connect(db_path, timeout=60) as connection:
            if self.config.allow_wal_checkpoint:
                self._emit("wal", t("wal_progress"), 72)
                row = connection.execute("PRAGMA wal_checkpoint(TRUNCATE);").fetchone()
                result.add(
                    t("step_wal_checkpoint"),
                    "ok",
                    t("wal_ok", row=row),
                )
            else:
                result.add(t("step_wal_checkpoint"), "skipped", t("step_disabled"))

            if self.config.allow_optimize:
                self._emit("optimize", t("optimize_progress"), 78)
                connection.execute("PRAGMA optimize;")
                result.add(t("step_optimize"), "ok", t("optimize_ok"))
            else:
                result.add(t("step_optimize"), "skipped", t("step_disabled"))

            if self.config.allow_vacuum:
                self._emit(
                    "vacuum",
                    t("vacuum_progress"),
                    82,
                    indeterminate=True,
                )
                start = time.monotonic()
                connection.execute("VACUUM;")
                elapsed = time.monotonic() - start
                result.add(t("step_vacuum"), "ok", t("vacuum_ok", seconds=elapsed))
                self._emit("vacuum", t("vacuum_done_progress", seconds=elapsed), 98)
            else:
                result.add(t("step_vacuum"), "skipped", t("step_disabled"))

    def write_log(self, result: MaintenanceResult) -> Path:
        self.config.logs_path.mkdir(parents=True, exist_ok=True)
        log_base = self.config.logs_path / f"maintenance-{timestamp()}"
        json_path = log_base.with_suffix(".json")
        text_path = log_base.with_suffix(".txt")
        json_path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        text_path.write_text(result.to_text() + "\n", encoding="utf-8")
        return json_path
