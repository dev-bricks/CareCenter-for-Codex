"""Tests fuer das i18n-Modul (Deutsch/Englisch)."""

from __future__ import annotations

from pathlib import Path

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


# ---------------------------------------------------------------------------
# Tier-2 Mehrsprachigkeit (P-006): 4-Stufen-Fallback & Locales-Support
# ---------------------------------------------------------------------------

def test_tier2_constants_and_types() -> None:
    from codex_logdatenbank_wartung.i18n import (
        DEFAULT_LANGUAGE,
        FALLBACK_CHAIN,
        LANGUAGE_DISPLAY_NAMES,
        LANGUAGES,
        SUPPORTED_LANGUAGES,
    )

    assert SUPPORTED_LANGUAGES == ("de", "en", "es", "zh", "ja", "ru")
    assert DEFAULT_LANGUAGE == "de"
    assert FALLBACK_CHAIN == ("en", "de")
    assert LANGUAGES == SUPPORTED_LANGUAGES

    for lang in SUPPORTED_LANGUAGES:
        assert lang in LANGUAGE_DISPLAY_NAMES
        assert len(LANGUAGE_DISPLAY_NAMES[lang]) > 0


def test_tier2_normalization_and_locales() -> None:
    assert normalize_language("es") == "es"
    assert normalize_language("ES") == "es"
    assert normalize_language(" es-ES ") == "es"
    assert normalize_language("zh") == "zh"
    assert normalize_language("zh_CN") == "zh"
    assert normalize_language("ja") == "ja"
    assert normalize_language("ja-JP") == "ja"
    assert normalize_language("ru") == "ru"
    assert normalize_language("ru_RU") == "ru"
    assert normalize_language("fr") is None
    assert normalize_language("it_IT") is None
    assert normalize_language(None) is None
    assert normalize_language(123) is None


def test_four_stage_fallback_chain() -> None:
    """Prüft die 4-stufige Fallback-Kette: Zielsprache -> en -> de -> key."""
    # Test-Einträge im Katalog simulieren
    _CATALOG["_test_fallback_all"] = {"de": "DE_Wert", "en": "EN_Wert", "es": "ES_Wert"}
    _CATALOG["_test_fallback_no_es"] = {"de": "DE_Wert", "en": "EN_Wert"}
    _CATALOG["_test_fallback_only_de"] = {"de": "DE_Wert"}
    _CATALOG["_test_fallback_none"] = {}

    try:
        set_language("es")
        # Stufe 1: Zielsprache vorhanden -> ES_Wert
        assert t("_test_fallback_all") == "ES_Wert"
        # Stufe 2: Zielsprache fehlt -> Fallback auf EN
        assert t("_test_fallback_no_es") == "EN_Wert"
        # Stufe 3: Zielsprache & EN fehlen -> Fallback auf DE
        assert t("_test_fallback_only_de") == "DE_Wert"
        # Stufe 4: Keine Übersetzung vorhanden -> Key selbst
        assert t("_test_fallback_none") == "_test_fallback_none"
        assert t("_test_completely_unknown") == "_test_completely_unknown"
    finally:
        set_language("de")
        _CATALOG.pop("_test_fallback_all", None)
        _CATALOG.pop("_test_fallback_no_es", None)
        _CATALOG.pop("_test_fallback_only_de", None)
        _CATALOG.pop("_test_fallback_none", None)


def test_language_labels_for_all_tier2_languages() -> None:
    set_language("de")
    assert language_label("de") == "Deutsch"
    assert language_label("en") == "Englisch"
    assert language_label("es") == "Spanisch"
    assert language_label("zh") == "Chinesisch"
    assert language_label("ja") == "Japanisch"
    assert language_label("ru") == "Russisch"

    set_language("en")
    assert language_label("de") == "German"
    assert language_label("en") == "English"
    assert language_label("es") == "Spanish"
    assert language_label("zh") == "Chinese"
    assert language_label("ja") == "Japanese"
    assert language_label("ru") == "Russian"
    set_language("de")


def test_locales_file_paths_and_loading(tmp_path) -> None:
    import json

    from codex_logdatenbank_wartung.i18n import (
        export_translations_json,
        get_locales_path,
        load_translations_file,
    )

    path = get_locales_path()
    assert isinstance(path, Path)

    # Exportieren in temporäre Datei
    export_path = tmp_path / "exported.json"
    exported = export_translations_json(export_path)
    assert exported.is_file()

    with open(export_path, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict)
    assert "ready" in data

    # Laden aus temporärer Datei mit neuem Schlüssel
    custom_json = tmp_path / "custom.json"
    with open(custom_json, "w", encoding="utf-8") as f:
        json.dump({"_custom_dyn_key": {"de": "Dynamisch", "en": "Dynamic"}}, f)

    loaded_count = load_translations_file(custom_json)
    assert loaded_count == 1
    assert t("_custom_dyn_key") == "Dynamisch"

    set_language("en")
    assert t("_custom_dyn_key") == "Dynamic"
    set_language("de")

    # Aufräumen
    _CATALOG.pop("_custom_dyn_key", None)

    # Nicht existierende Datei oder Fehler führen nicht zum Absturz
    assert load_translations_file(tmp_path / "nonexistent.json") == 0


def test_locales_translations_json_exists_and_valid() -> None:
    import json

    from codex_logdatenbank_wartung.i18n import get_locales_path

    locales_file = get_locales_path()
    assert locales_file.is_file(), f"locales/translations.json fehlt unter {locales_file}"

    with open(locales_file, encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, dict)
    assert len(data) >= 318
    assert "ready" in data
    assert "settings_language" in data
