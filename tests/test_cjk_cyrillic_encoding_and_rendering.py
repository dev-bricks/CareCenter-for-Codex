"""Tests für CCC-I18N-05: CJK- (ZH, JA) und Kyrillisch- (RU) Rendering- und Encoding-Härtung.

Validiert:
1. Console- und File-Logging mit CJK- und kyrillischen String-Payloads ohne cp1252-Crashes.
2. Defensive Stream-Rekonfiguration via ensure_console_encoding().
3. CLI-Ausführungsresilienz unter CJK- und kyrillischen Textausgaben.
4. i18n-Sprachumschaltung, Platzhalter-Interpolation und 4-Stufen-Fallback für zh, ja, ru.
5. Qt6/PySide6 Tray-Menü, Action- und Label-Font-Rendering mit CJK/Cyrillic-Glyphen.
"""

from __future__ import annotations

import io
import logging
import sys
from unittest.mock import MagicMock

import pytest
from PySide6.QtGui import QAction, QFont, QFontMetrics
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QMenu, QPushButton

from codex_logdatenbank_wartung.cli import main
from codex_logdatenbank_wartung.i18n import (
    SUPPORTED_LANGUAGES,
    get_language,
    language_label,
    normalize_language,
    set_language,
    t,
)
from codex_logdatenbank_wartung.runtime.app_logging import (
    ensure_console_encoding,
    setup_logging,
)
from codex_logdatenbank_wartung.tray import StatusWindow


@pytest.fixture(autouse=True)
def _reset_i18n_and_logging():
    initial_lang = get_language()
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    yield
    set_language(initial_lang)
    root.handlers.clear()
    root.handlers.extend(saved_handlers)


def _get_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(["-platform", "offscreen"])
    return app


# ==============================================================================
# 1. Encoding- & Stream-Resilienz
# ==============================================================================


def test_ensure_console_encoding_resilience(monkeypatch):
    """ensure_console_encoding rekonfiguriert Streams und fängt Fehler defensiv ab."""
    mock_stdout = MagicMock()
    mock_stderr = MagicMock()
    mock_stdout.reconfigure = MagicMock()
    mock_stderr.reconfigure = MagicMock(side_effect=OSError("Unsupported ioctl"))

    monkeypatch.setattr(sys, "stdout", mock_stdout)
    monkeypatch.setattr(sys, "stderr", mock_stderr)

    # Darf trotz OSError auf stderr nicht abstürzen
    ensure_console_encoding()

    mock_stdout.reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")
    mock_stderr.reconfigure.assert_called_once_with(encoding="utf-8", errors="replace")


def test_ensure_console_encoding_handles_none_and_missing_reconfigure(monkeypatch):
    """ensure_console_encoding funktioniert auch bei None-Streams oder Streams ohne reconfigure."""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", object())  # kein reconfigure-Attribut

    # Darf keinen AttributeError auslösen
    ensure_console_encoding()


def test_file_logging_cjk_and_cyrillic_payloads(tmp_path, monkeypatch):
    """Dateilogging speichert CJK- und kyrillische Zeichen verlustfrei in UTF-8."""
    monkeypatch.setenv("CCC_DATA_ROOT", str(tmp_path))
    target = setup_logging()

    logger = logging.getLogger("CareCenterForCodex")
    zh_payload = "简体中文日志测试: 修复Codex日志数据库及清理僵尸进程"
    ja_payload = "日本語ログテスト: Codexログデータベースのメンテナンスとゾンビプロセス終了"
    ru_payload = "Русский лог-тест: Обслуживание базы данных журнала Codex и завершение процессов-зомби"

    logger.info(zh_payload)
    logger.warning(ja_payload)
    logger.error(ru_payload)

    content = target.read_text(encoding="utf-8")
    assert zh_payload in content
    assert ja_payload in content
    assert ru_payload in content


def test_console_stream_handler_cp1252_resilience(tmp_path, monkeypatch):
    """Simulierter cp1252-Stream mit errors='replace' wirft bei CJK/Cyrillic keinen UnicodeEncodeError."""
    monkeypatch.setenv("CCC_DATA_ROOT", str(tmp_path))

    # Erzeuge einen simulierten Stream, der cp1252 mit replace emuliert
    raw_buffer = io.BytesIO()
    cp1252_stream = io.TextIOWrapper(raw_buffer, encoding="cp1252", errors="replace")

    monkeypatch.setattr(sys, "stderr", cp1252_stream)
    setup_logging(console=True)

    logger = logging.getLogger("CareCenterForCodex")
    # Darf nicht abstürzen trotz CJK / Kyrillisch auf cp1252-Stream
    logger.info("Chinese: 修复, Japanese: メンテナンス, Russian: Обслуживание")
    cp1252_stream.flush()

    raw_bytes = raw_buffer.getvalue()
    assert len(raw_bytes) > 0


