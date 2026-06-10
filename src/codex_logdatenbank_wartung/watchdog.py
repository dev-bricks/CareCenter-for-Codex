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

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Literal

from .config import MaintenanceConfig
from .health import RepairResult, diagnose, repair_start
from .processes import ProcessProvider, find_companion_orphans

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

    import subprocess

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
        companion_reaped = _reap_companion_orphans(config, execute=execute, provider=provider, killer=killer)
        msg = "Codex aktiv (Renderer vorhanden) -- Waechter haelt sich raus."
        if companion_reaped:
            msg += f" {companion_reaped} Companion-Orphan(s) bereinigt."
        result = WatchdogTickResult("codex_active", msg)
        result.companion_orphans_reaped = companion_reaped
        return result

    zombie_pids = list(getattr(report, "zombie_main_pids", []) or [])
    stale_lockfile = bool(getattr(report, "stale_lockfile", False))

    if not zombie_pids and not stale_lockfile:
        companion_reaped = _reap_companion_orphans(config, execute=execute, provider=provider, killer=killer)
        msg = "Codex zu, keine haengenden Reste."
        if companion_reaped:
            msg += f" {companion_reaped} Companion-Orphan(s) bereinigt."
        result = WatchdogTickResult("idle", msg)
        result.companion_orphans_reaped = companion_reaped
        return result

    if not config.watcher_enabled:
        companion_reaped = _reap_companion_orphans(config, execute=execute, provider=provider, killer=killer)
        msg = "Haengende Reste erkannt, aber der Waechter ist deaktiviert (watcher_enabled=False)."
        if companion_reaped:
            msg += f" {companion_reaped} Companion-Orphan(s) bereinigt."
        result = WatchdogTickResult(
            "disabled",
            msg,
            zombie_pids=zombie_pids,
            stale_lockfile=stale_lockfile,
        )
        result.companion_orphans_reaped = companion_reaped
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
            return WatchdogTickResult(
                "busy",
                "Haengende Reste erkannt, aber der Codex-Baum arbeitet aktiv (CPU) -- kein "
                "Eingriff, um keinen Hintergrundlauf abzubrechen ('kein Renderer' != idle).",
                zombie_pids=zombie_pids,
                stale_lockfile=stale_lockfile,
            )

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

    companion_reaped = _reap_companion_orphans(config, execute=execute, provider=provider, killer=killer)

    return WatchdogTickResult(
        "reaped",
        message,
        zombie_pids=zombie_pids,
        stale_lockfile=stale_lockfile,
        repair_status=repair_result.status,
        relaunched=relaunched,
        companion_orphans_reaped=companion_reaped,
    )
