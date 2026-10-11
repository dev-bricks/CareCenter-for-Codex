from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QTreeWidget

from codex_logdatenbank_wartung.i18n import _CATALOG, set_language, t
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
    assert window.empty_threads_combo.accessibleName() == "Leere Threads"
    assert window.empty_threads_combo.accessibleDescription() == t("settings_empty_threads_tooltip")
    assert window.thread_archive_days.accessibleName() == "Threads automatisch archivieren nach"
    assert window.thread_archive_days.accessibleDescription() == t("settings_auto_archive_days_tooltip")
    assert window.thread_read_days.accessibleName() == "Threads automatisch als gelesen markieren nach"
    assert window.thread_read_days.accessibleDescription() == t("settings_auto_mark_read_days_tooltip")

    set_language("en")
    window.retranslate()

    assert window.loop_interval_combo.accessibleName() == "Interval"
    assert window.loop_interval_combo.accessibleDescription() == t("fast_loop_interval_tooltip")
    assert window.language_combo.accessibleName() == "Language"
    assert window.language_combo.accessibleDescription() == t("settings_language_tooltip")
    assert window.mcp_combo.accessibleName() == "MCP duplicates"
    assert window.plugin_combo.accessibleName() == "Unused plugins"
    assert window.empty_threads_combo.accessibleName() == "Empty threads"
    assert window.empty_threads_combo.accessibleDescription() == t("settings_empty_threads_tooltip")
    assert window.thread_archive_days.accessibleName() == "Automatically archive threads after"
    assert window.thread_read_days.accessibleName() == "Automatically mark threads as read after"

    window.close()
    app.processEvents()
    set_language("de")


