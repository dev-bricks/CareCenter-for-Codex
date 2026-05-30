"""Windows-Prozessprüfung für Codex."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import subprocess
from typing import Callable, Iterable

from .config import MaintenanceConfig


@dataclass(frozen=True, slots=True)
class ProcessInfo:
    pid: int
    name: str
    executable: str = ""
    command_line: str = ""
    parent_pid: int = 0
    created_at: str = ""
    cpu_ticks: int = 0  # KernelModeTime + UserModeTime in 100-ns-Einheiten (kumulativ)


ProcessProvider = Callable[[], list[ProcessInfo]]

# Electron-Hilfsprozess-Typen werden ueber --type=<typ> erkannt;
# der Hauptprozess (Browser) traegt keinen --type-Schalter.
_TYPE_PATTERN = re.compile(r"--type=([a-z0-9-]+)")

# Unterdrueckt das kurze Aufblitzen von Konsolenfenstern (PowerShell/taskkill/schtasks),
# wenn die windowed Tray-EXE Subprozesse startet.
CREATE_NO_WINDOW = 0x08000000


def no_window_kwargs() -> dict[str, object]:
    if os.name == "nt":
        return {"creationflags": CREATE_NO_WINDOW}
    return {}


def _as_process_list(raw: object) -> list[dict[str, object]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


def windows_processes() -> list[ProcessInfo]:
    """Lese laufende Prozesse über PowerShell, ohne externe Python-Dependencies."""
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        (
            "Get-CimInstance Win32_Process | "
            "Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine,"
            "@{N='CpuTicks';E={ [int64]$_.UserModeTime + [int64]$_.KernelModeTime }},"
            "@{N='CreationDate';E={ if ($_.CreationDate) { $_.CreationDate.ToString('s') } else { '' } }} | "
            "ConvertTo-Json -Compress"
        ),
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **no_window_kwargs(),
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return []

    try:
        rows = _as_process_list(json.loads(completed.stdout))
    except json.JSONDecodeError:
        return []

    processes: list[ProcessInfo] = []
    for row in rows:
        try:
            pid = int(row.get("ProcessId") or 0)
        except (TypeError, ValueError):
            continue
        name = str(row.get("Name") or "")
        executable = str(row.get("ExecutablePath") or "")
        command_line = str(row.get("CommandLine") or "")
        try:
            parent_pid = int(row.get("ParentProcessId") or 0)
        except (TypeError, ValueError):
            parent_pid = 0
        created_at = str(row.get("CreationDate") or "")
        try:
            cpu_ticks = int(row.get("CpuTicks") or 0)
        except (TypeError, ValueError):
            cpu_ticks = 0
        if pid:
            processes.append(
                ProcessInfo(
                    pid, name, executable, command_line, parent_pid, created_at, cpu_ticks
                )
            )
    return processes


def find_codex_processes(
    config: MaintenanceConfig,
    provider: ProcessProvider | None = None,
    *,
    include_self: bool = False,
) -> list[ProcessInfo]:
    """Finde Codex-Prozesse nach Namen und Pfadhinweisen."""
    provider = provider or windows_processes
    own_pid = os.getpid()
    configured_names = {name.lower() for name in config.codex_process_names}
    matches: list[ProcessInfo] = []

    for process in provider():
        if not include_self and process.pid == own_pid:
            continue
        haystack = " ".join(
            [process.name, process.executable, process.command_line]
        ).lower()
        name_match = process.name.lower().removesuffix(".exe") in configured_names
        path_match = "\\codex\\" in haystack or "codex.exe" in haystack
        if name_match or path_match:
            matches.append(process)

    return sorted(matches, key=lambda item: (item.name.lower(), item.pid))


def describe_processes(processes: Iterable[ProcessInfo]) -> str:
    rows = []
    for process in processes:
        path = process.executable or process.command_line
        rows.append(f"{process.pid} {process.name} {path}".strip())
    return "\n".join(rows)


def process_type(process: ProcessInfo) -> str:
    """Electron-Prozesstyp: 'main' fuer den Browserprozess, sonst der --type-Wert."""
    match = _TYPE_PATTERN.search(process.command_line)
    return match.group(1) if match else "main"


def _normalise_path(path: str) -> str:
    return path.replace("/", "\\").strip().strip('"').lower()


def matches_codex_executable(process: ProcessInfo, config: MaintenanceConfig) -> bool:
    """Praezise Zuordnung ueber den EXAKTEN Exe-Pfad (nicht ueber Substrings).

    Bewusst eng gehalten, weil das Ergebnis fuer das Beenden von Prozessen genutzt
    wird. Ein blosses Vorkommen von 'codex' in einer Kommandozeile reicht NICHT.
    """
    target = _normalise_path(config.codex_executable)
    exe = _normalise_path(process.executable)
    if target and exe == target:
        return True
    # Store-Version: versionsabhaengiger WindowsApps-Pfad -> ueber stabilen Marker erkennen,
    # aber nur bei Basisname Codex.exe (kein Over-Matching fremder Prozesse).
    marker = _normalise_path(getattr(config, "codex_store_marker", "") or "")
    if marker and marker in exe and exe.endswith("\\codex.exe"):
        return True
    # Fallback: Hauptprozess kennt manchmal keinen ExecutablePath, aber die
    # Kommandozeile beginnt mit dem (ggf. zitierten) Exe-Pfad.
    cmd = _normalise_path(process.command_line)
    if target and (cmd == target or cmd.startswith(target + " ")):
        return True
    if marker and marker in cmd and "codex.exe" in cmd:
        return True
    return False


def find_codex_processes_by_executable(
    config: MaintenanceConfig,
    provider: ProcessProvider | None = None,
    *,
    include_self: bool = False,
) -> list[ProcessInfo]:
    """Finde Codex-Prozesse ausschliesslich ueber den exakten konfigurierten Exe-Pfad."""
    provider = provider or windows_processes
    own_pid = os.getpid()
    matches = [
        process
        for process in provider()
        if (include_self or process.pid != own_pid)
        and matches_codex_executable(process, config)
    ]
    return sorted(matches, key=lambda item: item.pid)


def build_children_map(processes: Iterable[ProcessInfo]) -> dict[int, list[int]]:
    children: dict[int, list[int]] = {}
    for process in processes:
        children.setdefault(process.parent_pid, []).append(process.pid)
    return children


def descendant_pids(root_pid: int, processes: Iterable[ProcessInfo]) -> set[int]:
    """Alle Nachfahren-PIDs von root_pid (ohne root_pid selbst)."""
    children = build_children_map(processes)
    result: set[int] = set()
    stack = list(children.get(root_pid, []))
    while stack:
        pid = stack.pop()
        if pid in result or pid == root_pid:
            continue
        result.add(pid)
        stack.extend(children.get(pid, []))
    return result


def tree_pids(root_pid: int, processes: Iterable[ProcessInfo]) -> set[int]:
    """root_pid plus alle Nachfahren."""
    return {root_pid} | descendant_pids(root_pid, processes)
