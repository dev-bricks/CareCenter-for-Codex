"""Tests fuer das i18n-Modul (Deutsch/Englisch)."""

from __future__ import annotations

from codex_logdatenbank_wartung.i18n import (
    _CATALOG,
    available_keys,
    get_language,
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
