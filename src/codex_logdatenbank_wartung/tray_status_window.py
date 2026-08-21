"""Status-Fenster für die PySide6-Systemtray-App (CareCenter for Codex).

Stellt das kompakte Status-Fenster mit Fortschrittsbalken, Live-Labels,
Aktionsknöpfen und Einstellungsbereich bereit.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .i18n import LANGUAGES, get_language, language_label, normalize_language, t

APP_NAME = "CareCenter for Codex"
FAST_LOOP_INTERVAL_HOURS = (2, 3, 5, 7, 10, 12, 24)


def _zombie_text(count: int) -> str:
    """Zaehler-Text fuer entfernte Codex-Reste im Status-Fenster."""
    return t("zombie_counter", count=count)


__all__ = [
    "APP_NAME",
    "FAST_LOOP_INTERVAL_HOURS",
    "StatusWindow",
    "_zombie_text",
]

class StatusWindow(QWidget):
    """Kleines Statusfenster: aktueller Zustand, Fortschrittsbalken, letztes Ergebnis."""

    request_safe = Signal()
    request_fast = Signal()
    request_cancel_auto = Signal()
    request_loop_start = Signal(int)
    request_loop_stop = Signal()
    request_diagnose = Signal()
    request_codex_repair = Signal()
    request_store_repair = Signal()
    request_store_reinstall = Signal()
    request_safe_start_report = Signal()
    request_safe_start_install = Signal()
    audit_requested = Signal()
    mcp_mode_changed = Signal(str)
    plugin_mode_changed = Signal(str)
    empty_threads_mode_changed = Signal(str)
    loop_interval_changed = Signal(int)
    language_changed = Signal(str)
    auto_archive_days_changed = Signal(int)
    auto_mark_read_days_changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumWidth(470)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self._loop_enabled = False

        layout = QVBoxLayout(self)
        self.state_label = QLabel(t("ready"))
        self.state_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.state_label)

        self.zombie_label = QLabel(_zombie_text(0))
        self.zombie_label.setStyleSheet("color: #2a7a4a;")
        layout.addWidget(self.zombie_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet("color: #555;")
        layout.addWidget(self.result_label)

        # Haupt-Aktion: EINE zusammengefasste Codex-Start-Reparatur (Eskalation, Stopp bei Erfolg).
        repair_row = QHBoxLayout()
        self.repair_button = QPushButton()
        self.repair_button.clicked.connect(self.request_codex_repair)
        self.diagnose_button = QPushButton()
        self.diagnose_button.clicked.connect(self.request_diagnose)
        repair_row.addWidget(self.repair_button)
        repair_row.addWidget(self.diagnose_button)
        layout.addLayout(repair_row)

        # DB-Wartung (eigene Funktion, bewusst getrennt von der Start-Reparatur).
        maint_row = QHBoxLayout()
        self.safe_button = QPushButton()
        self.safe_button.clicked.connect(self.request_safe)
        self.fast_button = QPushButton()
        self.fast_button.clicked.connect(self.request_fast)
        self.cancel_auto_button = QPushButton()
        self.cancel_auto_button.clicked.connect(self.request_cancel_auto)
        self.cancel_auto_button.setEnabled(False)
        maint_row.addWidget(self.safe_button)
        maint_row.addWidget(self.fast_button)
        maint_row.addWidget(self.cancel_auto_button)
        layout.addLayout(maint_row)

        self.loop_group = QGroupBox()
        loop_layout = QVBoxLayout(self.loop_group)
        loop_interval_row = QHBoxLayout()
        self.loop_interval_label = QLabel()
        loop_interval_row.addWidget(self.loop_interval_label)
        self.loop_interval_combo = QComboBox()
        for hours in FAST_LOOP_INTERVAL_HOURS:
            self.loop_interval_combo.addItem(t("fast_loop_interval_hours", hours=hours), hours)
        self.loop_interval_combo.currentIndexChanged.connect(self._on_loop_interval_index_changed)
        loop_interval_row.addWidget(self.loop_interval_combo)
        loop_layout.addLayout(loop_interval_row)
        loop_button_row = QHBoxLayout()
        self.loop_start_button = QPushButton()
        self.loop_start_button.clicked.connect(self._emit_loop_start)
        self.loop_stop_button = QPushButton()
        self.loop_stop_button.clicked.connect(self.request_loop_stop)
        loop_button_row.addWidget(self.loop_start_button)
        loop_button_row.addWidget(self.loop_stop_button)
        loop_layout.addLayout(loop_button_row)
        layout.addWidget(self.loop_group)

        # Store-Werkzeuge (Vorschläge/Notfall): meist als Vorschlag aus der Eskalation,
        # hier zusätzlich direkt erreichbar.
        store_row = QHBoxLayout()
        self.store_button = QPushButton()
        self.store_button.clicked.connect(self.request_store_repair)
        self.store_reinstall_button = QPushButton()
        self.store_reinstall_button.clicked.connect(self.request_store_reinstall)
        store_row.addWidget(self.store_button)
        store_row.addWidget(self.store_reinstall_button)
        layout.addLayout(store_row)

        safe_start_row = QHBoxLayout()
        self.safe_start_report_button = QPushButton()
        self.safe_start_report_button.clicked.connect(self.request_safe_start_report)
        self.safe_start_install_button = QPushButton()
        self.safe_start_install_button.clicked.connect(self.request_safe_start_install)
        safe_start_row.addWidget(self.safe_start_report_button)
        safe_start_row.addWidget(self.safe_start_install_button)
        layout.addLayout(safe_start_row)

        self.settings_group = QGroupBox()
        settings_layout = QVBoxLayout(self.settings_group)

        language_row = QHBoxLayout()
        self.language_label_widget = QLabel()
        language_row.addWidget(self.language_label_widget)
        self.language_combo = QComboBox()
        for language in LANGUAGES:
            self.language_combo.addItem(language_label(language), language)
        self.language_combo.currentIndexChanged.connect(self._on_language_index_changed)
        language_row.addWidget(self.language_combo)
        settings_layout.addLayout(language_row)

        mcp_row = QHBoxLayout()
        self.mcp_label = QLabel()
        mcp_row.addWidget(self.mcp_label)
        self.mcp_combo = QComboBox()
        self.mcp_combo.addItems(["off", "notify", "auto"])
        mcp_row.addWidget(self.mcp_combo)
        settings_layout.addLayout(mcp_row)

        plugin_row = QHBoxLayout()
        self.plugin_label = QLabel()
        plugin_row.addWidget(self.plugin_label)
        self.plugin_combo = QComboBox()
        self.plugin_combo.addItems(["off", "notify", "auto"])
        plugin_row.addWidget(self.plugin_combo)
        settings_layout.addLayout(plugin_row)

        empty_threads_row = QHBoxLayout()
        self.empty_threads_label = QLabel()
        empty_threads_row.addWidget(self.empty_threads_label)
        self.empty_threads_combo = QComboBox()
        self.empty_threads_combo.addItems(["off", "notify", "auto"])
        empty_threads_row.addWidget(self.empty_threads_combo)
        settings_layout.addLayout(empty_threads_row)

        self.mcp_combo.currentTextChanged.connect(self.mcp_mode_changed.emit)
        self.plugin_combo.currentTextChanged.connect(self.plugin_mode_changed.emit)
        self.empty_threads_combo.currentTextChanged.connect(self.empty_threads_mode_changed.emit)

        thread_archive_row = QHBoxLayout()
        self.thread_archive_label = QLabel()
        self.thread_archive_days = QSpinBox()
        self.thread_archive_days.setRange(0, 3650)
        self.thread_archive_days.setSuffix(" Tagen")
        self.thread_archive_days.setSpecialValueText("Aus")
        self.thread_archive_days.valueChanged.connect(self.auto_archive_days_changed.emit)
        thread_archive_row.addWidget(self.thread_archive_label)
        thread_archive_row.addWidget(self.thread_archive_days)
        settings_layout.addLayout(thread_archive_row)

        thread_read_row = QHBoxLayout()
        self.thread_read_label = QLabel()
        self.thread_read_days = QSpinBox()
        self.thread_read_days.setRange(0, 3650)
        self.thread_read_days.setSuffix(" Tagen")
        self.thread_read_days.setSpecialValueText("Aus")
        self.thread_read_days.valueChanged.connect(self.auto_mark_read_days_changed.emit)
        thread_read_row.addWidget(self.thread_read_label)
        thread_read_row.addWidget(self.thread_read_days)
        settings_layout.addLayout(thread_read_row)

        self.audit_button = QPushButton()
        self.audit_button.clicked.connect(self.request_audit)
        settings_layout.addWidget(self.audit_button)

        layout.addWidget(self.settings_group)

        self.close_button = QPushButton()
        self.close_button.clicked.connect(self.hide)
        layout.addWidget(self.close_button)
        self.retranslate()

    def request_audit(self) -> None:
        self.audit_requested.emit()

    def _selected_loop_interval(self) -> int:
        value = self.loop_interval_combo.currentData()
        try:
            hours = int(value)
        except (TypeError, ValueError):
            hours = 3
        return hours if hours in FAST_LOOP_INTERVAL_HOURS else 3

    def _emit_loop_start(self) -> None:
        self.request_loop_start.emit(self._selected_loop_interval())

    def _on_loop_interval_index_changed(self, index: int) -> None:
        value = self.loop_interval_combo.itemData(index)
        try:
            hours = int(value)
        except (TypeError, ValueError):
            return
        if hours in FAST_LOOP_INTERVAL_HOURS:
            self.loop_interval_changed.emit(hours)

    def set_loop_settings(self, enabled: bool, interval_hours: int) -> None:
        self._loop_enabled = bool(enabled)
        self.loop_interval_combo.blockSignals(True)
        target = interval_hours if interval_hours in FAST_LOOP_INTERVAL_HOURS else 3
        for index in range(self.loop_interval_combo.count()):
            if self.loop_interval_combo.itemData(index) == target:
                self.loop_interval_combo.setCurrentIndex(index)
                break
        self.loop_interval_combo.blockSignals(False)
        self.loop_interval_combo.setEnabled(not enabled)
        self.loop_start_button.setEnabled(not enabled)
        self.loop_stop_button.setEnabled(enabled)

    def set_audit_settings(self, mcp_mode: str, plugin_mode: str, empty_threads_mode: str) -> None:
        """Setzt die Combo-Werte ohne Signals auszuloesen."""
        self.mcp_combo.blockSignals(True)
        self.plugin_combo.blockSignals(True)
        self.empty_threads_combo.blockSignals(True)
        idx_mcp = self.mcp_combo.findText(mcp_mode)
        if idx_mcp >= 0:
            self.mcp_combo.setCurrentIndex(idx_mcp)
        idx_plugin = self.plugin_combo.findText(plugin_mode)
        if idx_plugin >= 0:
            self.plugin_combo.setCurrentIndex(idx_plugin)
        idx_empty = self.empty_threads_combo.findText(empty_threads_mode)
        if idx_empty >= 0:
            self.empty_threads_combo.setCurrentIndex(idx_empty)
        self.mcp_combo.blockSignals(False)
        self.plugin_combo.blockSignals(False)
        self.empty_threads_combo.blockSignals(False)

    def set_thread_hygiene_settings(self, archive_days: int, read_days: int) -> None:
        for widget, value in (
            (self.thread_archive_days, archive_days),
            (self.thread_read_days, read_days),
        ):
            widget.blockSignals(True)
            widget.setValue(max(0, min(3650, int(value))))
            widget.blockSignals(False)

    def set_language_setting(self, language: str) -> None:
        """Setzt den sichtbaren Sprachwert ohne Signals auszulösen."""
        normalized = normalize_language(language) or get_language()
        self.language_combo.blockSignals(True)
        for index in range(self.language_combo.count()):
            if self.language_combo.itemData(index) == normalized:
                self.language_combo.setCurrentIndex(index)
                break
        self.language_combo.blockSignals(False)

    def _on_language_index_changed(self, index: int) -> None:
        language = normalize_language(self.language_combo.itemData(index))
        if language is not None:
            self.language_changed.emit(language)

    @staticmethod
    def _accessible_label_text(label: QLabel) -> str:
        return label.text().rstrip(":：").strip()

    def _set_accessible_context(self, widget: QWidget, label: QLabel, description: str) -> None:
        widget.setAccessibleName(self._accessible_label_text(label))
        widget.setAccessibleDescription(description)

    def retranslate(self) -> None:
        """Aktualisiert alle statischen UI-Texte nach einem Sprachwechsel."""
        self.repair_button.setText(t("repair_codex"))
        self.repair_button.setToolTip(t("repair_codex_tooltip"))
        self.diagnose_button.setText(t("diagnose"))
        self.diagnose_button.setToolTip(t("diagnose_tooltip"))
        self.safe_button.setText(t("maintenance_safe_button"))
        self.safe_button.setToolTip(t("maintenance_safe_tooltip"))
        self.fast_button.setText(t("maintenance_fast_button"))
        self.fast_button.setToolTip(t("maintenance_fast_tooltip"))
        self.cancel_auto_button.setText(t("maintenance_cancel_button"))
        self.cancel_auto_button.setToolTip(t("maintenance_cancel_tooltip"))
        self.store_button.setText(t("store_repair"))
        self.store_button.setToolTip(t("store_repair_tooltip"))
        self.store_reinstall_button.setText(t("store_reinstall"))
        self.store_reinstall_button.setToolTip(t("store_reinstall_tooltip"))
        self.safe_start_report_button.setText(t("safe_start_check"))
        self.safe_start_report_button.setToolTip(t("safe_start_tooltip"))
        self.safe_start_install_button.setText(t("safe_start_install"))
        self.safe_start_install_button.setToolTip(t("safe_start_install_tooltip"))
        self.loop_group.setTitle(t("fast_loop_group"))
        self.loop_interval_label.setText(t("fast_loop_interval"))
        self.loop_interval_combo.blockSignals(True)
        for index in range(self.loop_interval_combo.count()):
            hours = self.loop_interval_combo.itemData(index)
            self.loop_interval_combo.setItemText(
                index,
                t("fast_loop_interval_hours", hours=hours),
            )
        self.loop_interval_combo.blockSignals(False)
        self.loop_interval_combo.setToolTip(t("fast_loop_interval_tooltip"))
        self.loop_start_button.setText(t("fast_loop_start"))
        self.loop_start_button.setToolTip(t("fast_loop_start_tooltip"))
        self.loop_stop_button.setText(t("fast_loop_stop"))
        self.loop_stop_button.setToolTip(t("fast_loop_stop_tooltip"))
        self.settings_group.setTitle(f"{t('settings_group')}: {t('settings_config_audit')}")
        self.language_label_widget.setText(t("settings_language"))
        self.language_combo.setToolTip(t("settings_language_tooltip"))
        self.language_combo.blockSignals(True)
        for index, language in enumerate(LANGUAGES):
            if index < self.language_combo.count():
                self.language_combo.setItemText(index, language_label(language))
        self.language_combo.blockSignals(False)
        self.mcp_label.setText(t("settings_mcp_duplicates"))
        self.plugin_label.setText(t("settings_unused_plugins"))
        self.empty_threads_label.setText(t("settings_empty_threads"))
        self.thread_archive_label.setText(t("settings_auto_archive_days"))
        self.thread_read_label.setText(t("settings_auto_mark_read_days"))
        self.mcp_combo.setToolTip(t("settings_audit_mode_tooltip"))
        self.plugin_combo.setToolTip(t("settings_plugin_mode_tooltip"))
        self.empty_threads_combo.setToolTip(t("settings_empty_threads_tooltip"))
        self.thread_archive_days.setToolTip(t("settings_auto_archive_days_tooltip"))
        self.thread_read_days.setToolTip(t("settings_auto_mark_read_days_tooltip"))
        self._set_accessible_context(
            self.loop_interval_combo,
            self.loop_interval_label,
            t("fast_loop_interval_tooltip"),
        )
        self._set_accessible_context(
            self.language_combo,
            self.language_label_widget,
            t("settings_language_tooltip"),
        )
        self._set_accessible_context(
            self.mcp_combo,
            self.mcp_label,
            t("settings_audit_mode_tooltip"),
        )
        self._set_accessible_context(
            self.plugin_combo,
            self.plugin_label,
            t("settings_plugin_mode_tooltip"),
        )
        self._set_accessible_context(
            self.empty_threads_combo,
            self.empty_threads_label,
            t("settings_empty_threads_tooltip"),
        )
        self._set_accessible_context(
            self.thread_archive_days,
            self.thread_archive_label,
            t("settings_auto_archive_days_tooltip"),
        )
        self._set_accessible_context(
            self.thread_read_days,
            self.thread_read_label,
            t("settings_auto_mark_read_days_tooltip"),
        )
        self.audit_button.setText(t("settings_audit_now"))
        self.audit_button.setToolTip(t("settings_audit_now_tooltip"))
        self.close_button.setText(t("window_close"))
        self.close_button.setToolTip(t("window_close_tooltip"))

    def set_zombie_count(self, count: int) -> None:
        self.zombie_label.setText(_zombie_text(count))

    def set_running(self, running: bool, can_cancel: bool = False) -> None:
        for button in (
            self.repair_button,
            self.diagnose_button,
            self.safe_button,
            self.fast_button,
            self.store_button,
            self.store_reinstall_button,
            self.safe_start_report_button,
            self.safe_start_install_button,
        ):
            button.setEnabled(not running)
        self.cancel_auto_button.setEnabled(running and can_cancel)
        self.loop_start_button.setEnabled((not running) and not self._loop_enabled)
        self.loop_stop_button.setEnabled(self._loop_enabled)
        self.loop_interval_combo.setEnabled((not running) and not self._loop_enabled)

    def set_cancel_enabled(self, enabled: bool) -> None:
        self.cancel_auto_button.setEnabled(enabled)

    def set_progress(self, percent: int, message: str, indeterminate: bool) -> None:
        if indeterminate:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(percent)
        if message:
            self.detail_label.setText(message)

    def set_state(self, text: str) -> None:
        self.state_label.setText(text)

    def set_result(self, text: str) -> None:
        self.result_label.setText(text)


