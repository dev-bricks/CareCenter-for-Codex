"""Tests fuer das Config-Audit-Modul (6c + 6d)."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.config_audit import (
    AuditReport,
    EmptyThread,
    audit_cli_installation,
    audit_config_toml,
    audit_threads,
    find_empty_threads,
    run_full_audit,
    _parse_toml_sections,
    _extract_mcp_package,
    _strip_inline_comment,
)


def _make_config(tmp: Path, toml_content: str = "", state_db: bool = False) -> MaintenanceConfig:
    codex_home = tmp / ".codex"
    codex_home.mkdir(parents=True, exist_ok=True)
    if toml_content:
        (codex_home / "config.toml").write_text(toml_content, encoding="utf-8")
    if state_db:
        db_path = codex_home / "state_5.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE threads (
                id TEXT PRIMARY KEY,
                name TEXT,
                created_at TEXT,
                total_tokens INTEGER,
                first_user_message TEXT
            )
        """)
        conn.commit()
        conn.close()
    return MaintenanceConfig(database_path=str(codex_home / "logs_2.sqlite"))


# ---------------------------------------------------------------------------
# TOML-Parser
# ---------------------------------------------------------------------------

def test_parse_toml_sections_basic():
    text = """
[mcp_servers.foo]
command = "npx"
args = ["-y", "ellmos-filecommander-mcp"]

[mcp_servers.bar]
command = "node"
args = ["C:/npm/node_modules/ellmos-filecommander-mcp/dist/index.js"]

[plugins."slack@openai-curated"]
enabled = true
"""
    sections = _parse_toml_sections(text)
    assert "mcp_servers.foo" in sections
    assert "mcp_servers.bar" in sections
    assert 'plugins."slack@openai-curated"' in sections


def test_strip_inline_comment_basic():
    assert _strip_inline_comment("true # default") == "true"
    assert _strip_inline_comment("true") == "true"
    assert _strip_inline_comment('"hello # world"') == '"hello # world"'
    assert _strip_inline_comment("120 # seconds") == "120"


def test_parse_toml_handles_inline_comments():
    text = """
[plugins."build-ios-apps@openai-curated"]
enabled = true # was deaktiviert

[mcp_servers.foo]
command = "node"
args = ["C:/path/to/mcp"] # pfad zum server
"""
    sections = _parse_toml_sections(text)
    assert sections['plugins."build-ios-apps@openai-curated"']["enabled"] == "true"
    assert sections["mcp_servers.foo"]["args"] == '["C:/path/to/mcp"]'


def test_extract_mcp_package_from_npx():
    data = {"command": "npx", "args": '["-y", "ellmos-filecommander-mcp"]'}
    assert _extract_mcp_package(data) == "ellmos-filecommander-mcp"


def test_extract_mcp_package_from_node_modules():
    data = {"command": "node", "args": '["C:/npm/node_modules/ellmos-filecommander-mcp/dist/index.js"]'}
    assert _extract_mcp_package(data) == "ellmos-filecommander-mcp"


# ---------------------------------------------------------------------------
# 6c: MCP-Duplikat-Erkennung
# ---------------------------------------------------------------------------

def test_audit_detects_mcp_duplicates():
    toml = """
[mcp_servers.codecommander]
command = "npx"
args = ["-y", "ellmos-codecommander-mcp"]
startup_timeout_sec = 120

[mcp_servers.ellmos-codecommander]
command = "node"
args = ["C:/npm/node_modules/ellmos-codecommander-mcp/dist/index.js"]
"""
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config(Path(tmp), toml)
        report = audit_config_toml(config)
        duplicates = [f for f in report.findings if f.category == "MCP-Duplikat"]
        assert len(duplicates) == 1
        assert "ellmos-codecommander-mcp" in duplicates[0].message


