"""Startup-Diagnose und gezielte Reparatur fuer die Codex-Desktop-App.

Bewusst getrennt vom konservativen Wartungskern (`maintenance.py`):

* `maintenance.py` blockiert jede Wartung, sobald irgendein Codex-Prozess laeuft
  (Datensicherheit, siehe DECISIONS.md). Dieses Verhalten bleibt unangetastet.
* `health.py` adressiert das *Startproblem*: haengende (Zombie-)Prozesse und ein
  verwaistes Electron-Lockfile, die einen Neustart der App verhindern.

Sicherheitsgarantie: Reparatur beendet ausschliesslich Hauptprozesse OHNE Renderer
(totes Fenster). Eine aktive Codex-Sitzung (mit Renderer) wird niemals beendet.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .automation_control import find_automation_anomalies
from .config import MaintenanceConfig
from .processes import (
    ProcessProvider,
    find_codex_processes_by_executable,
    no_window_kwargs,
    process_type,
    tree_pids,
    windows_processes,
)

Severity = str  # "info" | "warn" | "critical"

# Killer beendet den gesamten Prozessbaum einer (Haupt-)PID und meldet (erfolg, text).
ProcessKiller = Callable[[int], "tuple[bool, str]"]


def _iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


@dataclass(slots=True)
class HealthIssue:
    code: str
    severity: Severity
    message: str
    fixable: bool = False


@dataclass(slots=True)
class HealthReport:
    status: Severity
    checked_at: str
    database_path: str
    lockfile_path: str
    main_pids: list[int] = field(default_factory=list)
    zombie_main_pids: list[int] = field(default_factory=list)
    renderer_present: bool = False
    stale_lockfile: bool = False
    wal_mb: float = 0.0
    db_mb: float = 0.0
    disk_free_gb: float = 0.0
    badstate_files: list[str] = field(default_factory=list)
    codex_exe_present: bool = True
    update_leftovers: list[str] = field(default_factory=list)
    nested_automations: list[str] = field(default_factory=list)
    duplicate_automation_ids: list[str] = field(default_factory=list)
    issues: list[HealthIssue] = field(default_factory=list)

    def add(self, code: str, severity: Severity, message: str, *, fixable: bool = False) -> None:
        self.issues.append(HealthIssue(code, severity, message, fixable))

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_text(self) -> str:
        lines = [
            f"Status: {self.status}",
            f"Geprueft: {self.checked_at}",
            f"Datenbank: {self.database_path}",
            f"DB-Groesse: {self.db_mb:.1f} MB; WAL: {self.wal_mb:.1f} MB; "
            f"frei: {self.disk_free_gb:.1f} GB",
            f"Codex-Hauptprozesse: {self.main_pids or 'keine'}; Renderer aktiv: {self.renderer_present}",
        ]
        if self.zombie_main_pids:
            lines.append(f"Zombie-Hauptprozesse (ohne Renderer): {self.zombie_main_pids}")
        if self.stale_lockfile:
            lines.append(f"Verwaistes Lockfile: {self.lockfile_path}")
        if self.badstate_files:
            lines.append(f".badstate-Dateien: {', '.join(self.badstate_files)}")
        lines.append(f"Codex-Installation intakt (Codex.exe vorhanden): {self.codex_exe_present}")
        if self.update_leftovers:
            lines.append(f"Update-Reste: {', '.join(self.update_leftovers)}")
        if self.nested_automations:
            lines.append(f"Verschachtelte Automationen: {', '.join(self.nested_automations)}")
        if self.duplicate_automation_ids:
            lines.append(f"Doppelte Automations-IDs: {', '.join(self.duplicate_automation_ids)}")
        lines.append("Befunde:")
        if self.issues:
            for issue in self.issues:
                flag = " [behebbar]" if issue.fixable else ""
                lines.append(f"  - [{issue.severity}] {issue.code}: {issue.message}{flag}")
        else:
            lines.append("  - keine")
        return "\n".join(lines)


def _file_mb(path: Path) -> float:
    try:
        return path.stat().st_size / (1024 * 1024)
    except OSError:
        return 0.0


def _age_seconds(created_at: str, now: datetime) -> float:
    if not created_at:
        return float("inf")  # unbekanntes Alter -> als "alt genug" behandeln
    try:
        return (now - datetime.fromisoformat(created_at)).total_seconds()
    except ValueError:
        return float("inf")


def _severity_rank(severity: Severity) -> int:
    return {"info": 0, "ok": 0, "warn": 1, "critical": 2}.get(severity, 0)


# Marker, die ein hängendes/abgebrochenes Update hinterlassen kann. Bewusst eng und nur
# auf Codex-eigene Pfade (Install + Profil) angewandt -- NICHT auf das geteilte SquirrelTemp.
_UPDATE_LEFTOVER_GLOBS = ("*.dead", "pending", "__update__", "*.nupkg", "Update.exe.new", "*.asar.tmp")


def _find_update_leftovers(config: MaintenanceConfig) -> list[str]:
    found: list[str] = []
    for base in (config.install_dir_path, config.user_data_path):
        for pattern in _UPDATE_LEFTOVER_GLOBS:
            try:
                found.extend(str(path) for path in base.glob(pattern))
            except OSError:
                continue
    return sorted(set(found))


def diagnose(
    config: MaintenanceConfig,
    provider: ProcessProvider | None = None,
    *,
    now: datetime | None = None,
) -> HealthReport:
    """Read-only Startup-Diagnose. Veraendert nichts."""
    provider = provider or windows_processes
    now = now or datetime.now()
    all_processes = provider()

    codex = find_codex_processes_by_executable(config, lambda: all_processes)
    by_pid = {p.pid: p for p in codex}
    mains = [p for p in codex if process_type(p) == "main"]
    renderer_present = any(process_type(p) == "renderer" for p in codex)

    zombie_main_pids: list[int] = []
    for main in mains:
        subtree = tree_pids(main.pid, all_processes)
        has_renderer = any(
            pid in by_pid and process_type(by_pid[pid]) == "renderer" for pid in subtree
        )
        old_enough = _age_seconds(main.created_at, now) >= config.zombie_min_age_seconds
        if not has_renderer and old_enough:
            zombie_main_pids.append(main.pid)

    db_path = config.db_path
    wal_mb = _file_mb(Path(str(db_path) + "-wal"))
    db_mb = _file_mb(db_path)
    lockfile = config.lockfile_path
    stale_lockfile = lockfile.exists() and not mains

    try:
        disk_free_gb = shutil.disk_usage(db_path.anchor or db_path.parent).free / (1024**3)
    except OSError:
        disk_free_gb = 0.0

    badstate_files: list[str] = []
    with contextlib.suppress(OSError):
        badstate_files = sorted(p.name for p in config.codex_home.glob("*.badstate"))

    # Update-Health: ein fehlgeschlagenes Auto-Update kann die Codex.exe entfernen
    # oder Update-Reste hinterlassen, die den Start blockieren ("Aktualisierungen").
    codex_exe_present = Path(config.codex_executable).exists()
    update_leftovers = _find_update_leftovers(config)

    # Automations-Anomalien: verwaiste/verschachtelte Ordner und id-Duplikate, die ein
    # rekursiver Scan in der Codex-App doppelt zaehlt. Read-only, separat von load_automations.
    anomalies = find_automation_anomalies(config)
    nested_automations = [str(item.path) for item in anomalies.nested]
    duplicate_automation_ids = [item.id for item in anomalies.duplicate_ids]

    report = HealthReport(
        status="ok",
        checked_at=_iso_now(),
        database_path=str(db_path),
        lockfile_path=str(lockfile),
        main_pids=sorted(p.pid for p in mains),
        zombie_main_pids=sorted(zombie_main_pids),
        renderer_present=renderer_present,
        stale_lockfile=stale_lockfile,
        wal_mb=round(wal_mb, 1),
        db_mb=round(db_mb, 1),
        disk_free_gb=round(disk_free_gb, 1),
        badstate_files=badstate_files,
        codex_exe_present=codex_exe_present,
        update_leftovers=update_leftovers,
        nested_automations=nested_automations,
        duplicate_automation_ids=duplicate_automation_ids,
    )

    if zombie_main_pids:
        report.add(
            "zombie-prozess",
            "critical",
            "Codex-Hauptprozess ohne Renderer erkannt (haengt/Fenster tot) und blockiert den Neustart.",
            fixable=True,
        )
    if stale_lockfile:
        report.add(
            "verwaistes-lockfile",
            "critical",
            "Electron-Lockfile vorhanden, aber kein Codex-Hauptprozess laeuft.",
            fixable=True,
        )
    if not db_path.exists():
        report.add("db-fehlt", "warn", f"Logdatenbank nicht gefunden: {db_path}")
    if wal_mb >= config.wal_warn_mb:
        report.add(
            "wal-aufblaehung",
            "warn",
            f"WAL-Datei ist {wal_mb:.1f} MB gross (Schwelle {config.wal_warn_mb} MB); "
            "WAL-Checkpoint via Wartung empfohlen.",
        )
    if db_mb >= config.db_warn_mb:
        report.add(
            "db-aufblaehung",
            "warn",
            f"Logdatenbank ist {db_mb:.1f} MB gross (Schwelle {config.db_warn_mb} MB); "
            "VACUUM via Wartung empfohlen.",
        )
    if disk_free_gb < config.disk_min_gb:
        report.add(
            "wenig-speicher",
            "warn",
            f"Nur {disk_free_gb:.1f} GB frei (Schwelle {config.disk_min_gb} GB).",
        )
    if badstate_files:
        report.add(
            "badstate",
            "warn",
            f"{len(badstate_files)} .badstate-Datei(en) gefunden (frueherer Korruptionsfall).",
        )
    store_installed = bool(getattr(config, "codex_store_aumid", "") or "")
    if not codex_exe_present and not store_installed:
        report.add(
            "codex-exe-fehlt",
            "critical",
            f"Codex.exe nicht gefunden: {config.codex_executable}. "
            "Mögliche Ursache: fehlgeschlagenes/abgebrochenes Update. Neuinstallation empfohlen.",
        )
    if update_leftovers:
        report.add(
            "update-reste",
            "warn",
            f"{len(update_leftovers)} Update-Rest/-Marker im Installations-/Profilpfad gefunden "
            "(evtl. hängengebliebenes Update).",
        )
    if anomalies.nested:
        paths = ", ".join(str(item.path) for item in anomalies.nested)
        report.add(
            "verschachtelte-automation",
            "warn",
            f"{len(anomalies.nested)} verschachtelte(r) Automations-Ordner (Tiefe > 1) in "
            f"~/.codex/automations gefunden: {paths}. Ein rekursiver Scan zählt diese doppelt; "
            "verwaisten/verschachtelten Automations-Ordner aus ~/.codex/automations herausnehmen "
            "(z. B. nach ~/.codex/_orphan-automations-quarantine verschieben).",
        )
    if anomalies.duplicate_ids:
        details = "; ".join(
            f"{item.id} ({', '.join(str(path) for path in item.paths)})"
            for item in anomalies.duplicate_ids
        )
        report.add(
            "automation-id-duplikat",
            "warn",
            f"{len(anomalies.duplicate_ids)} doppelte Automations-ID(s) in "
            f"~/.codex/automations gefunden: {details}. Die Codex-App zählt die Automation "
            "dadurch doppelt; den überzähligen/verwaisten Automations-Ordner aus "
            "~/.codex/automations herausnehmen.",
        )

    report.status = "ok"
    for issue in report.issues:
        if _severity_rank(issue.severity) > _severity_rank(report.status):
            report.status = issue.severity
    return report


def default_tree_killer(pid: int) -> tuple[bool, str]:
    """Beendet den gesamten Prozessbaum einer PID per taskkill /T /F."""
    completed = subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **no_window_kwargs(),
    )
    output = (completed.stdout or "").strip() or (completed.stderr or "").strip()
    return completed.returncode == 0, output


@dataclass(slots=True)
class RepairStep:
    name: str
    status: str
    message: str


@dataclass(slots=True)
class RepairResult:
    status: str
    dry_run: bool
    started_at: str
    ended_at: str
    trigger: str = "manual"
    steps: list[RepairStep] = field(default_factory=list)
    report: dict[str, object] | None = None

    def add(self, name: str, status: str, message: str) -> None:
        self.steps.append(RepairStep(name, status, message))

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_text(self) -> str:
        lines = [f"Status: {self.status}", f"Dry-Run: {self.dry_run}", "Schritte:"]
        for step in self.steps:
            lines.append(f"  - [{step.status}] {step.name}: {step.message}")
        return "\n".join(lines)


def repair_start(
    config: MaintenanceConfig,
    provider: ProcessProvider | None = None,
    killer: ProcessKiller | None = None,
    *,
    execute: bool = False,
    trigger: str = "manual",
    write_log: bool = False,
) -> RepairResult:
    """Behebt Startblockaden: Zombie-Hauptprozesse beenden + verwaistes Lockfile entfernen.

    Ohne ``execute`` nur Dry-Run (kein Kill, keine Loeschung). Es werden ausschliesslich
    Hauptprozesse ohne Renderer beendet -- aktive Sitzungen bleiben unangetastet.
    """
    killer = killer or default_tree_killer
    started = _iso_now()
    report = diagnose(config, provider)
    result = RepairResult(
        status="dry-run" if not execute else "ok",
        dry_run=not execute,
        started_at=started,
        ended_at=started,
        trigger=trigger,
        report=report.to_dict(),
    )

    did_something = False
    had_failure = False

    # 1) Zombie-Hauptprozesse beenden.
    if report.zombie_main_pids:
        for pid in report.zombie_main_pids:
            if not execute:
                result.add("Zombie beenden", "planned", f"PID {pid} wuerde beendet (Prozessbaum).")
            elif not config.allow_repair_zombies:
                result.add("Zombie beenden", "blocked", f"PID {pid}: durch Konfiguration deaktiviert.")
            else:
                ok, message = killer(pid)
                did_something = True
                if ok:
                    result.add("Zombie beenden", "ok", f"PID {pid} beendet. {message}".strip())
                else:
                    had_failure = True
                    result.add("Zombie beenden", "failed", f"PID {pid}: {message}")
    else:
        result.add("Zombie-Pruefung", "ok", "Keine Zombie-Hauptprozesse erkannt.")

    # 2) Verwaistes Lockfile entfernen.
    # Nach dem Zombie-Kill kann das Lockfile nun verwaist sein, auch wenn der Snapshot
    # es noch nicht als stale markiert hatte (weil damals mains existierten).
    # Sicher: nur entfernen wenn ALLE mains Zombies waren UND alle Kills erfolgreich
    # (eine aktive Sitzung mit Renderer wird nie gestört).
    lockfile = Path(report.lockfile_path)
    no_live_mains = set(report.main_pids) <= set(report.zombie_main_pids)
    lockfile_stale = report.stale_lockfile or (
        execute and did_something and not had_failure and no_live_mains and lockfile.exists()
    )
    if lockfile_stale:
        if not execute:
            result.add("Lockfile", "planned", f"{report.lockfile_path} wuerde entfernt.")
        elif not config.allow_clear_lockfile:
            result.add("Lockfile", "blocked", "Entfernen durch Konfiguration deaktiviert.")
        else:
            try:
                lockfile.unlink()
                did_something = True
                result.add("Lockfile", "ok", f"Verwaistes Lockfile entfernt: {report.lockfile_path}")
            except FileNotFoundError:
                result.add("Lockfile", "ok", "Lockfile bereits entfernt.")
            except OSError as exc:
                had_failure = True
                result.add("Lockfile", "failed", f"Konnte Lockfile nicht entfernen: {exc}")
    else:
        result.add("Lockfile-Pruefung", "ok", "Kein verwaistes Lockfile erkannt.")

    if not execute:
        result.status = "dry-run"
    elif had_failure:
        result.status = "failed"
    elif did_something:
        result.status = "repaired"
    else:
        result.status = "nothing-to-do"

    result.ended_at = _iso_now()
    if execute and write_log:
        _write_repair_log(config, result)
    return result


def _write_repair_log(config: MaintenanceConfig, result: RepairResult) -> Path:
    logs_path = config.logs_path
    logs_path.mkdir(parents=True, exist_ok=True)
    base = logs_path / f"repair-{_timestamp()}"
    base.with_suffix(".json").write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    base.with_suffix(".txt").write_text(result.to_text() + "\n", encoding="utf-8")
    return base.with_suffix(".json")
