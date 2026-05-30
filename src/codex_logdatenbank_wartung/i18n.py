"""Minimale i18n-Unterstützung (Deutsch/Englisch) für UI-Texte.

Übersetzungskatalog als einfaches Dict — kein externes Framework nötig für zwei Sprachen.
Die aktive Sprache wird einmal beim Start gesetzt (Config oder System-Locale) und bleibt
für die Laufzeit konstant.
"""

from __future__ import annotations

import locale
from typing import Literal

Language = Literal["de", "en"]

_CATALOG: dict[str, dict[Language, str]] = {
    # -- Tray / StatusWindow --
    "ready": {"de": "Bereit.", "en": "Ready."},
    "maintenance_running": {"de": "Eine Wartung läuft bereits.", "en": "Maintenance already running."},
    "maintenance_safe_label": {"de": "Safe-Modus", "en": "Safe mode"},
    "maintenance_fast_label": {"de": "Fast-Modus", "en": "Fast mode"},
    "maintenance_started": {
        "de": "Wartung gestartet ({mode}). Fortschritt über Klick aufs Tray-Symbol.",
        "en": "Maintenance started ({mode}). Click tray icon for progress.",
    },
    "maintenance_done_ok": {"de": "Wartung abgeschlossen.", "en": "Maintenance completed."},
    "maintenance_done_blocked": {
        "de": "Verschoben — Codex war aktiv (kein Lauf abgebrochen).",
        "en": "Deferred — Codex was active (no run interrupted).",
    },
    "maintenance_done_failed": {
        "de": "Fehlgeschlagen — Details im Protokoll.",
        "en": "Failed — see log for details.",
    },
    "codex_active_no_close": {
        "de": "Codex läuft und Schließen ist nicht freigegeben.",
        "en": "Codex is running and closing is not permitted.",
    },
    "waiting_for_idle": {
        "de": "Wartung eingereiht — warte auf Codex-Leerlauf (CPU {cpu:.0f}%).",
        "en": "Maintenance queued — waiting for Codex idle (CPU {cpu:.0f}%).",
    },
    "idle_timeout": {
        "de": "Codex blieb aktiv; Wartung verschoben — kein Lauf abgebrochen.",
        "en": "Codex stayed active; maintenance deferred — no run interrupted.",
    },
    # -- Prozessprüfung --
    "process_check_blocked": {
        "de": "Codex-Desktop läuft (exakter Exe-Pfad erkannt). Wartung wird nicht gestartet.",
        "en": "Codex Desktop running (exact exe path matched). Maintenance will not start.",
    },
    "process_check_ok": {
        "de": "Keine Codex-Desktop-Prozesse erkannt.",
        "en": "No Codex Desktop processes detected.",
    },
    "process_check_fail_closed": {
        "de": "Prozessliste konnte nicht gelesen werden (fail-closed).",
        "en": "Process list could not be read (fail-closed).",
    },
    # -- Watchdog --
    "watchdog_codex_active": {
        "de": "Codex aktiv (Renderer vorhanden) — Wächter hält sich raus.",
        "en": "Codex active (renderer present) — watchdog standing down.",
    },
    "watchdog_idle": {"de": "Codex zu, keine hängenden Reste.", "en": "Codex closed, no hanging remnants."},
    "watchdog_disabled": {
        "de": "Hängende Reste erkannt, aber der Wächter ist deaktiviert.",
        "en": "Hanging remnants detected, but watchdog is disabled.",
    },
    "watchdog_busy": {
        "de": "Codex-Baum arbeitet aktiv (CPU) — kein Eingriff.",
        "en": "Codex tree actively working (CPU) — no intervention.",
    },
    "watchdog_reaped": {
        "de": "{detail}. Du kannst Codex jetzt sauber starten.",
        "en": "{detail}. You can now start Codex cleanly.",
    },
    # -- Diagnose / Repair --
    "zombie_detected": {
        "de": "Codex-Hauptprozess ohne Renderer erkannt (hängt/Fenster tot).",
        "en": "Codex main process without renderer detected (hanging/window dead).",
    },
    "stale_lockfile": {
        "de": "Electron-Lockfile vorhanden, aber kein Codex-Hauptprozess läuft.",
        "en": "Electron lockfile present, but no Codex main process running.",
    },
    "lockfile_removed": {
        "de": "Verwaistes Lockfile entfernt.",
        "en": "Stale lockfile removed.",
    },
    "repair_nothing_to_do": {"de": "Keine Startblockaden erkannt.", "en": "No start blockers detected."},
    # -- Store --
    "store_reinstall_needed": {
        "de": "Keine Codex-Installation gefunden — Neuinstallation aus dem Microsoft Store nötig.",
        "en": "No Codex installation found — reinstall from Microsoft Store required.",
    },
    "codex_already_running": {"de": "Codex läuft bereits — nichts zu tun.", "en": "Codex already running — nothing to do."},
}

_current: Language = "de"


def detect_language() -> Language:
    """Sprache aus System-Locale ableiten (Fallback: Deutsch)."""
    try:
        lang, _ = locale.getdefaultlocale()
        if lang and lang.lower().startswith("en"):
            return "en"
    except (ValueError, TypeError):
        pass
    return "de"


def set_language(lang: Language) -> None:
    global _current
    _current = lang


def get_language() -> Language:
    return _current


def t(key: str, **kwargs: object) -> str:
    """Übersetze einen Schlüssel in die aktive Sprache. Unbekannte Keys werden direkt zurückgegeben."""
    entry = _CATALOG.get(key)
    if entry is None:
        return key
    text = entry.get(_current) or entry.get("de") or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def available_keys() -> list[str]:
    """Alle verfügbaren Übersetzungsschlüssel (für Tests)."""
    return sorted(_CATALOG.keys())
