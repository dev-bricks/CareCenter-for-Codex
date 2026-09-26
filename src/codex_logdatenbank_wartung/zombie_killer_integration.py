"""Optionale zombie-killer-tray-Integration für CareCenter.

CareCenter's eigener Runtime-MCP-Reaper (`processes.py`/`watchdog.py`) bleibt
unverändert und zielt gezielt auf Codex-Companion-Prozesse; zombie-killer-tray
deckt den breiteren, produktübergreifenden Fall ab (verwaiste MCP- und
Language-Server-Prozesse beliebiger Agenten-Frameworks, nicht nur Codex) und
läuft als eigener Subprozess -- exakt das Muster aus `safe_start_integration.py`
(git-gepinnte Abhängigkeit, `python -m <paket> ...`-Start, keine In-Process-
Kopplung). T-20260926-212716751 / T-20260926-368033290 (c).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import MaintenanceConfig

# T-20260926-212716751: zombie-killer-tray#4 (src/-Paketierung) merged as 039b4f2.
ZOMBIE_KILLER_PACKAGE_SPEC = (
    "zombie-killer-tray @ "
    "git+https://github.com/dev-bricks/zombie-killer-tray.git"
    "@039b4f2c7acd69063b39d6168c757b0b2fca2438"
)
ZOMBIE_KILLER_SOURCE_ENV = "CARECENTER_ZOMBIE_KILLER_SOURCE"
CREATE_NO_WINDOW = 0x08000000


@dataclass(slots=True)
class ZombieKillerInstallResult:
    status: str
    target: str
    command: list[str]
    message: str
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_text(self) -> str:
        lines = [
            f"Status: {self.status}",
            f"Ziel: {self.target}",
            "Befehl: " + " ".join(self.command),
            self.message,
        ]
        if self.stdout.strip():
            lines.append("Ausgabe:")
            lines.append(self.stdout.strip())
        if self.stderr.strip():
            lines.append("Fehlerausgabe:")
            lines.append(self.stderr.strip())
        return "\n".join(lines)


@dataclass(slots=True)
class ZombieKillerLaunchResult:
    status: str
    command: list[str]
    message: str
    state_dir: str
    pid: int | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_text(self) -> str:
        lines = [
            f"Status: {self.status}",
            "Befehl: " + " ".join(self.command),
            self.message,
            f"Statusordner: {self.state_dir}",
        ]
        if self.pid is not None:
            lines.append(f"PID: {self.pid}")
        return "\n".join(lines)


@dataclass(slots=True)
class ZombieKillerStatus:
    available: bool
    state_dir: str
    last_cycle_at: float | None
    last_cycle_count: int | None
    notes: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_text(self) -> str:
        availability = "installiert" if self.available else "nicht installiert"
        lines = [
            f"zombie-killer-tray: {availability}",
            f"Statusordner: {self.state_dir}",
        ]
        if self.last_cycle_at is not None:
            lines.append(
                f"Letzter Zyklus: {self.last_cycle_at} (bereinigt: {self.last_cycle_count})"
            )
        if self.notes:
            lines.append("Hinweise:")
            lines.extend(f"- {note}" for note in self.notes)
        return "\n".join(lines)


def _no_window_kwargs() -> dict[str, object]:
    if os.name == "nt":
        return {"creationflags": CREATE_NO_WINDOW}
    return {}


def _zombie_killer_importable() -> bool:
    try:
        __import__("zombie_killer_tray.killer")
    except Exception:
        return False
    return True


def _local_zombie_killer_source() -> Path | None:
    env_path = os.environ.get(ZOMBIE_KILLER_SOURCE_ENV)
    if env_path:
        candidate = Path(env_path).expanduser()
        if (candidate / "pyproject.toml").exists():
            return candidate

    project_root = Path(__file__).resolve().parents[2]
    sibling = project_root.parent / "REL-PUB_zombie-killer-tray"
    if (sibling / "pyproject.toml").exists():
        return sibling
    return None


def zombie_killer_install_target() -> str:
    """Bevorzuge die lokale Schwesterquelle, sonst die commit-gepinnte GitHub-Quelle."""
    local_source = _local_zombie_killer_source()
    if local_source is not None:
        return str(local_source)
    return ZOMBIE_KILLER_PACKAGE_SPEC


def _pip_command_candidates() -> list[list[str]]:
    candidates: list[list[str]] = []
    if not getattr(sys, "frozen", False):
        candidates.append([sys.executable, "-m", "pip"])
    candidates.extend((["py", "-3", "-m", "pip"], ["python", "-m", "pip"]))

    unique: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for candidate in candidates:
        key = tuple(candidate)
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def _python_command_candidates() -> list[list[str]]:
    candidates: list[list[str]] = []
    if not getattr(sys, "frozen", False):
        candidates.append([sys.executable])
    candidates.extend((["py", "-3"], ["python"]))

    unique: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for candidate in candidates:
        key = tuple(candidate)
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def _run_install_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def install_zombie_killer_package(
    *,
    target: str | None = None,
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
) -> ZombieKillerInstallResult:
    """Installiere oder aktualisiere zombie-killer-tray über pip.

    Bewusst eine explizite Nutzeraktion -- der Tray/CLI-Befehl nutzt dieselbe
    Funktion; automatisch wird hier nichts nachinstalliert (Muster identisch
    zu `install_safe_start_package`).
    """
    chosen_target = target or zombie_killer_install_target()
    run = runner or _run_install_command
    attempts: list[ZombieKillerInstallResult] = []
    for pip_command in _pip_command_candidates():
        command = [*pip_command, "install", "--upgrade", chosen_target]
        try:
            completed = run(command)
        except OSError as exc:
            attempts.append(
                ZombieKillerInstallResult(
                    status="failed",
                    target=chosen_target,
                    command=command,
                    message=str(exc),
                )
            )
            continue
        status = "ok" if completed.returncode == 0 else "failed"
        result = ZombieKillerInstallResult(
            status=status,
            target=chosen_target,
            command=command,
            message=(
                "zombie-killer-tray wurde installiert oder aktualisiert."
                if status == "ok"
                else f"pip endete mit Code {completed.returncode}."
            ),
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )
        if status == "ok":
            return result
        attempts.append(result)

    if attempts:
        last = attempts[-1]
        return ZombieKillerInstallResult(
            status="failed",
            target=chosen_target,
            command=last.command,
            message="zombie-killer-tray konnte nicht installiert werden.",
            stdout=last.stdout,
            stderr=last.stderr or last.message,
        )
    return ZombieKillerInstallResult(
        status="failed",
        target=chosen_target,
        command=[],
        message="Kein Python/pip-Befehl gefunden.",
    )


def _zombie_killer_env(config: MaintenanceConfig) -> dict[str, str]:
    env = os.environ.copy()
    local_source = _local_zombie_killer_source()
    if local_source is not None:
        src = str(local_source / "src")
        old_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = src if not old_pythonpath else src + os.pathsep + old_pythonpath
    return env


def launch_zombie_killer_watch(
    config: MaintenanceConfig,
    *,
    interval_seconds: int | None = None,
    min_age_seconds: int | None = None,
    popen: Callable[..., subprocess.Popen[str]] | None = None,
) -> ZombieKillerLaunchResult:
    """Starte `python -m zombie_killer_tray watch` als eigenen Subprozess.

    Laufzeitzustand (`zombie_events.jsonl`, `zombie_worker_errors.log`)
    landet im zombie-killer-eigenen Statusordner unterhalb von CODEX_HOME
    (via `cwd=`) -- zombie-killer-tray selbst entscheidet anhand seines
    Arbeitsverzeichnisses, wohin es schreibt (T-20260926-212716751); CareCenter
    liest hier nichts direkt in den laufenden Prozess hinein, sondern nur die
    JSONL-Datei danach (siehe `build_zombie_killer_status`).
    """
    state_dir = config.zombie_killer_state_dir
    state_dir.mkdir(parents=True, exist_ok=True)
    args = [
        "watch",
        "--yes",
        "--interval", str(interval_seconds or config.zombie_killer_watch_interval_seconds),
        "--min-age", str(min_age_seconds or config.zombie_killer_min_age_seconds),
        "--parent-pid", str(os.getpid()),
    ]

    env = _zombie_killer_env(config)
    run = popen or subprocess.Popen
    last_error = ""
    last_command: list[str] = []

    for python_command in _python_command_candidates():
        command = [*python_command, "-m", "zombie_killer_tray", *args]
        last_command = command
        try:
            process = run(
                command,
                cwd=str(state_dir),
                env=env,
                close_fds=True,
                **_no_window_kwargs(),
            )
        except OSError as exc:
            last_error = str(exc)
            continue
        pid = getattr(process, "pid", None)
        return ZombieKillerLaunchResult(
            status="ok",
            command=command,
            message="zombie-killer-tray wurde als eigener Watch-Subprozess gestartet.",
            state_dir=str(state_dir),
            pid=int(pid) if isinstance(pid, int) else None,
        )

    return ZombieKillerLaunchResult(
        status="failed",
        command=last_command,
        message=last_error or "Kein Python-Befehl für zombie-killer-tray gefunden.",
        state_dir=str(state_dir),
    )


def _last_cycle_event(state_dir: Path) -> dict[str, object] | None:
    events_path = state_dir / "zombie_events.jsonl"
    if not events_path.exists():
        return None
    last: dict[str, object] | None = None
    try:
        with events_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict) and "cycle_at" in record:
                    last = record
    except OSError:
        return None
    return last


def build_zombie_killer_status(config: MaintenanceConfig) -> ZombieKillerStatus:
    state_dir = config.zombie_killer_state_dir
    notes: list[str] = []
    available = _zombie_killer_importable()
    if not available:
        notes.append("zombie-killer-tray-Paket nicht importierbar; nutze vorhandenes Audit-Log.")

    last_cycle = _last_cycle_event(state_dir)
    return ZombieKillerStatus(
        available=available,
        state_dir=str(state_dir),
        last_cycle_at=float(last_cycle["cycle_at"]) if last_cycle else None,
        last_cycle_count=int(last_cycle["count"]) if last_cycle and "count" in last_cycle else None,
        notes=notes,
    )
