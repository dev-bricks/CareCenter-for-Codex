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
from datetime import datetime
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
            f"Status: {self.status}",
            f"Dry-Run: {self.dry_run}",
            f"Datenbank: {self.database_path}",
        ]
        if self.backup_dir:
            lines.append(f"Backup: {self.backup_dir}")
        if self.codex_processes:
            lines.append("Codex-Prozesse:")
            for process in self.codex_processes:
                lines.append(
                    f"  - {process.get('pid')} {process.get('name')} "
                    f"{process.get('executable') or process.get('command_line') or ''}".rstrip()
                )
        lines.append("Schritte:")
        for step in self.steps:
            lines.append(f"  - [{step.status}] {step.name}: {step.message}")
        if self.error:
            lines.append(f"Fehler: {self.error}")
        return "\n".join(lines)


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def is_onedrive_path(path: Path) -> bool:
    return any("onedrive" in part.lower() for part in path.resolve().parts)


def database_sidecars(db_path: Path) -> list[Path]:
    return [db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")]


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

        self._emit("start", "Wartung gestartet …", 0)
        try:
            self._run_inner(result)
        except Exception as exc:  # pragma: no cover - Schutznetz für Protokollierung
            result.status = "failed"
            result.error = f"{type(exc).__name__}: {exc}"
            result.add("Ausnahme", "failed", traceback.format_exc())
        finally:
            result.ended_at = iso_now()
            if not dry_run:
                self.write_log(result)
        terminal = {
            "ok": "Wartung abgeschlossen.",
            "blocked": "Wartung übersprungen (blockiert).",
            "failed": "Wartung fehlgeschlagen.",
            "dry-run": "Dry-Run abgeschlossen.",
        }.get(result.status, f"Wartung beendet: {result.status}")
        self._emit(result.status, terminal, 100)
        return result

    def _run_inner(self, result: MaintenanceResult) -> None:
        db_path = self.config.db_path
        sidecars = database_sidecars(db_path)
        existing_sidecars = [path for path in sidecars if path.exists()]

        if not db_path.exists():
            result.status = "failed"
            result.add("Datenbank", "failed", f"{db_path} wurde nicht gefunden.")
            return

        result.add(
            "Datenbank",
            "ok",
            f"{db_path} vorhanden; {len(existing_sidecars)} Datei(en) inklusive WAL/SHM gefunden.",
        )

        if self.process_provider is None:
            all_processes = windows_processes()
            if not all_processes:
                result.status = "blocked"
                result.add(
                    "Codex-Prozessprüfung",
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
            result.add("Codex-Prozessprüfung", "blocked", t("process_check_blocked"))
            return
        result.add("Codex-Prozessprüfung", "ok", t("process_check_ok"))

        if is_onedrive_path(db_path) and not self.config.allow_onedrive_control:
            result.status = "blocked"
            result.add(
                "OneDrive-Schutz",
                "blocked",
                "Datenbank liegt in OneDrive; OneDrive-Kontrolle ist nicht freigegeben.",
            )
            return
        result.add("OneDrive-Schutz", "ok", "Keine blockierende OneDrive-Lage erkannt.")

        if result.dry_run:
            result.add("Backup", "planned", "Backup würde in einem Zeitstempelordner erstellt.")
            if self.config.backup_state_db:
                result.add("State-DB-Backup", "planned", "state_5.sqlite würde mitgesichert (kein VACUUM).")
            result.add("Integritätscheck", "planned", "Integritätscheck würde auf dem Backup laufen.")
            if self.config.allow_optimize:
                result.add("Optimize", "planned", "PRAGMA optimize würde ausgeführt.")
            if self.config.allow_vacuum:
                result.add("Vacuum", "planned", "VACUUM würde nach erfolgreichem Check laufen.")
            result.add(
                "Archivierung",
                "skipped",
                "Alte Logs werden ohne explizite Konfiguration nicht archiviert oder gelöscht.",
            )
            return

        with MaintenanceLock(self.config.lock_path) as lock:
            if not lock.acquired:
                result.status = "blocked"
                result.add("Wartungs-Lock", "blocked", "Eine Wartung läuft bereits.")
                return
            result.add("Wartungs-Lock", "ok", f"Lock gesetzt: {self.config.lock_path}")

            self._emit("backup", "Sicherung wird erstellt …", 5)
            backup_dir = self.create_backup(existing_sidecars)
            result.backup_dir = str(backup_dir)
            result.add("Backup", "ok", f"Backup erstellt: {backup_dir}")

            if self.config.backup_state_db:
                self._backup_state_db(backup_dir, result)

            self.prune_backups(result)

            self._emit("integrity", "Integritätscheck auf der Sicherung …", 58, indeterminate=True)
            backup_db = backup_dir / db_path.name
            integrity = self.integrity_check(backup_db)
            if integrity != "ok":
                result.status = "failed"
                result.add("Integritätscheck", "failed", integrity)
                return
            result.add("Integritätscheck", "ok", "SQLite meldet integrity_check=ok.")

            self.archive_old_logs(result)
            self.optimize_and_vacuum(db_path, result)

    def _backup_state_db(self, backup_dir: Path, result: MaintenanceResult) -> None:
        """Sichert state_5.sqlite (+ WAL/SHM) ins Backup-Verzeichnis. Kein VACUUM (#21750)."""
        state_files = database_sidecars(self.config.state_db_path)
        existing = [f for f in state_files if f.exists()]
        if not existing:
            result.add("State-DB-Backup", "skipped", "state_5.sqlite nicht gefunden.")
            return
        try:
            for source in existing:
                shutil.copy2(source, backup_dir / source.name)
            total_mb = sum(f.stat().st_size for f in existing) / (1024 * 1024)
            result.add(
                "State-DB-Backup",
                "ok",
                f"state_5.sqlite gesichert ({total_mb:.1f} MB, {len(existing)} Datei(en)).",
            )
        except OSError as exc:
            result.add("State-DB-Backup", "failed", f"Backup fehlgeschlagen: {exc}")

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
                        f"Sicherung … {done_mb} / {total // (1024 * 1024)} MB",
                        percent,
                    )
        shutil.copystat(source, target)
        return copied

    def prune_backups(self, result: MaintenanceResult) -> None:
        """Begrenze die Zahl der DB-Backups (Lektion: unbegrenzte Backups fuellten 123 GB)."""
        keep = self.config.backup_keep
        if keep <= 0:
            result.add("Backup-Retention", "skipped", "Aufbewahrung unbegrenzt (backup_keep<=0).")
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
        if removed:
            result.add(
                "Backup-Retention",
                "ok",
                f"{len(removed)} alte Backup(s) entfernt; behalte die neuesten {keep}.",
            )
        else:
            result.add(
                "Backup-Retention",
                "ok",
                f"Keine ueberzaehligen Backups; behalte die neuesten {keep}.",
            )

    def integrity_check(self, db_path: Path) -> str:
        uri = f"file:{db_path.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=30) as connection:
            rows = connection.execute("PRAGMA integrity_check;").fetchall()
        if rows == [("ok",)]:
            return "ok"
        return "; ".join(str(row[0]) for row in rows)

    def archive_old_logs(self, result: MaintenanceResult) -> None:
        if not self.config.allow_archive_old_logs:
            result.add(
                "Archivierung",
                "skipped",
                "Nicht aktiviert; es werden keine Logdaten gelöscht oder verschoben.",
            )
            return
        result.add(
            "Archivierung",
            "skipped",
            "Archivierung ist freigegeben, aber noch nicht schemaspezifisch implementiert.",
        )

    def optimize_and_vacuum(self, db_path: Path, result: MaintenanceResult) -> None:
        with sqlite3.connect(db_path, timeout=60) as connection:
            if self.config.allow_wal_checkpoint:
                self._emit("wal", "WAL-Checkpoint …", 72)
                row = connection.execute("PRAGMA wal_checkpoint(TRUNCATE);").fetchone()
                result.add(
                    "WAL-Checkpoint",
                    "ok",
                    f"PRAGMA wal_checkpoint(TRUNCATE) ausgeführt (Ergebnis {row}).",
                )
            else:
                result.add("WAL-Checkpoint", "skipped", "In der Konfiguration deaktiviert.")

            if self.config.allow_optimize:
                self._emit("optimize", "PRAGMA optimize …", 78)
                connection.execute("PRAGMA optimize;")
                result.add("Optimize", "ok", "PRAGMA optimize ausgeführt.")
            else:
                result.add("Optimize", "skipped", "In der Konfiguration deaktiviert.")

            if self.config.allow_vacuum:
                self._emit(
                    "vacuum",
                    "VACUUM läuft … (kann 1–2 Minuten dauern)",
                    82,
                    indeterminate=True,
                )
                start = time.monotonic()
                connection.execute("VACUUM;")
                elapsed = time.monotonic() - start
                result.add("Vacuum", "ok", f"VACUUM abgeschlossen in {elapsed:.1f}s.")
                self._emit("vacuum", f"VACUUM abgeschlossen in {elapsed:.0f}s", 98)
            else:
                result.add("Vacuum", "skipped", "In der Konfiguration deaktiviert.")

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
