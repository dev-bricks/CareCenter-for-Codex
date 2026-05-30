from __future__ import annotations

from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.processes import (
    ProcessInfo,
    descendant_pids,
    find_codex_processes_by_executable,
    process_type,
    tree_pids,
)


CODEX_EXE = r"C:\Users\dev\AppData\Local\Programs\Codex\Codex.exe"


def make_config() -> MaintenanceConfig:
    return MaintenanceConfig(codex_executable=CODEX_EXE)


def test_process_type_parses_electron_helper_types() -> None:
    main = ProcessInfo(100, "Codex.exe", CODEX_EXE, f'"{CODEX_EXE}" ')
    renderer = ProcessInfo(
        101, "Codex.exe", CODEX_EXE, f'"{CODEX_EXE}" --type=renderer --lang=de'
    )
    gpu = ProcessInfo(102, "Codex.exe", CODEX_EXE, f"{CODEX_EXE} --type=gpu-process")

    assert process_type(main) == "main"
    assert process_type(renderer) == "renderer"
    assert process_type(gpu) == "gpu-process"


def test_find_by_executable_uses_exact_path_not_substring() -> None:
    config = make_config()
    processes = [
        ProcessInfo(1, "Codex.exe", CODEX_EXE, f'"{CODEX_EXE}"'),
        # Fremdprozess, der nur "codex" im Kommandozeilentext trägt -> darf NICHT matchen
        ProcessInfo(2, "node.exe", r"C:\Program Files\nodejs\node.exe", "node serve --dir C:\\Users\\dev\\.codex"),
        # Anderes Codex an fremdem Pfad -> darf NICHT als unsere Ziel-Exe matchen
        ProcessInfo(3, "Codex.exe", r"C:\Other\Codex.exe", r'"C:\Other\Codex.exe"'),
    ]
    matches = find_codex_processes_by_executable(config, lambda: processes)
    assert [p.pid for p in matches] == [1]


def test_find_by_executable_also_matches_store_version() -> None:
    config = make_config()
    store_exe = r"C:\Program Files\WindowsApps\OpenAI.Codex_26.513.4821.0_x64__2p2nqsd0c76g0\app\Codex.exe"
    processes = [
        ProcessInfo(1, "Codex.exe", store_exe, f'"{store_exe}"'),                      # Store-Version -> match
        ProcessInfo(2, "Spotify.exe", r"C:\Program Files\WindowsApps\Spotify_1.2\Spotify.exe", ""),  # andere Store-App -> kein match
        ProcessInfo(3, "Codex.exe", CODEX_EXE, f'"{CODEX_EXE}"'),                       # Standalone -> match
    ]
    matches = find_codex_processes_by_executable(config, lambda: processes)
    assert [p.pid for p in matches] == [1, 3]


def test_tree_and_descendants() -> None:
    processes = [
        ProcessInfo(100, "Codex.exe", CODEX_EXE, f'"{CODEX_EXE}"', parent_pid=10),
        ProcessInfo(101, "Codex.exe", CODEX_EXE, f"{CODEX_EXE} --type=gpu-process", parent_pid=100),
        ProcessInfo(102, "Codex.exe", CODEX_EXE, f"{CODEX_EXE} --type=renderer", parent_pid=100),
        ProcessInfo(103, "Codex.exe", CODEX_EXE, f"{CODEX_EXE} --type=utility", parent_pid=101),
    ]
    assert descendant_pids(100, processes) == {101, 102, 103}
    assert tree_pids(100, processes) == {100, 101, 102, 103}