# ==============================================================================
# 2. i18n & 4-Stufen-Fallback für ZH, JA, RU
# ==============================================================================


def test_i18n_language_switching_zh_ja_ru():
    """Umschaltung auf zh, ja, ru funktioniert und liefert valide Sprachbezeichnungen."""
    assert "zh" in SUPPORTED_LANGUAGES
    assert "ja" in SUPPORTED_LANGUAGES
    assert "ru" in SUPPORTED_LANGUAGES

    # Normalisierung
    assert normalize_language("zh-CN") == "zh"
    assert normalize_language("zh_Hans") == "zh"
    assert normalize_language("ja_JP") == "ja"
    assert normalize_language("ru-RU") == "ru"

    # Set & Get
    set_language("zh")
    assert get_language() == "zh"
    assert language_label("zh") == "中文"

    set_language("ja")
    assert get_language() == "ja"
    assert language_label("ja") == "日本語"

    set_language("ru")
    assert get_language() == "ru"
    assert language_label("ru") == "Русский"


def test_i18n_fallback_chain_for_cjk_and_cyrillic():
    """Schlüssel ohne CJK/Cyrillic-Übersetzung fallen deterministisch auf en -> de durch."""
    set_language("zh")
    # Ein Schlüssel, der de/en/es hat, aber (noch) kein zh
    translated = t("settings_group")
    # Muss auf Englisch zurückfallen ("Settings") statt auf den rohen Schlüssel
    assert translated == "Settings"

    set_language("ja")
    translated_ja = t("settings_group")
    assert translated_ja == "Settings"

    set_language("ru")
    translated_ru = t("settings_group")
    assert translated_ru == "Settings"


def test_i18n_formatting_with_cjk_and_cyrillic_parameters():
    """t() formatiert dynamische Parameter mit CJK- und kyrillischen Inhalten fehlerfrei."""
    set_language("de")
    res_zh = t("cli_database", path="C:\\用户\\测试\\logs.sqlite")
    assert "C:\\用户\\测试\\logs.sqlite" in res_zh

    res_ja = t("cli_database", path="C:\\ユーザー\\テスト\\logs.sqlite")
    assert "C:\\ユーザー\\テスト\\logs.sqlite" in res_ja

    res_ru = t("cli_database", path="C:\\Пользователи\\Тест\\logs.sqlite")
    assert "C:\\Пользователи\\Тест\\logs.sqlite" in res_ru


# ==============================================================================
# 3. CLI-Resilienz
# ==============================================================================


def test_cli_main_cjk_help_and_execution(monkeypatch):
    """CLI startet und führt help/args ohne Encoding-Fehler aus."""
    test_args = ["--help"]
    out_capture = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out_capture)

    with pytest.raises(SystemExit) as exc:
        main(test_args)
    assert exc.value.code == 0
    assert "codex-logwartung" in out_capture.getvalue()


# ==============================================================================
# 4. Qt6/PySide6 Font-Rendering & UI-Elemente
# ==============================================================================


def test_qt_widgets_render_cjk_and_cyrillic_glyphs(monkeypatch):
    """Qt-Widgets und Menüs akzeptieren und berechnen Font-Metriken für CJK- & Cyrillic-Glyphen."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    _get_qapp()

    font = QFont()
    metrics = QFontMetrics(font)

    zh_text = "CareCenter 修复与维护"
    ja_text = "CareCenter 修復とメンテナンス"
    ru_text = "Восстановление и обслуживание CareCenter"

    # Verifikation Font-Metriken: horizontale Ausdehnung muss > 0 sein
    assert metrics.horizontalAdvance(zh_text) > 0
    assert metrics.horizontalAdvance(ja_text) > 0
    assert metrics.horizontalAdvance(ru_text) > 0

    # QMenu & QAction
    menu = QMenu()
    action_zh = QAction(zh_text, menu)
    action_ja = QAction(ja_text, menu)
    action_ru = QAction(ru_text, menu)

    assert action_zh.text() == zh_text
    assert action_ja.text() == ja_text
    assert action_ru.text() == ru_text

    # QLabel & QPushButton
    label = QLabel(zh_text)
    assert label.text() == zh_text

    btn = QPushButton(ja_text)
    assert btn.text() == ja_text

    combo = QComboBox()
    combo.addItem(ru_text, "ru")
    assert combo.itemText(0) == ru_text


def test_status_window_retranslate_under_zh_ja_ru(monkeypatch):
    """StatusWindow aktualisiert alle Widgets und Buttons unter zh, ja und ru ohne Exceptions."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    _get_qapp()

    window = StatusWindow()

    for lang in ("zh", "ja", "ru"):
        set_language(lang)
        window.retranslate()
        # Buttons müssen valide Texte tragen
        assert len(window.repair_button.text()) > 0
        assert len(window.diagnose_button.text()) > 0
        assert len(window.safe_button.text()) > 0
        assert len(window.fast_button.text()) > 0
