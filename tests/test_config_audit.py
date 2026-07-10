"""Tests fuer das Config-Audit-Modul (6c + 6d)."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.config_audit import (
    AuditReport,
    _extract_mcp_package,
    _parse_toml_sections,
    _strip_inline_comment,
    audit_cli_installation,
    audit_config_toml,
    audit_threads,
    find_empty_threads,
    fix_duplicate_mcp,
    fix_unused_plugins,
    run_full_audit,
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

[plugins."build-macos-apps@openai-curated"]
enabled = true

[plugins."browser@openai-bundled"]
enabled = true
"""
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config(Path(tmp), toml)
        report = audit_config_toml(config)
        unused = [f for f in report.findings if f.category == "Ungenutztes Plugin"]
        assert len(unused) == 2
        messages = " ".join(u.message for u in unused)
        assert "build-ios-apps" in messages
        assert "build-macos-apps" in messages


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


def test_find_empty_threads_detects_whitespace_only_first_message():
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config(Path(tmp), state_db=True)
        db_path = config.state_db_path
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO threads (id, name, created_at, total_tokens, first_user_message) "
            "VALUES ('t1', 'Whitespace', '2026-05-31', 0, '   \n\t')"
        )
        conn.commit()
        conn.close()

        empty = find_empty_threads(config)
        assert len(empty) == 1
        assert empty[0].thread_id == "t1"


def test_find_empty_threads_detects_empty_message_payload_table():
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config(Path(tmp))
        db_path = config.state_db_path
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE messages (
                id TEXT PRIMARY KEY,
                thread_id TEXT,
                created_at TEXT,
                payload TEXT
            )
        """)
        conn.execute(
            "INSERT INTO messages (id, thread_id, created_at, payload) VALUES (?, ?, ?, ?)",
            ("m1", "thread-empty", "2026-05-31", '{"role":"user","content":""}'),
        )
        conn.execute(
            "INSERT INTO messages (id, thread_id, created_at, payload) VALUES (?, ?, ?, ?)",
            ("m2", "thread-full", "2026-05-31", '{"role":"user","content":"Hello"}'),
        )
        conn.commit()
        conn.close()

        empty = find_empty_threads(config)
        assert [item.thread_id for item in empty] == ["thread-empty"]


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


# ---------------------------------------------------------------------------
# Auto-Fix: fix_duplicate_mcp
# ---------------------------------------------------------------------------

def test_fix_duplicate_mcp_removes_duplicate():
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
        removed = fix_duplicate_mcp(config)
        assert removed == 1
        # Datei wurde geschrieben — pruefen dass nur ein Server bleibt
        new_text = config.config_toml_path.read_text(encoding="utf-8")
        assert "ellmos-codecommander" in new_text
        # npx-Eintrag ist weg (node_modules bevorzugt)
        assert "codecommander]" in new_text
        assert 'npx' not in new_text


def test_fix_duplicate_mcp_preserves_rest_of_file():
    toml = """approval_policy = "never"
model = "gpt-5.5"

[mcp_servers.cc1]
command = "npx"
args = ["-y", "ellmos-codecommander-mcp"]

[mcp_servers.cc2]
command = "node"
args = ["C:/node_modules/ellmos-codecommander-mcp/dist/index.js"]

[plugins."browser@openai-bundled"]
enabled = true
"""
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config(Path(tmp), toml)
        fix_duplicate_mcp(config)
        new_text = config.config_toml_path.read_text(encoding="utf-8")
        # Restliche Sektionen bleiben erhalten
        assert 'approval_policy = "never"' in new_text
        assert 'model = "gpt-5.5"' in new_text
        assert 'plugins."browser@openai-bundled"' in new_text
        assert "enabled = true" in new_text


def test_fix_duplicate_mcp_no_change_when_clean():
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
        removed = fix_duplicate_mcp(config)
        assert removed == 0


def test_fix_duplicate_mcp_creates_backup():
    toml = """
