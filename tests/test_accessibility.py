"""Accessibility checks for the tray status window."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from codex_logdatenbank_wartung.i18n import set_language, t
from codex_logdatenbank_wartung.tray import StatusWindow


def _app() -> QApplication:
    app = QApplication.instance()
    return app if app is not None else QApplication([])


def test_status_window_comboboxes_expose_accessible_context(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = _app()

    set_language("de")
    window = StatusWindow()
    window.retranslate()

    assert window.loop_interval_combo.toolTip() == t("fast_loop_interval_tooltip")
    assert window.loop_interval_combo.accessibleName() == "Intervall"
    assert window.loop_interval_combo.accessibleDescription() == t("fast_loop_interval_tooltip")
    assert window.language_combo.accessibleName() == "Sprache"
    assert window.language_combo.accessibleDescription() == t("settings_language_tooltip")
    assert window.mcp_combo.accessibleName() == "MCP-Duplikate"
    assert window.mcp_combo.accessibleDescription() == t("settings_audit_mode_tooltip")
    assert window.plugin_combo.accessibleName() == "Ungenutzte Plugins"
    assert window.plugin_combo.accessibleDescription() == t("settings_plugin_mode_tooltip")

    set_language("en")
    window.retranslate()

    assert window.loop_interval_combo.accessibleName() == "Interval"
    assert window.loop_interval_combo.accessibleDescription() == t("fast_loop_interval_tooltip")
    assert window.language_combo.accessibleName() == "Language"
    assert window.language_combo.accessibleDescription() == t("settings_language_tooltip")
    assert window.mcp_combo.accessibleName() == "MCP duplicates"
    assert window.plugin_combo.accessibleName() == "Unused plugins"

    window.close()
    app.processEvents()
    set_language("de")
