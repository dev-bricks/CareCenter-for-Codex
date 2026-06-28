"""Leichtgewichtige i18n-Unterstützung (Deutsch/Englisch) für Enduser-Texte.

Der Katalog bleibt bewusst direkt im Code: Für zwei Sprachen ist ein externes
Framework mehr Reibung als Nutzen. Die aktive Sprache wird aus der Konfiguration
oder System-Locale gesetzt und kann im Tray über die Einstellungen gewechselt werden.
"""

from __future__ import annotations

import locale
from typing import Literal, cast

Language = Literal["de", "en"]
LANGUAGES: tuple[Language, ...] = ("de", "en")

_CATALOG: dict[str, dict[Language, str]] = {
    # -- Language / settings --
    "language_de": {"de": "Deutsch", "en": "German"},
    "language_en": {"de": "Englisch", "en": "English"},
    "settings_group": {"de": "Einstellungen", "en": "Settings"},
    "settings_config_audit": {"de": "Config-Audit", "en": "Config audit"},
    "settings_language": {"de": "Sprache:", "en": "Language:"},
    "settings_language_tooltip": {
        "de": "Sprache der Oberfläche ändern und in der lokalen Konfiguration speichern.",
        "en": "Change the interface language and save it in the local configuration.",
    },
    "settings_mcp_duplicates": {"de": "MCP-Duplikate:", "en": "MCP duplicates:"},
    "settings_unused_plugins": {"de": "Ungenutzte Plugins:", "en": "Unused plugins:"},
    "settings_audit_mode_tooltip": {
        "de": "off = ignorieren, notify = bei Fund benachrichtigen, auto = automatisch bereinigen",
        "en": "off = ignore, notify = notify when found, auto = fix automatically",
    },
    "settings_plugin_mode_tooltip": {
        "de": "off = ignorieren, notify = bei Fund benachrichtigen, auto = plattform-inkompatible Plugins automatisch deaktivieren",
        "en": "off = ignore, notify = notify when found, auto = disable platform-incompatible plugins automatically",
    },
    "settings_audit_now": {"de": "Audit jetzt ausführen", "en": "Run audit now"},
    "settings_audit_now_tooltip": {
        "de": "Config-Audit sofort starten (prüft MCP, Plugins und CLI).",
        "en": "Run the config audit now (checks MCP, plugins and CLI).",
    },
    "settings_language_saved": {
        "de": "Sprache gespeichert: {language}.",
        "en": "Language saved: {language}.",
    },
    # -- Tray / StatusWindow --
    "ready": {"de": "Bereit.", "en": "Ready."},
    "done": {"de": "Fertig.", "en": "Done."},
    "tray_ready": {
        "de": "{app}: bereit; entfernte Reste: {count}",
        "en": "{app}: ready; removed remnants: {count}",
    },
    "zombie_counter": {
        "de": "{count} hängende Codex-Reste seit Start entfernt",
        "en": "{count} hanging Codex remnants removed since start",
    },
    "window_close": {
        "de": "Schließen (läuft im Hintergrund weiter)",
        "en": "Close (continues in background)",
    },
    "window_close_tooltip": {
        "de": "Schließt nur das Fenster. Eine laufende Reparatur läuft weiter; über das Tray-Menü 'Status & Fortschritt anzeigen' jederzeit wieder öffnen.",
        "en": "Only closes the window. A running repair continues; reopen it any time from the tray menu via 'Show status & progress'.",
    },
    "open_carecenter": {"de": "CareCenter öffnen", "en": "Open CareCenter"},
    "open_carecenter_tooltip": {
        "de": "Öffnet das CareCenter-Fenster (Übersicht, Reparatur, Wartung, Store).",
        "en": "Open the CareCenter window (overview, repair, maintenance, Store).",
    },
    "show_status_progress": {
        "de": "Status & Fortschritt anzeigen",
        "en": "Show status & progress",
    },
    "quit": {"de": "Beenden", "en": "Quit"},
    "maintenance": {"de": "Wartung", "en": "Maintenance"},
    "maintenance_action_tooltip": {
        "de": "Öffnet das Fenster mit den Wartungs-Buttons (Safe/Fast: DB-Wartung).",
        "en": "Open the window with maintenance buttons (Safe/Fast: DB maintenance).",
    },
    "carecenter_busy": {
        "de": "CareCenter führt bereits eine Aktion aus.",
        "en": "CareCenter is already running an action.",
    },
    "maintenance_running": {"de": "Eine Wartung läuft bereits.", "en": "Maintenance already running."},
    "maintenance_safe_label": {"de": "Safe-Modus", "en": "Safe mode"},
    "maintenance_fast_label": {"de": "Fast-Modus", "en": "Fast mode"},
    "maintenance_safe_button": {"de": "Wartung – Safe", "en": "Maintenance - Safe"},
    "maintenance_fast_button": {"de": "Wartung – Fast", "en": "Maintenance - Fast"},
    "maintenance_cancel_button": {"de": "Abbrechen", "en": "Cancel"},
    "maintenance_safe_tooltip": {
        "de": "Wartet auf Codex-Leerlauf, schließt Codex, wartet, startet neu.",
        "en": "Waits for Codex to become idle, closes Codex, maintains, then restarts.",
    },
    "maintenance_fast_tooltip": {
        "de": "Sofort: Codex beenden und warten, ohne auf Leerlauf zu warten.",
        "en": "Immediate: close Codex and maintain without waiting for idle.",
    },
    "maintenance_cancel_tooltip": {
        "de": "Bricht einen wartenden Safe-Wartungslauf ab, bevor Codex geschlossen oder die Datenbank angefasst wird.",
        "en": "Cancels a waiting Safe maintenance run before Codex is closed or the database is touched.",
    },
    "maintenance_state_running": {
        "de": "Wartung läuft ({mode}) …",
        "en": "Maintenance running ({mode}) ...",
    },
    "maintenance_prepare": {"de": "Wird vorbereitet …", "en": "Preparing ..."},
    "maintenance_started": {
        "de": "Wartung gestartet ({mode}). Fortschritt über Klick aufs Tray-Symbol.",
        "en": "Maintenance started ({mode}). Click tray icon for progress.",
    },
    "maintenance_tooltip_started": {
        "de": "CareCenter: {mode} gestartet …",
        "en": "CareCenter: {mode} started ...",
    },
    "maintenance_done_ok": {"de": "Wartung abgeschlossen.", "en": "Maintenance completed."},
    "maintenance_done_blocked": {
        "de": "Verschoben — Codex war aktiv (kein Lauf abgebrochen).",
        "en": "Deferred — Codex was active (no run interrupted).",
    },
    "maintenance_done_cancelled": {
        "de": "Abgebrochen — Wartung wurde nicht gestartet.",
        "en": "Cancelled — maintenance was not started.",
    },
    "maintenance_done_failed": {
        "de": "Fehlgeschlagen — Details im Protokoll.",
        "en": "Failed — see log for details.",
    },
    "maintenance_cancel_requested": {
        "de": "Abbruch angefordert — Safe-Wartung stoppt beim nächsten sicheren Punkt.",
        "en": "Cancel requested — Safe maintenance will stop at the next safe point.",
    },
    "maintenance_cancel_noop": {
        "de": "Keine wartende Safe-Wartung aktiv.",
        "en": "No waiting Safe maintenance run is active.",
    },
    "maintenance_done_other": {"de": "Beendet: {status}", "en": "Finished: {status}"},
    "maintenance_toast_done": {"de": "CareCenter — fertig", "en": "CareCenter - done"},
    "click_for_details": {"de": "Klick für Details", "en": "click for details"},
    "detail_waited_idle": {"de": "auf Leerlauf gewartet", "en": "waited for idle"},
    "detail_closed_codex": {"de": "Codex beendet", "en": "closed Codex"},
    "detail_restarted_codex": {"de": "Codex neu gestartet", "en": "restarted Codex"},
    "detail_maintenance_status": {"de": "Wartung: {status}", "en": "Maintenance: {status}"},
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
    "tray_start_message": {
        "de": "Tray läuft. Klick aufs Symbol öffnet Status & Fortschritt.",
        "en": "Tray is running. Click the icon to open status & progress.",
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
    "process_check_step": {"de": "Codex-Prozessprüfung", "en": "Codex process check"},
    # -- Watchdog --
    "watchdog_menu": {
        "de": "Auto-Wächter: Start-Reste entfernen",
        "en": "Auto watchdog: remove start remnants",
    },
    "watchdog_tooltip": {
        "de": "Überwacht im Hintergrund: ist Codex zu und hängen alte Reste (Ghost-Prozess ohne Fenster / verwaistes Lockfile), werden sie entfernt, damit der nächste Start sauber ist. Beendet nie eine aktive Sitzung und nie die Codex-CLI. Benachrichtigt beim Aufräumen.",
        "en": "Watches in the background: when Codex is closed and old remnants remain (ghost process without window / stale lockfile), removes them so the next start is clean. Never ends an active session or the Codex CLI. Notifies when cleanup happened.",
    },
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
    "watchdog_reaped_short": {
        "de": "Hängende Codex-Reste entfernt.",
        "en": "Removed hanging Codex remnants.",
    },
    "watchdog_toast_title": {
        "de": "CareCenter – Start-Prävention",
        "en": "CareCenter - start prevention",
    },
    "watchdog_toggle_title": {
        "de": "Codex-Start-Prävention",
        "en": "Codex start prevention",
    },
    "watchdog_enabled": {"de": "Auto-Wächter aktiv.", "en": "Auto watchdog enabled."},
    "watchdog_disabled_toast": {
        "de": "Auto-Wächter deaktiviert.",
        "en": "Auto watchdog disabled.",
    },
    # -- Diagnose / Repair --
    "repair_codex": {"de": "Codex reparieren", "en": "Repair Codex"},
    "repair_codex_tooltip": {
        "de": "Begrenzte Reparatur (ohne Admin): hängende Reste entfernen, ClipSVC, sanftes Re-Register, ein Reset-Fallback. Stoppt, sobald Codex startet. Schlägt bei Bedarf Reboot, Neustart als Administrator oder Store-Neuinstallation vor.",
        "en": "Bounded repair (no admin): remove hanging remnants, ClipSVC, gentle re-register, one reset fallback. Stops as soon as Codex starts. Suggests reboot, admin restart or Store reinstall only when needed.",
    },
    "repair_running": {"de": "Läuft bereits.", "en": "Already running."},
    "diagnose": {"de": "Diagnose", "en": "Diagnose"},
    "diagnose_tooltip": {
        "de": "Nur prüfen (read-only), nichts ändern.",
        "en": "Check only (read-only), change nothing.",
    },
    "repair_light_state": {
        "de": "Codex-Reparatur: leichte Stufe (ohne Admin) …",
        "en": "Codex repair: light stage (no admin) ...",
    },
    "repair_light_prepare": {
        "de": "Lage prüfen und hängende Reste entfernen …",
        "en": "Checking state and removing hanging remnants ...",
    },
    "repair_light_reap": {
        "de": "Leichte Stufe: hängende Codex-Reste entfernen (ohne Admin) …",
        "en": "Light stage: removing hanging Codex remnants (no admin) ...",
    },
    "repair_launch_wait": {
        "de": "Codex starten und auf Fenster warten …",
        "en": "Starting Codex and waiting for a window ...",
    },
    "repair_light_ok": {
        "de": "Codex gestartet — leichte Reparatur genügte (kein Admin nötig).",
        "en": "Codex started — light repair was enough (no admin needed).",
    },
    "repair_light_escalate": {
        "de": "Leichte Stufe genügte nicht — volle Reparatur folgt …",
        "en": "Light stage was not enough — full repair follows ...",
    },
    "repair_full_needed": {
        "de": "Volle Reparatur nötig …",
        "en": "Full repair needed ...",
    },
    "repair_escalating": {
        "de": "Eskaliere zur vollen Reparatur …",
        "en": "Escalating to full repair ...",
    },
    "repair_reinstall_hint": {
        "de": "→ Knopf 'Codex neu installieren' (öffnet die Store-Seite). Es ist Teil desselben Problems: ohne Installation kann nichts starten.",
        "en": "→ Use 'Reinstall Codex' (opens the Store page). It is the same problem: without an installation, nothing can start.",
    },
    "repair_toast_title": {
        "de": "CareCenter – Codex reparieren",
        "en": "CareCenter - repair Codex",
    },
    "safe_start_check": {"de": "Safe Start prüfen", "en": "Check Safe Start"},
    "safe_start_tooltip": {
        "de": "Zeigt Safe-Start-Snapshots, Start-Storm-Signale und seltene Catch-up-Kandidaten.",
        "en": "Shows Safe Start snapshots, start-storm signals and rare catch-up candidates.",
    },
    "safe_start_install": {
        "de": "Safe Start installieren",
        "en": "Install Safe Start",
    },
    "safe_start_install_tooltip": {
        "de": "Installiert oder aktualisiert Safe Start for Codex über pip. Bevorzugt die lokale Schwesterquelle, sonst das Paket safe-start-for-codex.",
        "en": "Installs or updates Safe Start for Codex via pip. Prefers the local sibling source, otherwise the safe-start-for-codex package.",
    },
    "safe_start_install_running": {
        "de": "Safe Start wird installiert oder aktualisiert …",
        "en": "Installing or updating Safe Start ...",
    },
    "safe_start_install_progress": {
        "de": "pip installiert Safe Start for Codex …",
        "en": "pip is installing Safe Start for Codex ...",
    },
    "safe_start_install_ok": {
        "de": "Safe Start ist installiert oder aktualisiert.",
        "en": "Safe Start is installed or updated.",
    },
    "safe_start_install_failed": {
        "de": "Safe Start konnte nicht installiert werden.",
        "en": "Safe Start could not be installed.",
    },
    "safe_start_active": {
        "de": "Safe Start ist aktiv; CareCenter hält Start-Gegenaktionen zurück.",
        "en": "Safe Start is active; CareCenter is holding back start counteractions.",
    },
    "safe_start_catchup": {
        "de": "{count} seltene Automation(en) für Catch-up priorisieren.",
        "en": "Prioritize {count} rare automation(s) for catch-up.",
    },
    "safe_start_ok": {
        "de": "Keine Safe-Start-Auffälligkeiten.",
        "en": "No Safe Start findings.",
    },
    "codex_safe_start": {
        "de": "Codex safe starten",
        "en": "Start Codex safely",
    },
    "codex_safe_start_tooltip": {
        "de": "Startet Safe Start for Codex im eigenen Tray. Nutzt dessen config.json; falls sie fehlt, nimmt CareCenter 1 Minute Abstand.",
        "en": "Starts Safe Start for Codex in its own tray. Uses its config.json; if missing, CareCenter uses a 1-minute interval.",
    },
    "codex_safe_start_ok": {
        "de": "Codex-Safe-Start wurde gestartet.",
        "en": "Codex Safe Start was launched.",
    },
    "codex_safe_start_already_running": {
        "de": "Safe Start läuft bereits; kein zweiter Start wurde ausgelöst.",
        "en": "Safe Start is already running; no second launch was triggered.",
    },
    "codex_safe_start_failed": {
        "de": "Codex-Safe-Start konnte nicht gestartet werden.",
        "en": "Codex Safe Start could not be launched.",
    },
    "codex_start": {
        "de": "Codex starten",
        "en": "Start Codex",
    },
    "codex_start_tooltip": {
        "de": "Startet Codex normal ohne Safe-Start-Gate.",
        "en": "Starts Codex normally without the Safe Start gate.",
    },
    "codex_start_ok": {
        "de": "Codex wurde gestartet.",
        "en": "Codex was launched.",
    },
    "codex_start_restored_safe_start": {
        "de": "Safe Start war aktiv; Automatisierungen wurden zurückgegeben. Codex wurde nicht erneut gestartet.",
        "en": "Safe Start was active; automations were restored. Codex was not launched again.",
    },
    "codex_start_restore_failed": {
        "de": "Safe-Start-Restore fehlgeschlagen. Codex wurde nicht gestartet.",
        "en": "Safe Start restore failed. Codex was not launched.",
    },
    "codex_start_failed": {
        "de": "Codex konnte nicht gestartet werden.",
        "en": "Codex could not be launched.",
    },
    # -- Automation control --
    "automations_menu": {"de": "Automatisierungen", "en": "Automations"},
    "automations_pause_active": {
        "de": "Alle aktivierten Automatisierungen aus",
        "en": "Turn off all active automations",
    },
    "automations_pause_active_tooltip": {
        "de": "Setzt alle aktuell aktiven Codex-Automatisierungen auf PAUSED und merkt sie als von CCC ausgeschaltet.",
        "en": "Sets all currently active Codex automations to PAUSED and remembers them as disabled by CCC.",
    },
    "automations_restore_ccc": {
        "de": "Alle von CCC ausgeschalteten Automatisierungen wieder an",
        "en": "Turn on automations disabled by CCC",
    },
    "automations_restore_ccc_tooltip": {
        "de": "Aktiviert nur Automatisierungen, die CareCenter selbst ausgeschaltet hat.",
        "en": "Activates only automations that CareCenter disabled itself.",
    },
    "automations_restore_ccc_staggered": {
        "de": "Alle von CCC ausgeschalteten Automatisierungen gestaffelt aktivieren (1 Minute Abstand beim Start)",
        "en": "Stagger automations disabled by CCC (1 minute apart)",
    },
    "automations_restore_ccc_staggered_tooltip": {
        "de": "Aktiviert die von CCC ausgeschalteten Automatisierungen nacheinander mit einer Minute Abstand.",
        "en": "Activates automations disabled by CCC one after another, one minute apart.",
    },
    "automations_activate_all": {
        "de": "Alle Automatisierungen sofort an",
        "en": "Turn on all automations now",
    },
    "automations_activate_all_tooltip": {
        "de": "Setzt jede gefundene Codex-Automatisierung sofort auf ACTIVE, auch wenn sie vorher nicht von CCC pausiert wurde.",
        "en": "Sets every found Codex automation to ACTIVE immediately, even if CCC did not pause it.",
    },
    "automations_activate_all_staggered": {
        "de": "Alle Automatisierungen gestaffelt an",
        "en": "Stagger all automations on",
    },
    "automations_activate_all_staggered_tooltip": {
        "de": "Setzt alle gefundenen Codex-Automatisierungen nacheinander mit einer Minute Abstand auf ACTIVE.",
        "en": "Sets all found Codex automations to ACTIVE one after another, one minute apart.",
    },
    "automations_running": {
        "de": "Eine Automationsaktion läuft bereits.",
        "en": "An automation action is already running.",
    },
    "automations_busy": {
        "de": "CareCenter arbeitet bereits. Bitte warte, bis der laufende Vorgang fertig ist.",
        "en": "CareCenter is already working. Please wait until the current operation finishes.",
    },
    "automations_started": {
        "de": "Automationsaktion gestartet …",
        "en": "Automation action started ...",
    },
    "automations_prepare": {
        "de": "Lese Codex-Automatisierungen …",
        "en": "Reading Codex automations ...",
    },
    "automations_progress": {
        "de": "Aktiviere {current}/{total}: {automation_id}",
        "en": "Activating {current}/{total}: {automation_id}",
    },
    "automations_pause_done": {
        "de": "{count} aktive Automatisierung(en) ausgeschaltet.",
        "en": "Disabled {count} active automation(s).",
    },
    "automations_restore_done": {
        "de": "{count} von CCC ausgeschaltete Automatisierung(en) aktiviert.",
        "en": "Activated {count} automation(s) disabled by CCC.",
    },
    "automations_activate_all_done": {
        "de": "{count} Automatisierung(en) aktiviert.",
        "en": "Activated {count} automation(s).",
    },
    "automations_none": {
        "de": "Keine passende Automatisierung gefunden.",
        "en": "No matching automation found.",
    },
    "automations_partial": {
        "de": "Teilweise abgeschlossen: {count} aktiviert/geändert, {errors} Fehler.",
        "en": "Partially completed: {count} activated/changed, {errors} error(s).",
    },
    "automations_failed": {
        "de": "Automationsaktion fehlgeschlagen: {errors} Fehler.",
        "en": "Automation action failed: {errors} error(s).",
    },
    "automations_result_detail": {
        "de": "Ziel: {target}; übersprungen: {skipped}; fehlend: {missing}",
        "en": "Target: {target}; skipped: {skipped}; missing: {missing}",
    },
    "automations_toast_title": {
        "de": "CareCenter – Automatisierungen",
        "en": "CareCenter - automations",
    },
    "diagnosis_start_blocker": {
        "de": "Startblockade erkannt (Status: {status}). Über 'Codex reparieren' beheben.",
        "en": "Start blocker detected (status: {status}). Fix via 'Repair Codex'.",
    },
    "diagnosis_findings": {
        "de": "{count} Hinweis(e), Status: {status}.",
        "en": "{count} finding(s), status: {status}.",
    },
    "diagnosis_ok": {
        "de": "Keine Startprobleme erkannt. Codex sollte normal starten.",
        "en": "No start problems detected. Codex should start normally.",
    },
    "diagnosis_title": {"de": "Codex-Start-Diagnose", "en": "Codex start diagnosis"},
    "repair_running_state": {"de": "Reparatur läuft …", "en": "Repair running ..."},
    "repair_searching": {
        "de": "Suche hängende Codex-Prozesse / verwaiste Lockfiles …",
        "en": "Searching hanging Codex processes / stale lockfiles ...",
    },
    "repair_done": {"de": "Reparatur beendet.", "en": "Repair finished."},
    "repair_state_status": {"de": "Reparatur: {status}", "en": "Repair: {status}"},
    "repair_done_title": {
        "de": "Codex-Start-Reparatur — fertig",
        "en": "Codex start repair - done",
    },
    "repair_done_status": {
        "de": "Reparatur beendet: {status}.",
        "en": "Repair finished: {status}.",
    },
    "repair_full": {
        "de": "Codex-Start-Reparatur (voll)",
        "en": "Codex start repair (full)",
    },
    "repair_full_running": {
        "de": "Volle Reparatur läuft …",
        "en": "Full repair running ...",
    },
    "repair_full_progress": {
        "de": "Volle Eskalation läuft …",
        "en": "Full escalation running ...",
    },
    "repair_full_started": {
        "de": "Volle Eskalation gestartet.",
        "en": "Full escalation started.",
    },
    "repair_interrupted": {
        "de": "Reparatur unterbrochen",
        "en": "Repair interrupted",
    },
    "repair_interrupted_detail": {
        "de": "Die Reparatur wurde unterbrochen oder ist fehlgeschlagen. Bitte erneut versuchen.",
        "en": "The repair was interrupted or failed. Please try again.",
    },
    "repair_admin_required": {
        "de": "CareCenter braucht für die Reparatur Admin-Rechte. Starte die App neu mit Admin-Rechten.",
        "en": "CareCenter needs admin rights for the repair. Restart the app with admin rights.",
    },
    "repair_store_missing": {
        "de": "Store-Paket fehlt — Neuinstallation aus dem Store nötig (kein Reboot).",
        "en": "Store package missing — reinstall from the Store required (no reboot).",
    },
    "repair_full_ok": {
        "de": "Codex-Start repariert — Fenster erschienen.",
        "en": "Codex start repaired — window appeared.",
    },
    "repair_full_blocked": {
        "de": "Gestoppt — AppX-Engine verklemmt. Reboot empfohlen.",
        "en": "Stopped — AppX engine is stuck. Reboot recommended.",
    },
    "repair_full_failed": {
        "de": "Reparatur erschöpft (sanftes Re-Register + Reset). Reboot empfohlen.",
        "en": "Repair exhausted (gentle re-register + reset). Reboot recommended.",
    },
    "repair_admin_hint": {
        "de": "→ App als Administrator neu starten (Rechtsklick → 'Als Administrator ausführen').",
        "en": "→ Restart the app as administrator (right-click → 'Run as administrator').",
    },
    "repair_reinstall_button_hint": {
        "de": "→ Knopf 'Codex neu installieren' im Fenster (öffnet die Store-Seite). Nur ein Vorschlag.",
        "en": "→ Use the 'Reinstall Codex' button in the window (opens the Store page). Suggestion only.",
    },
    "repair_reboot_hint": {
        "de": "→ Reboot empfohlen (nur ein Vorschlag).",
        "en": "→ Reboot recommended (suggestion only).",
    },
    "repair_window_detected": {
        "de": "→ Codex-Fenster erkannt.",
        "en": "→ Codex window detected.",
    },
    "repair_admin_tip": {
        "de": "Admin-Rechte nötig — App als Administrator neu starten.",
        "en": "Admin rights needed — restart app as administrator.",
    },
    "repair_reinstall_tip": {
        "de": "Store-Paket fehlt — Knopf 'Codex neu installieren' im Fenster.",
        "en": "Store package missing — use 'Reinstall Codex' in the window.",
    },
    "repair_reboot_tip": {
        "de": "Reparatur gestoppt — Reboot empfohlen.",
        "en": "Repair stopped — reboot recommended.",
    },
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
    "store_repair": {"de": "Store-Update reparieren", "en": "Repair Store update"},
    "store_repair_tooltip": {
        "de": "Store-Cache leeren und Codex-Paket neu registrieren.",
        "en": "Clear Store cache and re-register the Codex package.",
    },
    "store_reinstall": {"de": "Codex neu installieren", "en": "Reinstall Codex"},
    "store_reinstall_tooltip": {
        "de": "Öffnet die Microsoft-Store-Seite der OpenAI-Codex-App.",
        "en": "Open the Microsoft Store page for the OpenAI Codex app.",
    },
    "store_repair_running": {
        "de": "Store-Reparatur läuft …",
        "en": "Store repair running ...",
    },
    "store_repair_progress": {
        "de": "Store-Cache leeren und Codex-Paket neu registrieren …",
        "en": "Clearing Store cache and re-registering Codex package ...",
    },
    "store_repair_toast_progress": {
        "de": "Leere Store-Cache und registriere das Codex-Paket neu …",
        "en": "Clearing Store cache and re-registering the Codex package ...",
    },
    "store_repair_ok": {
        "de": "Store-Cache geleert und Codex-Paket neu registriert. Codex sollte wieder aktualisierbar sein.",
        "en": "Store cache cleared and Codex package re-registered. Codex should update again.",
    },
    "store_repair_failed": {
        "de": "Store-Reparatur: {status} — Details im Protokoll/Logfenster.",
        "en": "Store repair: {status} — details in the log/status window.",
    },
    "store_repair_done": {"de": "Store-Reparatur beendet.", "en": "Store repair finished."},
    "store_repair_done_title": {
        "de": "Store-Reparatur — fertig",
        "en": "Store repair - done",
    },
    "store_reinstall_title": {
        "de": "Codex aus dem Store neu installieren",
        "en": "Reinstall Codex from the Store",
    },
    "store_product_missing": {
        "de": "Keine Store-Produkt-ID konfiguriert.",
        "en": "No Store product ID configured.",
    },
    "store_page_opened": {
        "de": "Store-Seite geöffnet. Dort auf 'Installieren' klicken — danach ist Codex wieder Store-verwaltet (Auto-Updates).",
        "en": "Store page opened. Click 'Install' there — afterwards Codex is Store-managed again (auto-updates).",
    },
    "store_page_failed": {
        "de": "Store-Seite konnte nicht geöffnet werden: {detail}",
        "en": "Could not open Store page: {detail}",
    },
    "store_reinstall_needed": {
        "de": "Keine Codex-Installation gefunden — Neuinstallation aus dem Microsoft Store nötig.",
        "en": "No Codex installation found — reinstall from Microsoft Store required.",
    },
    "codex_already_running": {"de": "Codex läuft bereits — nichts zu tun.", "en": "Codex already running — nothing to do."},
    # -- Config audit / CLI --
    "audit_title": {"de": "CareCenter – Config-Audit", "en": "CareCenter - config audit"},
    "audit_done": {"de": "Config-Audit abgeschlossen", "en": "Config audit completed"},
    "audit_fixed_mcp": {
        "de": "Auto-Fix: {count} MCP-Duplikat(e) entfernt.",
        "en": "Auto-fix: removed {count} MCP duplicate(s).",
    },
    "audit_fixed_plugins": {
        "de": "Auto-Fix: {count} Plugin(s) deaktiviert.",
        "en": "Auto-fix: disabled {count} plugin(s).",
    },
    "audit_findings": {
        "de": "{count} Befund(e)",
        "en": "{count} finding(s)",
    },
    "audit_auto_fixed_suffix": {
        "de": ", {count} auto-korrigiert",
        "en": ", {count} auto-fixed",
    },
    "audit_no_findings": {"de": "Keine Auffälligkeiten.", "en": "No findings."},
    "audit_finding": {"de": "Config-Befund", "en": "Config finding"},
    "config_exists": {
        "de": "Konfiguration existiert bereits: {path}",
        "en": "Configuration already exists: {path}",
    },
    "config_written": {
        "de": "Konfiguration geschrieben: {path}",
        "en": "Configuration written: {path}",
    },
    "cli_config": {"de": "Konfiguration: {path}", "en": "Configuration: {path}"},
    "cli_database": {"de": "Datenbank: {path}", "en": "Database: {path}"},
    "cli_database_exists": {
        "de": "Datenbank vorhanden: {exists}",
        "en": "Database exists: {exists}",
    },
    "cli_codex_running": {"de": "Codex läuft:", "en": "Codex running:"},
    "cli_no_codex_processes": {
        "de": "Keine Codex-Prozesse erkannt.",
        "en": "No Codex processes detected.",
    },
    "cli_screenshot_written": {
        "de": "Store-Screenshot geschrieben: {path}",
        "en": "Store screenshot written: {path}",
    },
    "cli_log": {"de": "Log: {path}", "en": "Log: {path}"},
    "report_status": {"de": "Status", "en": "Status"},
    "report_dry_run": {"de": "Dry-Run", "en": "Dry run"},
    "report_database": {"de": "Datenbank", "en": "Database"},
    "report_backup": {"de": "Backup", "en": "Backup"},
    "report_codex_processes": {"de": "Codex-Prozesse", "en": "Codex processes"},
    "report_steps": {"de": "Schritte", "en": "Steps"},
    "report_error": {"de": "Fehler", "en": "Error"},
    "maintenance_progress_start": {
        "de": "Wartung gestartet …",
        "en": "Maintenance started ...",
    },
    "maintenance_terminal_blocked": {
        "de": "Wartung übersprungen (blockiert).",
        "en": "Maintenance skipped (blocked).",
    },
    "maintenance_terminal_failed": {
        "de": "Wartung fehlgeschlagen.",
        "en": "Maintenance failed.",
    },
    "maintenance_terminal_dry_run": {
        "de": "Dry-Run abgeschlossen.",
        "en": "Dry run completed.",
    },
    "maintenance_terminal_other": {
        "de": "Wartung beendet: {status}",
        "en": "Maintenance finished: {status}",
    },
    "step_exception": {"de": "Ausnahme", "en": "Exception"},
    "step_database": {"de": "Datenbank", "en": "Database"},
    "step_onedrive": {"de": "OneDrive-Schutz", "en": "OneDrive protection"},
    "step_backup": {"de": "Backup", "en": "Backup"},
    "step_state_backup": {"de": "State-DB-Backup", "en": "State DB backup"},
    "step_integrity": {"de": "Integritätscheck", "en": "Integrity check"},
    "step_archive": {"de": "Archivierung", "en": "Archiving"},
    "step_codex_running": {"de": "Codex läuft", "en": "Codex running"},
    "step_lock": {"de": "Wartungs-Lock", "en": "Maintenance lock"},
    "step_backup_retention": {"de": "Backup-Retention", "en": "Backup retention"},
    "step_wal_checkpoint": {"de": "WAL-Checkpoint", "en": "WAL checkpoint"},
    "step_optimize": {"de": "Optimize", "en": "Optimize"},
    "step_vacuum": {"de": "Vacuum", "en": "Vacuum"},
    "database_missing": {
        "de": "{path} wurde nicht gefunden.",
        "en": "{path} was not found.",
    },
    "database_found": {
        "de": "{path} vorhanden; {count} Datei(en) inklusive WAL/SHM gefunden.",
        "en": "{path} exists; found {count} file(s), including WAL/SHM.",
    },
    "onedrive_blocked": {
        "de": "Datenbank liegt in OneDrive; OneDrive-Kontrolle ist nicht freigegeben.",
        "en": "Database is in OneDrive; OneDrive control is not allowed.",
    },
    "onedrive_ok": {
        "de": "Keine blockierende OneDrive-Lage erkannt.",
        "en": "No blocking OneDrive state detected.",
    },
    "backup_planned": {
        "de": "Backup würde in einem Zeitstempelordner erstellt.",
        "en": "Backup would be created in a timestamped folder.",
    },
    "state_backup_planned": {
        "de": "state_5.sqlite würde mitgesichert (kein VACUUM).",
        "en": "state_5.sqlite would be backed up as well (no VACUUM).",
    },
    "integrity_planned": {
        "de": "Integritätscheck würde auf dem Backup laufen.",
        "en": "Integrity check would run on the backup.",
    },
    "optimize_planned": {
        "de": "PRAGMA optimize würde ausgeführt.",
        "en": "PRAGMA optimize would be executed.",
    },
    "vacuum_planned": {
        "de": "VACUUM würde nach erfolgreichem Check laufen.",
        "en": "VACUUM would run after a successful check.",
    },
    "archive_skipped": {
        "de": "Alte Logs werden ohne explizite Konfiguration nicht archiviert oder gelöscht.",
        "en": "Old logs are not archived or deleted without explicit configuration.",
    },
    "lock_running": {"de": "Eine Wartung läuft bereits.", "en": "Maintenance already running."},
    "lock_set": {"de": "Lock gesetzt: {path}", "en": "Lock set: {path}"},
    "backup_progress_start": {
        "de": "Sicherung wird erstellt …",
        "en": "Creating backup ...",
    },
    "backup_progress": {
        "de": "Sicherung … {done} / {total} MB",
        "en": "Backup ... {done} / {total} MB",
    },
    "backup_created": {"de": "Backup erstellt: {path}", "en": "Backup created: {path}"},
    "integrity_progress": {
        "de": "Integritätscheck auf der Sicherung …",
        "en": "Integrity check on backup ...",
    },
    "integrity_ok": {
        "de": "SQLite meldet integrity_check=ok.",
        "en": "SQLite reports integrity_check=ok.",
    },
    "state_backup_missing": {
        "de": "state_5.sqlite nicht gefunden.",
        "en": "state_5.sqlite not found.",
    },
    "state_backup_ok": {
        "de": "state_5.sqlite gesichert ({mb:.1f} MB, {count} Datei(en)).",
        "en": "state_5.sqlite backed up ({mb:.1f} MB, {count} file(s)).",
    },
    "backup_failed": {"de": "Backup fehlgeschlagen: {error}", "en": "Backup failed: {error}"},
    "retention_unlimited": {
        "de": "Aufbewahrung unbegrenzt (backup_keep<=0).",
        "en": "Retention unlimited (backup_keep<=0).",
    },
    "retention_removed": {
        "de": "{removed} alte Backup(s) entfernt; behalte die neuesten {keep}.",
        "en": "Removed {removed} old backup(s); keeping the newest {keep}.",
    },
    "retention_ok": {
        "de": "Keine überzähligen Backups; behalte die neuesten {keep}.",
        "en": "No excess backups; keeping the newest {keep}.",
    },
    "archive_disabled": {
        "de": "Nicht aktiviert; es werden keine Logdaten gelöscht oder verschoben.",
        "en": "Not enabled; no log data is deleted or moved.",
    },
    "archive_not_implemented": {
        "de": "Archivierung ist freigegeben, aber noch nicht schemaspezifisch implementiert.",
        "en": "Archiving is allowed but not yet implemented for this schema.",
    },
    "archive_progress": {
        "de": "Archivierung alter Log-Einträge …",
        "en": "Archiving old log entries ...",
    },
    "archive_dry_run": {
        "de": "{count} Eintrag/Einträge würden archiviert.",
        "en": "{count} entry/entries would be archived.",
    },
    "archive_no_days": {
        "de": "archive_days nicht konfiguriert; Archivierung übersprungen.",
        "en": "archive_days not configured; archiving skipped.",
    },
    "archive_result": {
        "de": "{archived} Eintrag/Einträge archiviert ({tables} Tabelle(n)).",
        "en": "{archived} entry/entries archived ({tables} table(s)).",
    },
    "archive_table_result": {
        "de": "Tabelle '{table}': {count} Eintrag/Einträge.",
        "en": "Table '{table}': {count} entry/entries.",
    },
    "archive_nothing": {
        "de": "Keine archivierbaren Einträge gefunden (alle Einträge aktuell).",
        "en": "No archivable entries found (all entries are current).",
    },
    "archive_table_error": {
        "de": "Tabelle '{table}': Archivierungsfehler — {error}",
        "en": "Table '{table}': archiving error — {error}",
    },
    "wal_progress": {"de": "WAL-Checkpoint …", "en": "WAL checkpoint ..."},
    "wal_ok": {
        "de": "PRAGMA wal_checkpoint(TRUNCATE) ausgeführt (Ergebnis {row}).",
        "en": "PRAGMA wal_checkpoint(TRUNCATE) executed (result {row}).",
    },
    "step_disabled": {
        "de": "In der Konfiguration deaktiviert.",
        "en": "Disabled in configuration.",
    },
    "optimize_progress": {"de": "PRAGMA optimize …", "en": "PRAGMA optimize ..."},
    "optimize_ok": {"de": "PRAGMA optimize ausgeführt.", "en": "PRAGMA optimize executed."},
    "vacuum_progress": {
        "de": "VACUUM läuft … (kann 1–2 Minuten dauern)",
        "en": "VACUUM running ... (can take 1-2 minutes)",
    },
    "vacuum_ok": {
        "de": "VACUUM abgeschlossen in {seconds:.1f}s.",
        "en": "VACUUM completed in {seconds:.1f}s.",
    },
    "vacuum_done_progress": {
        "de": "VACUUM abgeschlossen in {seconds:.0f}s",
        "en": "VACUUM completed in {seconds:.0f}s",
    },
    # -- Auto-maintain orchestration --
    "auto_assess": {"de": "Prüfe Codex-Zustand …", "en": "Checking Codex state ..."},
    "auto_waiting_idle": {
        "de": "Wartung eingereiht — warte auf Codex-Leerlauf (CPU {cpu:.0f}%). Laufende Automatisierungen werden nicht unterbrochen.",
        "en": "Maintenance queued — waiting for Codex idle (CPU {cpu:.0f}%). Running automations are not interrupted.",
    },
    "auto_timeout_step": {
        "de": "Codex blieb über {seconds}s aktiv (CPU {cpu:.0f}%); Wartung verschoben — kein Lauf abgebrochen.",
        "en": "Codex stayed active for more than {seconds}s (CPU {cpu:.0f}%); maintenance deferred — no run interrupted.",
    },
    "auto_timeout_short": {
        "de": "Codex noch aktiv — Wartung verschoben.",
        "en": "Codex still active — maintenance deferred.",
    },
    "auto_cancelled_step": {
        "de": "Safe-Wartung durch Nutzer abgebrochen; Codex wurde nicht geschlossen.",
        "en": "Safe maintenance cancelled by user; Codex was not closed.",
    },
    "auto_cancelled_short": {
        "de": "Safe-Wartung abgebrochen.",
        "en": "Safe maintenance cancelled.",
    },
    "auto_idle_ok": {
        "de": "Codex ist im Leerlauf (keine aktiven Automatisierungen).",
        "en": "Codex is idle (no active automations).",
    },
    "auto_fast_mode": {
        "de": "Fast-Modus: ohne auf Leerlauf zu warten.",
        "en": "Fast mode: not waiting for idle.",
    },
    "auto_close_blocked": {
        "de": "Codex läuft und Schließen ist nicht freigegeben (auto_close_codex=False bzw. kein --close). Bitte Codex selbst beenden oder den Tray-Button nutzen.",
        "en": "Codex is running and closing is not permitted (auto_close_codex=False or no --close). Please close Codex yourself or use the tray button.",
    },
    "auto_close_blocked_short": {
        "de": "Codex läuft — Schließen nicht freigegeben.",
        "en": "Codex running — closing not permitted.",
    },
    "auto_close_planned": {
        "de": "Würde Codex beenden ({mode}-Modus) und Reste bereinigen.",
        "en": "Would close Codex ({mode} mode) and clean remnants.",
    },
    "auto_closing": {
        "de": "Beende Codex vollständig (inkl. Tray) …",
        "en": "Closing Codex completely (including tray) ...",
    },
    "auto_closed": {"de": "Codex vollständig beendet.", "en": "Codex fully closed."},
    "auto_abort_active": {
        "de": "Codex wurde wieder aktiv; Wartung abgebrochen.",
        "en": "Codex became active again; maintenance aborted.",
    },
    "auto_abort_active_short": {
        "de": "Codex wieder aktiv — Wartung abgebrochen.",
        "en": "Codex active again — maintenance aborted.",
    },
    "auto_abort_not_closed": {
        "de": "Codex ließ sich nicht vollständig beenden; Wartung abgebrochen.",
        "en": "Codex could not be fully closed; maintenance aborted.",
    },
    "auto_abort_not_closed_short": {
        "de": "Codex nicht beendbar — Wartung abgebrochen.",
        "en": "Codex cannot be closed — maintenance aborted.",
    },
    "auto_maintain_start": {"de": "Starte Wartung …", "en": "Starting maintenance ..."},
    "auto_restart": {"de": "Starte Codex neu …", "en": "Restarting Codex ..."},
    "auto_restart_ok": {
        "de": "Codex neu gestartet (Fenster erkannt). {message}",
        "en": "Codex restarted (window detected). {message}",
    },
    "auto_restart_warn": {
        "de": "Codex gestartet, aber Fenster (Renderer) nicht innerhalb {seconds}s erkannt. {message}",
        "en": "Codex started, but no window (renderer) appeared within {seconds}s. {message}",
    },
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


def normalize_language(lang: object) -> Language | None:
    """Prüfe und normalisiere einen externen Sprachwert."""
    if isinstance(lang, str):
        value = lang.strip().lower()
        if value in LANGUAGES:
            return cast(Language, value)
    return None


def set_language(lang: Language | str) -> None:
    global _current
    _current = normalize_language(lang) or detect_language()


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


def language_label(lang: Language | str) -> str:
    """Lokalisierter Name einer Sprache in der aktuell aktiven Sprache."""
    normalized = normalize_language(lang) or "de"
    return t(f"language_{normalized}")


def available_keys() -> list[str]:
    """Alle verfügbaren Übersetzungsschlüssel (für Tests)."""
    return sorted(_CATALOG.keys())
