"""Tests fuer den CLI-Einstiegspunkt (main)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from codex_logdatenbank_wartung.cli import main


def test_init_config_writes_on_fresh_system(tmp_path: Path, capsys) -> None:
    """init-config muss die Config-Datei erstellen und 'geschrieben' melden,
    auch wenn main() vorher die Sprache initialisieren will."""
    cfg = tmp_path / "config.json"
    assert not cfg.exists()

    rc = main(["--config", str(cfg), "init-config"])

    assert rc == 0
    assert cfg.exists()
    out = capsys.readouterr().out
    assert "geschrieben" in out.lower() or "written" in out.lower()


def test_init_config_reports_existing_without_force(tmp_path: Path, capsys) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")

    rc = main(["--config", str(cfg), "init-config"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "existiert" in out.lower() or "exists" in out.lower()


def test_init_config_reports_existing_in_english_from_config(tmp_path: Path, capsys) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"language": "en"}), encoding="utf-8")

    rc = main(["--config", str(cfg), "init-config"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Configuration already exists" in out


def test_main_sets_language_from_config(tmp_path: Path) -> None:
    """Wenn config.language='en' gesetzt ist, wird die Sprache in main() auf Englisch gestellt."""
    from codex_logdatenbank_wartung.i18n import get_language, set_language

    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"language": "en"}), encoding="utf-8")

    db = tmp_path / "logs_2.sqlite"
    db.write_text("", encoding="utf-8")

    set_language("de")
    main(["--config", str(cfg), "doctor"])

    assert get_language() == "en"
    set_language("de")


def test_store_materials_command_returns_warning_for_missing_files(tmp_path: Path, capsys) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")

    rc = main(
        [
            "--config",
            str(cfg),
            "store-materials",
            "--project-root",
            str(tmp_path),
        ]
    )

    assert rc == 1
    out = capsys.readouterr().out
    assert "Store-Materialien" in out


def test_store_screenshot_command_writes_png(tmp_path: Path, capsys, monkeypatch) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")
    output = tmp_path / "README" / "screenshots" / "main.png"
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    rc = main(
        [
            "--config",
            str(cfg),
            "store-screenshot",
            "--output",
            str(output),
        ]
    )

    assert rc == 0
    assert output.exists()
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert "Store-Screenshot geschrieben" in capsys.readouterr().out


def test_safe_start_install_command_uses_installer(tmp_path: Path, capsys) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")

    class Result:
        status = "ok"

        def to_text(self) -> str:
            return "Safe Start installiert"

    with patch(
        "codex_logdatenbank_wartung.safe_start_integration.install_safe_start_package",
        return_value=Result(),
    ) as installer:
        rc = main(["--config", str(cfg), "safe-start-install", "--target", "local-src"])

    assert rc == 0
    installer.assert_called_once_with(target="local-src")
    assert "Safe Start installiert" in capsys.readouterr().out


def test_tray_command_starts_runtime_logging_before_launch(tmp_path: Path) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")

    with patch("codex_logdatenbank_wartung.runtime.app_logging.start") as start_logging, patch(
        "codex_logdatenbank_wartung.tray.run_tray", return_value=0
    ) as run_tray:
        rc = main(["--config", str(cfg), "tray"])

    assert rc == 0
    start_logging.assert_called_once_with()
    run_tray.assert_called_once_with(cfg)
