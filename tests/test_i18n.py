"""Tests fuer das i18n-Modul (Deutsch/Englisch)."""

from __future__ import annotations

from codex_logdatenbank_wartung.i18n import (
    _CATALOG,
    available_keys,
    get_language,
    language_label,
    normalize_language,
    set_language,
    t,
)


def test_default_language_is_german() -> None:
    set_language("de")
    assert get_language() == "de"


def test_german_translation() -> None:
    set_language("de")
    assert t("ready") == "Bereit."
    assert t("maintenance_done_ok") == "Wartung abgeschlossen."


def test_english_translation() -> None:
    set_language("en")
    assert t("ready") == "Ready."
    assert t("maintenance_done_ok") == "Maintenance completed."
    set_language("de")


def test_format_parameters() -> None:
    set_language("de")
    result = t("waiting_for_idle", cpu=42.7)
    assert "43%" in result or "42%" in result

    set_language("en")
    result = t("waiting_for_idle", cpu=42.7)
    assert "43%" in result or "42%" in result
    set_language("de")


def test_unknown_key_returns_key() -> None:
    assert t("nonexistent_key_xyz") == "nonexistent_key_xyz"


def test_all_keys_have_both_languages() -> None:
    """Jeder Eintrag muss sowohl 'de' als auch 'en' enthalten."""
    missing: list[str] = []
    for key, translations in _CATALOG.items():
        if "de" not in translations:
            missing.append(f"{key}: missing 'de'")
        if "en" not in translations:
            missing.append(f"{key}: missing 'en'")
    assert not missing, f"Fehlende Uebersetzungen: {missing}"


def test_available_keys_returns_sorted_list() -> None:
    keys = available_keys()
    assert isinstance(keys, list)
    assert len(keys) > 10
    assert keys == sorted(keys)


def test_format_with_missing_param_does_not_crash() -> None:
    set_language("de")
    result = t("waiting_for_idle")
    assert isinstance(result, str)
    assert len(result) > 0


def test_language_switch_is_consistent() -> None:
    set_language("en")
    en = t("process_check_ok")
    set_language("de")
    de = t("process_check_ok")
    assert en != de
    assert "No Codex" in en
    assert "Keine Codex" in de


def test_language_helpers_normalize_and_label_values() -> None:
    assert normalize_language("EN") == "en"
    assert normalize_language(" de ") == "de"
    assert normalize_language("fr") is None

    set_language("en")
    assert language_label("de") == "German"
    assert language_label("en") == "English"

    set_language("de")
    assert language_label("de") == "Deutsch"
    assert language_label("en") == "Englisch"


def test_automation_menu_translations_are_localized_with_umlauts() -> None:
    set_language("de")
    assert t("automations_menu") == "Automatisierungen"
    assert "ausgeschalteten Automatisierungen" in t("automations_restore_ccc")
    assert "gestaffelt" in t("automations_activate_all_staggered")

    set_language("en")
    assert t("automations_menu") == "Automations"
    assert "disabled by CCC" in t("automations_restore_ccc")
    set_language("de")


# ---------------------------------------------------------------------------
# Integration: i18n wirkt im echten Code-Pfad (nicht nur im Katalog)
# ---------------------------------------------------------------------------

def test_maintenance_runner_uses_i18n_english(tmp_path) -> None:
    """MaintenanceRunner gibt englische Meldungen aus, wenn language=en gesetzt ist."""
    import sqlite3

    from codex_logdatenbank_wartung.config import MaintenanceConfig
    from codex_logdatenbank_wartung.maintenance import MaintenanceRunner
    from codex_logdatenbank_wartung.processes import ProcessInfo

    set_language("en")
    try:
        db_path = tmp_path / "logs_2.sqlite"
        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE logs (id INTEGER PRIMARY KEY, msg TEXT)")
            conn.execute("INSERT INTO logs (msg) VALUES ('test')")

        CODEX_EXE = r"C:\Users\dev\AppData\Local\Programs\Codex\Codex.exe"
        config = MaintenanceConfig(
            codex_executable=CODEX_EXE,
            database_path=str(db_path),
            backup_dir=str(tmp_path / "backups"),
            log_dir=str(tmp_path / "logs"),
            maintenance_lock_path=str(tmp_path / "maintenance.lock"),
        )

        def provider():
            return [ProcessInfo(99, "Codex.exe", CODEX_EXE, f'"{CODEX_EXE}"')]
        result = MaintenanceRunner(config, provider).run(dry_run=True)

        assert result.status == "blocked"
        blocked_step = next(s for s in result.steps if s.status == "blocked")
        assert "running" in blocked_step.message.lower() or "Desktop" in blocked_step.message
    finally:
        set_language("de")


def test_maintenance_runner_uses_i18n_german(tmp_path) -> None:
    """MaintenanceRunner gibt deutsche Meldungen aus, wenn language=de gesetzt ist."""
    import sqlite3

    from codex_logdatenbank_wartung.config import MaintenanceConfig
    from codex_logdatenbank_wartung.maintenance import MaintenanceRunner

    set_language("de")
    db_path = tmp_path / "logs_2.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE logs (id INTEGER PRIMARY KEY, msg TEXT)")
        conn.execute("INSERT INTO logs (msg) VALUES ('test')")

    config = MaintenanceConfig(
        codex_executable=r"C:\test\Codex.exe",
        database_path=str(db_path),
        backup_dir=str(tmp_path / "backups"),
        log_dir=str(tmp_path / "logs"),
        maintenance_lock_path=str(tmp_path / "maintenance.lock"),
    )

    result = MaintenanceRunner(config, lambda: []).run(dry_run=False)
    ok_step = next(s for s in result.steps if s.name == "Codex-Prozessprüfung")
    assert "Keine Codex" in ok_step.message
