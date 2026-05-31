"""PySide6-Systemtray-App mit Status-Fenster, Fortschrittsbalken und zwei Wartungsmodi.

Hintergrund (empirisch belegt): Windows-Toast-Benachrichtigungen einer nicht im
Startmenü registrierten App werden oft unterdrückt. Verlässliche Rückmeldung läuft
daher über (1) ein anklickbares **Status-Fenster mit Fortschrittsbalken** und
(2) einen **Live-Tooltip**. Toasts bleiben nur ergänzend.

Zwei Modi (ein Tray):
* **Safe:** Wartung wird eingereiht; es wird gewartet, bis Codex wirklich im
  Leerlauf ist (ganzer Prozessbaum), dann kontrolliert geschlossen, gewartet und
  neu gestartet. Laufende Automatisierungen werden nie unterbrochen.
* **Fast:** sofort.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Callable

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .config import MaintenanceConfig
from .health import RepairResult, diagnose, repair_start
from .orchestrator import AutoMaintainResult, AutoProgress, auto_maintain
from .processes import no_window_kwargs
from .single_instance import SingleInstanceGuard
from .store_repair import StoreRepairResult, open_store_page, repair_store_codex
from .watchdog import run_watchdog_tick

ICON_FILENAME = "CareCenterForCodex.ico"

# Produktname (Brand zuerst, "Codex" nur als Zweckangabe -> markenrechtlich nominative use).
# Interner Paket-/Ordnername bleibt unveraendert.
APP_NAME = "CareCenter for Codex"
APP_SHORT = "CareCenter"


def _zombie_text(count: int) -> str:
    """Zombie-Zaehler-Text fuers Status-Fenster (mit Zombie-Emoji, vom User gewuenscht)."""
    return f"\U0001F9DF  {count} hängende Codex-Reste seit Start entfernt"


def _app_icon() -> QIcon:
    """App-Icon laden — gebündelt (PyInstaller `_MEIPASS`) oder aus dem Projekt-Root (Dev)."""
    bases = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        bases.append(Path(meipass))
    bases.append(Path(__file__).resolve().parents[2])  # Projekt-Root im src-Layout
    for base in bases:
        candidate = base / ICON_FILENAME
        if candidate.exists():
            icon = QIcon(str(candidate))
            if not icon.isNull():
                return icon
    app = QApplication.instance()
    if app is not None:
        return app.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)
    return QIcon()


class AutoMaintainWorker(QObject):
    progress = Signal(object)  # AutoProgress
    finished = Signal(object)  # AutoMaintainResult

    def __init__(self, config: MaintenanceConfig, mode: str) -> None:
        super().__init__()
        self.config = config
        self.mode = mode

    def run(self) -> None:
        result = auto_maintain(
            self.config,
            mode=self.mode,
            execute=True,
            allow_close=True,  # expliziter Tray-Klick = Zustimmung zum Schließen
            progress=lambda update: self.progress.emit(update),
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


def _resolve_python_and_src() -> Path | None:
    """Ermittle das ``src``-Verzeichnis fuer die elevated CLI-Ausfuehrung.

    Im Dev-Layout liegt ``src`` als ``parents[1]`` zu dieser Datei. In der gefrorenen
    PyInstaller-EXE zeigt ``__file__`` aber in den fluechtigen ``_MEIPASS``-Tempordner --
    dort gibt es kein nutzbares ``src``. Dann wird der echte Quellbaum neben der EXE bzw.
    am bekannten Projektpfad gesucht. Rueckgabe ``None``, wenn kein gueltiges ``src``
    (mit dem Paketordner) gefunden wird -- der Aufrufer meldet das sauber, statt zu crashen.
    """
    import os

    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        # Gefrorene EXE: echtes src NICHT im _MEIPASS, sondern im Projektbaum suchen.
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "src")
        candidates.append(exe_dir.parent / "src")
        # Optionaler Override fuer beliebige Installationsorte (kein hartcodierter Pfad im Code).
        env_src = os.environ.get("CARECENTER_SRC_DIR")
        if env_src:
            candidates.append(Path(env_src))
    else:
        candidates.append(Path(__file__).resolve().parents[1])

    for candidate in candidates:
        if (candidate / "codex_logdatenbank_wartung" / "cli.py").exists():
            return candidate
    return None


def _write_elevation_script(script_path: Path, src_dir: Path, config_path: Path, out_path: Path) -> None:
    """Schreibe ein eigenstaendiges .ps1, das die volle Reparatur elevated ausfuehrt.

    Bewusst eine separate Skript-Datei statt verschachtelter ``-Command``-Strings: so
    gibt es nur EINE Ausfuehrungsebene und KEINE doppelte ``$``-Expansion (die Variante
    mit verschachteltem ``& { ... }`` im ``-ArgumentList`` expandiert ``$env:PYTHONPATH``
    bereits im aeusseren Shell und zerbricht). Einfachquotes um Windows-Pfade sind literal.
    """
    content = (
        f"$env:PYTHONPATH = '{src_dir}'\n"
        f"& python -m codex_logdatenbank_wartung.cli "
        f"--config '{config_path}' repair --execute --out '{out_path}'\n"
    )
    script_path.write_text(content, encoding="utf-8")


def _elevation_launch_args(script_path: Path) -> list[str]:
    """Argumente fuer das aeussere PowerShell, das das .ps1 mit EINEM UAC elevated startet."""
    return [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        (
            "Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden "
            f"-ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File','{script_path}')"
        ),
    ]


def _parse_repair_out(out_path: Path) -> dict[str, object] | None:
    """Lies die JSONL-Out-Datei und liefere das vollstaendige Ergebnis (letzte Zeile).

    Die letzte Zeile MUSS das vollstaendige Outcome (mit ``status`` und ``steps``) sein.
    Ist die Datei leer oder die letzte Zeile nur ein Einzelschritt (UAC abgelehnt /
    elevated Prozess vorzeitig beendet), wird ``None`` zurueckgegeben -> 'unterbrochen'.
    """
    try:
        lines = [line for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return None
    if not lines:
        return None
    try:
        data = json.loads(lines[-1])
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and "status" in data and "steps" in data:
        return data
    return None


class FullRepairWorker(QObject):
    """Startet die volle Reparatur ELEVATED (ein UAC) und tailt die Out-Datei live."""

    progress = Signal(str)  # Stufentext (eine Zeile pro neuer Stufe)
    finished = Signal(object)  # dict (Outcome) oder None (unterbrochen)

    def __init__(self, config_path: Path) -> None:
        super().__init__()
        self.config_path = config_path
        self._stop = False

    def run(self) -> None:
        import os
        from time import sleep

        # Voraussetzung: nutzbares src-Verzeichnis (Dev oder echter Quellbaum neben der EXE).
        src_dir = _resolve_python_and_src()
        if src_dir is None:
            self.progress.emit(
                "[failed] Voraussetzung: Quellverzeichnis (src) der Reparatur-CLI nicht gefunden."
            )
            self.finished.emit(None)
            return

        # mkstemp legt eine leere Datei an; sie dient als Out-Pfad fuers Tailing.
        out_fd, out_name = tempfile.mkstemp(prefix="codex-repair-", suffix=".jsonl")
        os.close(out_fd)
        out_path = Path(out_name)

        # Eigenstaendiges Elevation-Skript schreiben (keine verschachtelte $-Expansion).
        script_fd, script_name = tempfile.mkstemp(prefix="codex-repair-", suffix=".ps1")
        os.close(script_fd)
        script_path = Path(script_name)
        _write_elevation_script(script_path, src_dir, self.config_path, out_path)

        args = _elevation_launch_args(script_path)
        try:
            # Elevated-Lauf starten; parallel die Out-Datei tailen.
            proc = subprocess.Popen(
                ["powershell", *args],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **no_window_kwargs(),
            )

            seen = 0
            while proc.poll() is None:
                seen = self._emit_new_steps(out_path, seen)
                sleep(1.0)
            # Letzte Stufen nach Prozessende noch einsammeln.
            self._emit_new_steps(out_path, seen)

            outcome = _parse_repair_out(out_path)
        finally:
            for path in (out_path, script_path):
                try:
                    path.unlink()
                except OSError:
                    pass
        self.finished.emit(outcome)

    def _emit_new_steps(self, out_path: Path, seen: int) -> int:
        """Neue, noch nicht gemeldete Zeilen als Stufentext emittieren. Gibt neuen Stand zurueck."""
        try:
            lines = [line for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except OSError:
            return seen
        for line in lines[seen:]:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Outcome-Zeile (status+steps) NICHT als Einzelstufe melden.
            if isinstance(payload, dict) and "name" in payload and "status" in payload and "steps" not in payload:
                self.progress.emit(f"[{payload.get('status')}] {payload.get('name')}: {payload.get('message')}")
        return len(lines)


class WatchdogWorker(QObject):
    """Hintergrund-Waechter: tickt periodisch und reapt bei geschlossenem Codex Start-Reste.

    Laeuft in einem eigenen QThread (eigener Event-Loop -> der interne QTimer feuert dort,
    nicht im GUI-Thread). Jeder Tick liest die Config frisch (Toggles greifen sofort) und ist
    rundum fehlertolerant -- ein Tick darf den Waechter nie crashen. Gekillt wird ausschliesslich
    ueber den getesteten ``run_watchdog_tick``/``repair_start`` (nur Ghosts ohne Renderer, nie die
    npm-CLI, nie eine aktive Sitzung).
    """

    reaped = Signal(object)  # WatchdogTickResult.to_dict(), nur wenn wirklich aufgeraeumt wurde

    def __init__(self, config_path: Path, is_busy: "Callable[[], bool]") -> None:
        super().__init__()
        self.config_path = config_path
        self._is_busy = is_busy
        self._timer: QTimer | None = None
        self._stopped = False

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
            result = run_watchdog_tick(config, execute=True)
        except Exception:  # noqa: BLE001 -- ein Tick darf den Waechter nie crashen
            return
        self._audit(config, result)
        if result.action == "reaped":
            self.reaped.emit(result.to_dict())

    def _audit(self, config: MaintenanceConfig, result: object) -> None:
        """Lueckenloser Nachweis JEDES Ticks (auch 'nichts getan') in logs/watchdog.log.

        So ist nie unklar, ob der Waechter Codex angefasst hat: jeder Tick hinterlaesst
        eine Zeile mit Aktion, Ziel-PIDs und Reap-Status -- unabhaengig davon, ob etwas
        beendet wurde. Fehler beim Schreiben duerfen den Waechter nie kippen.
        """
        from datetime import datetime

        try:
            logs = config.logs_path
            logs.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            action = getattr(result, "action", "?")
            zombies = getattr(result, "zombie_pids", [])
            stale = getattr(result, "stale_lockfile", False)
            status = getattr(result, "repair_status", None)
            line = (
                f"{stamp}  action={action}  zombies={zombies}  "
                f"lockfile={stale}  reap_status={status}\n"
            )
            with (logs / "watchdog.log").open("a", encoding="utf-8") as handle:
                handle.write(line)
        except Exception:  # noqa: BLE001 -- Audit-Schreibfehler darf den Tick nie crashen
            pass


class StartRepairWorker(QObject):
    """Leichte Stufe der zusammengefassten Codex-Reparatur -- OHNE UAC.

    Klassifiziert die Lage (Renderer da? Codex ueberhaupt installiert? haengende Reste?)
    und behandelt die billigen Faelle selbst: haengende Reste entfernen (`repair_start`,
    nicht-elevated taskkill), Codex starten, auf Renderer warten. Reicht das nicht und ist
    Codex installiert, signalisiert sie ``escalate`` -> der Controller startet die elevated
    Vollstufe. Ist gar kein Codex installiert, signalisiert sie ``needs_store_reinstall``.
    """

    progress = Signal(str)
    finished = Signal(object)  # dict: {outcome, reaped, message}

    def __init__(self, config: MaintenanceConfig) -> None:
        super().__init__()
        self.config = config

    def run(self) -> None:
        import time

        from .orchestrator import default_launcher
        from .processes import find_codex_processes_by_executable, process_type
        from .start_repair import classify_start_state, codex_installed_for_user

        config = self.config
        try:
            report = diagnose(config)
        except Exception as exc:  # noqa: BLE001 -- Diagnose darf den Lauf nicht crashen
            self.finished.emit({"outcome": "escalate", "reaped": 0, "message": f"Diagnose-Fehler: {exc}"})
            return

        installed = codex_installed_for_user(config)
        decision = classify_start_state(
            renderer_present=report.renderer_present,
            codex_installed=installed,
            zombie_pids=list(report.zombie_main_pids),
            stale_lockfile=report.stale_lockfile,
        )

        if decision == "already_running":
            self.finished.emit({"outcome": "already_running", "reaped": 0, "message": "Codex läuft bereits — nichts zu tun."})
            return
        if decision == "needs_store_reinstall":
            self.finished.emit({
                "outcome": "needs_store_reinstall", "reaped": 0,
                "message": "Keine Codex-Installation gefunden — Neuinstallation aus dem Microsoft Store nötig.",
            })
            return

        reaped = 0
        if decision == "reap":
            self.progress.emit("Leichte Stufe: hängende Codex-Reste entfernen (ohne Admin) …")
            try:
                result = repair_start(config, execute=True, trigger="tray-start", write_log=True)
                reaped = sum(
                    1 for step in result.steps
                    if step.name.startswith("Zombie beenden") and step.status == "ok"
                )
            except Exception as exc:  # noqa: BLE001
                self.finished.emit({"outcome": "escalate", "reaped": 0, "message": f"Reap-Fehler: {exc}"})
                return

            self.progress.emit("Codex starten und auf Fenster warten …")
            try:
                default_launcher(config)()
            except Exception:  # noqa: BLE001 -- Start kann scheitern, dann eskaliert die naechste Pruefung
                pass

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
                    "message": "Codex gestartet — leichte Reparatur genügte (kein Admin nötig).",
                })
                return
            self.finished.emit({
                "outcome": "escalate", "reaped": reaped,
                "message": "Leichte Stufe genügte nicht — eskaliere (Admin nötig) …",
            })
            return

        # decision == "needs_escalation": installiert, aber Start scheitert ohne offensichtliche Reste.
        self.finished.emit({"outcome": "escalate", "reaped": 0, "message": "Tiefer eskalieren nötig (Admin) …"})


class StatusWindow(QWidget):
    """Kleines Statusfenster: aktueller Zustand, Fortschrittsbalken, letztes Ergebnis."""

    request_safe = Signal()
    request_fast = Signal()
    request_diagnose = Signal()
    request_codex_repair = Signal()
    request_store_repair = Signal()
    request_store_reinstall = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumWidth(470)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        layout = QVBoxLayout(self)
        self.state_label = QLabel("Bereit.")
        self.state_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.state_label)

        self.zombie_label = QLabel(_zombie_text(0))
        self.zombie_label.setStyleSheet("color: #2a7a4a;")
        layout.addWidget(self.zombie_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet("color: #555;")
        layout.addWidget(self.result_label)

        # Haupt-Aktion: EINE zusammengefasste Codex-Start-Reparatur (Eskalation, Stopp bei Erfolg).
        repair_row = QHBoxLayout()
        self.repair_button = QPushButton("Codex reparieren")
        self.repair_button.setToolTip(
            "Eskalationskette: erst hängende Reste entfernen (ohne Admin), nur wenn nötig "
            "elevated weiter (ClipSVC, Store-Update, Reset, Reinstall). Stoppt, sobald Codex "
            "startet. Schlägt bei Bedarf Reboot oder Store-Neuinstallation vor."
        )
        self.repair_button.clicked.connect(self.request_codex_repair)
        self.diagnose_button = QPushButton("Diagnose")
        self.diagnose_button.setToolTip("Nur prüfen (read-only), nichts ändern.")
        self.diagnose_button.clicked.connect(self.request_diagnose)
        repair_row.addWidget(self.repair_button)
        repair_row.addWidget(self.diagnose_button)
        layout.addLayout(repair_row)

        # DB-Wartung (eigene Funktion, bewusst getrennt von der Start-Reparatur).
        maint_row = QHBoxLayout()
        self.safe_button = QPushButton("Wartung – Safe")
        self.safe_button.setToolTip("Wartet auf Codex-Leerlauf, schließt Codex, wartet, startet neu.")
        self.safe_button.clicked.connect(self.request_safe)
        self.fast_button = QPushButton("Wartung – Fast")
        self.fast_button.setToolTip("Sofort: Codex beenden und warten, ohne auf Leerlauf zu warten.")
        self.fast_button.clicked.connect(self.request_fast)
        maint_row.addWidget(self.safe_button)
        maint_row.addWidget(self.fast_button)
        layout.addLayout(maint_row)

        # Store-Werkzeuge (Vorschläge/Notfall): meist als Vorschlag aus der Eskalation,
        # hier zusätzlich direkt erreichbar.
        store_row = QHBoxLayout()
        self.store_button = QPushButton("Store-Update reparieren")
        self.store_button.setToolTip("Store-Cache leeren und Codex-Paket neu registrieren.")
        self.store_button.clicked.connect(self.request_store_repair)
        self.store_reinstall_button = QPushButton("Codex neu installieren")
        self.store_reinstall_button.setToolTip("Öffnet die Microsoft-Store-Seite der OpenAI-Codex-App.")
        self.store_reinstall_button.clicked.connect(self.request_store_reinstall)
        store_row.addWidget(self.store_button)
        store_row.addWidget(self.store_reinstall_button)
        layout.addLayout(store_row)

        self.close_button = QPushButton("Schließen (läuft im Hintergrund weiter)")
        self.close_button.setToolTip(
            "Schließt nur das Fenster. Eine laufende Reparatur läuft weiter; über das "
            "Tray-Menü 'Status & Fortschritt anzeigen' jederzeit wieder öffnen."
        )
        self.close_button.clicked.connect(self.hide)
        layout.addWidget(self.close_button)

    def set_zombie_count(self, count: int) -> None:
        self.zombie_label.setText(_zombie_text(count))

    def set_running(self, running: bool) -> None:
        for button in (
            self.repair_button,
            self.diagnose_button,
            self.safe_button,
            self.fast_button,
            self.store_button,
            self.store_reinstall_button,
        ):
            button.setEnabled(not running)

    def set_progress(self, percent: int, message: str, indeterminate: bool) -> None:
        if indeterminate:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(percent)
        if message:
            self.detail_label.setText(message)

    def set_state(self, text: str) -> None:
        self.state_label.setText(text)

    def set_result(self, text: str) -> None:
        self.result_label.setText(text)


class TrayController(QObject):
    def __init__(self, config_path: Path, tray: QSystemTrayIcon) -> None:
        super().__init__()
        self.config_path = config_path
        self.config = MaintenanceConfig.load(config_path)
        self.tray = tray
        self.running = False
        self.auto_thread: QThread | None = None
        self.auto_worker: AutoMaintainWorker | None = None
        self.repair_thread: QThread | None = None
        self.repair_worker: RepairWorker | None = None
        self.store_thread: QThread | None = None
        self.store_worker: StoreRepairWorker | None = None
        self.full_repair_thread: QThread | None = None
        self.full_repair_worker: FullRepairWorker | None = None
        self.watchdog_thread: QThread | None = None
        self.watchdog_worker: WatchdogWorker | None = None
        self.start_repair_thread: QThread | None = None
        self.start_repair_worker: StartRepairWorker | None = None
        self.zombie_kill_count = 0  # vom Hintergrund-Waechter + leichter Reparatur seit Start

        self.app_icon = _app_icon()  # konstantes Tray-Icon (kein Wechsel)

        self.window = StatusWindow()
        self.window.request_safe.connect(lambda: self.run_auto("safe"))
        self.window.request_fast.connect(lambda: self.run_auto("fast"))
        self.window.request_diagnose.connect(self.show_diagnosis)
        self.window.request_codex_repair.connect(self.run_codex_repair)
        self.window.request_store_repair.connect(self.run_store_repair)
        self.window.request_store_reinstall.connect(self.open_store_reinstall)

        # Bewusst schlankes Tray-Menue: EIN Reparatur-Eintrag (Eskalation), der Rest
        # (Diagnose, Wartung, Store) liegt als Buttons im Status-Fenster.
        self.menu = QMenu()
        # Drei Einträge öffnen alle dasselbe Status-Fenster -- die Labels machen aber die
        # Use-Cases sichtbar (App-Übersicht / Fortschritt / Wartung), damit der User erkennt,
        # was das Tool kann.
        self.open_action = QAction("CareCenter öffnen")
        self.open_action.setToolTip("Öffnet das CareCenter-Fenster (Übersicht, Reparatur, Wartung, Store).")
        self.open_action.triggered.connect(self.show_window)
        self.status_action = QAction("Status & Fortschritt anzeigen")
        self.status_action.triggered.connect(self.show_window)
        self.maintenance_action = QAction("Wartung")
        self.maintenance_action.setToolTip("Öffnet das Fenster mit den Wartungs-Buttons (Safe/Fast: DB-Wartung).")
        self.maintenance_action.triggered.connect(self.show_window)
        self.repair_action = QAction("Codex reparieren")
        self.repair_action.setToolTip(
            "Eine Eskalationskette: erst hängende Reste entfernen (ohne Admin), nur wenn nötig "
            "elevated weiter, Stopp sobald Codex startet. Schlägt bei Bedarf Reboot oder "
            "Store-Neuinstallation vor."
        )
        self.repair_action.triggered.connect(self.run_codex_repair)
        self.watchdog_action = QAction("Auto-Wächter: Start-Reste entfernen")
        self.watchdog_action.setCheckable(True)
        self.watchdog_action.setChecked(bool(self.config.watcher_enabled))
        self.watchdog_action.setToolTip(
            "Überwacht im Hintergrund: ist Codex zu und hängen alte Reste (Ghost-Prozess ohne "
            "Fenster / verwaistes Lockfile), werden sie entfernt, damit der nächste Start sauber "
            "ist. Beendet nie eine aktive Sitzung und nie die Codex-CLI. Benachrichtigt beim Aufräumen."
        )
        self.watchdog_action.toggled.connect(self.on_toggle_watchdog)
        self.quit_action = QAction("Beenden")
        self.quit_action.triggered.connect(QApplication.quit)

        self.menu.addAction(self.open_action)
        self.menu.addAction(self.status_action)
        self.menu.addAction(self.maintenance_action)
        self.menu.addSeparator()
        self.menu.addAction(self.repair_action)
        self.menu.addSeparator()
        self.menu.addAction(self.watchdog_action)
        self.menu.addSeparator()
        self.menu.addAction(self.quit_action)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.on_tray_activated)

        self.timer = QTimer(self)
        self.timer.setInterval(30_000)
        self.timer.timeout.connect(self.refresh_idle_tooltip)
        self.timer.start()
        self.refresh_idle_tooltip()

        # Hintergrund-Waechter (Start-Praevention) starten; sauberes Stoppen beim Beenden.
        self._start_watchdog()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop_watchdog)

    # -- Tray-Interaktion -------------------------------------------------

    def on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_window()

    def show_window(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def refresh_idle_tooltip(self) -> None:
        if self.running:
            return
        self.tray.setToolTip(f"{APP_SHORT}: bereit  \U0001F9DF {self.zombie_kill_count}")

    def _add_zombie_kills(self, count: int) -> None:
        """Zombie-Zaehler erhoehen und in Fenster + Tooltip spiegeln."""
        if count <= 0:
            return
        self.zombie_kill_count += count
        self.window.set_zombie_count(self.zombie_kill_count)
        if not self.running:
            self.tray.setToolTip(f"{APP_SHORT}: bereit  \U0001F9DF {self.zombie_kill_count}")

    # -- Autonome Wartung (Safe/Fast) -------------------------------------

    def run_auto(self, mode: str) -> None:
        if self.running:
            self.tray.showMessage(
                "CareCenter", "Eine Wartung läuft bereits.",
                QSystemTrayIcon.MessageIcon.Information, 3000,
            )
            self.show_window()
            return
        self.running = True
        self.window.set_running(True)
        label = "Safe-Modus" if mode == "safe" else "Fast-Modus"
        self.window.set_state(f"Wartung läuft ({label}) …")
        self.window.set_progress(0, "Wird vorbereitet …", True)
        self.window.set_result("")
        self.show_window()
        self.tray.setToolTip(f"CareCenter: {label} gestartet …")
        self.tray.showMessage(
            "CareCenter",
            f"Wartung gestartet ({label}). Fortschritt über Klick aufs Tray-Symbol.",
            QSystemTrayIcon.MessageIcon.Information, 4000,
        )

        self.auto_thread = QThread(self)
        self.auto_worker = AutoMaintainWorker(MaintenanceConfig.load(self.config_path), mode)
        self.auto_worker.moveToThread(self.auto_thread)
        self.auto_thread.started.connect(self.auto_worker.run)
        self.auto_worker.progress.connect(self.on_auto_progress)
        self.auto_worker.finished.connect(self.on_auto_finished)
        self.auto_worker.finished.connect(self.auto_thread.quit)
        self.auto_worker.finished.connect(self.auto_worker.deleteLater)
        self.auto_thread.finished.connect(self.auto_thread.deleteLater)
        self.auto_thread.finished.connect(self.clear_auto_thread)
        self.auto_thread.start()

    def on_auto_progress(self, update: AutoProgress) -> None:
        self.window.set_progress(update.percent, update.message, update.indeterminate)
        short = update.message if len(update.message) < 60 else update.message[:57] + "…"
        self.tray.setToolTip(f"CareCenter: {short} ({update.percent}%)")

    def on_auto_finished(self, result: AutoMaintainResult) -> None:
        self.running = False
        self.window.set_running(False)
        self.window.set_progress(100, "Fertig.", False)
        summary = {
            "ok": "Wartung abgeschlossen.",
            "blocked": "Verschoben — Codex war aktiv (kein Lauf abgebrochen).",
            "failed": "Fehlgeschlagen — Details im Protokoll.",
        }.get(result.status, f"Beendet: {result.status}")
        self.window.set_state(summary)
        details = []
        if result.waited:
            details.append("auf Leerlauf gewartet")
        if result.closed_codex:
            details.append("Codex beendet")
        if result.restarted_codex:
            details.append("Codex neu gestartet")
        if result.maintenance:
            details.append(f"Wartung: {result.maintenance.get('status')}")
        self.window.set_result(" · ".join(details) if details else "")
        icon = (
            QSystemTrayIcon.MessageIcon.Information
            if result.status == "ok"
            else QSystemTrayIcon.MessageIcon.Warning
        )
        self.tray.setToolTip(f"CareCenter: {summary} (Klick für Details)")
        self.tray.showMessage("CareCenter — fertig", summary, icon, 8000)

    def clear_auto_thread(self) -> None:
        self.auto_thread = None
        self.auto_worker = None

    # -- Diagnose & Reparatur --------------------------------------------

    def run_codex_repair(self) -> None:
        """EINE zusammengefasste Codex-Start-Reparatur als Eskalation (Stopp bei Erfolg).

        Stufe A (ohne UAC): leichte Reparatur -- hängende Reste entfernen, Codex starten,
        auf Renderer prüfen. Erscheint ein Fenster, sind wir fertig. Ist gar kein Codex
        installiert, wird die Store-Neuinstallation vorgeschlagen. Genügt Stufe A nicht
        (Codex installiert, Start scheitert weiter), eskaliert der Controller automatisch
        auf die elevated Vollstufe (``run_full_repair``).
        """
        if self.start_repair_thread is not None or self.full_repair_thread is not None:
            self.tray.showMessage(
                "Codex reparieren", "Läuft bereits.",
                QSystemTrayIcon.MessageIcon.Information, 3000,
            )
            self.show_window()
            return
        self.running = True
        self.window.set_running(True)
        self.window.set_state("Codex-Reparatur: leichte Stufe (ohne Admin) …")
        self.window.set_progress(0, "Lage prüfen und hängende Reste entfernen …", True)
        self.window.set_result("")
        self.show_window()

        self.start_repair_thread = QThread(self)
        self.start_repair_worker = StartRepairWorker(MaintenanceConfig.load(self.config_path))
        self.start_repair_worker.moveToThread(self.start_repair_thread)
        self.start_repair_thread.started.connect(self.start_repair_worker.run)
        self.start_repair_worker.progress.connect(self.on_start_repair_progress)
        self.start_repair_worker.finished.connect(self.on_start_repair_finished)
        self.start_repair_worker.finished.connect(self.start_repair_thread.quit)
        self.start_repair_worker.finished.connect(self.start_repair_worker.deleteLater)
        self.start_repair_thread.finished.connect(self.start_repair_thread.deleteLater)
        self.start_repair_thread.finished.connect(self.clear_start_repair_thread)
        self.start_repair_thread.start()

    def on_start_repair_progress(self, line: str) -> None:
        self.window.set_progress(0, line, True)
        self.window.set_state(line)

    def on_start_repair_finished(self, info: object) -> None:
        data = info if isinstance(info, dict) else {}
        outcome = str(data.get("outcome", "escalate"))
        self._add_zombie_kills(int(data.get("reaped") or 0))
        message = str(data.get("message") or "")

        if outcome == "escalate":
            # Leichte Stufe genügte nicht -> elevated Vollstufe automatisch anschließen.
            self.running = False  # run_full_repair verwaltet seinen eigenen Lauf-Zustand
            self.window.set_state("Eskaliere — bitte UAC bestätigen …")
            self.window.set_result(message)
            self.run_full_repair()
            return

        self.running = False
        self.window.set_running(False)
        self.window.set_progress(100, "Fertig.", False)
        self.window.set_state(message)

        if outcome == "needs_store_reinstall":
            self.window.set_result(
                "→ Knopf 'Codex neu installieren' (öffnet die Store-Seite). Es ist Teil "
                "desselben Problems: ohne Installation kann nichts starten."
            )
            icon = QSystemTrayIcon.MessageIcon.Warning
        else:  # ok / already_running
            self.window.set_result("")
            icon = QSystemTrayIcon.MessageIcon.Information
        self.tray.setToolTip(f"{APP_SHORT}: {message}")
        self.tray.showMessage("CareCenter – Codex reparieren", message, icon, 9000)

    def clear_start_repair_thread(self) -> None:
        self.start_repair_thread = None
        self.start_repair_worker = None

    def show_diagnosis(self) -> None:
        report = diagnose(MaintenanceConfig.load(self.config_path))
        if report.zombie_main_pids or report.stale_lockfile or not report.codex_exe_present:
            text = f"Startblockade erkannt (Status: {report.status}). Über 'Start reparieren' beheben."
        elif report.status != "ok":
            text = f"{len(report.issues)} Hinweis(e), Status: {report.status}."
        else:
            text = "Keine Startprobleme erkannt. Codex sollte normal starten."
        self.window.set_state("Diagnose")
        self.window.set_result(text)
        self.show_window()
        self.tray.showMessage("Codex-Start-Diagnose", text, QSystemTrayIcon.MessageIcon.Information, 5000)

    def repair_start_problems(self) -> None:
        if self.repair_thread is not None:
            self.tray.showMessage(
                "Codex-Start-Reparatur", "Eine Reparatur läuft bereits.",
                QSystemTrayIcon.MessageIcon.Information, 3000,
            )
            return
        self.window.set_state("Reparatur läuft …")
        self.window.set_progress(0, "Suche hängende Codex-Prozesse / verwaiste Lockfiles …", True)
        self.repair_thread = QThread(self)
        self.repair_worker = RepairWorker(MaintenanceConfig.load(self.config_path))
        self.repair_worker.moveToThread(self.repair_thread)
        self.repair_thread.started.connect(self.repair_worker.run)
        self.repair_worker.finished.connect(self.on_repair_finished)
        self.repair_worker.finished.connect(self.repair_thread.quit)
        self.repair_worker.finished.connect(self.repair_worker.deleteLater)
        self.repair_thread.finished.connect(self.repair_thread.deleteLater)
        self.repair_thread.finished.connect(self.clear_repair_thread)
        self.repair_thread.start()

    def on_repair_finished(self, result: RepairResult) -> None:
        self.window.set_progress(100, "Reparatur beendet.", False)
        self.window.set_state(f"Reparatur: {result.status}")
        self.tray.showMessage(
            "Codex-Start-Reparatur — fertig",
            f"Reparatur beendet: {result.status}.",
            QSystemTrayIcon.MessageIcon.Information, 6000,
        )

    def clear_repair_thread(self) -> None:
        self.repair_thread = None
        self.repair_worker = None

    # -- Store-Update-Reparatur ------------------------------------------

    def run_store_repair(self) -> None:
        if self.store_thread is not None:
            self.tray.showMessage(
                "Store-Reparatur", "Läuft bereits.",
                QSystemTrayIcon.MessageIcon.Information, 3000,
            )
            return
        self.window.set_state("Store-Reparatur läuft …")
        self.window.set_progress(0, "Store-Cache leeren und Codex-Paket neu registrieren …", True)
        self.show_window()
        self.tray.showMessage(
            "Store-Reparatur",
            "Leere Store-Cache und registriere das Codex-Paket neu …",
            QSystemTrayIcon.MessageIcon.Information, 4000,
        )
        self.store_thread = QThread(self)
        self.store_worker = StoreRepairWorker()
        self.store_worker.moveToThread(self.store_thread)
        self.store_thread.started.connect(self.store_worker.run)
        self.store_worker.finished.connect(self.on_store_repair_finished)
        self.store_worker.finished.connect(self.store_thread.quit)
        self.store_worker.finished.connect(self.store_worker.deleteLater)
        self.store_thread.finished.connect(self.store_thread.deleteLater)
        self.store_thread.finished.connect(self.clear_store_thread)
        self.store_thread.start()

    def on_store_repair_finished(self, result: StoreRepairResult) -> None:
        ok = result.status == "ok"
        msg = (
            "Store-Cache geleert und Codex-Paket neu registriert. Codex sollte wieder aktualisierbar sein."
            if ok else f"Store-Reparatur: {result.status} — Details im Protokoll/Logfenster."
        )
        self.window.set_progress(100, "Store-Reparatur beendet.", False)
        self.window.set_state(msg)
        # Tray-Icon bleibt konstant (kein Wechsel) -- siehe CODEX-AUTO-DEBUG-DESIGN.md.
        self.tray.showMessage(
            "Store-Reparatur — fertig", msg,
            QSystemTrayIcon.MessageIcon.Information if ok else QSystemTrayIcon.MessageIcon.Warning,
            7000,
        )

    def clear_store_thread(self) -> None:
        self.store_thread = None
        self.store_worker = None

    def open_store_reinstall(self) -> None:
        """Store-Produktseite der OpenAI-Codex-App oeffnen (fuer den absenten Fall)."""
        product_id = getattr(self.config, "codex_store_product_id", "") or ""
        if not product_id:
            self.tray.showMessage(
                "Codex aus dem Store neu installieren",
                "Keine Store-Produkt-ID konfiguriert.",
                QSystemTrayIcon.MessageIcon.Warning, 6000,
            )
            return
        ok, detail = open_store_page(product_id)
        if ok:
            self.tray.showMessage(
                "Codex aus dem Store neu installieren",
                "Store-Seite geoeffnet. Dort auf 'Installieren' klicken — danach ist Codex "
                "wieder Store-verwaltet (Auto-Updates).",
                QSystemTrayIcon.MessageIcon.Information, 8000,
            )
        else:
            self.tray.showMessage(
                "Codex aus dem Store neu installieren",
                f"Store-Seite konnte nicht geoeffnet werden: {detail}",
                QSystemTrayIcon.MessageIcon.Warning, 8000,
            )

    # -- Volle Codex-Start-Reparatur (elevated, voll ausgeschoepft) -------

    def run_full_repair(self) -> None:
        if self.full_repair_thread is not None:
            self.tray.showMessage(
                "Codex-Start-Reparatur (voll)", "Läuft bereits.",
                QSystemTrayIcon.MessageIcon.Information, 3000,
            )
            self.show_window()
            return
        self.running = True
        self.window.set_running(True)
        self.window.set_state("Volle Reparatur läuft (elevated) …")
        self.window.set_progress(0, "UAC bestätigen — danach läuft die volle Eskalation …", True)
        self.window.set_result("")
        self.show_window()
        self.tray.showMessage(
            "Codex-Start-Reparatur (voll)",
            "Bitte den UAC-Prompt bestätigen. Danach läuft die volle Eskalation automatisch.",
            QSystemTrayIcon.MessageIcon.Information, 5000,
        )

        self.full_repair_thread = QThread(self)
        self.full_repair_worker = FullRepairWorker(self.config_path)
        self.full_repair_worker.moveToThread(self.full_repair_thread)
        self.full_repair_thread.started.connect(self.full_repair_worker.run)
        self.full_repair_worker.progress.connect(self.on_full_repair_progress)
        self.full_repair_worker.finished.connect(self.on_full_repair_finished)
        self.full_repair_worker.finished.connect(self.full_repair_thread.quit)
        self.full_repair_worker.finished.connect(self.full_repair_worker.deleteLater)
        self.full_repair_thread.finished.connect(self.full_repair_thread.deleteLater)
        self.full_repair_thread.finished.connect(self.clear_full_repair_thread)
        self.full_repair_thread.start()

    def on_full_repair_progress(self, line: str) -> None:
        # Stufen live ins Status-Fenster schreiben (jede neue Zeile anhaengen).
        prev = self.window.result_label.text()
        combined = f"{prev}\n{line}" if prev else line
        self.window.set_result(combined)
        self.window.set_progress(0, line, True)
        short = line if len(line) < 60 else line[:57] + "…"
        self.tray.setToolTip(f"Codex-Reparatur: {short}")

    def on_full_repair_finished(self, outcome: object) -> None:
        self.running = False
        self.window.set_running(False)
        self.window.set_progress(100, "Fertig.", False)
        if not isinstance(outcome, dict):
            self.window.set_state("Reparatur unterbrochen")
            self.window.set_result(
                "Die Reparatur wurde unterbrochen (UAC abgelehnt oder vorzeitig beendet). "
                "Bitte erneut versuchen."
            )
            self.tray.setToolTip("CareCenter: Reparatur unterbrochen")
            self.tray.showMessage(
                "Codex-Start-Reparatur (voll)",
                "Reparatur unterbrochen (UAC abgelehnt oder vorzeitig beendet).",
                QSystemTrayIcon.MessageIcon.Warning, 7000,
            )
            return
        status = str(outcome.get("status", "?"))
        reached = bool(outcome.get("reached_window"))
        reboot = bool(outcome.get("recommend_reboot"))
        needs_reinstall = bool(outcome.get("needs_store_reinstall"))
        steps = outcome.get("steps") or []
        if needs_reinstall:
            # Store-Paket vollstaendig weg -> Reparatur kann nichts registrieren.
            # Ehrliche Botschaft + Hinweis aufs Menue (KEIN Auto-Install -- der User
            # entscheidet, wann er neu installiert).
            summary = "Store-Paket fehlt — Neuinstallation aus dem Store nötig (kein Reboot)."
        else:
            summary = {
                "ok": "Codex-Start repariert — Fenster erschienen.",
                "blocked": "Gestoppt — AppX-Engine verklemmt. Reboot empfohlen.",
                "failed": "Alle Stufen erschöpft. Reboot empfohlen.",
            }.get(status, f"Beendet: {status}")
        self.window.set_state(summary)
        lines = [
            f"[{step.get('status')}] {step.get('name')}: {step.get('message')}"
            for step in steps
            if isinstance(step, dict)
        ]
        if needs_reinstall:
            lines.append("→ Knopf 'Codex neu installieren' im Fenster (öffnet die Store-Seite). Nur ein Vorschlag.")
        elif reboot:
            lines.append("→ Reboot empfohlen (nur ein Vorschlag).")
        elif reached:
            lines.append("→ Codex-Fenster erkannt.")
        self.window.set_result("\n".join(lines))
        icon = (
            QSystemTrayIcon.MessageIcon.Information
            if status == "ok"
            else QSystemTrayIcon.MessageIcon.Warning
        )
        if needs_reinstall:
            tip = "Store-Paket fehlt — Knopf 'Codex neu installieren' im Fenster."
        elif reboot:
            tip = "Reparatur gestoppt — Reboot empfohlen."
        else:
            tip = summary
        self.tray.setToolTip(f"CareCenter: {tip}")
        self.tray.showMessage("CareCenter – Codex reparieren (Vollstufe)", summary, icon, 9000)

    def clear_full_repair_thread(self) -> None:
        self.full_repair_thread = None
        self.full_repair_worker = None

    # -- Hintergrund-Waechter (Start-Praevention) -------------------------

    def _start_watchdog(self) -> None:
        if self.watchdog_thread is not None:
            return
        self.watchdog_thread = QThread(self)
        self.watchdog_worker = WatchdogWorker(self.config_path, self._watchdog_busy)
        self.watchdog_worker.moveToThread(self.watchdog_thread)
        self.watchdog_thread.started.connect(self.watchdog_worker.start)
        self.watchdog_worker.reaped.connect(self.on_watchdog_reaped)
        self.watchdog_thread.start()

    def _watchdog_busy(self) -> bool:
        """Waehrend einer manuellen Wartung/Reparatur haelt sich der Waechter raus (keine Races)."""
        return (
            self.running
            or self.auto_thread is not None
            or self.repair_thread is not None
            or self.store_thread is not None
            or self.full_repair_thread is not None
        )

    def on_watchdog_reaped(self, info: object) -> None:
        message = "Hängende Codex-Reste entfernt."
        if isinstance(info, dict):
            message = str(info.get("message") or message)
            self._add_zombie_kills(len(info.get("zombie_pids") or []))
        self.tray.showMessage(
            "CareCenter – Start-Prävention",
            message,
            QSystemTrayIcon.MessageIcon.Information, 8000,
        )

    def on_toggle_watchdog(self, checked: bool) -> None:
        self.config.watcher_enabled = bool(checked)
        try:
            self.config.save(self.config_path)
        except OSError:
            pass
        if checked and self.watchdog_thread is None:
            self._start_watchdog()
        self.tray.showMessage(
            "Codex-Start-Prävention",
            "Auto-Wächter aktiv." if checked else "Auto-Wächter deaktiviert.",
            QSystemTrayIcon.MessageIcon.Information, 4000,
        )

    def _stop_watchdog(self) -> None:
        if self.watchdog_worker is not None:
            self.watchdog_worker.request_stop()  # nur Flag setzen (thread-safe)
        if self.watchdog_thread is not None:
            self.watchdog_thread.quit()
            self.watchdog_thread.wait(2000)
            self.watchdog_thread = None
            self.watchdog_worker = None


def run_tray(config_path: Path) -> int:
    # Eigene AppUserModelID -> Windows-Benachrichtigungen (Toasts) erscheinen zuverlässiger.
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "CareCenterForCodex.Tray"
            )
        except Exception:
            pass

    config = MaintenanceConfig.load(config_path)

    from .i18n import detect_language, set_language
    set_language(config.language if config.language in ("de", "en") else detect_language())

    guard = SingleInstanceGuard(
        "Global\\CareCenterForCodex",
        config.lock_path.with_name("tray-instance.lock"),
    )
    if not guard.acquire():
        return 0

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    icon = _app_icon()
    app.setWindowIcon(icon)
    tray = QSystemTrayIcon(icon)
    tray.setToolTip("CareCenter")
    controller = TrayController(config_path, tray)
    tray.show()
    tray.showMessage(
        "CareCenter",
        "Tray läuft. Klick aufs Symbol öffnet Status & Fortschritt.",
        QSystemTrayIcon.MessageIcon.Information, 4000,
    )
    exit_code = app.exec()
    controller.deleteLater()
    guard.release()
    return int(exit_code)
