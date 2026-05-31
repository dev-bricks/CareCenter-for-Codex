"""Tests fuer run_audit_cycle (reine Orchestrierungsfunktion fuer den Watchdog).

Prueft die drei Modi (off/notify/auto), den Dedup-Guard fuer notify,
das Codex-closed-Gate (renderer_present) fuer auto-writes, und die
per-Kategorie-Filterung.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.config_audit import (
    fix_duplicate_mcp,
    fix_unused_plugins,
    run_audit_cycle,
)


def _make_config_with_toml(tmp: Path, toml_content: str, **overrides) -> MaintenanceConfig:
    codex_home = tmp / ".codex"
    codex_home.mkdir(parents=True, exist_ok=True)
    (codex_home / "config.toml").write_text(toml_content, encoding="utf-8")
    return MaintenanceConfig(database_path=str(codex_home / "logs_2.sqlite"), **overrides)


TOML_WITH_DUPLICATE = """
[mcp_servers.cc1]
command = "npx"
args = ["-y", "ellmos-codecommander-mcp"]

[mcp_servers.cc2]
command = "node"
args = ["C:/node_modules/ellmos-codecommander-mcp/dist/index.js"]
"""

TOML_WITH_PLATFORM_LOCKED = """
[plugins."build-ios-apps@openai-curated"]
enabled = true

[plugins."browser@openai-bundled"]
enabled = true
"""

TOML_MIXED = """
[mcp_servers.cc1]
command = "npx"
args = ["-y", "ellmos-codecommander-mcp"]

[mcp_servers.cc2]
command = "node"
args = ["C:/node_modules/ellmos-codecommander-mcp/dist/index.js"]

[plugins."build-ios-apps@openai-curated"]
enabled = true
"""


# ---------------------------------------------------------------------------
# OFF-Modus: nichts passiert
# ---------------------------------------------------------------------------

def test_audit_cycle_off_does_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config_with_toml(
            Path(tmp), TOML_WITH_DUPLICATE,
            audit_duplicate_mcp="off", audit_unused_plugins="off",
        )
        result = run_audit_cycle(config, last_hash="", renderer_present=False)
        assert result.mcp_fixed == 0
        assert result.plugins_fixed == 0
        assert result.notification is None
        assert result.new_hash == ""


# ---------------------------------------------------------------------------
# AUTO-Modus + Renderer-Gate (KERN-SICHERHEIT)
# ---------------------------------------------------------------------------

def test_audit_cycle_auto_fixes_when_codex_closed():
    """Auto-Modus entfernt Duplikate wenn Codex NICHT laeuft."""
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config_with_toml(
            Path(tmp), TOML_WITH_DUPLICATE,
            audit_duplicate_mcp="auto", audit_unused_plugins="off",
        )
        original_bytes = config.config_toml_path.read_bytes()

        result = run_audit_cycle(config, last_hash="", renderer_present=False)

        assert result.mcp_fixed == 1
        new_bytes = config.config_toml_path.read_bytes()
        assert new_bytes != original_bytes  # Datei wurde geschrieben


def test_audit_cycle_auto_DOES_NOT_write_when_codex_running():
    """KERN-SICHERHEIT: Auto-Fix schreibt NICHT wenn Codex laeuft (Renderer da)."""
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config_with_toml(
            Path(tmp), TOML_WITH_DUPLICATE,
            audit_duplicate_mcp="auto", audit_unused_plugins="off",
        )
        original_bytes = config.config_toml_path.read_bytes()

        result = run_audit_cycle(config, last_hash="", renderer_present=True)

        assert result.mcp_fixed == 0
        assert result.plugins_fixed == 0
        # DATEI BYTE-IDENTISCH — kein Schreibzugriff!
        assert config.config_toml_path.read_bytes() == original_bytes


def test_audit_cycle_auto_plugins_respects_renderer_gate():
    """Plugin-Auto-Fix wird ebenfalls durch renderer_present=True blockiert."""
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config_with_toml(
            Path(tmp), TOML_WITH_PLATFORM_LOCKED,
            audit_duplicate_mcp="off", audit_unused_plugins="auto",
        )
        original_bytes = config.config_toml_path.read_bytes()

        result = run_audit_cycle(config, last_hash="", renderer_present=True)
        assert result.plugins_fixed == 0
        assert config.config_toml_path.read_bytes() == original_bytes

        # Renderer weg -> Fix greift
        result2 = run_audit_cycle(config, last_hash="", renderer_present=False)
        assert result2.plugins_fixed == 1


# ---------------------------------------------------------------------------
# NOTIFY-Modus: Dedup und per-Kategorie-Filter
# ---------------------------------------------------------------------------

def test_audit_cycle_notify_emits_on_first_finding():
    """Erster Durchlauf mit MCP-Duplikat erzeugt eine Notification."""
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config_with_toml(
            Path(tmp), TOML_WITH_DUPLICATE,
            audit_duplicate_mcp="notify", audit_unused_plugins="off",
        )
        result = run_audit_cycle(config, last_hash="", renderer_present=True)
        assert result.notification is not None
        assert "MCP-Duplikat" in result.notification
        assert result.new_hash != ""


def test_audit_cycle_notify_dedup_suppresses_repeat():
    """Zweiter Durchlauf mit gleichem Befund unterdrückt die Notification."""
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config_with_toml(
            Path(tmp), TOML_WITH_DUPLICATE,
            audit_duplicate_mcp="notify", audit_unused_plugins="off",
        )
        first = run_audit_cycle(config, last_hash="", renderer_present=True)
        assert first.notification is not None

        second = run_audit_cycle(config, last_hash=first.new_hash, renderer_present=True)
        assert second.notification is None
        assert second.new_hash == first.new_hash


def test_audit_cycle_notify_respects_category_filter_mcp_only():
    """mcp=notify, plugins=off -> Plugin-Befunde werden NICHT gemeldet."""
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config_with_toml(
            Path(tmp), TOML_MIXED,
            audit_duplicate_mcp="notify", audit_unused_plugins="off",
        )
        result = run_audit_cycle(config, last_hash="", renderer_present=True)
        assert result.notification is not None
        assert "MCP-Duplikat" in result.notification
        assert "Ungenutztes Plugin" not in result.notification


def test_audit_cycle_notify_respects_category_filter_plugins_only():
    """mcp=off, plugins=notify -> MCP-Befunde werden NICHT gemeldet."""
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config_with_toml(
            Path(tmp), TOML_MIXED,
            audit_duplicate_mcp="off", audit_unused_plugins="notify",
        )
        result = run_audit_cycle(config, last_hash="", renderer_present=True)
        assert result.notification is not None
        assert "Ungenutztes Plugin" in result.notification
        assert "MCP-Duplikat" not in result.notification


def test_audit_cycle_notify_clears_hash_when_finding_resolved():
    """Wenn der Befund verschwindet (z.B. User hat es manuell gefixt), wird der Hash geleert."""
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config_with_toml(
            Path(tmp), TOML_WITH_DUPLICATE,
            audit_duplicate_mcp="notify", audit_unused_plugins="off",
        )
        first = run_audit_cycle(config, last_hash="", renderer_present=True)
        assert first.new_hash != ""

        # User hat Duplikat manuell entfernt
        clean_toml = """
