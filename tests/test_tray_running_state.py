"""Minimaler Test fuer den running-State bei run_full_repair (Bug-Fix #2, Sweep 2026-05-31).

Prueft die Invariante: waehrend run_full_repair ist self.running True, danach False.
Patcht PySide6 so, dass QObject eine echte Basisklasse ist (kein MagicMock als Elternklasse).
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch
import tempfile


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

            tray_mock = MagicMock()
            controller = object.__new__(TrayController)
            controller.config_path = config_path
            controller.config = config
            controller.tray = tray_mock
            controller.running = False
            controller.auto_thread = None
            controller.repair_thread = None
            controller.store_thread = None
            controller.full_repair_thread = None
            controller.full_repair_worker = None
            controller.start_repair_thread = None
            controller.watchdog_thread = None
            controller.zombie_kill_count = 0
            controller.window = MagicMock()

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
