from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.processes import (
    ProcessInfo,
    descendant_pids,
    find_codex_processes,
    find_codex_processes_by_executable,
    find_companion_orphans,
    find_runtime_mcp_duplicate_roots,
    is_companion_orphan,
    process_type,
    tree_pids,
    windows_processes,
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


def test_process_type_recognises_embedded_app_server() -> None:
    app_server = ProcessInfo(
        103,
        "codex.exe",
        r"C:\Program Files\WindowsApps\OpenAI.Codex_26.707.3563.0_x64__2p2nqsd0c76g0\app\resources\codex.exe",
        '"...\\app\\resources\\codex.exe" -c features.code_mode_host=true app-server --analytics-default-enabled',
    )
    assert process_type(app_server) == "app-server"


def test_find_by_executable_uses_exact_path_not_substring() -> None:
    config = make_config()
    processes = [
        ProcessInfo(1, "Codex.exe", CODEX_EXE, f'"{CODEX_EXE}"'),
        # Fremdprozess, der nur "codex" im Kommandozeilentext traegt -> darf NICHT matchen
        ProcessInfo(2, "node.exe", r"C:\Program Files\nodejs\node.exe", "node serve --dir C:\\Users\\dev\\.codex"),
        # Anderes Codex an fremdem Pfad -> darf NICHT als unsere Ziel-Exe matchen
        ProcessInfo(3, "Codex.exe", r"C:\Other\Codex.exe", r'"C:\Other\Codex.exe"'),
    ]
    matches = find_codex_processes_by_executable(config, lambda: processes)
    assert [p.pid for p in matches] == [1]


def test_general_finder_excludes_carecenter_codex_maintenance_path() -> None:
    config = make_config()
    processes = [
        ProcessInfo(
            1,
            "CareCenterForCodex.exe",
            r"C:\_Local_DEV\codex-maintenance\bin\CareCenterForCodex.exe",
            r'"C:\_Local_DEV\codex-maintenance\bin\CareCenterForCodex.exe"',
        ),
        ProcessInfo(
            2,
            "codex.exe",
            r"C:\Users\dev\AppData\Roaming\npm\node_modules\@openai\codex\vendor\codex.exe",
            "codex.exe",
        ),
    ]
    matches = find_codex_processes(config, lambda: processes)
    assert [p.pid for p in matches] == [2]


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


def test_find_by_executable_matches_current_chatgpt_named_store_tree() -> None:
    config = make_config()
    root = r"C:\Program Files\WindowsApps\OpenAI.Codex_26.707.3563.0_x64__2p2nqsd0c76g0\app"
    processes = [
        ProcessInfo(10, "ChatGPT.exe", root + r"\ChatGPT.exe", '"' + root + r'\ChatGPT.exe"'),
        ProcessInfo(11, "ChatGPT.exe", root + r"\ChatGPT.exe", '"' + root + r'\ChatGPT.exe" --type=renderer', parent_pid=10),
        ProcessInfo(12, "codex.exe", root + r"\resources\codex.exe", '"' + root + r'\resources\codex.exe" app-server --analytics-default-enabled', parent_pid=10),
    ]
    matches = find_codex_processes_by_executable(config, lambda: processes)
    assert [p.pid for p in matches] == [10, 11, 12]
    assert [process_type(p) for p in matches] == ["main", "renderer", "app-server"]


def test_is_companion_orphan_npm_global() -> None:
    proc = ProcessInfo(
        pid=1234,
        name="codex.exe",
        executable=r"C:\Users\Example\AppData\Roaming\npm\node_modules\@openai\codex\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\codex\codex.exe",
        command_line=r"codex.exe app-server",
        created_at="2026-05-31T10:00:00",
    )
    assert is_companion_orphan(proc, min_age_seconds=0) is True


def test_is_companion_orphan_embedded_stdio() -> None:
    proc = ProcessInfo(
        pid=5678,
        name="codex.exe",
        executable=r"C:\Users\Example\AppData\Local\OpenAI\Codex\bin\7dea4a003bc76627\codex.exe",
        command_line=r'"C:\Users\Example\AppData\Local\OpenAI\Codex\bin\7dea4a003bc76627\codex.exe" app-server --listen stdio://',
        created_at="2026-05-31T10:00:00",
    )
    assert is_companion_orphan(proc, min_age_seconds=0) is True


def test_is_companion_orphan_rejects_desktop_app_server() -> None:
    proc = ProcessInfo(
        pid=9999,
        name="codex.exe",
        executable=r"C:\Program Files\WindowsApps\OpenAI.Codex_26.527.3686.0_x64__2p2nqsd0c76g0\app\resources\codex.exe",
        command_line=r'"...\app\resources\codex.exe" app-server --analytics-default-enabled',
        created_at="2026-05-31T10:00:00",
    )
    assert is_companion_orphan(proc, min_age_seconds=0) is False


def test_is_companion_orphan_respects_min_age() -> None:
    from datetime import datetime

    now = datetime.now().isoformat()
    proc = ProcessInfo(
        pid=1111,
        name="codex.exe",
        executable=r"C:\Users\Example\AppData\Roaming\npm\node_modules\@openai\codex\vendor\codex.exe",
        command_line=r"codex.exe app-server",
        created_at=now,
    )
    assert is_companion_orphan(proc, min_age_seconds=300) is False


def test_find_companion_orphans_filters_correctly() -> None:
    procs = [
        ProcessInfo(1, "codex.exe", r"C:\Users\Example\AppData\Roaming\npm\node_modules\@openai\codex\v\codex.exe", "codex.exe app-server", created_at="2026-05-31T10:00:00"),
        ProcessInfo(2, "Codex.exe", r"C:\Program Files\WindowsApps\OpenAI.Codex\app\Codex.exe", "Codex.exe", created_at="2026-05-31T10:00:00"),
        ProcessInfo(3, "node.exe", r"C:\Program Files\nodejs\node.exe", "node index.js", created_at="2026-05-31T10:00:00"),
    ]
    result = find_companion_orphans(provider=lambda: procs, min_age_seconds=0)
    assert len(result) == 1
    assert result[0].pid == 1


def _desktop_runtime_generations() -> list[ProcessInfo]:
    store_root = (
        r"C:\Program Files\WindowsApps\OpenAI.Codex_26.707.3563.0_x64__2p2nqsd0c76g0"
        r"\app\resources"
    )
    repl = r"C:\Users\Example\AppData\Local\OpenAI\Codex\runtimes\cua_node\abc\node_repl.exe"
    return [
        ProcessInfo(
            100,
            "codex.exe",
            store_root + r"\codex.exe",
            '"codex.exe" app-server --analytics-default-enabled',
            parent_pid=10,
            created_at="2026-07-16T09:00:00",
        ),
        # Alte, vollstaendig wiederholte Generation.
        ProcessInfo(110, "node_repl.exe", repl, f'"{repl}"', 100, "2026-07-16T09:10:00"),
        ProcessInfo(
            111,
            "cmd.exe",
            r"C:\Windows\System32\cmd.exe",
            'cmd.exe /c "npx.cmd -y ellmos-filecommander-mcp"',
            100,
            "2026-07-16T09:10:01",
        ),
        ProcessInfo(
            112,
            "node.exe",
            r"C:\Program Files\nodejs\node.exe",
            'node.exe ./mcp/server.mjs --stdio',
            100,
            "2026-07-16T09:10:02",
        ),
        # Nachfahre wird spaeter per taskkill /T erfasst, aber nicht als eigener Root geliefert.
        ProcessInfo(113, "node.exe", command_line="node dist/index.js", parent_pid=111,
                    created_at="2026-07-16T09:10:10"),
        # Zeitlich passend, aber kein MCP-Launcher: muss unangetastet bleiben.
        ProcessInfo(114, "pwsh.exe", command_line="pwsh -EncodedCommand AAA", parent_pid=100,
                    created_at="2026-07-16T09:10:03"),
        # Neueste Generation bleibt immer erhalten.
        ProcessInfo(210, "node_repl.exe", repl, f'"{repl}"', 100, "2026-07-16T09:20:00"),
        ProcessInfo(
            211,
            "cmd.exe",
            r"C:\Windows\System32\cmd.exe",
            'cmd.exe /c "npx.cmd -y ellmos-filecommander-mcp"',
            100,
            "2026-07-16T09:20:01",
        ),
        ProcessInfo(
            212,
            "node.exe",
            r"C:\Program Files\nodejs\node.exe",
            'node.exe ./mcp/server.mjs --stdio',
            100,
            "2026-07-16T09:20:02",
        ),
    ]


def test_runtime_mcp_reaper_finds_only_old_repeated_desktop_roots() -> None:
    processes = _desktop_runtime_generations()

    result = find_runtime_mcp_duplicate_roots(
        provider=lambda: processes,
        now=datetime.fromisoformat("2026-07-16T09:20:30"),
        min_age_seconds=300,
        minimum_matching_mcp_roots=2,
    )

    assert [process.pid for process in result] == [110, 111, 112]


def test_runtime_mcp_reaper_default_waits_until_every_root_is_one_hour_old() -> None:
    processes = _desktop_runtime_generations()

    one_root_still_too_young = find_runtime_mcp_duplicate_roots(
        provider=lambda: processes,
        now=datetime.fromisoformat("2026-07-16T10:10:01"),
    )
    all_roots_old_enough = find_runtime_mcp_duplicate_roots(
        provider=lambda: processes,
        now=datetime.fromisoformat("2026-07-16T10:10:02"),
    )

    assert one_root_still_too_young == []
    assert [process.pid for process in all_roots_old_enough] == [110, 111, 112]


def test_runtime_mcp_reaper_keeps_single_or_fresh_generation() -> None:
    processes = _desktop_runtime_generations()

    single = find_runtime_mcp_duplicate_roots(
        provider=lambda: [process for process in processes if process.pid < 200],
        now=datetime.fromisoformat("2026-07-16T09:20:30"),
        min_age_seconds=300,
    )
    fresh = find_runtime_mcp_duplicate_roots(
        provider=lambda: processes,
        now=datetime.fromisoformat("2026-07-16T09:12:00"),
        min_age_seconds=300,
    )

    assert single == []
    assert fresh == []


def test_runtime_mcp_reaper_rejects_cli_app_server_and_incomplete_repeat() -> None:
    processes = _desktop_runtime_generations()
    cli_processes = [
        ProcessInfo(
            process.pid,
            process.name,
            process.executable.replace(r"C:\Program Files\WindowsApps", r"C:\Users\Example\AppData\Roaming\npm"),
            process.command_line.replace(" --analytics-default-enabled", ""),
            process.parent_pid,
            process.created_at,
        )
        for process in processes
    ]
    incomplete = [process for process in processes if process.pid not in {112, 212}]

    cli = find_runtime_mcp_duplicate_roots(
        provider=lambda: cli_processes,
        now=datetime.fromisoformat("2026-07-16T09:20:30"),
        min_age_seconds=300,
    )
    not_enough_evidence = find_runtime_mcp_duplicate_roots(
        provider=lambda: incomplete,
        now=datetime.fromisoformat("2026-07-16T09:20:30"),
        min_age_seconds=300,
        minimum_matching_mcp_roots=2,
    )

    assert cli == []
    assert not_enough_evidence == []


def test_tree_and_descendants() -> None:
    processes = [
        ProcessInfo(100, "Codex.exe", CODEX_EXE, f'"{CODEX_EXE}"', parent_pid=10),
        ProcessInfo(101, "Codex.exe", CODEX_EXE, f"{CODEX_EXE} --type=gpu-process", parent_pid=100),
        ProcessInfo(102, "Codex.exe", CODEX_EXE, f"{CODEX_EXE} --type=renderer", parent_pid=100),
        ProcessInfo(103, "Codex.exe", CODEX_EXE, f"{CODEX_EXE} --type=utility", parent_pid=101),
    ]
    assert descendant_pids(100, processes) == {101, 102, 103}
    assert tree_pids(100, processes) == {100, 101, 102, 103}


# ---------------------------------------------------------------------------
# windows_processes: Steuerzeichen im JSON-Output (Bug-Fix)
# ---------------------------------------------------------------------------

def _make_ps_result(stdout: str, returncode: int = 0) -> MagicMock:
    """Hilfsfunktion: subprocess.CompletedProcess-Mock fuer windows_processes()."""
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = ""
    return mock


def _buggy_ps_json_with_control_chars() -> str:
    """Simuliert PowerShell-Output: Null-Byte (chr(0)) im CommandLine-Feld PLUS
    das abschliessende \\r\\n wie PowerShell es immer anhaengt.

    Damit werden BEIDE Teile des Bugs abgedeckt:
    1. Null-Byte (0x00) im Stringwert -> json.loads scheitert an ungueltigem Steuerzeichen.
    2. Trailing \\r\\n -> nach Sanitisierung ohne vorherigen strip() werden \\r\\n
       zu \\u000d\\u000a ausserhalb der JSON-Struktur -> 'Extra data'-Fehler.
    """
    valid = json.dumps([{
        "ProcessId": 42,
        "ParentProcessId": 1,
        "Name": "test.exe",
        "ExecutablePath": "C:\\test.exe",
        "CommandLine": "PLACEHOLDER",
        "CpuTicks": 0,
        "CreationDate": "",
    }])
    # chr(0) erzeugt das Null-Byte-Zeichen ohne Literal-Null-Byte im Quelltext.
    json_with_null = valid.replace('"PLACEHOLDER"', '"test' + chr(0) + 'arg"')
    # chr(13) + chr(10) = \\r\\n wie PowerShell es an den JSON-Output anhaengt.
    return json_with_null + chr(13) + chr(10)


def test_windows_processes_tolerates_control_chars_in_commandline() -> None:
    """Bug-Fix: PowerShell laesst Steuerzeichen (z.B. Null-Bytes) in CommandLine
    unescaped stehen und haengt \\r\\n ans Ende. Beide zusammen liessen
    windows_processes() eine leere Liste zurueckgeben.

    Dieser Test sperrt BEIDE Haelften des Fixes fest:
    - Die Steuerzeichen-Sanitisierung (Null-Byte -> kein JSONDecodeError mehr)
    - Das strip() vor der Sanitisierung (kein 'Extra data' durch \\r\\n)
    """
    import pytest

    buggy_json = _buggy_ps_json_with_control_chars()

    # Haelfte 1: json.loads muss ohne Fix scheitern (Null-Byte im Stringwert).
    with pytest.raises(json.JSONDecodeError):
        json.loads(buggy_json)

    with patch("codex_logdatenbank_wartung.processes.subprocess.run") as mock_run:
        mock_run.return_value = _make_ps_result(buggy_json)
        result = windows_processes()

    # Haelfte 2: Nach dem Fix (strip + sanitize) muessen die Prozesse korrekt geparst werden.
    assert len(result) == 1
    assert result[0].pid == 42
    assert result[0].name == "test.exe"


def test_windows_processes_returns_empty_on_powershell_failure() -> None:
    """Fail-closed: Wenn PowerShell-Aufruf fehlschlaegt (returncode!=0), leere Liste."""
    with patch("codex_logdatenbank_wartung.processes.subprocess.run") as mock_run:
        mock_run.return_value = _make_ps_result("", returncode=1)
        result = windows_processes()
    assert result == []


def test_windows_processes_returns_empty_on_empty_stdout() -> None:
    """Fail-closed: Leerer stdout (PowerShell hat nichts ausgegeben) -> leere Liste."""
    with patch("codex_logdatenbank_wartung.processes.subprocess.run") as mock_run:
        mock_run.return_value = _make_ps_result("")
        result = windows_processes()
    assert result == []
