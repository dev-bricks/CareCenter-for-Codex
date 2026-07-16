"""Hintergrund-Waechter fuer die Start-Praevention der Codex-Desktop-App.

Warum gerade der Start-Fehler? Er ist der **erste Dominostein**: Codex startet nicht
(ein haengender Ghost-Hauptprozess ohne Renderer haelt den Singleton-Lock) -> der User
fordert eine Store-Reparatur/-Aktualisierung an -> das Store-Update haengt -> die
AppX-Engine verklemmt -> das Paket verwaist. Wird der Ghost frueh und automatisch
entfernt, entsteht die ganze Eskalation gar nicht erst. Hoechste Hebelwirkung an der Wurzel.

Sicherheitsgarantien (alle aus `health.diagnose`/`repair_start` geerbt, hier NICHT dupliziert):
* Ziele werden ueber den **exakten** Codex-Exe-Pfad bestimmt (`find_codex_processes_by_executable`)
  -- die node-basierte **npm-CLI `codex`** wird nie erfasst (User-Regel: CLI muss ueberleben).
* Es werden NUR Hauptprozesse **ohne Renderer** und **aelter als** `zombie_min_age_seconds`
  beendet -> eine aktive Sitzung (Renderer da) und ein **frischer Start** (zu jung) bleiben
  unangetastet.
* Read-only Beobachtung zuerst; gekillt wird nur im Reap-Zweig (bei geschlossenem Codex).

Dieses Modul ist bewusst Qt-frei und voll testbar; die Tray-Anbindung (periodischer Tick in
einem Worker-Thread + Benachrichtigung) liegt in `tray.py`.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Literal

from .config import (
    DEFAULT_RUNTIME_MCP_DUPLICATE_MIN_AGE_SECONDS,
    MaintenanceConfig,
)
from .health import RepairResult, diagnose, repair_start
from .processes import (
    ProcessInfo,
    ProcessProvider,
    find_companion_orphans,
    find_runtime_mcp_duplicate_roots,
    tree_pids,
    windows_processes,
)

WatchdogAction = Literal["codex_active", "idle", "disabled", "busy", "failed", "reaped"]


@dataclass(slots=True)
class WatchdogTickResult:
    """Ergebnis genau eines Waechter-Ticks."""

    action: WatchdogAction
    message: str
    zombie_pids: list[int] = field(default_factory=list)
    stale_lockfile: bool = False
    repair_status: str | None = None  # Status der repair_start-RepairResult, falls gereapt
    relaunched: bool = False
    companion_orphans_reaped: int = 0
    runtime_mcp_roots_reaped: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _reap_companion_orphans(
    config: MaintenanceConfig,
    *,
    execute: bool = True,
    provider: ProcessProvider | None = None,
    killer: Callable[[int], tuple[bool, str]] | None = None,
) -> int:
    """Bereinigt verwaiste Companion-app-server-Prozesse (codex-plugin-cc #277).

    Laeuft unabhaengig vom Desktop-Zustand — Companion-Orphans koennen auch bei
    aktivem Desktop existieren. Gibt die Anzahl erfolgreich beendeter Prozesse zurueck.
    """
    if not getattr(config, "reap_companion_orphans", True):
        return 0

    min_age = getattr(config, "companion_orphan_min_age_seconds", 300)
    orphans = find_companion_orphans(provider=provider, min_age_seconds=min_age)
    if not orphans:
        return 0

    if not execute:
        return len(orphans)

    from .processes import no_window_kwargs

    reaped = 0
    for orphan in orphans:
        if killer:
            ok, _ = killer(orphan.pid)
            if ok:
                reaped += 1
        else:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(orphan.pid)],
                    check=True,
                    capture_output=True,
                    **no_window_kwargs(),
                )
                reaped += 1
            except (subprocess.CalledProcessError, OSError):
                pass
    return reaped


def reap_runtime_mcp_duplicates(
    config: MaintenanceConfig,
    *,
    execute: bool = True,
    provider: ProcessProvider | None = None,
    activity_provider: ProcessProvider | None = None,
    killer: Callable[[int], tuple[bool, str]] | None = None,
) -> int:
    """Entferne alte, sicher wiederholte MCP-Launcher samt Prozessbaum.

    Die Erkennung in ``processes`` schuetzt den neuesten Runtime-Cohort, den
    Desktop-App-Server selbst, fremde Kindprozesse und alle CLI-app-server.
    Default-seitig wird jeder gefundene direkte Launcher mit ``taskkill /T``
    beendet, damit npx-/cmd-Nachfahren nicht als neue Orphans zurueckbleiben.
    """
    if not getattr(config, "reap_runtime_mcp_duplicates", True):
        return 0

    resolved_provider = provider or windows_processes
    initial_processes = resolved_provider()
    roots = find_runtime_mcp_duplicate_roots(
        provider=lambda: initial_processes,
        min_age_seconds=getattr(
            config,
            "runtime_mcp_duplicate_min_age_seconds",
            DEFAULT_RUNTIME_MCP_DUPLICATE_MIN_AGE_SECONDS,
        ),
        generation_gap_seconds=getattr(
            config, "runtime_mcp_generation_gap_seconds", 90
        ),
        batch_window_seconds=getattr(
            config, "runtime_mcp_batch_window_seconds", 30
        ),
        minimum_matching_mcp_roots=getattr(
            config, "runtime_mcp_min_matching_roots", 2
        ),
    )
    if not roots or not execute:
        return len(roots)

    # Noch arbeitende alte Baeume bleiben unangetastet. Das zweite Snapshot-
    # Fenster laeuft nur, wenn es ueberhaupt sichere Duplikat-Kandidaten gibt.
    # Ein fehlgeschlagener zweiter Snapshot ist fail-closed: dann wird nichts beendet.
    sample_seconds = max(
        0.0,
        float(getattr(config, "runtime_mcp_activity_sample_seconds", 1.0)),
    )
    if killer is None and sample_seconds > 0:
        time.sleep(sample_seconds)
        later_processes = (activity_provider or resolved_provider)()
        if not later_processes:
            return 0
        before_ticks = {process.pid: process.cpu_ticks for process in initial_processes}
        later_ticks = {process.pid: process.cpu_ticks for process in later_processes}
        idle_roots = []
        for root in roots:
            if root.pid not in later_ticks:
                continue
            members = tree_pids(root.pid, initial_processes) | tree_pids(
                root.pid, later_processes
            )
            before_total = sum(before_ticks.get(pid, 0) for pid in members)
            later_total = sum(later_ticks.get(pid, 0) for pid in members)
            if later_total <= before_total:
                idle_roots.append(root)
        roots = idle_roots
        if not roots:
            return 0

    from .processes import no_window_kwargs

    if killer:
        reaped = 0
        for root in roots:
            ok, _ = killer(root.pid)
            if ok:
                reaped += 1
        return reaped

    def kill_tree(root: ProcessInfo) -> int:
        try:
            completed = subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(root.pid)],
                check=False,
                capture_output=True,
                timeout=15,
                **no_window_kwargs(),
            )
            return int(completed.returncode == 0)
        except (OSError, subprocess.TimeoutExpired):
            return 0

    # Alle Roots sind direkte, voneinander unabhaengige Kinder des App-Servers.
    # Eine kleine Worker-Grenze verhindert, dass ein grosser Erstfund den Tray
    # minutenlang blockiert, ohne Windows mit hunderten taskkill-Prozessen zu fluten.
    workers = min(8, len(roots))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return sum(pool.map(kill_tree, roots))


def _reap_runtime_residue(
    config: MaintenanceConfig,
    *,
    execute: bool,
    provider: ProcessProvider | None,
    killer: Callable[[int], tuple[bool, str]] | None,
) -> tuple[int, int]:
    """Teile eine Prozessaufnahme zwischen beiden Runtime-Reapern."""
    if not (
        getattr(config, "reap_companion_orphans", True)
        or getattr(config, "reap_runtime_mcp_duplicates", True)
    ):
        return 0, 0

    cache: list[ProcessInfo] | None = None

    def cached_provider():
        nonlocal cache
        if cache is None:
            cache = (provider or windows_processes)()
        return cache

    companion = _reap_companion_orphans(
        config,
        execute=execute,
        provider=cached_provider,
        killer=killer,
    )
    runtime_mcp = reap_runtime_mcp_duplicates(
        config,
        execute=execute,
        provider=cached_provider,
        activity_provider=provider or windows_processes,
        killer=killer,
    )
    return companion, runtime_mcp


def _reap_message(companion: int, runtime_mcp: int) -> str:
    parts: list[str] = []
    if companion:
        parts.append(f"{companion} Companion-Orphan(s) bereinigt")
    if runtime_mcp:
        parts.append(f"{runtime_mcp} alte Runtime-MCP-Prozessbäume bereinigt")
    return (" " + "; ".join(parts) + ".") if parts else ""


def run_watchdog_tick(
    config: MaintenanceConfig,
    *,
    execute: bool = True,
    provider: ProcessProvider | None = None,
    killer: Callable[[int], tuple[bool, str]] | None = None,
    relauncher: Callable[[], object] | None = None,
    diagnose_fn: Callable[..., object] | None = None,
    repair_fn: Callable[..., RepairResult] | None = None,
    activity_fn: Callable[..., object] | None = None,
) -> WatchdogTickResult:
    """Fuehre einen einzelnen Waechter-Tick aus.

    Ablauf (read-only zuerst, mutierend nur im Reap-Zweig):
      1. Codex aktiv (Renderer da)?           -> nichts tun ('codex_active').
      2. Keine haengenden Reste?              -> nichts tun ('idle').
      3. Waechter deaktiviert?                -> nur melden, nicht killen ('disabled').
      4. AKTIVITAETS-GATE: arbeitet der Codex-Baum (CPU), obwohl kein Fenster da ist?
         -> NICHT killen ('busy'). "Kein Renderer != idle": Codex fuehrt nach dem
         Schliessen Hintergrund-Automationen weiter (empirisch belegt 29.05). Ein
         echter haengender Ghost ist ~0 % CPU -- genau das, was wir killen wollen.
      5. sonst: Reste vorhanden, Codex zu UND idle -> ``repair_start`` (Ghost-Kill +
         Lockfile), optional Neustart ('reaped'). Nur ``repair_status=='repaired'``
         gilt als echtes Aufraeumen (sonst Race/Fehlschlag -> 'idle'/'failed').

    ``execute=False`` macht den Reap-Zweig zum Dry-Run (kein echter Kill, kein Aktivitaets-
    Gate noetig) -- nuetzlich fuer einen sicheren Selbsttest.
    """
    diagnose_fn = diagnose_fn or diagnose
    repair_fn = repair_fn or repair_start

    report = diagnose_fn(config, provider)

    if getattr(report, "renderer_present", False):
        companion_reaped, runtime_mcp_reaped = _reap_runtime_residue(
            config, execute=execute, provider=provider, killer=killer
        )
        msg = "Codex aktiv (Renderer vorhanden) -- Waechter haelt sich raus."
        msg += _reap_message(companion_reaped, runtime_mcp_reaped)
        result = WatchdogTickResult("codex_active", msg)
        result.companion_orphans_reaped = companion_reaped
        result.runtime_mcp_roots_reaped = runtime_mcp_reaped
        return result

    zombie_pids = list(getattr(report, "zombie_main_pids", []) or [])
    stale_lockfile = bool(getattr(report, "stale_lockfile", False))

    if not zombie_pids and not stale_lockfile:
        companion_reaped, runtime_mcp_reaped = _reap_runtime_residue(
            config, execute=execute, provider=provider, killer=killer
        )
        msg = "Codex zu, keine haengenden Reste."
        msg += _reap_message(companion_reaped, runtime_mcp_reaped)
        result = WatchdogTickResult("idle", msg)
        result.companion_orphans_reaped = companion_reaped
        result.runtime_mcp_roots_reaped = runtime_mcp_reaped
        return result

    if not config.watcher_enabled:
        companion_reaped, runtime_mcp_reaped = _reap_runtime_residue(
            config, execute=execute, provider=provider, killer=killer
        )
        msg = "Haengende Reste erkannt, aber der Waechter ist deaktiviert (watcher_enabled=False)."
        msg += _reap_message(companion_reaped, runtime_mcp_reaped)
        result = WatchdogTickResult(
            "disabled",
            msg,
            zombie_pids=zombie_pids,
            stale_lockfile=stale_lockfile,
        )
        result.companion_orphans_reaped = companion_reaped
        result.runtime_mcp_roots_reaped = runtime_mcp_reaped
        return result

    # Aktivitaets-Gate: nur fuer den Ghost-Kill relevant (ein reines verwaistes Lockfile hat
    # keinen laufenden Baum). Beim echten Kill (execute) messen wir die CPU des Codex-Baums;
    # arbeitet er, halten wir uns raus, um keinen Hintergrundlauf abzubrechen.
    if execute and zombie_pids:
        resolved_activity_fn: Callable[..., object]
        if activity_fn is None:
            from .orchestrator import observe_activity

            resolved_activity_fn = observe_activity
        else:
            resolved_activity_fn = activity_fn
        try:
            activity = resolved_activity_fn(config)
            busy = bool(getattr(activity, "active", False))
        except Exception:  # noqa: BLE001 -- im Zweifel NICHT killen (konservativ)
            busy = True
        if busy:
            companion_reaped, runtime_mcp_reaped = _reap_runtime_residue(
                config, execute=execute, provider=provider, killer=killer
            )
            msg = (
                "Haengende Reste erkannt, aber der Codex-Baum arbeitet aktiv (CPU) -- kein "
                "Eingriff, um keinen Hintergrundlauf abzubrechen ('kein Renderer' != idle)."
            )
            msg += _reap_message(companion_reaped, runtime_mcp_reaped)
            result = WatchdogTickResult(
                "busy",
                msg,
                zombie_pids=zombie_pids,
                stale_lockfile=stale_lockfile,
            )
            result.companion_orphans_reaped = companion_reaped
            result.runtime_mcp_roots_reaped = runtime_mcp_reaped
            return result

    # Reap: genau der getestete, sichere S1-Schritt (nur Ghosts ohne Renderer + verwaistes Lockfile).
    repair_result = repair_fn(
        config, provider, killer, execute=execute, trigger="watchdog", write_log=execute
    )

    # Nur echtes Aufraeumen gilt als 'reaped' (sonst Falschmeldung + Zaehler-Spam alle 60 s).
    if execute and repair_result.status != "repaired":
        action: WatchdogAction = "idle" if repair_result.status == "nothing-to-do" else "failed"
        return WatchdogTickResult(
            action,
            f"Kein Reap durchgefuehrt (Status: {repair_result.status}).",
            zombie_pids=zombie_pids,
            stale_lockfile=stale_lockfile,
            repair_status=repair_result.status,
        )

    relaunched = False
    if (
        execute
        and repair_result.status == "repaired"
        and getattr(config, "watcher_relaunch_after_reap", False)
        and relauncher is not None
    ):
        try:
            relauncher()
            relaunched = True
        except Exception:  # noqa: BLE001 -- ein fehlgeschlagener Neustart darf den Tick nicht kippen
            relaunched = False

    parts: list[str] = []
    if zombie_pids:
        parts.append(f"{len(zombie_pids)} haengende(n) Codex-Rest(e) entfernt")
    if stale_lockfile:
        parts.append("verwaistes Lockfile entfernt")
    detail = " und ".join(parts) if parts else "aufgeraeumt"
    suffix = " Codex neu gestartet." if relaunched else " Du kannst Codex jetzt sauber starten."
    message = f"{detail}.{suffix}"

    companion_reaped, runtime_mcp_reaped = _reap_runtime_residue(
        config, execute=execute, provider=provider, killer=killer
    )

    return WatchdogTickResult(
        "reaped",
        message,
        zombie_pids=zombie_pids,
        stale_lockfile=stale_lockfile,
        repair_status=repair_result.status,
        relaunched=relaunched,
        companion_orphans_reaped=companion_reaped,
        runtime_mcp_roots_reaped=runtime_mcp_reaped,
    )
