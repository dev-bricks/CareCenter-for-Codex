"""Regressionstests fuer den Bugsweep am 2026-09-28 (SOFTWARE_BUGSEARCH).

Umfasst:
1. config_audit: _extract_mcp_package Unterstuetzung fuer Scoped Packages (@scope/pkg-mcp) und command-Pfade
2. config_audit: fix_duplicate_mcp Bevorzugung von node_modules in command
3. config_audit: _parse_toml_sections mit Trailing-Comments auf Section-Headers
4. single_instance: SingleInstanceGuard Win32 Error-Handling & Lockfile-Fallback wenn Mutex fehlschlaegt
5. automation_control: Case- & Whitespace-Resilienz fuer Status-Felder ('active', 'Active', 'ACTIVE ')
6. scheduler: build_runner_script Resilienz gegen undefiniertes PYTHONPATH
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import tomlkit

from codex_logdatenbank_wartung.automation_control import (
    ACTIVE,
    PAUSED,
    load_automations,
    pause_active_automations,
)
from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.config_audit import (
    _extract_mcp_package,
    _parse_toml_sections,
    fix_duplicate_mcp,
    fix_unused_plugins,
)
from codex_logdatenbank_wartung.scheduler import build_runner_script
from codex_logdatenbank_wartung.single_instance import SingleInstanceGuard


def test_extract_mcp_package_from_command_without_args() -> None:
    data = {
        "command": "C:/Users/lukas/AppData/Roaming/npm/node_modules/ellmos-codecommander-mcp/dist/index.js",
        "args": "",
    }
    extracted = _extract_mcp_package(data)
    assert extracted == "ellmos-codecommander-mcp"


def test_extract_mcp_package_scoped_packages() -> None:
    data_node = {
        "command": "node",
        "args": '["C:/npm/node_modules/@modelcontextprotocol/server-filesystem-mcp/dist/index.js"]',
    }
    assert _extract_mcp_package(data_node) == "@modelcontextprotocol/server-filesystem-mcp"

    data_npx = {
        "command": "npx",
        "args": '["-y", "@modelcontextprotocol/server-filesystem-mcp"]',
    }
    assert _extract_mcp_package(data_npx) == "@modelcontextprotocol/server-filesystem-mcp"

    data_other_scope = {
        "command": "npx",
        "args": '["-y", "@custom/server-filesystem-mcp"]',
    }
    assert _extract_mcp_package(data_other_scope) == "@custom/server-filesystem-mcp"
    assert _extract_mcp_package(data_npx) != _extract_mcp_package(data_other_scope)


def test_fix_duplicate_mcp_keeps_node_modules_in_command() -> None:
    toml = """
[mcp_servers.srv1]
command = "C:/npm/node_modules/ellmos-codecommander-mcp/dist/index.js"
args = []

[mcp_servers.srv2]
command = "npx"
args = ["-y", "ellmos-codecommander-mcp"]
"""
    with tempfile.TemporaryDirectory() as tmp:
        codex_home = Path(tmp) / ".codex"
        codex_home.mkdir(parents=True, exist_ok=True)
        config_file = codex_home / "config.toml"
        config_file.write_text(toml, encoding="utf-8")
        config = MaintenanceConfig(database_path=str(codex_home / "logs_2.sqlite"))

        removed = fix_duplicate_mcp(config)
        assert removed == 1

        new_text = config_file.read_text(encoding="utf-8")
        assert "srv1" in new_text
        assert "srv2" not in new_text


def test_parse_toml_sections_handles_trailing_comments_on_headers() -> None:
    text = """
[mcp_servers.test] # inline comment on header
command = "node"
args = ["test-mcp"]

[plugins."build-ios-apps@openai-curated"] # disabled plugin
enabled = true
"""
    sections = _parse_toml_sections(text)
    assert "mcp_servers.test" in sections
    assert 'plugins."build-ios-apps@openai-curated"' in sections
    assert sections['plugins."build-ios-apps@openai-curated"']["enabled"] == "true"


def test_single_instance_guard_fallback_when_mutex_fails(tmp_path: Path) -> None:
    lock_file = tmp_path / "tray.lock"
    guard = SingleInstanceGuard("Invalid\\Mutex\\Name", lock_file)

    # Simulate CreateMutexW returning NULL (0) with ERROR_ACCESS_DENIED (5)
    mock_kernel32 = MagicMock()
    mock_kernel32.CreateMutexW.return_value = 0
    mock_kernel32.GetLastError.return_value = 5

    with patch("os.name", "nt"), patch("ctypes.windll.kernel32", mock_kernel32, create=True):
        acquired = guard.acquire()
        assert acquired is True
        assert lock_file.exists()

        # Second attempt with same lock_file should fail
        guard2 = SingleInstanceGuard("Invalid\\Mutex\\Name", lock_file)
        acquired2 = guard2.acquire()
        assert acquired2 is False
        assert guard2.already_running is True

        guard.release()
        assert not lock_file.exists()


def test_single_instance_guard_closes_handle_on_already_exists(tmp_path: Path) -> None:
    lock_file = tmp_path / "tray.lock"
    guard = SingleInstanceGuard("TestMutex", lock_file)

    mock_kernel32 = MagicMock()
    mock_kernel32.CreateMutexW.return_value = 1234
    mock_kernel32.GetLastError.return_value = 183  # ERROR_ALREADY_EXISTS

    with patch("os.name", "nt"), patch("ctypes.windll.kernel32", mock_kernel32, create=True):
        acquired = guard.acquire()
        assert acquired is False
        assert guard.already_running is True
        mock_kernel32.CloseHandle.assert_called_once_with(1234)


def test_automation_control_case_insensitive_status(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    folder = codex_home / "automations" / "my-job"
    folder.mkdir(parents=True)
    toml_path = folder / "automation.toml"

    doc = tomlkit.document()
    doc["id"] = "my-job"
    doc["name"] = "My Job"
    doc["status"] = "active"  # Lowercase status!
    doc["updated_at"] = 1
    toml_path.write_text(tomlkit.dumps(doc), encoding="utf-8")

    config = MaintenanceConfig(database_path=str(codex_home / "logs_2.sqlite"))

    records = load_automations(config)
    assert len(records) == 1
    assert records[0].status == ACTIVE

    # pause_active_automations should properly detect and pause it
    res = pause_active_automations(config)
    assert res.status == "ok"
    assert "my-job" in res.changed_ids

    parsed = tomlkit.parse(toml_path.read_text(encoding="utf-8"))
    assert parsed["status"] == PAUSED


def test_scheduler_runner_script_defined_pythonpath(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    script = build_runner_script(
        config_path=config_path,
        project_root=tmp_path / "project",
        python_executable=tmp_path / "python.exe",
    )
    assert 'if defined PYTHONPATH (set "PYTHONPATH=' in script
    assert 'else (set "PYTHONPATH=' in script


def test_fix_unused_plugins_disables_bare_names(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    codex_home.mkdir(parents=True, exist_ok=True)
    config_file = codex_home / "config.toml"
    config_file.write_text(
        '[plugins.build-ios-apps]\nenabled = true\n\n[plugins."build-macos-apps"]\nenabled = true\n',
        encoding="utf-8",
    )
    config = MaintenanceConfig(database_path=str(codex_home / "logs_2.sqlite"))

    fixed = fix_unused_plugins(config)
    assert fixed == 2

    doc = tomlkit.parse(config_file.read_text(encoding="utf-8"))
    assert doc["plugins"]["build-ios-apps"]["enabled"] is False
    assert doc["plugins"]["build-macos-apps"]["enabled"] is False
