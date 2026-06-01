"""Voll ausschoepfende, aber hang-sichere Codex-Start-Reparatur-Engine.

Bewusst getrennt von der konservativen DB-Wartung (`maintenance.py`/`orchestrator.py`)
und der gezielten Startblockaden-Reparatur (`health.py`). Dieses Modul adressiert den
Fall "Codex (Store/Electron) startet nicht" als **automatische Eskalation durch alle
Stufen**, bis ein Renderer-Fenster erscheint.

Philosophie (siehe CODEX-AUTO-DEBUG-DESIGN.md, justiert 2026-05-29):
Die Gefahr ist NICHT das Reparieren an sich, sondern das **Haengen/Stapeln** von
AppX-Deployment-Operationen. Wird die Reparatur ausgeloest, wird sie **voll
ausgeschoepft** -- alle Stufen automatisch, auch die aggressiven (reset_package,
remove_staged_version, reinstall_package). Diese stehen aber bewusst SPAET in der
Reihenfolge (billig+sicher zuerst) und laufen timeboxed.

EINZIGE HARTE REGEL: HAENGEN VERMEIDEN.
* Jede Deploy-Op (complete_staged_update, remove_staged_version, reset_package,
  reinstall_package) laeuft ueber ``run_with_timeout(fn, deploy_timeout_seconds)``.
  Immer nur EINE Deploy-Op gleichzeitig.
* Reisst eine Deploy-Op den Timeout -> die AppX-Engine gilt als verklemmt -> SOFORT
  STOPP: ``status='blocked'``, ``recommend_reboot=True``, KEINE weitere Deploy-Op
  (das Stapeln von Reset->Register->Remove hat real die Engine verklemmt).
* Ein sauberer FEHLSCHLAG (Op endet mit Fehler, OHNE Timeout) ist KEIN Stopp ->
  weiter zur naechsten Stufe.

Erfolgskriterium je Stufe: nach jeder fixenden Stufe wird ``launch_codex()`` ausgeloest
und ``renderer_appears(renderer_timeout)`` geprueft. Erscheint ein Renderer -> sofort 'ok'.
(``renderer_appears`` wartet nur -- ohne vorheriges ``launch_codex`` erscheint nach einem
reinen Ghost-Kill nie ein Renderer; darum gehoeren beide zusammen.)

Es werden KEINE echten AppX-Operationen ausgefuehrt; alles laeuft ueber die injizierbaren
Bausteine in ``RepairDeps``. Nur deren Default-Implementierungen duerfen real sein --
``run_repair`` ruft ausschliesslich die Deps.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Callable, Literal, Protocol

from .config import MaintenanceConfig


# Status eines Einzelschrittes der Reparatur.
StepStatus = Literal["ok", "failed", "timeout", "skipped", "blocked"]
# Gesamtstatus der Reparatur.
OutcomeStatus = Literal["ok", "blocked", "failed"]
# Ergebnis von run_with_timeout: ('ok'|'timeout'|'failed', result).
TimeoutStatus = Literal["ok", "timeout", "failed"]

ProgressFn = Callable[["RepairStepResult"], None]


# ---------------------------------------------------------------------------
# Fehlerart-Signale der Deploy-Ops
#
# Die LIVE-Deploy-Callables (repair_live) klassifizieren das Ergebnis ihres
# *mutierenden* PowerShell-Befehls und werfen bei eindeutiger Fehlerart eine dieser
# Exceptions. Sie reisen durch ``_default_run_with_timeout`` (das jeden Fehler zu
# ('failed', exc) faengt) und werden in ``run_deploy`` per ``isinstance`` ausgewertet.
# So bleibt die Engine PowerShell-unwissend und trotzdem "intelligent" gegenueber der
# Fehlerart (User-Wunsch 2026-06-01: erkennt Fehlerart -> klar Admin -> Admin-Meldung,
# unklar -> ein Fallback).
# ---------------------------------------------------------------------------

class DeployTimeout(Exception):
    """Eine Deploy-Op riss den (PowerShell-)Timeout -> AppX-Engine gilt als verklemmt.

    Folge in der Engine: sofortiger Abbruch, ``status='blocked'``, ``recommend_reboot``.
    Ein Tree-Kill (repair_live) verhindert neue Orphan-Kinder, HEILT aber keine verklemmte
    AppX-Engine (die delegiert an den AppXSVC-Dienst) -- nur ein Reboot tut das.
    """


class AdminRequired(Exception):
    """Eine Deploy-Op scheiterte EINDEUTIG an fehlenden Admin-Rechten (Access Denied).

    Folge in der Engine: sofortiger Abbruch, ``status='failed'`` + ``needs_admin=True``.
    KEIN Fallback -- der wuerde aus demselben Grund scheitern (User-Logik 2026-06-01).
    Es wird NIE eine Selbst-Elevation (UAC) ausgeloest; stattdessen meldet der Aufrufer
    dem User: 'als Administrator neu starten'.
    """


class CodexState(Protocol):
    """Beobachteter Codex-Zustand (read-only Momentaufnahme).

    Als Protocol typisiert, damit ``RepairDeps.observe`` jeden Wert mit diesen
    Attributen liefern darf (die mitgelieferte ``RepairState`` erfuellt es).
    """

    codex_present: bool
    renderer_present: bool
    ghost_pids: list[int]
    stale_lockfile: bool
    clipsvc_running: bool
    staged_update: bool
    package_user_registered: bool
    codex_exe_present: bool
    # True NUR, wenn das Store-Paket nachweislich vollstaendig abwesend ist (erfolgreiche,
    # aber leere -AllUsers-Abfrage + kein WindowsApps-Ordner). Bewusst getrennt von
    # codex_exe_present (die Standalone-Exe kann da sein, das Store-Paket trotzdem weg).
    package_absent: bool


@dataclass(slots=True)
class RepairState:
    """Konkrete Standard-Implementierung des beobachteten Codex-Zustands.

    Auch als Fake in Tests nutzbar (alle Felder mit sicheren Defaults).
    """

    codex_present: bool = False
    renderer_present: bool = False
    ghost_pids: list[int] = field(default_factory=list)
    stale_lockfile: bool = False
    clipsvc_running: bool = True
    staged_update: bool = False
    package_user_registered: bool = True
    codex_exe_present: bool = True
    package_absent: bool = False


@dataclass(slots=True)
class RepairStepResult:
    """Ergebnis genau einer Eskalationsstufe."""

    name: str
    status: StepStatus
    message: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class RepairOutcome:
    """Gesamtergebnis der Reparatur-Eskalation."""

    status: OutcomeStatus
    steps: list[RepairStepResult] = field(default_factory=list)
    recommend_reboot: bool = False
    reached_window: bool = False
    # True, wenn das Store-Paket vollstaendig abwesend ist und die Reparatur deshalb
    # nichts registrieren/zuruecksetzen kann -> Neuinstallation aus dem Microsoft Store
    # noetig (ein Reboot hilft NICHT). Der Tray bietet daraufhin die Store-Reinstallation an.
    needs_store_reinstall: bool = False
    # True, wenn eine Deploy-Op EINDEUTIG an fehlenden Admin-Rechten scheiterte (Access Denied).
    # Die App elevatet sich NIE selbst (kaputter UAC-Pfad verklemmte frueher den Appinfo-Dienst);
    # stattdessen meldet der Tray: 'CareCenter braucht fuer die Reparatur Admin-Rechte -- starte
    # die App neu mit Admin-Rechten.' Ein Reboot hilft hier NICHT (recommend_reboot bleibt False).
    needs_admin: bool = False

    def add(self, name: str, status: StepStatus, message: str) -> RepairStepResult:
        step = RepairStepResult(name, status, message)
        self.steps.append(step)
        return step

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_text(self) -> str:
        lines = [
            f"Status: {self.status}",
            f"Codex-Fenster erreicht: {self.reached_window}",
            f"Reboot empfohlen: {self.recommend_reboot}",
        ]
        if self.needs_store_reinstall:
            lines.append("Store-Neuinstallation noetig: True (Paket abwesend -- Reboot hilft NICHT)")
        if self.needs_admin:
            lines.append("Admin-Rechte noetig: True (App als Administrator neu starten -- Reboot hilft NICHT)")
        lines.append("Schritte:")
        if self.steps:
            for step in self.steps:
                lines.append(f"  - [{step.status}] {step.name}: {step.message}")
        else:
            lines.append("  - keine")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Default-Bausteine
#
# Real, aber nur ueber RepairDeps-Defaults und nur durch run_repair aufgerufen.
# Die mutierenden Defaults sind bewusst sichere No-Ops: eine echte AppX-Reparatur
# entsteht erst, wenn der Aufrufer die mutierenden Callables mit realen
# Implementierungen belegt. So bleibt das Modul vollstaendig testbar, ohne je eine
# LIVE-AppX-Operation auszuloesen.
# ---------------------------------------------------------------------------

def _default_observe(config: MaintenanceConfig) -> Callable[[], RepairState]:
    """Default-Observer: leitet den Zustand aus der bestehenden Diagnose ab.

    Bewusst read-only. Die AppX-spezifischen Felder (clipsvc_running,
    package_user_registered) werden konservativ gefuellt; eine genauere Erhebung
    (Get-Service ClipSVC, PackageUserInformation) kann spaeter injiziert werden.
    """

    def observe() -> RepairState:
        # Lazy-Import, um Zyklen und unnoetige Prozesserhebung im Test zu vermeiden.
        from .health import diagnose

        report = diagnose(config)
        store_installed = bool(getattr(config, "codex_store_aumid", "") or "")
        return RepairState(
            codex_present=bool(report.main_pids),
            renderer_present=report.renderer_present,
            ghost_pids=list(report.zombie_main_pids),
            stale_lockfile=report.stale_lockfile,
            clipsvc_running=True,
            staged_update=bool(report.update_leftovers),
            package_user_registered=True,
            codex_exe_present=report.codex_exe_present or store_installed,
        )

    return observe


def _default_run_with_timeout(
    fn: Callable[[], object], seconds: float
) -> tuple[TimeoutStatus, object]:
    """Fuehre ``fn`` aus und brich nach ``seconds`` ab.

    Laeuft die Funktion in einem Daemon-Thread; bleibt sie nach Ablauf des Timeouts
    haengen, wird sie NICHT zurueckgeholt (der Thread bleibt verwaist, der Aufrufer
    erhaelt aber sofort 'timeout' und stoppt jede weitere Deploy-Op -- das ist genau
    die geforderte Hang-Vermeidung).
    """
    import threading

    box: dict[str, object] = {}

    def _worker() -> None:
        try:
            box["result"] = fn()
            box["status"] = "ok"
        except Exception as exc:  # noqa: BLE001 -- jeder Fehler = sauberer Fehlschlag
            box["error"] = exc
            box["status"] = "failed"

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        return "timeout", None
    if box.get("status") == "ok":
        return "ok", box.get("result")
    return "failed", box.get("error")


def _noop_bool(*_args: object, **_kwargs: object) -> bool:
    return False


def _noop(*_args: object, **_kwargs: object) -> None:
    return None


@dataclass(slots=True)
class RepairDeps:
    """Injizierbare Bausteine der Reparatur-Engine.

    Default-Werte sind absichtlich sichere No-Ops bzw. die read-only Diagnose --
    eine echte AppX-Reparatur entsteht erst, wenn der Aufrufer die mutierenden
    Callables mit realen Implementierungen belegt. So bleibt das Modul vollstaendig
    testbar, ohne je eine LIVE-AppX-Operation auszuloesen.
    """

    # --- Beobachtung -------------------------------------------------------
    observe: Callable[[], CodexState]

    # --- S1: sofort/sicher -------------------------------------------------
    kill_ghosts: Callable[[], object] = _noop
    clear_lockfile: Callable[[], object] = _noop
    # --- S2: ClipSVC -------------------------------------------------------
    ensure_clipsvc: Callable[[], object] = _noop
    # --- S3-S6: Deploy-Ops (NUR ueber run_with_timeout aufrufen!) ----------
    complete_staged_update: Callable[[], object] = _noop
    remove_staged_version: Callable[[], object] = _noop
    reset_package: Callable[[], object] = _noop
    reinstall_package: Callable[[], object] = _noop
    # --- Start + Erfolgskriterium ------------------------------------------
    launch_codex: Callable[[], object] = _noop
    renderer_appears: Callable[[float], bool] = _noop_bool
    # --- Infrastruktur -----------------------------------------------------
    run_with_timeout: Callable[
        [Callable[[], object], float], tuple[TimeoutStatus, object]
    ] = _default_run_with_timeout
    sleeper: Callable[[float], None] = _noop
    clock: Callable[[], datetime] = datetime.now

    @classmethod
    def with_defaults(cls, config: MaintenanceConfig) -> "RepairDeps":
        """Erzeuge Deps mit dem read-only Default-Observer (keine mutierenden Ops)."""
        return cls(observe=_default_observe(config))


def run_repair(
    config: MaintenanceConfig,
    deps: RepairDeps,
    *,
    execute: bool = True,
    dry_run: bool = False,
    progress: ProgressFn | None = None,
) -> RepairOutcome:
    """Begrenzte, hang-sichere Reparatur: 1 sanfter Kern-Versuch + maximal 1 Fallback.

    Bewusste UMKEHR der frueheren 'voll ausschoepfen S1-S7'-Philosophie (User 2026-06-01):
    KEINE endlose Eskalation mehr, die bei verklemmter AppX-Engine reihenweise haengende
    PowerShell-Deploy-Ops stapelte.

    Reihenfolge:
      S1  Ghosts beenden + verwaistes Lockfile entfernen   (sofort/sicher, KEIN Admin)
      S2  ClipSVC sicherstellen                            (best effort -- bricht NIE ab)
      S3  staged Update abschliessen (RegisterByFamilyName, sanft)  [Deploy-Op, timeboxed]
      FB  genau EIN Fallback = reset_package                        [Deploy-Op, timeboxed]
          -- nur wenn S3 sauber durchlief, aber Codex trotzdem nicht startet.

    Nach S1/S2/S3/FB wird ``launch_codex()`` ausgeloest und ``renderer_appears`` geprueft;
    bei Erfolg sofort ``status='ok'``.

    INTELLIGENTE Fehlerart-Behandlung pro Deploy-Op (siehe ``run_deploy``):
      * Timeout/Hang  -> AppX-Engine verklemmt -> ``status='blocked'``, ``recommend_reboot``,
                         sofortiger Abbruch (keine weitere Deploy-Op -- auch kein Fallback,
                         der wuerde genauso haengen).
      * Access Denied -> ``status='failed'`` + ``needs_admin`` -> sofortiger Abbruch, KEIN
                         Fallback (scheitert aus demselben Grund). Es wird NIE selbst elevated;
                         der Aufrufer meldet 'als Administrator neu starten'.
      * sauberer Fehlschlag / Op-ok-aber-kein-Renderer -> EIN Fallback (reset_package).
    Schlaegt auch der Fallback fehl (ohne Timeout/Admin) -> ``status='failed'``,
    ``recommend_reboot`` -> ehrlicher Abbruch.

    S4 (remove_staged_version, destruktiv) und S6 (reinstall_package) werden NICHT mehr
    automatisch durchlaufen -- genau diese stapelten frueher weitere Zombie-PowerShells.
    Die Deps bleiben fuer gezielte/manuelle Nutzung erhalten.

    Planungsmodus (``dry_run=True`` ODER ``execute=False``): jede Stufe wird nur
    aufgelistet, kein Dep ausser ``observe`` wird aufgerufen.
    """
    planning = dry_run or not execute
    outcome = RepairOutcome(status="failed")

    def record(name: str, status: StepStatus, message: str) -> RepairStepResult:
        step = outcome.add(name, status, message)
        if progress is not None:
            progress(step)
        return step

    renderer_timeout = float(config.renderer_timeout_seconds)
    deploy_timeout = float(config.deploy_timeout_seconds)

    # --- Schritt 0: Baseline -- laeuft Codex bereits mit Fenster? -----------
    # Vermeidet einen verschwendeten launch_codex/renderer-Wartelauf ueber einem
    # noch nicht beendeten Ghost (Design-Stufe 0).
    state = deps.observe()
    if state.renderer_present:
        record("Baseline", "ok", "Codex-Renderer bereits aktiv -- keine Reparatur noetig.")
        outcome.status = "ok"
        outcome.reached_window = True
        return outcome

    # --- Absentes Store-Paket: kein Deploy-Op kann etwas registrieren -------
    # Erfolgreiche, aber leere -AllUsers-Abfrage + kein WindowsApps-Ordner = Paket vollstaendig
    # weg. Die Eskalation waere sinnlos (nichts zu registrieren/zuruecksetzen) und teils
    # gefaehrlich (Remove/Reset ueber Nichts). Stattdessen ehrlicher Abbruch mit der EINZIG
    # korrekten Massnahme: Neuinstallation aus dem Microsoft Store. Gilt auch im Planungsmodus.
    # (Lektion 29./30.05: Eine fruehere Version no-oppte durch alle Stufen und empfahl
    # faelschlich einen Reboot -- der hier NICHT hilft.)
    if getattr(state, "package_absent", False):
        record(
            "Store-Paket",
            "failed",
            "Codex-Store-Paket vollstaendig abwesend (kein registriertes, gestagtes oder "
            "WindowsApps-Paket). Reparatur kann nichts registrieren -- Neuinstallation aus dem "
            "Microsoft Store noetig. Ein Reboot hilft hier NICHT.",
        )
        outcome.status = "failed"
        outcome.needs_store_reinstall = True
        outcome.recommend_reboot = False
        return outcome

    # --- Planungsmodus: nur auflisten, nichts ausfuehren --------------------
    if planning:
        return _plan_only(outcome, state, record)

    # Erfolgskriterium: Codex starten UND auf Renderer warten.
    # (Reines renderer_appears ohne launch_codex liefert nach S1/S2 nie 'ok'.)
    def launched_ok(stage: str) -> bool:
        deps.launch_codex()
        if deps.renderer_appears(renderer_timeout):
            record(stage, "ok", "Codex-Renderer erschienen -- Start erfolgreich.")
            outcome.status = "ok"
            outcome.reached_window = True
            return True
        return False

    # Eine Deploy-Op timeboxed ausfuehren UND die Fehlerart klassifizieren.
    # Rueckgabe (vom Aufrufer ausgewertet):
    #   "ok"          -> Op lief sauber durch -> Renderer pruefen, sonst Fallback erlaubt.
    #   "timeout"     -> Hang (aeusserer Thread-Timeout ODER DeployTimeout aus rc=124):
    #                    Engine verklemmt -> outcome.blocked + recommend_reboot -> SOFORT returnen.
    #   "needs_admin" -> AdminRequired (Access Denied): outcome.failed + needs_admin
    #                    -> SOFORT returnen, KEIN Fallback (scheitert aus demselben Grund).
    #   "failed"      -> sauberer, unklarer Fehlschlag -> Renderer pruefen, sonst Fallback erlaubt.
    def run_deploy(stage: str, fn: Callable[[], object]) -> str:
        status, result = deps.run_with_timeout(fn, deploy_timeout)
        # Hang: aeusserer Thread-Timeout ('timeout', None) ODER innerer PS-Timeout, der als
        # DeployTimeout-Instanz durch den ('failed', exc)-Kanal kam.
        if status == "timeout" or isinstance(result, DeployTimeout):
            record(
                stage,
                "timeout",
                f"Deploy-Op riss den Timeout ({deploy_timeout:.0f}s) -- AppX-Engine gilt als "
                "verklemmt. STOPP: keine weitere Deploy-Op, Reboot empfohlen.",
            )
            outcome.status = "blocked"
            outcome.recommend_reboot = True
            return "timeout"
        if isinstance(result, AdminRequired):
            record(
                stage,
                "failed",
                "Deploy-Op scheiterte an fehlenden Admin-Rechten (Zugriff verweigert). STOPP: "
                "kein Fallback -- App als Administrator neu starten.",
            )
            outcome.status = "failed"
            outcome.needs_admin = True
            return "needs_admin"
        if status == "ok":
            detail = f" {result}" if result else ""
            record(stage, "ok", f"Deploy-Op abgeschlossen.{detail}".rstrip())
            return "ok"
        record(stage, "failed", f"Deploy-Op fehlgeschlagen (kein Timeout): {result}")
        return "failed"

    # --- S1: Ghosts beenden + verwaistes Lockfile (sofort/sicher) -----------
    did_s1 = False
    if state.ghost_pids:
        deps.kill_ghosts()
        record("S1 Ghosts beenden", "ok", f"Ghost-Prozesse beendet: {state.ghost_pids}.")
        did_s1 = True
    if state.stale_lockfile:
        deps.clear_lockfile()
        record("S1 Lockfile", "ok", "Verwaistes Electron-Lockfile entfernt.")
        did_s1 = True
    if not did_s1:
        record("S1", "skipped", "Kein Ghost und kein verwaistes Lockfile.")
    if launched_ok("S1 Start-Check"):
        return outcome

    # --- S2: ClipSVC sicherstellen -----------------------------------------
    state = deps.observe()
    if not state.clipsvc_running:
        deps.ensure_clipsvc()
        record("S2 ClipSVC", "ok", "ClipSVC sichergestellt (Aktivierungsfehler 0x8000001A vermieden).")
        if launched_ok("S2 Start-Check"):
            return outcome
    else:
        record("S2 ClipSVC", "skipped", "ClipSVC laeuft bereits.")

    # --- S3: sanftes RegisterByFamilyName (Kern-Deploy, immer timeboxed) ----
    # RegisterByFamilyName registriert nur neu, setzt nichts zurueck -- die sanfte,
    # historisch korrekte Behebung des staged-Wedge. Bewusst UNGATED (auch ohne erkannten
    # staged-Wedge versucht): robust gegen einen mis-detektierenden Observer.
    s3 = run_deploy("S3 staged Update abschliessen", deps.complete_staged_update)
    if s3 in ("timeout", "needs_admin"):
        return outcome  # Engine verklemmt bzw. Admin noetig -> Abbruch (KEIN Fallback)
    if launched_ok("S3 Start-Check"):
        return outcome

    # --- Fallback: genau EINE andere Methode = reset_package [DEPLOY-OP] -----
    # Nur erreicht, wenn S3 sauber durchlief/fehlschlug (KEIN Timeout, KEIN Admin-Problem),
    # Codex aber trotzdem nicht startet. Reset-AppxPackage ist die 'andere Methode'
    # (setzt das Paket auf einen sauberen Zustand zurueck). Reisst sie den Timeout oder
    # scheitert sie an Admin -> Abbruch mit passender Meldung (kein weiterer Versuch).
    fb = run_deploy("Fallback reset_package", deps.reset_package)
    if fb in ("timeout", "needs_admin"):
        return outcome
    if launched_ok("Fallback Start-Check"):
        return outcome

    # --- Erschoepft (ohne Timeout/Admin): ehrlicher Abbruch, Reboot empfehlen --
    record(
        "Abschluss",
        "failed",
        "S3 (sanftes Re-Register) und Fallback (reset_package) erschoepft, Codex-Renderer "
        "erschien nicht. Reboot empfohlen (bei wiederkehrendem Problem: Store-Neuinstallation).",
    )
    outcome.status = "failed"
    outcome.recommend_reboot = True
    return outcome


def _plan_only(
    outcome: RepairOutcome,
    state: CodexState,
    record: Callable[[str, StepStatus, str], RepairStepResult],
) -> RepairOutcome:
    """Liste die Eskalation auf, ohne ein einziges mutierendes Dep aufzurufen."""

    def plan(name: str, applicable: bool, detail: str) -> None:
        prefix = "Geplant: " if applicable else "Uebersprungen: "
        record(name, "skipped", prefix + detail)

    s1_needed = bool(state.ghost_pids) or state.stale_lockfile
    plan(
        "S1 Ghosts + Lockfile",
        s1_needed,
        f"Ghosts {state.ghost_pids or 'keine'}, verwaistes Lockfile={state.stale_lockfile}.",
    )
    plan("S2 ClipSVC", not state.clipsvc_running, "ClipSVC sicherstellen (best effort, bricht nie ab).")
    plan("S3 staged Update abschliessen", True, "RegisterByFamilyName (sanft, immer, timeboxed).")
    plan(
        "Fallback reset_package",
        True,
        "Reset-AppxPackage -- genau EIN Fallback, nur falls S3 sauber durchlief, aber Codex nicht startet (timeboxed).",
    )
    plan(
        "Abschluss",
        True,
        "Falls S3 + Fallback erschoepft: Reboot empfehlen. Bei Timeout -> Reboot, bei Access Denied -> als Admin neu starten.",
    )
    outcome.status = "ok"  # Planung selbst ist erfolgreich (nichts ausgefuehrt).
    return outcome


def prevention_check(
    config: MaintenanceConfig, deps: RepairDeps
) -> list[RepairStepResult]:
    """Read-only Monitor: 'wuerde-Start-gehen?'.

    Prueft die bekannten Wedge-Vorboten (kein Ghost, ClipSVC laeuft, kein staged-Wedge,
    Paket fuer User registriert, Codex.exe/Paket vorhanden). Fuehrt keine Reparatur aus
    und ruft kein mutierendes Dep -- nur ``observe()``.
    """
    state = deps.observe()
    steps: list[RepairStepResult] = []

    def check(name: str, ok: bool, ok_msg: str, bad_msg: str) -> None:
        steps.append(RepairStepResult(name, "ok" if ok else "failed", ok_msg if ok else bad_msg))

    check(
        "Kein Ghost",
        not state.ghost_pids,
        "Kein haengender Codex-Hauptprozess ohne Renderer.",
        f"Ghost-Prozess(e) ohne Renderer erkannt: {state.ghost_pids}.",
    )
    check(
        "ClipSVC laeuft",
        state.clipsvc_running,
        "ClipSVC laeuft (keine Aktivierungsfehler 0x8000001A zu erwarten).",
        "ClipSVC gestoppt -- Store-Aktivierung kann mit 0x8000001A scheitern.",
    )
    check(
        "Kein staged-Wedge",
        not (state.staged_update and not state.package_user_registered),
        "Keine gestagte, nicht registrierte Update-Version.",
        "Gestagtes, nicht abgeschlossenes Update erkannt (staged-Wedge-Gefahr).",
    )
    check(
        "Paket fuer User registriert",
        state.package_user_registered,
        "Codex-Paket ist fuer den User registriert (PackageUserInformation gefuellt).",
        "Codex-Paket nicht fuer den User registriert (PUI leer) -- Start scheitert.",
    )
    check(
        "Codex vorhanden",
        state.codex_exe_present,
        "Codex-Installation vorhanden (Exe bzw. Store-Paket).",
        "Codex.exe/Store-Paket fehlt -- Neuinstallation noetig.",
    )
    check(
        "Store-Paket vorhanden",
        not getattr(state, "package_absent", False),
        "Codex-Store-Paket ist installiert/gestaged vorhanden.",
        "Codex-Store-Paket vollstaendig abwesend -- Neuinstallation aus dem Microsoft Store noetig "
        "(eine vorhandene Standalone-Exe taeuscht hier nicht darueber hinweg).",
    )
    return steps
