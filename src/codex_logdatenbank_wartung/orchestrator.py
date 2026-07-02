"""Autonome Wartung mit zwei Modi (Safe/Fast) und aktivitaetsbasierter Codex-Steuerung.

Empirisch belegt (2026-05-29):
* Das Schliessen der Codex-Desktop-App bricht laufende Automatisierungen ab
  (kein Output, kein memory.md-Update) -- closing == data loss fuer den Lauf.
* Verlaesslich erkennbar ist Aktivitaet ueber die **CPU-Last des gesamten Codex-
  Prozessbaums** (inkl. Worker-Kindern wie python/git/node) plus DB-Schreibzugriffe.
  Aktive Automatisierung: 25-500 % eines Kerns; Leerlauf-Rest: <2 %.

Daher:
* **Safe-Modus:** Wartung wird *eingereiht*. Es wird gewartet, bis der Codex-Baum
  wirklich im Leerlauf ist (CPU unter Schwelle UND DB ruhig). Erst dann wird Codex
  kontrolliert vollstaendig beendet, gewartet und danach (optional) neu gestartet.
  Nie ein Eingriff, solange etwas laeuft.
* **Fast-Modus:** sofort -- Codex beenden und Wartung ohne Warten (fuer tote Ghosts
  oder bewusstes Sofort-Aufraeumen).

Die Kernfunktion ist mit injizierbaren Bausteinen testbar (kein echtes Kill/Sleep
im Test).
"""

from __future__ import annotations

import subprocess
import time as _time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta
from typing import Literal

from .config import MaintenanceConfig
from .i18n import t
from .maintenance import MaintenanceResult, MaintenanceRunner, ProgressUpdate
from .processes import (
    ProcessProvider,
    matches_codex_executable,
    no_window_kwargs,
    process_type,
    tree_pids,
    windows_processes,
)

Mode = Literal["safe", "fast"]

# Bausteine (injizierbar fuer Tests)
ObserveFn = Callable[[], "CodexActivity"]
Killer = Callable[[int], "tuple[bool, str]"]
Closer = Callable[[int], "tuple[bool, str]"]
Launcher = Callable[[], "tuple[bool, str]"]
MaintainFn = Callable[[], MaintenanceResult]
Sleeper = Callable[[float], None]
Clock = Callable[[], datetime]
ProgressFn = Callable[["AutoProgress"], None]
CancelFn = Callable[[], bool]
LOOP_CLOSE_RETRY_REASONS = frozenset({"codex-not-closed", "codex-active-after-close"})


@dataclass(slots=True)
class AutoProgress:
    phase: str
    message: str
    percent: int
    indeterminate: bool = False


@dataclass(slots=True)
class CodexActivity:
    present: bool
    active: bool
    cpu_percent: float = 0.0
    db_quiet_seconds: float = 0.0
    renderer_present: bool = False
    main_pids: list[int] = field(default_factory=list)
    tree_pids: list[int] = field(default_factory=list)


@dataclass(slots=True)
class AutoStep:
    name: str
    status: str
    message: str


@dataclass(slots=True)
class AutoMaintainResult:
    status: str
    mode: Mode
    dry_run: bool
    block_reason: str = ""
    waited: bool = False
    closed_codex: bool = False
    restarted_codex: bool = False
    steps: list[AutoStep] = field(default_factory=list)
    maintenance: dict[str, object] | None = None

    def add(self, name: str, status: str, message: str) -> None:
        self.steps.append(AutoStep(name, status, message))

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_text(self) -> str:
        lines = [
            f"Status: {self.status}",
            f"Modus: {self.mode}",
            f"Dry-Run: {self.dry_run}",
            f"Blockgrund: {self.block_reason or '-'}",
            f"Gewartet: {self.waited}; Codex beendet: {self.closed_codex}; "
            f"Codex neu gestartet: {self.restarted_codex}",
            "Schritte:",
        ]
        for step in self.steps:
            lines.append(f"  - [{step.status}] {step.name}: {step.message}")
        if self.maintenance:
            lines.append(f"Wartung: {self.maintenance.get('status')}")
        return "\n".join(lines)


