"""Tests fuer den CLI-Einstiegspunkt (main)."""

from __future__ import annotations

from pathlib import Path

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


def test_main_sets_language_from_config(tmp_path: Path) -> None:
    """Wenn config.language='en' gesetzt ist, wird die Sprache in main() auf Englisch gestellt."""
    import json
    from codex_logdatenbank_wartung.i18n import get_language, set_language

    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"language": "en"}), encoding="utf-8")

    db = tmp_path / "logs_2.sqlite"
    db.write_text("", encoding="utf-8")

    set_language("de")
    main(["--config", str(cfg), "doctor"])

    assert get_language() == "en"
    set_language("de")