def test_status_window_buttons_accessible_names_and_descriptions(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = _app()

    set_language("de")
    window = StatusWindow()
    window.retranslate()

    buttons = [
        (window.repair_button, t("repair_codex"), t("repair_codex_tooltip")),
        (window.diagnose_button, t("diagnose"), t("diagnose_tooltip")),
        (window.safe_button, t("maintenance_safe_button"), t("maintenance_safe_tooltip")),
        (window.fast_button, t("maintenance_fast_button"), t("maintenance_fast_tooltip")),
        (window.cancel_auto_button, t("maintenance_cancel_button"), t("maintenance_cancel_tooltip")),
        (window.store_button, t("store_repair"), t("store_repair_tooltip")),
        (window.store_reinstall_button, t("store_reinstall"), t("store_reinstall_tooltip")),
        (window.safe_start_report_button, t("safe_start_check"), t("safe_start_tooltip")),
        (window.safe_start_install_button, t("safe_start_install"), t("safe_start_install_tooltip")),
        (window.loop_start_button, t("fast_loop_start"), t("fast_loop_start_tooltip")),
        (window.loop_stop_button, t("fast_loop_stop"), t("fast_loop_stop_tooltip")),
        (window.audit_button, t("settings_audit_now"), t("settings_audit_now_tooltip")),
        (window.help_button, t("shortcuts_btn_help"), t("shortcuts_btn_help_tooltip")),
        (window.close_button, t("window_close"), t("window_close_tooltip")),
    ]

    for btn, expected_name, expected_desc in buttons:
        expected_clean = re.sub(r"&([a-zA-Z0-9])", r"\1", expected_name).strip()
        assert btn.accessibleName() == expected_clean
        assert btn.accessibleDescription() == expected_desc
        assert btn.toolTip() == expected_desc

    set_language("en")
    window.retranslate()
    assert window.repair_button.accessibleName() == t("repair_codex")
    assert window.help_button.accessibleName() == t("shortcuts_btn_help")
    assert window.close_button.accessibleName() == t("window_close")

    window.close()
    app.processEvents()
    set_language("de")


def test_status_window_labels_and_progress_accessible_context(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = _app()

    set_language("de")
    window = StatusWindow()
    window.retranslate()

    assert window.progress.accessibleName() == t("progress_bar_a11y_name")
    assert window.progress.accessibleDescription() == t("progress_bar_a11y_desc")
    assert window.state_label.accessibleName() == t("state_label_a11y_name")
    assert window.zombie_label.accessibleName() == t("zombie_label_a11y_name")
    assert window.detail_label.accessibleName() == t("detail_label_a11y_name")
    assert window.result_label.accessibleName() == t("result_label_a11y_name")

    # Dynamic updates
    window.set_state("Wartung wird ausgeführt")
    assert window.state_label.text() == "Wartung wird ausgeführt"
    assert window.state_label.accessibleDescription() == "Wartung wird ausgeführt"

    window.set_progress(45, "Datenbank optimiert", False)
    assert window.progress.value() == 45
    assert window.detail_label.text() == "Datenbank optimiert"
    assert "45%" in window.progress.accessibleDescription()

    window.set_progress(0, "Warte auf Leerlauf...", True)
    assert window.progress.maximum() == 0  # indeterminate
    assert "Warte auf Leerlauf..." in window.progress.accessibleDescription()

    window.set_result("Erfolgreich abgeschlossen")
    assert window.result_label.text() == "Erfolgreich abgeschlossen"
    assert window.result_label.accessibleDescription() == "Erfolgreich abgeschlossen"

    window.set_zombie_count(3)
    assert "3" in window.zombie_label.text()
    assert "3" in window.zombie_label.accessibleDescription()

    window.close()
    app.processEvents()


def test_status_window_focus_policy_on_all_controls(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = _app()

    window = StatusWindow()
    controls = [
        window.repair_button,
        window.diagnose_button,
        window.safe_button,
        window.fast_button,
        window.cancel_auto_button,
        window.loop_interval_combo,
        window.loop_start_button,
        window.loop_stop_button,
        window.store_button,
        window.store_reinstall_button,
        window.safe_start_report_button,
        window.safe_start_install_button,
        window.language_combo,
        window.mcp_combo,
        window.plugin_combo,
        window.empty_threads_combo,
        window.thread_archive_days,
        window.thread_read_days,
        window.audit_button,
        window.help_button,
        window.close_button,
    ]

    for ctrl in controls:
        assert ctrl.focusPolicy() == Qt.FocusPolicy.StrongFocus

    window.close()
    app.processEvents()


def test_status_window_shortcuts_registered(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = _app()

    window = StatusWindow()
    assert len(window._shortcuts) >= 14

    registered_sequences = [s.key().toString() for s in window._shortcuts]
    assert "Esc" in registered_sequences
    assert "Ctrl+W" in registered_sequences
    assert "F1" in registered_sequences
    assert "Shift+F1" in registered_sequences
    assert "F5" in registered_sequences
    assert "Alt+R" in registered_sequences
    assert "Alt+D" in registered_sequences
    assert "Alt+S" in registered_sequences
    assert "Alt+F" in registered_sequences
    assert "Alt+A" in registered_sequences
    assert "Alt+P" in registered_sequences
    assert "Alt+L" in registered_sequences
    assert "Alt+O" in registered_sequences
    assert "Alt+C" in registered_sequences
    assert "Alt+H" in registered_sequences

    window.close()
    app.processEvents()


def test_status_window_escape_key_closes_window(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = _app()

    window = StatusWindow()
    window.show()
    assert window.isVisible()

    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    window.keyPressEvent(event)
    assert not window.isVisible()

    window.close()
    app.processEvents()


def test_status_window_shortcuts_dialog(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = _app()

    set_language("de")
    window = StatusWindow()
    dialog = window.show_shortcuts_dialog()

    assert isinstance(dialog, QDialog)
    assert dialog.isModal()
    assert dialog.windowTitle() == t("shortcuts_dialog_title")
    assert dialog.accessibleName() == t("shortcuts_dialog_title")
    assert dialog.accessibleDescription() == t("shortcuts_dialog_desc")

    # Find tree
    trees = dialog.findChildren(QTreeWidget)
    assert len(trees) == 1
    tree = trees[0]
    assert tree.topLevelItemCount() == 4  # 4 categories
    assert tree.headerItem().text(0) == t("shortcuts_action_header")
    assert tree.headerItem().text(1) == t("shortcuts_key_header")

    # Find close button
    buttons = dialog.findChildren(QPushButton)
    close_btns = [b for b in buttons if b.text() == t("shortcuts_btn_close")]
    assert len(close_btns) == 1
    assert close_btns[0].isDefault()

    dialog.accept()
    window.close()
    app.processEvents()


def test_status_window_about_dialog(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = _app()

    set_language("de")
    window = StatusWindow()
    dialog = window.show_about_dialog()

    assert isinstance(dialog, QDialog)
    assert dialog.isModal()
    assert dialog.windowTitle() == t("about_dialog_title")
    assert dialog.accessibleName() == t("about_dialog_title")

    buttons = dialog.findChildren(QPushButton)
    assert len(buttons) >= 1
    assert buttons[0].text() == t("shortcuts_btn_close")

    dialog.accept()
    window.close()
    app.processEvents()


def test_accessibility_tier2_language_parity() -> None:
    """Verifies all new accessibility keys have 100% 6-language parity in _CATALOG."""
    keys = [
        "shortcuts_dialog_title",
        "shortcuts_dialog_desc",
        "shortcuts_action_header",
        "shortcuts_key_header",
        "shortcuts_cat_nav",
        "shortcuts_cat_repair",
        "shortcuts_cat_maint",
        "shortcuts_cat_config",
        "shortcuts_a11y_notice",
        "shortcuts_btn_close",
        "shortcuts_btn_help",
        "shortcuts_btn_help_tooltip",
        "about_dialog_title",
        "about_dialog_text",
        "progress_bar_a11y_name",
        "progress_bar_a11y_desc",
        "state_label_a11y_name",
        "zombie_label_a11y_name",
        "detail_label_a11y_name",
        "result_label_a11y_name",
    ]
    required_langs = ("de", "en", "es", "zh", "ja", "ru")

    for k in keys:
        assert k in _CATALOG, f"Key {k} missing in _CATALOG"
        entry = _CATALOG[k]
        for lang in required_langs:
            assert lang in entry, f"Language {lang} missing for key {k}"
            assert isinstance(entry[lang], str) and entry[lang].strip(), f"Empty {lang} for key {k}"