@dataclass(slots=True)
class FastLoopCycleResult:
    """Ein kompletter Loop-Zyklus: Fast-Wartung, Automationen takten, Codex neu starten."""

    status: str
    dry_run: bool
    interval_hours: int = 0
    codex_present_at_start: bool = False
    closed_codex: bool = False
    restarted_codex: bool = False
    safe_fallback_used: bool = False
    loop_counter_reset_allowed: bool = False
    maintenance_attempts: int = 0
    close_retry_count: int = 0
    paused_automations: int = 0
    restored_automations: int = 0
    maintenance: dict[str, object] | None = None
    steps: list[AutoStep] = field(default_factory=list)

    def add(self, name: str, status: str, message: str) -> None:
        self.steps.append(AutoStep(name, status, message))

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_text(self) -> str:
        lines = [
            f"Status: {self.status}",
            f"Dry-Run: {self.dry_run}",
            f"Intervall: {self.interval_hours}h",
            f"Codex beim Start erkannt: {self.codex_present_at_start}",
            f"Codex beendet: {self.closed_codex}; Codex neu gestartet: {self.restarted_codex}",
            f"Safe-Fallback genutzt: {self.safe_fallback_used}; "
            f"Erfolg+Restart setzt Loop-Zaehler neu: {self.loop_counter_reset_allowed}",
            f"Wartungsversuche: {self.maintenance_attempts}; Close-Retries: {self.close_retry_count}",
            f"Automatisierungen pausiert: {self.paused_automations}; "
            f"wieder aktiviert: {self.restored_automations}",
            "Schritte:",
        ]
        for step in self.steps:
            lines.append(f"  - [{step.status}] {step.name}: {step.message}")
        if self.maintenance:
            lines.append(f"Wartung: {self.maintenance.get('status')}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Aktivitaetsmessung (Default-Implementierung)
# ---------------------------------------------------------------------------

def _db_quiet_seconds(config: MaintenanceConfig, *, now: datetime | None = None) -> float:
    now = now or datetime.now()
    newest: float | None = None
    db = config.db_path
    for path in (db, db.with_name(db.name + "-wal"), db.with_name(db.name + "-shm")):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        newest = mtime if newest is None else max(newest, mtime)
    if newest is None:
        return float("inf")
    return max(0.0, now.timestamp() - newest)


def _codex_tree(config: MaintenanceConfig, processes: list) -> tuple[set[int], list, list]:
    codex = [p for p in processes if matches_codex_executable(p, config)]
    mains = [p for p in codex if process_type(p) == "main"]
    pids: set[int] = {p.pid for p in codex}
    for proc in codex:
        pids |= tree_pids(proc.pid, processes)
    return pids, mains, codex


def observe_activity(
    config: MaintenanceConfig,
    *,
    provider: ProcessProvider | None = None,
    sleeper: Sleeper = _time.sleep,
    db_quiet_fn: Callable[[], float] | None = None,
) -> CodexActivity:
    """Miss die Aktivitaet des gesamten Codex-Prozessbaums (CPU + DB-Ruhe)."""
    provider = provider or windows_processes
    db_quiet_fn = db_quiet_fn or (lambda: _db_quiet_seconds(config))

    snap0 = provider()
    pids0, _mains0, codex0 = _codex_tree(config, snap0)
    if not codex0:
        return CodexActivity(present=False, active=False, db_quiet_seconds=db_quiet_fn())

    ticks0 = sum(p.cpu_ticks for p in snap0 if p.pid in pids0)
    sleeper(config.activity_sample_seconds)
    snap1 = provider()
    pids1, mains1, codex1 = _codex_tree(config, snap1)
    pids_all = pids0 | pids1
    ticks1 = sum(p.cpu_ticks for p in snap1 if p.pid in pids_all)

    interval = max(0.5, config.activity_sample_seconds)
    cpu_percent = max(0.0, (ticks1 - ticks0)) / 1e7 / interval * 100.0
    quiet = db_quiet_fn()
    renderer = any(process_type(p) == "renderer" for p in codex1)
    present = bool(codex1)
    active = present and (cpu_percent > config.idle_cpu_percent or quiet < config.idle_quiet_seconds)
    return CodexActivity(
        present=present,
        active=active,
        cpu_percent=round(cpu_percent, 1),
        db_quiet_seconds=round(quiet, 1) if quiet != float("inf") else quiet,
        renderer_present=renderer,
        main_pids=sorted(m.pid for m in mains1),
        tree_pids=sorted(pids1),
    )


def default_graceful_closer(pid: int) -> tuple[bool, str]:
    """Sanftes Schliessen: taskkill /T OHNE /F (sendet WM_CLOSE an Fenster)."""
    completed = subprocess.run(
        ["taskkill", "/PID", str(pid), "/T"],
        check=False, capture_output=True, text=True, encoding="utf-8", errors="replace",
        **no_window_kwargs(),
    )
    out = (completed.stdout or "").strip() or (completed.stderr or "").strip()
    return completed.returncode == 0, out


def default_launcher(config: MaintenanceConfig) -> Callable[[], tuple[bool, str]]:
    def _launch() -> tuple[bool, str]:
        aumid = getattr(config, "codex_store_aumid", "") or ""
        try:
            if aumid:
                # Store-App ueber stabile AppID starten (ueberlebt Versions-Updates).
                subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{aumid}"], **no_window_kwargs())
                return True, f"Store-App gestartet: {aumid}"
            subprocess.Popen([config.codex_executable], **no_window_kwargs())
            return True, f"gestartet: {config.codex_executable}"
        except OSError as exc:
            return False, str(exc)
    return _launch


# ---------------------------------------------------------------------------
# Orchestrierung
# ---------------------------------------------------------------------------

def auto_maintain(
    config: MaintenanceConfig,
    *,
    mode: Mode = "safe",
    execute: bool = False,
    allow_close: bool | None = None,
    observe_fn: ObserveFn | None = None,
    killer: Killer | None = None,
    graceful_closer: Closer | None = None,
    launcher: Launcher | None = None,
    maintain_fn: MaintainFn | None = None,
    sleeper: Sleeper = _time.sleep,
    clock: Clock = datetime.now,
    progress: ProgressFn | None = None,
    cancel_requested: CancelFn | None = None,
) -> AutoMaintainResult:
    from .health import default_tree_killer

    observe_fn = observe_fn or (lambda: observe_activity(config, sleeper=sleeper))
    killer = killer or default_tree_killer
    graceful_closer = graceful_closer or default_graceful_closer
    launcher = launcher or default_launcher(config)
    maintain_fn = maintain_fn or _default_maintain_fn(config, execute, progress)
    cancel_requested = cancel_requested or (lambda: False)
    # Schliessen ist nur erlaubt, wenn explizit gewuenscht (Tray-Klick / --close) oder
    # per Konfiguration freigegeben. Fast-Modus impliziert immer Berechtigung — er ist
    # per Definition ein "sofort beenden ohne Warten". Safe-Modus wartet erst auf Leerlauf
    # und blockiert dann, wenn keine Berechtigung vorliegt (kein Sofort-Abbruch).
    allow = config.auto_close_codex if allow_close is None else allow_close
    effective_allow = allow or (mode == "fast")

    def emit(phase: str, message: str, percent: int, indeterminate: bool = False) -> None:
        if progress is not None:
            progress(AutoProgress(phase, message, max(0, min(100, percent)), indeterminate))

    result = AutoMaintainResult(status="ok", mode=mode, dry_run=not execute)

    def cancel_result() -> AutoMaintainResult:
        result.status = "cancelled"
        result.add("Abbruch", "cancelled", t("auto_cancelled_step"))
        emit("cancelled", t("auto_cancelled_short"), 100)
        return result

    emit("assess", t("auto_assess"), 0, True)
    if cancel_requested():
        return cancel_result()
    act = observe_fn()

    if act.present:
        if mode == "safe":
            deadline = clock() + timedelta(seconds=config.idle_wait_timeout_seconds)
            while act.active:
                if cancel_requested():
                    return cancel_result()
                result.waited = True
                emit(
                    "wait",
                    t("auto_waiting_idle", cpu=act.cpu_percent),
                    5, True,
                )
                if clock() >= deadline:
                    result.status = "blocked"
                    result.block_reason = "idle-timeout"
                    result.add(
                        "Warten", "blocked",
                        t(
                            "auto_timeout_step",
                            seconds=config.idle_wait_timeout_seconds,
                            cpu=act.cpu_percent,
                        ),
                    )
                    emit("blocked", t("auto_timeout_short"), 100)
                    return result
                sleeper(config.activity_poll_seconds)
                if cancel_requested():
                    return cancel_result()
                act = observe_fn()
                if not act.present:
                    break
            result.add("Leerlauf", "ok", t("auto_idle_ok"))
        else:
            result.add("Modus", "ok", t("auto_fast_mode"))

    # Codex (falls noch da) kontrolliert vollstaendig beenden.
    if cancel_requested():
        return cancel_result()
    act = observe_fn()
    if act.present:
        if not effective_allow:
            result.status = "blocked"
            result.block_reason = "close-not-allowed"
            result.add(
                t("step_codex_running"), "blocked",
                t("auto_close_blocked"),
            )
            emit("blocked", t("auto_close_blocked_short"), 100)
            return result
        if not execute:
            result.add("Codex beenden", "planned", t("auto_close_planned", mode=mode))
        else:
            emit("close", t("auto_closing"), 10, True)
            for pid in act.main_pids:
                graceful_closer(pid)
            sleeper(config.activity_poll_seconds)
            leftover = observe_fn()
            if leftover.present:
                for pid in leftover.main_pids:
                    killer(pid)
                sleeper(2)
            result.closed_codex = True
            result.add("Codex beenden", "ok", t("auto_closed"))

    # Sicherheits-Check direkt vor der Wartung.
    if cancel_requested():
        return cancel_result()
    if execute:
        guard = observe_fn()
        if guard.present:
            if guard.active:
                result.status = "blocked"
                result.block_reason = "codex-active-after-close"
                result.add("Abbruch", "blocked", t("auto_abort_active"))
                emit("blocked", t("auto_abort_active_short"), 100)
                return result
            for pid in guard.main_pids:
                killer(pid)
            sleeper(2)
            if observe_fn().present:
                result.status = "blocked"
                result.block_reason = "codex-not-closed"
                result.add("Abbruch", "blocked", t("auto_abort_not_closed"))
                emit("blocked", t("auto_abort_not_closed_short"), 100)
                return result

    # Wartung ausfuehren.
    emit("maintain", t("auto_maintain_start"), 15)
    mres = maintain_fn()
    result.maintenance = mres.to_dict()
    result.status = "ok" if mres.status in {"ok", "dry-run"} else mres.status

    # Codex neu starten, falls WIR es beendet haben — und den Neustart VERIFIZIEREN
    # (ein blosser Popen-Erfolg kann einen frischen Ghost ohne Fenster sein).
    if result.closed_codex and config.restart_codex_after and execute:
        emit("restart", t("auto_restart"), 97, True)
        ok, msg = launcher()
        appeared = False
        if ok:
            tries = max(1, int(config.restart_verify_seconds / max(1, config.activity_poll_seconds)))
            for _ in range(tries):
                sleeper(config.activity_poll_seconds)
                check = observe_fn()
                if check.present and check.renderer_present:
                    appeared = True
                    break
        result.restarted_codex = appeared
        if appeared:
            result.add("Neustart", "ok", t("auto_restart_ok", message=msg).strip())
        else:
            result.add(
                "Neustart", "warn",
                t(
                    "auto_restart_warn",
                    seconds=config.restart_verify_seconds,
                    message=msg,
                ).strip(),
            )

    emit(result.status, t("done"), 100)
    return result


def fast_maintenance_loop_cycle(
    config: MaintenanceConfig,
    *,
    execute: bool = False,
    interval_hours: int | None = None,
    observe_fn: ObserveFn | None = None,
    killer: Killer | None = None,
    graceful_closer: Closer | None = None,
    launcher: Launcher | None = None,
    maintain_fn: MaintainFn | None = None,
    pause_fn: Callable[[], object] | None = None,
    restore_fn: Callable[[], object] | None = None,
    sleeper: Sleeper = _time.sleep,
    progress: ProgressFn | None = None,
    cancel_requested: CancelFn | None = None,
) -> FastLoopCycleResult:
    """Fuehre genau einen Loop-Zyklus aus.

    Der Zyklus nutzt absichtlich ``auto_maintain(..., mode="fast")`` ohne dessen
    eingebauten Restart. So bleibt die Reihenfolge kontrolliert:

    1. Fast-Wartung.
    2. Falls Fast-Close-Retries scheitern: Safe als verlaengerter Nachholversuch.
    3. Erst nach erfolgreicher Wartung: aktive Automatisierungen pausieren und merken.
    4. Codex neu starten, auch wenn Codex vor dem Zyklus nicht lief.
    5. Genau die von CareCenter pausierten Automatisierungen im 60-Sekunden-Takt
       wieder aktivieren.

    Safe ist kein Dauerzustand: Die Tray-Schicht kann den Nachholversuch per
    ``cancel_requested`` abbrechen, wenn das naechste regulaere Fast-Intervall
    faellig wird.
    """
    from .automation_control import (
        activate_carecenter_paused_automations,
        pause_active_automations,
    )
    from .health import default_tree_killer

    observe_fn = observe_fn or (lambda: observe_activity(config, sleeper=sleeper))
    killer = killer or default_tree_killer
    graceful_closer = graceful_closer or default_graceful_closer
    launcher = launcher or default_launcher(config)
    cancel_requested = cancel_requested or (lambda: False)
    hours = int(interval_hours if interval_hours is not None else config.fast_loop_interval_hours)
    result = FastLoopCycleResult(
        status="ok",
        dry_run=not execute,
        interval_hours=hours,
    )

    def emit(phase: str, message: str, percent: int, indeterminate: bool = False) -> None:
        if progress is not None:
            progress(AutoProgress(phase, message, max(0, min(100, percent)), indeterminate))

    emit("loop-assess", t("fast_loop_assess"), 0, True)
    first_activity = observe_fn()
    result.codex_present_at_start = first_activity.present
    first_observation_used = False

    def loop_observe() -> CodexActivity:
        nonlocal first_observation_used
        if not first_observation_used:
            first_observation_used = True
            return first_activity
        return observe_fn()

    loop_config = replace(config, restart_codex_after=False)
    retry_attempts = max(0, int(getattr(config, "fast_loop_close_retry_attempts", 3)))
    retry_delay = max(0, int(getattr(config, "fast_loop_close_retry_delay_seconds", 15)))
    max_attempts = retry_attempts + 1
    maintenance: AutoMaintainResult | None = None
    for attempt in range(1, max_attempts + 1):
        result.maintenance_attempts = attempt
        maintenance = auto_maintain(
            loop_config,
            mode="fast",
            execute=execute,
            allow_close=True,
            observe_fn=loop_observe,
            killer=killer,
            graceful_closer=graceful_closer,
            launcher=launcher,
            maintain_fn=maintain_fn,
            sleeper=sleeper,
            progress=progress,
            cancel_requested=cancel_requested,
        )
        if maintenance.status != "blocked" or maintenance.block_reason not in LOOP_CLOSE_RETRY_REASONS:
            break
        if attempt >= max_attempts:
            break
        result.close_retry_count += 1
        retry_message = t(
            "fast_loop_close_retry",
            attempt=attempt + 1,
            max_attempts=max_attempts,
            seconds=retry_delay,
        )
        result.add("Codex beenden Retry", "retry", retry_message)
        emit("loop-close-retry", retry_message, 68, True)
        sleeper(float(retry_delay))
    if maintenance is None:
        result.status = "failed"
        result.add("Fast-Wartung", "failed", "Kein Wartungsversuch ausgeführt.")
        emit(result.status, t("done"), 100)
        return result

    if (
        maintenance.status == "blocked"
        and maintenance.block_reason in LOOP_CLOSE_RETRY_REASONS
        and bool(getattr(config, "fast_loop_safe_fallback_enabled", True))
    ):
        result.safe_fallback_used = True
        message = t("fast_loop_safe_fallback")
        result.add("Safe-Fallback", "retry", message)
        emit("loop-safe-fallback", message, 69, True)
        maintenance = auto_maintain(
            loop_config,
            mode="safe",
            execute=execute,
            allow_close=True,
            observe_fn=observe_fn,
            killer=killer,
            graceful_closer=graceful_closer,
            launcher=launcher,
            maintain_fn=maintain_fn,
            sleeper=sleeper,
            progress=progress,
            cancel_requested=cancel_requested,
        )
        result.maintenance_attempts += 1

    result.maintenance = maintenance.to_dict()
    result.closed_codex = result.closed_codex or maintenance.closed_codex
    maintenance_label = "Safe-Wartung" if result.safe_fallback_used else "Fast-Wartung"
    result.add(
        maintenance_label,
        maintenance.status,
        f"Auto-Maintain abgeschlossen: {maintenance.status}",
    )
    if maintenance.status not in {"ok", "dry-run"}:
        result.status = maintenance.status
        emit(result.status, t("done"), 100)
        return result

    if not execute:
        result.status = "dry-run"
        result.add(
            "Automatisierungen",
            "planned",
            "Aktive Automatisierungen wuerden pausiert und im 60-Sekunden-Takt wieder aktiviert.",
        )
        result.add(
            "Neustart",
            "planned",
            "Codex wuerde nach der Wartung neu gestartet, auch wenn es vorher nicht lief.",
        )
        emit("dry-run", t("done"), 100)
        return result

    emit("loop-pause", t("fast_loop_pause"), 70, True)
    paused = pause_fn() if pause_fn is not None else pause_active_automations(config)
    pause_status = str(getattr(paused, "status", "ok"))
    result.paused_automations = int(getattr(paused, "changed_count", 0))
    result.add(
        "Automatisierungen pausieren",
        pause_status,
        f"{result.paused_automations} aktive Automatisierung(en) ausgeschaltet.",
    )

    emit("loop-restart", t("fast_loop_restart"), 78, True)
    ok, message = launcher()
    appeared = False
    if ok:
        tries = max(1, int(config.restart_verify_seconds / max(1, config.activity_poll_seconds)))
        for _ in range(tries):
            sleeper(config.activity_poll_seconds)
            check = observe_fn()
            if check.present and check.renderer_present:
                appeared = True
                break
    result.restarted_codex = appeared
    if appeared:
        result.add("Neustart", "ok", t("auto_restart_ok", message=message).strip())
    else:
        result.add(
            "Neustart",
            "warn",
            t("auto_restart_warn", seconds=config.restart_verify_seconds, message=message).strip(),
        )

    emit("loop-restore", t("fast_loop_restore"), 86, True)
    restored = restore_fn() if restore_fn is not None else activate_carecenter_paused_automations(
        config,
        staggered=True,
        delay_seconds=60,
        sleeper=sleeper,
    )
    restore_status = str(getattr(restored, "status", "ok"))
    result.restored_automations = int(getattr(restored, "changed_count", 0))
    result.add(
        "Automatisierungen aktivieren",
        restore_status,
        f"{result.restored_automations} zuvor aktive Automatisierung(en) gestaffelt aktiviert.",
    )

    statuses = {pause_status, restore_status}
    if "failed" in statuses:
        result.status = "failed"
    elif "partial" in statuses or not result.restarted_codex:
        result.status = "partial"
    else:
        result.status = "ok"
    result.loop_counter_reset_allowed = result.status == "ok" and result.restarted_codex
    emit(result.status, t("done"), 100)
    return result


def _default_maintain_fn(
    config: MaintenanceConfig, execute: bool, progress: ProgressFn | None
) -> MaintainFn:
    def _run() -> MaintenanceResult:
        cb = None
        if progress is not None:
            def cb(update: ProgressUpdate) -> None:
                # Wartungs-Fortschritt (0..100) in den Bereich 15..96 mappen.
                mapped = 15 + int(update.percent * 0.81)
                progress(AutoProgress("maintain", update.message, mapped, update.indeterminate))
        runner = MaintenanceRunner(config, progress_callback=cb)
        return runner.run(dry_run=not execute, trigger="auto-maintain")
    return _run
