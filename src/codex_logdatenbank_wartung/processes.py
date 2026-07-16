"""Windows-Prozessprüfung für Codex."""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .config import (
    DEFAULT_RUNTIME_MCP_DUPLICATE_MIN_AGE_SECONDS,
    MaintenanceConfig,
)


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


def no_window_kwargs() -> dict[str, Any]:
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


def _int_value(value: object, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


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
        # Erst strip(), dann sanitisieren: das abschliessende \r\n von PowerShell
        # darf nicht als Steuerzeichen-Escape in den JSON-Body wandern (Extra-data-Fehler).
        # PowerShell's ConvertTo-Json laesst manchmal rohe Steuerzeichen (z.B.
        # Null-Bytes in CommandLine-Feldern) unescaped stehen (JSON-RFC-Verletzung).
        # Loesung: erst Whitespace-Strip, dann U+0000-U+001F durch \uXXXX ersetzen.
        stdout_clean = re.sub(
            r'[\x00-\x1f]',
            lambda m: f'\\u{ord(m.group()):04x}',
            completed.stdout.strip(),
        )
        rows = _as_process_list(json.loads(stdout_clean))
    except json.JSONDecodeError:
        return []

    processes: list[ProcessInfo] = []
    for row in rows:
        pid = _int_value(row.get("ProcessId"))
        if not pid:
            continue
        name = str(row.get("Name") or "")
        executable = str(row.get("ExecutablePath") or "")
        command_line = str(row.get("CommandLine") or "")
        parent_pid = _int_value(row.get("ParentProcessId"))
        created_at = str(row.get("CreationDate") or "")
        cpu_ticks = _int_value(row.get("CpuTicks"))
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
        path_match = any(
            marker in haystack
            for marker in (
                r"\windowsapps\openai.codex_",
                r"\npm\node_modules\@openai\codex",
                r"\appdata\local\openai\codex",
            )
        )
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
    if match:
        return match.group(1)
    # Neuere Store-Builds (ab 26.707) starten den Rust-App-Server als
    # app/resources/codex.exe. Ohne Sonderfall wuerde er als Electron-Main und
    # damit als rendererloser Zombie klassifiziert.
    if "app-server" in process.command_line.lower():
        return "app-server"
    return "main"


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
    # Store-Version: versionsabhaengiger WindowsApps-Pfad -> ueber stabilen Marker erkennen.
    # Aktuelle Builds verwenden ChatGPT.exe fuer Electron und codex.exe fuer den
    # eingebetteten App-Server; beide gehoeren zum selben signierten Store-Paket.
    marker = _normalise_path(getattr(config, "codex_store_marker", "") or "")
    if marker and marker in exe and exe.rsplit("\\", 1)[-1] in {"codex.exe", "chatgpt.exe"}:
        return True
    # Fallback: Hauptprozess kennt manchmal keinen ExecutablePath, aber die
    # Kommandozeile beginnt mit dem (ggf. zitierten) Exe-Pfad.
    cmd = _normalise_path(process.command_line)
    if target and (cmd == target or cmd.startswith(target + " ")):
        return True
    return bool(
        marker
        and marker in cmd
        and ("codex.exe" in cmd or "chatgpt.exe" in cmd)
    )


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


_NPM_CODEX_MARKER = r"\npm\node_modules\@openai\codex"
_EMBEDDED_CODEX_MARKER = r"\appdata\local\openai\codex\bin"


def is_companion_orphan(process: ProcessInfo, *, min_age_seconds: int = 300) -> bool:
    """Erkennt verwaiste Companion-app-server-Prozesse (codex-plugin-cc #277).

    Zwei Signaturen:
    1. npm-global: Pfad enthaelt @openai/codex, CommandLine enthaelt 'app-server'
       aber NICHT '--analytics-default-enabled' (das waere der Desktop-eigene).
    2. embedded: Pfad enthaelt AppData/Local/OpenAI/Codex/bin/, CommandLine enthaelt
       'app-server --listen stdio://'.
    """
    cmd = process.command_line.lower()
    exe = (process.executable or "").lower()
    full = f"{exe} {cmd}"

    if "app-server" not in cmd:
        return False
    if "--analytics-default-enabled" in cmd:
        return False

    is_npm = _NPM_CODEX_MARKER.lower() in full
    is_embedded = _EMBEDDED_CODEX_MARKER.lower() in full and "--listen stdio://" in cmd

    if not (is_npm or is_embedded):
        return False

    if min_age_seconds > 0 and process.created_at:
        from datetime import datetime

        try:
            created = datetime.fromisoformat(process.created_at)
            age = (datetime.now() - created).total_seconds()
            if age < min_age_seconds:
                return False
        except (ValueError, TypeError):
            pass

    return True


def find_companion_orphans(
    provider: ProcessProvider | None = None,
    *,
    min_age_seconds: int = 300,
) -> list[ProcessInfo]:
    """Finde alle verwaisten Companion-app-server-Prozesse."""
    provider = provider or windows_processes
    return [
        p
        for p in provider()
        if is_companion_orphan(p, min_age_seconds=min_age_seconds)
    ]


def _created_datetime(process: ProcessInfo) -> datetime | None:
    """Parse den CIM-Zeitstempel; unbekannte Zeiten bleiben fail-closed."""
    if not process.created_at:
        return None
    try:
        value = datetime.fromisoformat(process.created_at)
    except ValueError:
        return None
    if value.tzinfo is not None:
        value = value.astimezone().replace(tzinfo=None)
    return value


def _is_desktop_app_server(process: ProcessInfo) -> bool:
    """Nur der eingebettete Store-App-Server, niemals npm-/CLI-app-server."""
    executable = _normalise_path(process.executable)
    command = process.command_line.lower()
    return bool(
        process.name.lower() == "codex.exe"
        and r"\windowsapps\openai.codex_" in executable
        and "app-server" in command
        and "--analytics-default-enabled" in command
    )


def _is_runtime_generation_anchor(process: ProcessInfo, app_server_pid: int) -> bool:
    if process.parent_pid != app_server_pid or process.name.lower() != "node_repl.exe":
        return False
    haystack = _normalise_path(f"{process.executable} {process.command_line}")
    return r"\openai\codex\runtimes\cua_node" in haystack


def _is_runtime_mcp_launcher(process: ProcessInfo, app_server_pid: int) -> bool:
    """Enger Root-Matcher: direkter node/cmd-Kindprozess mit MCP-Signatur."""
    if process.parent_pid != app_server_pid:
        return False
    if process.name.lower() not in {"cmd.exe", "node.exe"}:
        return False
    haystack = f"{process.executable} {process.command_line}".lower()
    return "mcp" in haystack


def _runtime_root_signature(process: ProcessInfo) -> str:
    command = re.sub(r"\s+", " ", process.command_line.strip()).lower()
    executable = _normalise_path(process.executable)
    return f"{process.name.lower()}|{executable}|{command}"


def find_runtime_mcp_duplicate_roots(
    provider: ProcessProvider | None = None,
    *,
    min_age_seconds: int = DEFAULT_RUNTIME_MCP_DUPLICATE_MIN_AGE_SECONDS,
    generation_gap_seconds: int = 90,
    batch_window_seconds: int = 30,
    minimum_matching_mcp_roots: int = 2,
    now: datetime | None = None,
) -> list[ProcessInfo]:
    """Finde nur sicher wiederholte, alte MCP-Launcher des Desktop-App-Servers.

    Codex startet jede Runtime-Generation mit einem direkten ``node_repl.exe``-
    Kind. MCP-Launcher derselben Generation entstehen im engen Zeitfenster um
    diesen Anker. Mehrere Anker innerhalb kurzer Zeit werden als ein Start-Cohort
    behandelt und gemeinsam geschuetzt. Entfernt werden nur Roots, deren exakte
    Prozesssignatur auch im neuesten Cohort vorkommt. Der neueste Cohort, fremde
    Kindprozesse, der Desktop-App-Server selbst und CLI-app-server sind tabu.

    Die Rueckgabe enthaelt nur direkte Launcher-Roots. Der Aufrufer beendet deren
    Baum mit ``taskkill /T``; Nachfahren werden deshalb nicht separat geliefert.
    """
    provider = provider or windows_processes
    processes = provider()
    current = now or datetime.now()
    if current.tzinfo is not None:
        current = current.astimezone().replace(tzinfo=None)

    gap = timedelta(seconds=max(0, generation_gap_seconds))
    window = timedelta(seconds=max(0, batch_window_seconds))
    min_age = max(0, min_age_seconds)
    minimum_roots = max(1, minimum_matching_mcp_roots)
    duplicates: list[ProcessInfo] = []

    for app_server in (
        process for process in processes if _is_desktop_app_server(process)
    ):
        direct_children = [
            process for process in processes if process.parent_pid == app_server.pid
        ]
        anchor_processes = [
            process
            for process in direct_children
            if _is_runtime_generation_anchor(process, app_server.pid)
        ]
        parsed_anchors = [
            (_created_datetime(process), process) for process in anchor_processes
        ]
        # Ein unbekannter Anker-Zeitstempel koennte die neueste Generation sein:
        # dann darf keine aeltere Generation irrtuemlich als "neueste" gelten.
        if any(started is None for started, _process in parsed_anchors):
            continue
        anchors = sorted(
            (
                (started, process)
                for started, process in parsed_anchors
                if started is not None
            ),
            key=lambda item: (item[0], item[1].pid),
        )
        if len(anchors) < 2:
            continue

        cohorts: list[list[tuple[datetime, ProcessInfo]]] = []
        for started, process in anchors:
            if not cohorts or started - cohorts[-1][-1][0] > gap:
                cohorts.append([])
            cohorts[-1].append((started, process))
        if len(cohorts) < 2:
            continue

        timed_roots: list[tuple[datetime, ProcessInfo]] = []
        for process in direct_children:
            if not (
                _is_runtime_generation_anchor(process, app_server.pid)
                or _is_runtime_mcp_launcher(process, app_server.pid)
            ):
                continue
            if root_started := _created_datetime(process):
                timed_roots.append((root_started, process))

        cohort_roots: list[list[ProcessInfo]] = []
        for cohort in cohorts:
            start = cohort[0][0] - window
            end = cohort[-1][0] + window
            cohort_roots.append(
                [process for started, process in timed_roots if start <= started <= end]
            )

        newest_signatures = {
            _runtime_root_signature(process) for process in cohort_roots[-1]
        }
        if not newest_signatures:
            continue

        for cohort, roots in zip(cohorts[:-1], cohort_roots[:-1], strict=True):
            cohort_age = (current - cohort[-1][0]).total_seconds()
            if cohort_age < min_age:
                continue
            matching: list[ProcessInfo] = []
            for process in roots:
                process_started = _created_datetime(process)
                if process_started is None:
                    continue
                process_age = (current - process_started).total_seconds()
                if process_age < min_age:
                    continue
                if _runtime_root_signature(process) in newest_signatures:
                    matching.append(process)
            matching_mcp_signatures = {
                _runtime_root_signature(process)
                for process in matching
                if _is_runtime_mcp_launcher(process, app_server.pid)
            }
            matching_anchor = any(
                _is_runtime_generation_anchor(process, app_server.pid)
                for process in matching
            )
            if not matching_anchor or len(matching_mcp_signatures) < minimum_roots:
                continue
            duplicates.extend(matching)

    unique = {process.pid: process for process in duplicates}
    return sorted(
        unique.values(),
        key=lambda process: (_created_datetime(process) or datetime.max, process.pid),
    )


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
