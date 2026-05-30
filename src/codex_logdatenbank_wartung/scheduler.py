"""Windows-Task-Scheduler-Integration fuer periodische Wartung."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from typing import Callable

from .config import DEFAULT_CONFIG_PATH, LOCAL_ROOT

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASK_NAME = "CodexLogdatenbankWartung-Autowartung"
DEFAULT_SCRIPT_PATH = LOCAL_ROOT / "run-maintenance.cmd"
DEFAULT_INTERVAL_MINUTES = 180

TaskRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


@dataclass(slots=True)
class ScheduleResult:
    status: str
    task_name: str
    script_path: str
    interval_minutes: int | None = None
    details: str = ""

    def to_text(self) -> str:
        lines = [f"Status: {self.status}", f"Task: {self.task_name}", f"Skript: {self.script_path}"]
        if self.interval_minutes is not None:
            lines.append(f"Intervall (Minuten): {self.interval_minutes}")
        if self.details:
            lines.append(f"Details: {self.details}")
        return "\n".join(lines)


def is_missing_task_message(message: str) -> bool:
    lowered = message.lower()
    return (
        "cannot find the file specified" in lowered
        or "kann die angegebene datei nicht finden" in lowered
    )


def build_runner_script(
    config_path: Path = DEFAULT_CONFIG_PATH,
    *,
    project_root: Path = PROJECT_ROOT,
    python_executable: Path | None = None,
) -> str:
    """Erzeuge das CMD-Helferskript fuer den geplanten Task."""
    python_path = Path(python_executable or sys.executable)
    source_path = project_root / "src"
    return (
        "@echo off\n"
        "setlocal\n"
        'set "PYTHONIOENCODING=utf-8"\n'
        f'set "PYTHONPATH={source_path};%PYTHONPATH%"\n'
        f'"{python_path}" -m codex_logdatenbank_wartung.cli --config "{config_path}" '
        "maintain --execute --trigger scheduled-task\n"
        "exit /b %errorlevel%\n"
    )


def write_runner_script(
    script_path: Path = DEFAULT_SCRIPT_PATH,
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    project_root: Path = PROJECT_ROOT,
    python_executable: Path | None = None,
) -> Path:
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(
        build_runner_script(
            config_path=config_path,
            project_root=project_root,
            python_executable=python_executable,
        ),
        encoding="utf-8",
    )
    return script_path


def run_schtasks(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    from .processes import no_window_kwargs

    return subprocess.run(
        ["schtasks.exe", *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **no_window_kwargs(),
    )


def ensure_valid_interval(interval_minutes: int) -> None:
    if interval_minutes < 15:
        raise ValueError("Intervall muss mindestens 15 Minuten betragen.")


def install_scheduled_task(
    *,
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    task_name: str = DEFAULT_TASK_NAME,
    script_path: Path = DEFAULT_SCRIPT_PATH,
    config_path: Path = DEFAULT_CONFIG_PATH,
    runner: TaskRunner = run_schtasks,
) -> ScheduleResult:
    ensure_valid_interval(interval_minutes)
    script_path = write_runner_script(script_path, config_path=config_path)
    command = f'"{script_path}"'
    result = runner(
        [
            "/Create",
            "/SC",
            "MINUTE",
            "/MO",
            str(interval_minutes),
            "/TN",
            task_name,
            "/TR",
            command,
            "/RL",
            "LIMITED",
            "/F",
        ]
    )
    if result.returncode != 0:
        details = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part).strip()
        raise RuntimeError(details or "Task-Scheduler-Eintrag konnte nicht erstellt werden.")
    return ScheduleResult(
        status="installed",
        task_name=task_name,
        script_path=str(script_path),
        interval_minutes=interval_minutes,
        details="Geplanter Task wurde erstellt oder ersetzt.",
    )


def remove_scheduled_task(
    *,
    task_name: str = DEFAULT_TASK_NAME,
    script_path: Path = DEFAULT_SCRIPT_PATH,
    runner: TaskRunner = run_schtasks,
) -> ScheduleResult:
    result = runner(["/Delete", "/TN", task_name, "/F"])
    combined = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part).strip()
    if result.returncode != 0:
        if is_missing_task_message(combined):
            return ScheduleResult(
                status="absent",
                task_name=task_name,
                script_path=str(script_path),
                details="Kein geplanter Task vorhanden.",
            )
        raise RuntimeError(combined or "Task-Scheduler-Eintrag konnte nicht entfernt werden.")
    return ScheduleResult(
        status="removed",
        task_name=task_name,
        script_path=str(script_path),
        details="Geplanter Task wurde entfernt.",
    )


def scheduled_task_status(
    *,
    task_name: str = DEFAULT_TASK_NAME,
    script_path: Path = DEFAULT_SCRIPT_PATH,
    runner: TaskRunner = run_schtasks,
) -> ScheduleResult:
    result = runner(["/Query", "/TN", task_name])
    combined = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part).strip()
    if result.returncode != 0:
        if is_missing_task_message(combined):
            return ScheduleResult(
                status="absent",
                task_name=task_name,
                script_path=str(script_path),
                details="Kein geplanter Task vorhanden.",
            )
        raise RuntimeError(combined or "Task-Status konnte nicht abgefragt werden.")
    return ScheduleResult(
        status="installed",
        task_name=task_name,
        script_path=str(script_path),
        details="Geplanter Task ist vorhanden.",
    )
