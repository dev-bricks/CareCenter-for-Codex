"""Minimaler Test fuer den running-State bei run_full_repair (Bug-Fix #2, Sweep 2026-05-31).

Prueft die Invariante: waehrend run_full_repair ist self.running True, danach False.
Patcht PySide6 so, dass QObject eine echte Basisklasse ist (kein MagicMock als Elternklasse).
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch


class _FakeQObject:
    """Minimale QObject-Attrappe die normale Attributzuweisung erlaubt."""
    def __init__(self, *a, **kw):
        pass


def _mock_pyside6():
    """Erzeuge Fake-PySide6-Module, damit tray.py importierbar ist ohne Display."""
    mocks = {}
    for name in (
        "PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
    ):
        mod = ModuleType(name)
        mocks[name] = mod
        sys.modules[name] = mod

    qt_core = mocks["PySide6.QtCore"]
    qt_core.QObject = _FakeQObject
    qt_core.Qt = MagicMock()
    qt_core.QThread = MagicMock
    qt_core.QTimer = MagicMock
    qt_core.Signal = lambda *a, **k: MagicMock()

    qt_gui = mocks["PySide6.QtGui"]
    qt_gui.QAction = MagicMock
    qt_gui.QIcon = MagicMock

    qt_widgets = mocks["PySide6.QtWidgets"]
    qt_widgets.QApplication = MagicMock
    qt_widgets.QApplication.instance = MagicMock(return_value=MagicMock())
    qt_widgets.QComboBox = MagicMock
    qt_widgets.QGroupBox = MagicMock
    qt_widgets.QHBoxLayout = MagicMock
    qt_widgets.QLabel = MagicMock
    qt_widgets.QMenu = MagicMock
    qt_widgets.QProgressBar = MagicMock
    qt_widgets.QPushButton = MagicMock
    qt_widgets.QStyle = MagicMock()
    fake_tray_icon = MagicMock()
    fake_tray_icon.MessageIcon = MagicMock()
    fake_tray_icon.ActivationReason = MagicMock()
    qt_widgets.QSystemTrayIcon = fake_tray_icon
    qt_widgets.QVBoxLayout = MagicMock
    qt_widgets.QWidget = _FakeQObject

    return mocks


def _bare_controller(klass, config_path: Path, config, *, running: bool = False):
    controller = object.__new__(klass)
    controller.config_path = config_path
    controller.config = config
    controller.tray = MagicMock()
    controller.window = MagicMock()
    controller.show_window = MagicMock()
    controller.running = running
    controller.auto_thread = None
    controller.auto_worker = None
    controller.repair_thread = None
    controller.repair_worker = None
    controller.store_thread = None
    controller.store_worker = None
    controller.safe_start_install_thread = None
    controller.safe_start_install_worker = None
    controller.automation_thread = None
    controller.automation_worker = None
    controller.full_repair_thread = None
    controller.full_repair_worker = None
    controller.start_repair_thread = None
    controller.start_repair_worker = None
    controller.watchdog_thread = None
    controller.watchdog_worker = None
    controller.zombie_kill_count = 0
    return controller


def test_full_repair_sets_running_true():
    """run_full_repair muss self.running = True setzen (Bug-Fix: war vorher vergessen)."""
    mocks = _mock_pyside6()
    try:
        for key in list(sys.modules):
            if "codex_logdatenbank_wartung.tray" in key:
                del sys.modules[key]

        from codex_logdatenbank_wartung.tray import TrayController

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            from codex_logdatenbank_wartung.config import MaintenanceConfig
            config = MaintenanceConfig()
            config.save(config_path)

            controller = _bare_controller(TrayController, config_path, config)

            with patch("codex_logdatenbank_wartung.tray.QThread") as mock_thread, \
                 patch("codex_logdatenbank_wartung.tray.FullRepairWorker") as mock_worker:
                mock_thread_inst = MagicMock()
                mock_thread.return_value = mock_thread_inst
                mock_worker_inst = MagicMock()
                mock_worker.return_value = mock_worker_inst

                controller.run_full_repair()
                assert controller.running is True, "run_full_repair must set self.running = True"

            controller.on_full_repair_finished(None)
            assert controller.running is False, "on_full_repair_finished must set self.running = False"
    finally:
        for key in list(sys.modules):
            if "codex_logdatenbank_wartung.tray" in key:
                del sys.modules[key]
        for key in list(mocks):
            if key in sys.modules and sys.modules[key] is mocks[key]:
                del sys.modules[key]


def test_watchdog_busy_includes_start_repair_thread():
    """_watchdog_busy() muss True liefern wenn start_repair_thread aktiv ist (Bug-Fix)."""
    mocks = _mock_pyside6()
    try:
        for key in list(sys.modules):
            if "codex_logdatenbank_wartung.tray" in key:
                del sys.modules[key]

        from codex_logdatenbank_wartung.tray import TrayController

        controller = object.__new__(TrayController)
        controller.running = False
        controller.auto_thread = None
        controller.repair_thread = None
        controller.store_thread = None
        controller.safe_start_install_thread = None
        controller.full_repair_thread = None
        controller.start_repair_thread = None

        assert controller._watchdog_busy() is False, "Kein aktiver Thread => nicht busy"

        controller.start_repair_thread = MagicMock()
        assert controller._watchdog_busy() is True, "start_repair_thread aktiv => busy"
    finally:
        for key in list(sys.modules):
            if "codex_logdatenbank_wartung.tray" in key:
                del sys.modules[key]
        for key in list(mocks):
            if key in sys.modules and sys.modules[key] is mocks[key]:
                del sys.modules[key]


def test_mutating_tray_actions_respect_global_busy_guard():
    """Start-/Reparaturaktionen duerfen nicht parallel zu einer laufenden Aktion loslaufen."""
    mocks = _mock_pyside6()
    try:
        for key in list(sys.modules):
            if "codex_logdatenbank_wartung.tray" in key:
                del sys.modules[key]

        from codex_logdatenbank_wartung.config import MaintenanceConfig
        from codex_logdatenbank_wartung.tray import TrayController

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config = MaintenanceConfig()
            config.save(config_path)
            controller = _bare_controller(TrayController, config_path, config, running=True)

            with patch(
                "codex_logdatenbank_wartung.safe_start_integration.launch_safe_start_tray"
            ) as safe_start:
                controller.launch_codex_safe()
                safe_start.assert_not_called()

            with patch(
                "codex_logdatenbank_wartung.safe_start_integration.safe_start_gate_active"
            ) as gate, patch(
                "codex_logdatenbank_wartung.orchestrator.default_launcher"
            ) as launcher:
                controller.launch_codex_normal()
                gate.assert_not_called()
                launcher.assert_not_called()

            with patch("codex_logdatenbank_wartung.tray.QThread") as thread:
                controller.install_safe_start()
                controller.run_codex_repair()
                controller.run_store_repair()
                controller.run_full_repair()
                thread.assert_not_called()
    finally:
        for key in list(sys.modules):
            if "codex_logdatenbank_wartung.tray" in key:
                del sys.modules[key]
        for key in list(mocks):
            if key in sys.modules and sys.modules[key] is mocks[key]:
                del sys.modules[key]


def test_full_repair_allows_start_repair_escalation_guard():
    """Die globale Busy-Sperre darf die interne leichte->volle Reparatur nicht blockieren."""
    mocks = _mock_pyside6()
    try:
        for key in list(sys.modules):
            if "codex_logdatenbank_wartung.tray" in key:
                del sys.modules[key]

        from codex_logdatenbank_wartung.config import MaintenanceConfig
        from codex_logdatenbank_wartung.tray import TrayController

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config = MaintenanceConfig()
            config.save(config_path)
            controller = _bare_controller(TrayController, config_path, config)
            controller.start_repair_thread = MagicMock()

            with patch("codex_logdatenbank_wartung.tray.QThread") as mock_thread, \
                 patch("codex_logdatenbank_wartung.tray.FullRepairWorker") as mock_worker:
                mock_thread_inst = MagicMock()
                mock_thread.return_value = mock_thread_inst
                mock_worker.return_value = MagicMock()

                controller.run_full_repair(from_start_repair=True)

            assert controller.running is True
            mock_thread.assert_called_once()
    finally:
        for key in list(sys.modules):
            if "codex_logdatenbank_wartung.tray" in key:
                del sys.modules[key]
        for key in list(mocks):
            if key in sys.modules and sys.modules[key] is mocks[key]:
                del sys.modules[key]


def test_start_repair_escalates_to_full_repair_with_internal_bypass():
    """on_start_repair_finished muss den Bypass explizit an run_full_repair weitergeben."""
    mocks = _mock_pyside6()
    try:
        for key in list(sys.modules):
            if "codex_logdatenbank_wartung.tray" in key:
                del sys.modules[key]

        from codex_logdatenbank_wartung.config import MaintenanceConfig
        from codex_logdatenbank_wartung.tray import TrayController

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config = MaintenanceConfig()
            config.save(config_path)
            controller = _bare_controller(TrayController, config_path, config, running=True)
            controller.run_full_repair = MagicMock()

            controller.on_start_repair_finished(
                {"outcome": "escalate", "reaped": 0, "message": "weiter"}
            )

            controller.run_full_repair.assert_called_once_with(from_start_repair=True)
    finally:
        for key in list(sys.modules):
            if "codex_logdatenbank_wartung.tray" in key:
                del sys.modules[key]
        for key in list(mocks):
            if key in sys.modules and sys.modules[key] is mocks[key]:
                del sys.modules[key]


def test_store_repair_sets_running_true():
    """run_store_repair muss self.running = True setzen (Bug-Fix: fehlte bisher)."""
    mocks = _mock_pyside6()
    try:
        for key in list(sys.modules):
            if "codex_logdatenbank_wartung.tray" in key:
                del sys.modules[key]

        from codex_logdatenbank_wartung.tray import TrayController

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            from codex_logdatenbank_wartung.config import MaintenanceConfig
            config = MaintenanceConfig()
            config.save(config_path)

            controller = _bare_controller(TrayController, config_path, config)

            with patch("codex_logdatenbank_wartung.tray.QThread") as mock_thread, \
                 patch("codex_logdatenbank_wartung.tray.StoreRepairWorker") as mock_worker:
                mock_thread_inst = MagicMock()
                mock_thread.return_value = mock_thread_inst
                mock_worker_inst = MagicMock()
                mock_worker.return_value = mock_worker_inst

                controller.run_store_repair()
                assert controller.running is True, "run_store_repair must set self.running = True"

            fake_result = MagicMock()
            fake_result.status = "ok"
            controller.on_store_repair_finished(fake_result)
            assert controller.running is False, "on_store_repair_finished must set self.running = False"
    finally:
        for key in list(sys.modules):
            if "codex_logdatenbank_wartung.tray" in key:
                del sys.modules[key]
        for key in list(mocks):
            if key in sys.modules and sys.modules[key] is mocks[key]:
                del sys.modules[key]


def test_language_setting_persists_and_retranslates():
    """Der Settings-Sprachwechsel speichert config.language und relabelt die UI."""
    mocks = _mock_pyside6()
    try:
        for key in list(sys.modules):
            if "codex_logdatenbank_wartung.tray" in key:
                del sys.modules[key]

        from codex_logdatenbank_wartung.config import MaintenanceConfig
        from codex_logdatenbank_wartung.i18n import get_language, set_language
        from codex_logdatenbank_wartung.tray import TrayController

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config = MaintenanceConfig(language="de")
            config.save(config_path)

            controller = _bare_controller(TrayController, config_path, config)
            controller._retranslate_menu = MagicMock()

            set_language("de")
            controller.on_language_changed("en")

            saved = json.loads(config_path.read_text(encoding="utf-8"))
            assert saved["language"] == "en"
            assert get_language() == "en"
            controller.window.set_language_setting.assert_called_once_with("en")
            controller.window.retranslate.assert_called_once()
            controller._retranslate_menu.assert_called_once()
            controller.tray.showMessage.assert_called()
            set_language("de")
    finally:
        for key in list(sys.modules):
            if "codex_logdatenbank_wartung.tray" in key:
                del sys.modules[key]
        for key in list(mocks):
            if key in sys.modules and sys.modules[key] is mocks[key]:
                del sys.modules[key]


def test_retranslate_menu_updates_automation_submenu_labels():
    """Das Tray-Rechtsklickmenü enthält die neuen Automationsaktionen lokalisiert."""
    mocks = _mock_pyside6()
    try:
        for key in list(sys.modules):
            if "codex_logdatenbank_wartung.tray" in key:
                del sys.modules[key]

        from codex_logdatenbank_wartung.i18n import set_language
        from codex_logdatenbank_wartung.tray import TrayController

        controller = object.__new__(TrayController)
        for attr in (
            "open_action",
            "status_action",
            "maintenance_action",
            "repair_action",
            "safe_start_action",
            "codex_safe_start_action",
            "codex_start_action",
            "automations_pause_active_action",
            "automations_restore_ccc_action",
            "automations_restore_ccc_staggered_action",
            "automations_activate_all_action",
            "automations_activate_all_staggered_action",
            "watchdog_action",
            "quit_action",
        ):
            setattr(controller, attr, MagicMock())
        controller.automations_menu = MagicMock()

        set_language("de")
        controller._retranslate_menu()

        controller.automations_menu.setTitle.assert_called_once_with("Automatisierungen")
        controller.codex_safe_start_action.setText.assert_called_once_with("Codex safe starten")
        controller.codex_start_action.setText.assert_called_once_with("Codex starten")
        controller.automations_pause_active_action.setText.assert_called_once_with(
            "Alle aktivierten Automatisierungen aus"
        )
        controller.automations_restore_ccc_action.setText.assert_called_once_with(
            "Alle von CCC ausgeschalteten Automatisierungen wieder an"
        )
        controller.automations_activate_all_staggered_action.setText.assert_called_once_with(
            "Alle Automatisierungen gestaffelt an"
        )
    finally:
        for key in list(sys.modules):
            if "codex_logdatenbank_wartung.tray" in key:
                del sys.modules[key]
        for key in list(mocks):
            if key in sys.modules and sys.modules[key] is mocks[key]:
                del sys.modules[key]


def test_launch_codex_safe_noops_when_safe_start_already_running():
    """Ein zweiter Klick auf 'Codex safe starten' darf keinen zweiten Safe Start öffnen."""
    mocks = _mock_pyside6()
    try:
        for key in list(sys.modules):
            if "codex_logdatenbank_wartung.tray" in key:
                del sys.modules[key]

        from codex_logdatenbank_wartung.config import MaintenanceConfig
        from codex_logdatenbank_wartung.i18n import set_language
        from codex_logdatenbank_wartung.tray import TrayController

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config = MaintenanceConfig()
            config.save(config_path)

            controller = _bare_controller(TrayController, config_path, config)
            set_language("de")

            result = SimpleNamespace(
                status="already-running",
                to_text=lambda: "Safe Start läuft bereits.",
            )
            with patch(
                "codex_logdatenbank_wartung.safe_start_integration.launch_safe_start_tray",
                return_value=result,
            ):
                controller.launch_codex_safe()

            controller.window.set_state.assert_called_once_with(
                "Safe Start läuft bereits; kein zweiter Start wurde ausgelöst."
            )
            controller.show_window.assert_called_once()
    finally:
        for key in list(sys.modules):
            if "codex_logdatenbank_wartung.tray" in key:
                del sys.modules[key]
        for key in list(mocks):
            if key in sys.modules and sys.modules[key] is mocks[key]:
                del sys.modules[key]


def test_launch_codex_normal_restores_safe_start_without_launching_codex():
    """Normalstart während Safe Start gibt Automatisierungen zurück und startet Codex nicht."""
    mocks = _mock_pyside6()
    try:
        for key in list(sys.modules):
            if "codex_logdatenbank_wartung.tray" in key:
                del sys.modules[key]

        from codex_logdatenbank_wartung.config import MaintenanceConfig
        from codex_logdatenbank_wartung.i18n import set_language
        from codex_logdatenbank_wartung.tray import TrayController

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config = MaintenanceConfig()
            config.save(config_path)

            controller = _bare_controller(TrayController, config_path, config)
            set_language("de")

            restore_result = SimpleNamespace(
                status="ok",
                to_text=lambda: "Automatisierungen zurückgegeben.",
            )
            with patch(
                "codex_logdatenbank_wartung.safe_start_integration.safe_start_gate_active",
                return_value=True,
            ), patch(
                "codex_logdatenbank_wartung.safe_start_integration.restore_safe_start_latest",
                return_value=restore_result,
            ), patch(
                "codex_logdatenbank_wartung.orchestrator.default_launcher",
                side_effect=AssertionError("Codex darf nicht gestartet werden"),
            ):
                controller.launch_codex_normal()

            controller.window.set_state.assert_called_once_with(
                "Safe Start war aktiv; Automatisierungen wurden zurückgegeben. Codex wurde nicht erneut gestartet."
            )
            controller.show_window.assert_called_once()
    finally:
        for key in list(sys.modules):
            if "codex_logdatenbank_wartung.tray" in key:
                del sys.modules[key]
        for key in list(mocks):
            if key in sys.modules and sys.modules[key] is mocks[key]:
                del sys.modules[key]
