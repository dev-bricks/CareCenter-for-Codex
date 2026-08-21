"""Hintergrund-Worker für die PySide6-Systemtray-App (CareCenter for Codex).

Enthält alle 12 Worker-Klassen zur asynchronen Ausführung blockierender Aufgaben
in separaten QThreads gemäß APP-RUNTIME-STANDARD 5c.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import cast

from PySide6.QtCore import QObject, QTimer, Signal

from .automation_control import AutomationAction
from .config import MaintenanceConfig
from .health import diagnose, repair_start
from .i18n import t
from .orchestrator import (
    Mode,
    auto_maintain,
    fast_maintenance_loop_cycle,
)
from .store_repair import repair_store_codex
from .watchdog import run_watchdog_tick

__all__ = [
    "AutoMaintainWorker",
    "AutomationControlWorker",
    "ConfigAuditWorker",
    "DiagnosisWorker",
    "FastLoopWorker",
    "FullRepairWorker",
    "NormalStartWorker",
    "RepairWorker",
    "SafeStartInstallWorker",
    "StartRepairWorker",
    "StoreRepairWorker",
    "WatchdogWorker",
]

class AutoMaintainWorker(QObject):
    progress = Signal(object)  # AutoProgress
    finished = Signal(object)  # AutoMaintainResult

    def __init__(self, config: MaintenanceConfig, mode: Mode) -> None:
        super().__init__()
        self.config = config
        self.mode = mode
        self._cancel_requested = Event()

    def request_cancel(self) -> None:
        self._cancel_requested.set()

    def _sleep(self, seconds: float) -> None:
        self._cancel_requested.wait(max(0.0, seconds))

    def run(self) -> None:
        result = auto_maintain(
            self.config,
            mode=self.mode,
            execute=True,
            sleeper=self._sleep,
            allow_close=True,  # expliziter Tray-Klick = Zustimmung zum Schließen
            progress=lambda update: self.progress.emit(update),
            cancel_requested=self._cancel_requested.is_set,
        )
        self.finished.emit(result)


class FastLoopWorker(QObject):
    progress = Signal(object)  # AutoProgress
    finished = Signal(object)  # FastLoopCycleResult

    def __init__(self, config: MaintenanceConfig, interval_hours: int) -> None:
        super().__init__()
        self.config = config
        self.interval_hours = interval_hours
        self._cancel_requested = Event()

    def request_cancel(self) -> None:
        self._cancel_requested.set()

    def _sleep(self, seconds: float) -> None:
        self._cancel_requested.wait(max(0.0, seconds))

    def run(self) -> None:
        result = fast_maintenance_loop_cycle(
            self.config,
            execute=True,
            interval_hours=self.interval_hours,
            sleeper=self._sleep,
            progress=lambda update: self.progress.emit(update),
            cancel_requested=self._cancel_requested.is_set,
        )
        self.finished.emit(result)


class RepairWorker(QObject):
    finished = Signal(object)

    def __init__(self, config: MaintenanceConfig) -> None:
        super().__init__()
        self.config = config

    def run(self) -> None:
        result = repair_start(self.config, execute=True, trigger="tray", write_log=True)
        self.finished.emit(result)


class StoreRepairWorker(QObject):
    finished = Signal(object)

    def run(self) -> None:
        # Sichere, nicht-destruktive Kombi: Store-Cache leeren + Paket neu registrieren.
        repair_store_codex(level="wsreset", execute=True)
        result = repair_store_codex(level="repair", execute=True)
        self.finished.emit(result)


class SafeStartInstallWorker(QObject):
    finished = Signal(object)

    def run(self) -> None:
        from .safe_start_integration import install_safe_start_package

        self.finished.emit(install_safe_start_package())


class AutomationControlWorker(QObject):
    progress = Signal(object)
    finished = Signal(object)

    def __init__(self, config: MaintenanceConfig, action: AutomationAction) -> None:
        super().__init__()
        self.config = config
        self.action = action

    def run(self) -> None:

        from .automation_control import run_automation_action

        def on_progress(current: int, total: int, automation_id: str) -> None:
            self.progress.emit(
                {"current": current, "total": total, "automation_id": automation_id}
            )

        result = run_automation_action(
            self.config,
            self.action,
            sleeper=time.sleep,
            progress=on_progress,
            stagger_delay_seconds=max(
                0, int(getattr(self.config, "automation_stagger_delay_seconds", 60))
            ),
        )
        self.finished.emit(result)


class FullRepairWorker(QObject):
    """Volle Reparatur direkt im Prozess — keine Elevation nötig."""

    progress = Signal(str)
    finished = Signal(object)

    def __init__(self, config_path: Path) -> None:
        super().__init__()
        self.config_path = config_path

    def run(self) -> None:
        from .repair_live import run_live_repair

        try:
            config = MaintenanceConfig.load(self.config_path)
        except Exception as exc:  # noqa: BLE001
            self.progress.emit(f"[failed] Config: {exc}")
            self.finished.emit(None)
            return

        from .repair_workflow import RepairStepResult

        def on_step(step: object) -> None:
            step_result = cast(RepairStepResult, step)
            self.progress.emit(
                f"[{step_result.status}] {step_result.name}: {step_result.message}"
            )

        try:
            outcome = run_live_repair(config, execute=True, progress=on_step)
            self.finished.emit(outcome.to_dict())
        except Exception as exc:  # noqa: BLE001
            self.progress.emit(f"[failed] Reparatur: {exc}")
            self.finished.emit(None)


class WatchdogWorker(QObject):
    """Hintergrund-Waechter: tickt periodisch und reapt bei geschlossenem Codex Start-Reste.

    Laeuft in einem eigenen QThread (eigener Event-Loop -> der interne QTimer feuert dort,
    nicht im GUI-Thread). Jeder Tick liest die Config frisch (Toggles greifen sofort) und ist
    rundum fehlertolerant -- ein Tick darf den Waechter nie crashen. Gekillt wird ausschliesslich
    ueber den getesteten ``run_watchdog_tick``/``repair_start`` (nur Ghosts ohne Renderer, nie die
    npm-CLI, nie eine aktive Sitzung).
    """

    reaped = Signal(object)  # WatchdogTickResult.to_dict(), nur wenn wirklich aufgeraeumt wurde
    audit_finding = Signal(str)  # Tray-Benachrichtigung bei notify-Modus (entprellt)

    def __init__(self, config_path: Path, is_busy: Callable[[], bool]) -> None:
        super().__init__()
        self.config_path = config_path
        self._is_busy = is_busy
        self._timer: QTimer | None = None
        self._stopped = False
        self._last_audit_hash: str = ""  # Dedup: nur bei neuem Befund melden

    def start(self) -> None:
        try:
            config = MaintenanceConfig.load(self.config_path)
            interval = max(15, int(getattr(config, "watcher_interval_seconds", 60)))
        except Exception:
            interval = 60
        self._timer = QTimer()
        self._timer.setInterval(interval * 1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def request_stop(self) -> None:
        # Nur ein Flag setzen (thread-safe); den QTimer NICHT cross-thread anfassen.
        self._stopped = True

    def _tick(self) -> None:
        if self._stopped:
            return
        try:
            if self._is_busy():
                return  # nicht waehrend einer manuellen Wartung/Reparatur eingreifen
            config = MaintenanceConfig.load(self.config_path)
            if not config.watcher_enabled:
                return  # global aus -> still (kein diagnose-Aufruf, schont CPU)
            from .safe_start_integration import should_defer_for_safe_start
            if should_defer_for_safe_start(config):
                return  # Safe Start staffelt gerade Freigaben; keine zusaetzliche Gegenaktion.
            result = run_watchdog_tick(config, execute=True)
        except Exception:  # noqa: BLE001 -- ein Tick darf den Waechter nie crashen
            return
        self._audit(config, result)
        if (
            result.action == "reaped"
            or result.companion_orphans_reaped
            or result.runtime_mcp_roots_reaped
        ):
            self.reaped.emit(result.to_dict())
        self._run_thread_hygiene(config)
        self._run_config_audit(config)

    def _run_thread_hygiene(self, config: MaintenanceConfig) -> None:
        """Wendet konfigurierte Altersregeln an, sobald Codex geschlossen ist."""
        try:
            if config.auto_archive_threads_days <= 0 and config.auto_mark_threads_read_days <= 0:
                return
            from .thread_hygiene import run_configured_thread_hygiene

            run_configured_thread_hygiene(config)
        except Exception:  # noqa: BLE001 -- Hintergrundpflege darf den Watchdog nie kippen
            return

    def _audit(self, config: MaintenanceConfig, result: object) -> None:
        """Lueckenloser Nachweis JEDES Ticks (auch 'nichts getan') in logs/watchdog.log.

        So ist nie unklar, ob der Waechter Codex angefasst hat: jeder Tick hinterlaesst
        eine Zeile mit Aktion, Ziel-PIDs und Reap-Status -- unabhaengig davon, ob etwas
        beendet wurde. Fehler beim Schreiben duerfen den Waechter nie kippen.
        """

        try:
            logs = config.logs_path
            logs.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            action = getattr(result, "action", "?")
            zombies = getattr(result, "zombie_pids", [])
            stale = getattr(result, "stale_lockfile", False)
            status = getattr(result, "repair_status", None)
            companion = getattr(result, "companion_orphans_reaped", 0)
            runtime_mcp = getattr(result, "runtime_mcp_roots_reaped", 0)
            line = (
                f"{stamp}  action={action}  zombies={zombies}  "
                f"lockfile={stale}  reap_status={status}  companion_reaped={companion}  "
                f"runtime_mcp_reaped={runtime_mcp}\n"
            )
            with (logs / "watchdog.log").open("a", encoding="utf-8") as handle:
                handle.write(line)
        except Exception:  # noqa: BLE001 -- Audit-Schreibfehler darf den Tick nie crashen
            pass

    def _run_config_audit(self, config: MaintenanceConfig) -> None:
        """Config-Audit im Watchdog-Tick via run_audit_cycle (reine Funktion)."""
        from .config_audit import run_audit_cycle
        from .health import diagnose

        try:
            if (
                config.audit_duplicate_mcp == "off"
                and config.audit_unused_plugins == "off"
                and config.audit_empty_threads == "off"
            ):
                return

            renderer_present = True
            if (
                config.audit_duplicate_mcp == "auto"
                or config.audit_unused_plugins == "auto"
                or config.audit_empty_threads == "auto"
            ):
                report = diagnose(config)
                renderer_present = report.renderer_present

            cycle = run_audit_cycle(config, self._last_audit_hash, renderer_present)
            self._last_audit_hash = cycle.new_hash
            if cycle.notification:
                self.audit_finding.emit(cycle.notification)
        except Exception:  # noqa: BLE001
            pass


class StartRepairWorker(QObject):
    """Leichte Stufe der zusammengefassten Codex-Reparatur -- OHNE UAC.

    Klassifiziert die Lage (Renderer da? Codex ueberhaupt installiert? haengende Reste?)
    und behandelt die billigen Faelle selbst: haengende Reste entfernen (`repair_start`,
    nicht-elevated taskkill), Codex starten, auf Renderer warten. Reicht das nicht und ist
    Codex installiert, signalisiert sie ``escalate`` -> der Controller startet die volle
    Reparatur (``run_full_repair``, ebenfalls OHNE UAC). Ist gar kein Codex installiert,
    signalisiert sie ``needs_store_reinstall``.
    """

    progress = Signal(str)
    finished = Signal(object)  # dict: {outcome, reaped, message}

    def __init__(self, config: MaintenanceConfig) -> None:
        super().__init__()
        self.config = config

    def run(self) -> None:

        from .orchestrator import default_launcher
        from .processes import find_codex_processes_by_executable, process_type
        from .start_repair import classify_start_state, codex_installed_for_user

        config = self.config
        try:
            report = diagnose(config)
        except Exception as exc:  # noqa: BLE001 -- Diagnose darf den Lauf nicht crashen
            self.finished.emit({"outcome": "escalate", "reaped": 0, "message": f"Diagnose: {exc}"})
            return

        installed = codex_installed_for_user(config)
        decision = classify_start_state(
            renderer_present=report.renderer_present,
            codex_installed=installed,
            zombie_pids=list(report.zombie_main_pids),
            stale_lockfile=report.stale_lockfile,
        )

        if decision == "already_running":
            self.finished.emit({"outcome": "already_running", "reaped": 0, "message": t("codex_already_running")})
            return
        if decision == "needs_store_reinstall":
            self.finished.emit({
                "outcome": "needs_store_reinstall", "reaped": 0,
                "message": t("store_reinstall_needed"),
            })
            return

        reaped = 0
        if decision == "reap":
            self.progress.emit(t("repair_light_reap"))
            try:
                result = repair_start(config, execute=True, trigger="tray-start", write_log=True)
                reaped = sum(
                    1 for step in result.steps
                    if step.name.startswith("Zombie beenden") and step.status == "ok"
                )
            except Exception as exc:  # noqa: BLE001
                self.finished.emit({"outcome": "escalate", "reaped": 0, "message": f"Reap: {exc}"})
                return

            self.progress.emit(t("repair_launch_wait"))
            with contextlib.suppress(Exception):  # noqa: BLE001 -- Startfehler eskalieren bei der naechsten Pruefung
                default_launcher(config)()

            deadline = time.monotonic() + max(10.0, float(config.renderer_timeout_seconds) / 4.0)
            appeared = False
            while time.monotonic() < deadline:
                try:
                    procs = find_codex_processes_by_executable(config)
                    if any(process_type(p) == "renderer" for p in procs):
                        appeared = True
                        break
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(2.0)

            if appeared:
                self.finished.emit({
                    "outcome": "ok", "reaped": reaped,
                    "message": t("repair_light_ok"),
                })
                return
            self.finished.emit({
                "outcome": "escalate", "reaped": reaped,
                "message": t("repair_light_escalate"),
            })
            return

        # decision == "needs_escalation": installiert, aber Start scheitert ohne offensichtliche Reste.
        self.finished.emit({"outcome": "escalate", "reaped": 0, "message": t("repair_full_needed")})


class NormalStartWorker(QObject):
    """Startet die Store-App und bestaetigt einen echten Renderer im Prozessbaum."""

    finished = Signal(object)

    def __init__(self, config: MaintenanceConfig) -> None:
        super().__init__()
        self.config = config

    def run(self) -> None:

        from .orchestrator import default_launcher
        from .processes import find_codex_processes_by_executable, process_type
        from .start_repair import codex_installation_status_for_user

        ok, message = default_launcher(self.config)()
        if not ok:
            self.finished.emit({"ok": False, "message": message})
            return

        deadline = time.monotonic() + max(10.0, float(self.config.renderer_timeout_seconds))
        inventory_error = ""
        while time.monotonic() < deadline:
            try:
                processes = find_codex_processes_by_executable(self.config)
                if any(process_type(process) == "renderer" for process in processes):
                    self.finished.emit({"ok": True, "message": message})
                    return
            except Exception as exc:  # noqa: BLE001 -- Fehler wird im Ergebnis datensparsam benannt.
                inventory_error = type(exc).__name__
            time.sleep(2.0)

        aumid = getattr(self.config, "codex_store_aumid", "") or "-"
        package_status = codex_installation_status_for_user(self.config)
        package_label = {
            "installed": "installiert",
            "missing": "nicht für den aktuellen Benutzer registriert",
            "unknown": "nicht ermittelbar",
        }[package_status]
        inventory_detail = (
            f" Prozessinventarfehler: {inventory_error}." if inventory_error else ""
        )
        self.finished.emit({
            "ok": False,
            "message": (
                "Kein ChatGPT/Codex-Renderer nach Start innerhalb des Zeitlimits erkannt "
                f"(AUMID: {aumid}). Paketstatus: {package_label}.{inventory_detail} "
                "Nächster sicherer Schritt: „Codex-Start prüfen (Diagnose)“ in CareCenter "
                "ausführen; diese Prüfung verändert keine Chat- oder Threaddaten."
            ),
        })


class DiagnosisWorker(QObject):
    """Diagnose im eigenen Thread.

    `diagnose()` ruft `subprocess.run` und braucht gemessen ueber 10 Sekunden —
    im GUI-Thread stand die Oberflaeche so lange still. Die Diagnose aendert
    nichts, sie liest nur; ein zweiter Lauf waehrend des ersten ist trotzdem
    unnoetig und wird in `show_diagnosis` abgefangen.
    """

    finished = Signal(object)

    def __init__(self, config: MaintenanceConfig) -> None:
        super().__init__()
        self.config = config

    def run(self) -> None:
        self.finished.emit(diagnose(self.config))


class ConfigAuditWorker(QObject):
    """Manueller Config-Audit im eigenen Thread.

    `diagnose()` ruft `subprocess.run` (health.py) und braucht gemessen ueber
    10 Sekunden; `run_manual_audit()` scannt danach die Konfigurationsdateien.
    Im GUI-Thread bedeutete das eine ebenso lange Totalblockade der Oberflaeche
    ("reagiert nicht"). Der Watchdog fuhr denselben Audit laengst im Worker
    (`WatchdogWorker._run_config_audit`) — nur der Knopf tat es synchron.
    """

    finished = Signal(object)

    def __init__(self, config: MaintenanceConfig) -> None:
        super().__init__()
        self.config = config

    def run(self) -> None:
        from .config_audit import run_manual_audit
        from .health import diagnose

        renderer_present = diagnose(self.config).renderer_present
        report, cycle = run_manual_audit(self.config, renderer_present=renderer_present)
        self.finished.emit((report, cycle))