[mcp_servers.cc1]
command = "npx"
args = ["-y", "ellmos-codecommander-mcp"]

[mcp_servers.cc2]
command = "node"
args = ["C:/node_modules/ellmos-codecommander-mcp/dist/index.js"]
"""
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config(Path(tmp), toml)
        fix_duplicate_mcp(config)
        codex_home = Path(tmp) / ".codex"
        backups = list(codex_home.glob("config.*.bak"))
        assert len(backups) >= 1


# ---------------------------------------------------------------------------
# Auto-Fix: fix_unused_plugins
# ---------------------------------------------------------------------------

def test_fix_unused_plugins_disables_platform_locked():
    toml = """
[plugins."build-ios-apps@openai-curated"]
enabled = true

[plugins."build-macos-apps@openai-curated"]
enabled = true

[plugins."browser@openai-bundled"]
enabled = true
"""
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config(Path(tmp), toml)
        fixed = fix_unused_plugins(config)
        assert fixed == 2
        new_text = config.config_toml_path.read_text(encoding="utf-8")
        # browser bleibt enabled
        assert "browser@openai-bundled" in new_text
        # Plattform-locked sind jetzt false
        import tomlkit
        doc = tomlkit.parse(new_text)
        assert doc["plugins"]["build-ios-apps@openai-curated"]["enabled"] is False
        assert doc["plugins"]["build-macos-apps@openai-curated"]["enabled"] is False
        assert doc["plugins"]["browser@openai-bundled"]["enabled"] is True


def test_fix_unused_plugins_no_change_when_already_disabled():
    toml = """
[plugins."build-ios-apps@openai-curated"]
enabled = false

[plugins."build-macos-apps@openai-curated"]
enabled = false
"""
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config(Path(tmp), toml)
        fixed = fix_unused_plugins(config)
        assert fixed == 0


def test_fix_unused_plugins_does_not_touch_cross_platform():
    """Plugins wie slack, figma, circleci sind cross-platform und werden NICHT deaktiviert."""
    toml = """
[plugins."slack@openai-curated"]
enabled = true

[plugins."figma@openai-curated"]
enabled = true

[plugins."circleci@openai-curated"]
enabled = true
"""
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config(Path(tmp), toml)
        fixed = fix_unused_plugins(config)
        assert fixed == 0


def test_manual_audit_rechecks_after_auto_fix():
    from codex_logdatenbank_wartung.config_audit import run_manual_audit

    duplicate_toml = """
[mcp_servers.cc1]
command = "npx"
args = ["-y", "ellmos-codecommander-mcp"]

[mcp_servers.cc2]
command = "node"
args = ["C:/node_modules/ellmos-codecommander-mcp/dist/index.js"]
"""
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config(Path(tmp), duplicate_toml)
        config.audit_duplicate_mcp = "auto"
        config.audit_unused_plugins = "off"
        report, cycle = run_manual_audit(config, renderer_present=False)
        assert cycle.mcp_fixed == 1
        assert cycle.fixes_deferred == 0
        assert not any(f.category == "MCP-Duplikat" for f in report.findings)


def test_manual_audit_reports_deferred_auto_fix_while_codex_runs():
    from codex_logdatenbank_wartung.config_audit import run_manual_audit

    duplicate_toml = """
[mcp_servers.cc1]
command = "npx"
args = ["-y", "ellmos-codecommander-mcp"]

[mcp_servers.cc2]
command = "node"
args = ["C:/node_modules/ellmos-codecommander-mcp/dist/index.js"]
"""
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config(Path(tmp), duplicate_toml)
        config.audit_duplicate_mcp = "auto"
        config.audit_unused_plugins = "off"
        original = config.config_toml_path.read_bytes()
        report, cycle = run_manual_audit(config, renderer_present=True)
        assert cycle.mcp_fixed == 0
        assert cycle.fixes_deferred == 1
        assert any(f.category == "MCP-Duplikat" for f in report.findings)
        assert config.config_toml_path.read_bytes() == original