def test_audit_no_duplicates_when_clean():
    toml = """
[mcp_servers.ellmos-codecommander]
command = "node"
args = ["C:/npm/node_modules/ellmos-codecommander-mcp/dist/index.js"]

[mcp_servers.ellmos-filecommander]
command = "node"
args = ["C:/npm/node_modules/ellmos-filecommander-mcp/dist/index.js"]
"""
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config(Path(tmp), toml)
        report = audit_config_toml(config)
        duplicates = [f for f in report.findings if f.category == "MCP-Duplikat"]
        assert len(duplicates) == 0


# ---------------------------------------------------------------------------
# 6c: Ungenutzte Plugins
# ---------------------------------------------------------------------------

def test_audit_detects_unused_windows_plugins():
    toml = """
[plugins."build-ios-apps@openai-curated"]
enabled = true

[plugins."browser@openai-bundled"]
enabled = true
"""
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config(Path(tmp), toml)
        report = audit_config_toml(config)
        unused = [f for f in report.findings if f.category == "Ungenutztes Plugin"]
        assert len(unused) == 1
        assert "build-ios-apps" in unused[0].message


def test_audit_ignores_disabled_plugins():
    toml = """
[plugins."build-ios-apps@openai-curated"]
enabled = false
"""
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config(Path(tmp), toml)
        report = audit_config_toml(config)
        unused = [f for f in report.findings if f.category == "Ungenutztes Plugin"]
        assert len(unused) == 0


# ---------------------------------------------------------------------------
# CLI-Installation
# ---------------------------------------------------------------------------

def test_cli_audit_warns_when_not_in_path():
    with patch("codex_logdatenbank_wartung.config_audit.shutil.which", return_value=None):
        report = audit_cli_installation()
        critical = [f for f in report.findings if f.severity == "critical"]
        assert len(critical) == 1
        assert "PATH" in critical[0].message


def test_cli_audit_ok_when_in_path():
    with patch("codex_logdatenbank_wartung.config_audit.shutil.which", return_value=r"C:\npm\codex.ps1"):
        report = audit_cli_installation()
        critical = [f for f in report.findings if f.severity == "critical"]
        assert len(critical) == 0


# ---------------------------------------------------------------------------
# 6d: Leere Threads
# ---------------------------------------------------------------------------

def test_find_empty_threads_detects_zero_token_threads():
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config(Path(tmp), state_db=True)
        db_path = config.state_db_path
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO threads (id, name, created_at, total_tokens, first_user_message) "
            "VALUES ('t1', 'Neuer Chat', '2026-05-31', 0, '')"
        )
        conn.execute(
            "INSERT INTO threads (id, name, created_at, total_tokens, first_user_message) "
            "VALUES ('t2', 'RH Research', '2026-05-31', 14500, 'Hello')"
        )
        conn.commit()
        conn.close()

        empty = find_empty_threads(config)
        assert len(empty) == 1
        assert empty[0].thread_id == "t1"


def test_find_empty_threads_handles_missing_db():
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config(Path(tmp))
        empty = find_empty_threads(config)
        assert empty == []


def test_audit_threads_reports_empty():
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config(Path(tmp), state_db=True)
        db_path = config.state_db_path
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO threads (id, name, created_at, total_tokens, first_user_message) "
            "VALUES ('t1', '', '2026-05-31', NULL, NULL)"
        )
        conn.commit()
        conn.close()

        report = audit_threads(config)
        warnings = [f for f in report.findings if f.severity == "warning"]
        assert len(warnings) == 1


# ---------------------------------------------------------------------------
# Gesamt-Audit
# ---------------------------------------------------------------------------

def test_full_audit_combines_all():
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config(Path(tmp), toml_content="[mcp_servers.x]\ncommand = 'node'\n", state_db=True)
        with patch("codex_logdatenbank_wartung.config_audit.shutil.which", return_value=r"C:\codex"):
            report = run_full_audit(config)
        assert isinstance(report, AuditReport)
        assert len(report.findings) >= 1
