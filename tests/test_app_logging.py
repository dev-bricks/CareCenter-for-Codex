"""Tests fuer den fensterlosen Start-Logger."""

from __future__ import annotations

import logging
import threading
import sys

import pytest

from codex_logdatenbank_wartung.runtime import app_logging


@pytest.fixture(autouse=True)
def _clean_handlers():
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_hook = sys.excepthook
    saved_thread_hook = threading.excepthook
    root.handlers.clear()
    yield
    root.handlers.clear()
    root.handlers.extend(saved_handlers)
    sys.excepthook = saved_hook
    threading.excepthook = saved_thread_hook


def test_log_file_uses_redirected_data_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CCC_DATA_ROOT", str(tmp_path))
    target = app_logging.log_file()
    assert target == tmp_path / "logs" / "app.log"


def test_setup_creates_the_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CCC_DATA_ROOT", str(tmp_path))
    target = app_logging.setup_logging()
    logging.getLogger("CareCenterForCodex").info("hallo")
    assert target.is_file()
    assert "hallo" in target.read_text(encoding="utf-8")


def test_setup_is_idempotent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CCC_DATA_ROOT", str(tmp_path))
    app_logging.setup_logging()
    app_logging.setup_logging()
    logging.getLogger("CareCenterForCodex").info("einmal")
    text = app_logging.log_file().read_text(encoding="utf-8")
    assert text.count("einmal") == 1


def test_survives_missing_stderr(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CCC_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(sys, "stderr", None)
    target = app_logging.setup_logging()
    logging.getLogger("CareCenterForCodex").warning("fensterlos")
    assert "fensterlos" in target.read_text(encoding="utf-8")


def test_crash_handler_writes_to_the_log(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CCC_DATA_ROOT", str(tmp_path))
    target = app_logging.setup_logging()
    app_logging.install_crash_handler()

    try:
        raise RuntimeError("spurloser Absturz")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())

    text = target.read_text(encoding="utf-8")
    assert "spurloser Absturz" in text
    assert "CRITICAL" in text


def test_keyboard_interrupt_is_not_a_crash(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CCC_DATA_ROOT", str(tmp_path))
    target = app_logging.setup_logging()
    app_logging.install_crash_handler()

    try:
        raise KeyboardInterrupt
    except KeyboardInterrupt:
        sys.excepthook(*sys.exc_info())

    assert "CRITICAL" not in target.read_text(encoding="utf-8")


def test_unicode_survives_in_the_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CCC_DATA_ROOT", str(tmp_path))
    target = app_logging.setup_logging()
    logging.getLogger("CareCenterForCodex").info("Umlaute: äöüß")
    assert "äöüß" in target.read_text(encoding="utf-8")


def test_rotation_is_configured(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CCC_DATA_ROOT", str(tmp_path))
    app_logging.setup_logging()
    handlers = [
        handler
        for handler in logging.getLogger().handlers
        if isinstance(handler, logging.handlers.RotatingFileHandler)
    ]
    assert handlers
    assert handlers[0].maxBytes > 0
    assert handlers[0].backupCount > 0