[mcp_servers.cc2]
command = "node"
args = ["C:/node_modules/ellmos-codecommander-mcp/dist/index.js"]
"""
        config.config_toml_path.write_text(clean_toml, encoding="utf-8")
        second = run_audit_cycle(config, last_hash=first.new_hash, renderer_present=True)
        assert second.notification is None
        assert second.new_hash == ""


# ---------------------------------------------------------------------------
# Atomic Write: Round-Trip-Sicherheit
# ---------------------------------------------------------------------------

def test_atomic_write_round_trip_preserves_content():
    """fix_duplicate_mcp schreibt valides TOML und lässt den Rest unverändert."""
    toml = """model = "gpt-5.5"

[mcp_servers.x1]
command = "npx"
args = ["-y", "ellmos-filecommander-mcp"]

[mcp_servers.x2]
command = "node"
args = ["C:/node_modules/ellmos-filecommander-mcp/dist/index.js"]

[plugins."browser@openai-bundled"]
enabled = true
"""
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config_with_toml(Path(tmp), toml)
        fix_duplicate_mcp(config)
        import tomlkit
        result = tomlkit.parse(config.config_toml_path.read_text(encoding="utf-8"))
        assert result["model"] == "gpt-5.5"
        assert result["plugins"]["browser@openai-bundled"]["enabled"] is True
        assert len(result["mcp_servers"]) == 1


def test_backup_created_before_auto_fix():
    """Auto-Fix erstellt ein .bak-Backup bevor die Datei geschrieben wird."""
    with tempfile.TemporaryDirectory() as tmp:
        config = _make_config_with_toml(
            Path(tmp), TOML_WITH_DUPLICATE,
            audit_duplicate_mcp="auto", audit_unused_plugins="off",
        )
        run_audit_cycle(config, last_hash="", renderer_present=False)
        codex_home = Path(tmp) / ".codex"
        backups = list(codex_home.glob("config.*.bak"))
        assert len(backups) >= 1
