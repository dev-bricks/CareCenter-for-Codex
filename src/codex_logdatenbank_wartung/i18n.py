"""Leichtgewichtige i18n-Unterstützung (Tier-2 Standard nach Policy P-006) für Enduser-Texte.

Enthält die Tier-2 Standardkonstanten (de, en, es, zh, ja, ru), eine 4-stufige
Fallback-Kette (Zielsprache -> en -> de -> key) sowie optionale Entkopplung über
externe locales/translations.json Dateien.
"""

from __future__ import annotations

import json
import locale
import logging
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

Language = Literal["de", "en", "es", "zh", "ja", "ru"]
SUPPORTED_LANGUAGES: tuple[Language, ...] = ("de", "en", "es", "zh", "ja", "ru")
DEFAULT_LANGUAGE: Language = "de"
FALLBACK_CHAIN: tuple[Language, ...] = ("en", "de")
LANGUAGES: tuple[Language, ...] = SUPPORTED_LANGUAGES

LANGUAGE_DISPLAY_NAMES: dict[str, str] = {
    "de": "Deutsch",
    "en": "English",
    "es": "Español",
    "zh": "中文",
    "ja": "日本語",
    "ru": "Русский",
}

_CATALOG: dict[str, dict[str, str]] = {
    "language_de": {
        "de": "Deutsch",
        "en": "German",
        "es": "Alemán",
        "zh": "德语",
        "ja": "ドイツ語",
        "ru": "Немецкий",
    },
    "language_en": {
        "de": "Englisch",
        "en": "English",
        "es": "Inglés",
        "zh": "英语",
        "ja": "英語",
        "ru": "Английский",
    },
    "language_es": {
        "de": "Spanisch",
        "en": "Spanish",
        "es": "Español",
        "zh": "西班牙语",
        "ja": "スペイン語",
        "ru": "Испанский",
    },
    "language_zh": {
        "de": "Chinesisch",
        "en": "Chinese",
        "es": "Chino",
        "zh": "中文",
        "ja": "中国語",
        "ru": "Китайский",
    },
    "language_ja": {
        "de": "Japanisch",
        "en": "Japanese",
        "es": "Japonés",
        "zh": "日语",
        "ja": "日本語",
        "ru": "Японский",
    },
    "language_ru": {
        "de": "Russisch",
        "en": "Russian",
        "es": "Ruso",
        "zh": "俄语",
        "ja": "ロシア語",
        "ru": "Русский",
    },
    "settings_group": {
        "de": "Einstellungen",
        "en": "Settings",
        "es": "Configuración",
    },
    "settings_config_audit": {
        "de": "Config-Audit",
        "en": "Config audit",
        "es": "Auditoría de configuración",
    },
    "settings_language": {
        "de": "Sprache:",
        "en": "Language:",
        "es": "Idioma:",
    },
    "settings_language_tooltip": {
        "de": "Sprache der Oberfläche ändern und in der lokalen Konfiguration speichern.",
        "en": "Change the interface language and save it in the local configuration.",
        "es": "Cambiar el idioma de la interfaz y guardarlo en la configuración local.",
    },
    "settings_mcp_duplicates": {
        "de": "MCP-Duplikate:",
        "en": "MCP duplicates:",
        "es": "Duplicados MCP:",
    },
    "settings_unused_plugins": {
        "de": "Ungenutzte Plugins:",
        "en": "Unused plugins:",
        "es": "Plugins no utilizados:",
    },
    "settings_audit_mode_tooltip": {
        "de": "off = ignorieren, notify = bei Fund benachrichtigen, auto = automatisch bereinigen",
        "en": "off = ignore, notify = notify when found, auto = fix automatically",
        "es": "off = ignorar, notify = notificar si se encuentra, auto = corregir automáticamente",
    },
    "settings_plugin_mode_tooltip": {
        "de": "off = ignorieren, notify = bei Fund benachrichtigen, auto = plattform-inkompatible Plugins automatisch deaktivieren",
        "en": "off = ignore, notify = notify when found, auto = disable platform-incompatible plugins automatically",
        "es": "off = ignorar, notify = notificar si se encuentra, auto = desactivar automáticamente plugins incompatibles",
    },
    "settings_empty_threads": {
        "de": "Leere Threads:",
        "en": "Empty threads:",
        "es": "Hilos vacíos:",
    },
    "settings_empty_threads_tooltip": {
        "de": "off = ignorieren, notify = bei Fund benachrichtigen, auto = leere Threads beim nächsten sicheren Wartungslauf archivieren",
        "en": "off = ignore, notify = notify when found, auto = archive empty threads during the next safe maintenance run",
        "es": "off = ignorar, notify = notificar si se encuentra, auto = archivar hilos vacíos en el próximo mantenimiento seguro",
    },
    "settings_auto_archive_days": {
        "de": "Threads automatisch archivieren nach:",
        "en": "Automatically archive threads after:",
        "es": "Archivar hilos automáticamente tras:",
    },
    "settings_auto_archive_days_tooltip": {
        "de": "Alter in Tagen für die automatische Archivierung. 0 deaktiviert diese Regel.",
        "en": "Age in days for automatic archiving. 0 disables this rule.",
        "es": "Antigüedad en días para el archivado automático. 0 desactiva esta regla.",
    },
    "settings_auto_mark_read_days": {
        "de": "Threads automatisch als gelesen markieren nach:",
        "en": "Automatically mark threads as read after:",
        "es": "Marcar hilos como leídos tras:",
    },
    "settings_auto_mark_read_days_tooltip": {
        "de": "Alter in Tagen zum automatischen Markieren ungelesener Threads. 0 deaktiviert diese Regel.",
        "en": "Age in days for automatically marking unread threads. 0 disables this rule.",
        "es": "Antigüedad en días para marcar automáticamente hilos no leídos. 0 desactiva esta regla.",
    },
    "settings_audit_now": {
        "de": "Audit jetzt ausführen",
        "en": "Run audit now",
        "es": "Ejecutar auditoría ahora",
    },
    "settings_audit_now_tooltip": {
        "de": "Audit sofort starten: prüft Konfiguration, Plugins, CLI und bereinigt sicher erkannte alte Runtime-MCP-Prozessbäume.",
        "en": "Run the audit now: checks configuration, plugins and CLI, and removes safely identified old runtime MCP process trees.",
        "es": "Iniciar auditoría de inmediato: comprueba configuración, plugins y CLI, y elimina árboles de procesos MCP antiguos reconocidos de forma segura.",
    },
    "settings_language_saved": {
        "de": "Sprache gespeichert: {language}.",
        "en": "Language saved: {language}.",
        "es": "Idioma guardado: {language}.",
    },
    "ready": {
        "de": "Bereit.",
        "en": "Ready.",
        "es": "Listo.",
    },
    "done": {
        "de": "Fertig.",
        "en": "Done.",
        "es": "Terminado.",
    },
    "tray_ready": {
        "de": "{app}: bereit; entfernte Reste: {count}",
        "en": "{app}: ready; removed remnants: {count}",
        "es": "{app}: listo; restos eliminados: {count}",
    },
    "zombie_counter": {
        "de": "{count} hängende Codex-Reste seit Start entfernt",
        "en": "{count} hanging Codex remnants removed since start",
        "es": "{count} restos colgados de Codex eliminados desde el inicio",
    },
    "window_close": {
        "de": "Schließen (läuft im Hintergrund weiter)",
        "en": "Close (continues in background)",
        "es": "Cerrar (continúa en segundo plano)",
    },
    "window_close_tooltip": {
        "de": "Schließt nur das Fenster. Eine laufende Reparatur läuft weiter; über das Tray-Menü 'Status & Fortschritt anzeigen' jederzeit wieder öffnen.",
        "en": "Only closes the window. A running repair continues; reopen it any time from the tray menu via 'Show status & progress'.",
        "es": "Solo cierra la ventana. Una reparación en curso continuará; se puede reabrir en cualquier momento desde el menú de la bandeja con 'Mostrar estado y progreso'.",
    },
    "open_carecenter": {
        "de": "CareCenter öffnen",
        "en": "Open CareCenter",
        "es": "Abrir CareCenter",
    },
    "open_carecenter_tooltip": {
        "de": "Öffnet das CareCenter-Fenster (Übersicht, Reparatur, Wartung, Store).",
        "en": "Open the CareCenter window (overview, repair, maintenance, Store).",
        "es": "Abre la ventana de CareCenter (visión general, reparación, mantenimiento, Store).",
    },
    "show_status_progress": {
        "de": "Status & Fortschritt anzeigen",
        "en": "Show status & progress",
        "es": "Mostrar estado y progreso",
    },
    "quit": {
        "de": "Beenden",
        "en": "Quit",
        "es": "Salir",
    },
    "maintenance": {
        "de": "Wartung",
        "en": "Maintenance",
        "es": "Mantenimiento",
    },
    "maintenance_action_tooltip": {
        "de": "Öffnet das Fenster mit den Wartungs-Buttons (Safe/Fast: DB-Wartung).",
        "en": "Open the window with maintenance buttons (Safe/Fast: DB maintenance).",
        "es": "Abre la ventana con los botones de mantenimiento (Safe/Fast: mantenimiento de BD).",
    },
    "carecenter_busy": {
        "de": "CareCenter führt bereits eine Aktion aus.",
        "en": "CareCenter is already running an action.",
        "es": "CareCenter ya está ejecutando una acción.",
    },
    "maintenance_running": {
        "de": "Eine Wartung läuft bereits.",
        "en": "Maintenance already running.",
        "es": "Ya hay un mantenimiento en ejecución.",
    },
    "maintenance_safe_label": {
        "de": "Safe-Modus",
        "en": "Safe mode",
        "es": "Modo Safe",
    },
    "maintenance_fast_label": {
        "de": "Fast-Modus",
        "en": "Fast mode",
        "es": "Modo Fast",
    },
    "maintenance_safe_button": {
        "de": "Wartung – Safe",
        "en": "Maintenance - Safe",
        "es": "Mantenimiento – Safe",
    },
    "maintenance_fast_button": {
        "de": "Wartung – Fast",
        "en": "Maintenance - Fast",
        "es": "Mantenimiento – Fast",
    },
    "maintenance_cancel_button": {
        "de": "Abbrechen",
        "en": "Cancel",
        "es": "Cancelar",
    },
    "maintenance_safe_tooltip": {
        "de": "Wartet auf Codex-Leerlauf, schließt Codex, wartet, startet neu.",
        "en": "Waits for Codex to become idle, closes Codex, maintains, then restarts.",
        "es": "Espera a la inactividad de Codex, cierra Codex, realiza el mantenimiento y reinicia.",
    },
    "maintenance_fast_tooltip": {
        "de": "Sofort: Codex beenden und warten, ohne auf Leerlauf zu warten.",
        "en": "Immediate: close Codex and maintain without waiting for idle.",
        "es": "Inmediato: cierra Codex y realiza el mantenimiento sin esperar a la inactividad.",
    },
    "maintenance_cancel_tooltip": {
        "de": "Bricht einen wartenden Safe-Wartungslauf ab, bevor Codex geschlossen oder die Datenbank angefasst wird.",
        "en": "Cancels a waiting Safe maintenance run before Codex is closed or the database is touched.",
        "es": "Cancela un ciclo de mantenimiento Safe en espera antes de cerrar Codex o tocar la base de datos.",
    },
    "maintenance_state_running": {
        "de": "Wartung läuft ({mode}) …",
        "en": "Maintenance running ({mode}) ...",
        "es": "Mantenimiento en curso ({mode}) …",
    },
    "maintenance_prepare": {
        "de": "Wird vorbereitet …",
        "en": "Preparing ...",
        "es": "Preparando …",
    },
    "maintenance_started": {
        "de": "Wartung gestartet ({mode}). Fortschritt über Klick aufs Tray-Symbol.",
        "en": "Maintenance started ({mode}). Click tray icon for progress.",
        "es": "Mantenimiento iniciado ({mode}). Progreso haciendo clic en el icono de la bandeja.",
    },
    "maintenance_tooltip_started": {
        "de": "CareCenter: {mode} gestartet …",
        "en": "CareCenter: {mode} started ...",
        "es": "CareCenter: {mode} iniciado …",
    },
    "maintenance_done_ok": {
        "de": "Wartung abgeschlossen.",
        "en": "Maintenance completed.",
        "es": "Mantenimiento completado.",
    },
    "maintenance_done_blocked": {
        "de": "Verschoben — Codex war aktiv (kein Lauf abgebrochen).",
        "en": "Deferred — Codex was active (no run interrupted).",
        "es": "Pospuesto — Codex estaba activo (ninguna ejecución interrumpida).",
    },
    "maintenance_done_cancelled": {
        "de": "Abgebrochen — Wartung wurde nicht gestartet.",
        "en": "Cancelled — maintenance was not started.",
        "es": "Cancelado — el mantenimiento no se inició.",
    },
    "maintenance_done_failed": {
        "de": "Fehlgeschlagen — Details im Protokoll.",
        "en": "Failed — see log for details.",
        "es": "Fallido — ver detalles en el registro.",
    },
    "maintenance_cancel_requested": {
        "de": "Abbruch angefordert — Safe-Wartung stoppt beim nächsten sicheren Punkt.",
        "en": "Cancel requested — Safe maintenance will stop at the next safe point.",
        "es": "Cancelación solicitada — el mantenimiento Safe se detendrá en el próximo punto seguro.",
    },
    "maintenance_cancel_noop": {
        "de": "Keine wartende Safe-Wartung aktiv.",
        "en": "No waiting Safe maintenance run is active.",
        "es": "No hay ningún mantenimiento Safe en espera activo.",
    },
    "maintenance_done_other": {
        "de": "Beendet: {status}",
        "en": "Finished: {status}",
        "es": "Finalizado: {status}",
    },
    "maintenance_toast_done": {
        "de": "CareCenter — fertig",
        "en": "CareCenter - done",
        "es": "CareCenter — terminado",
    },
    "click_for_details": {
        "de": "Klick für Details",
        "en": "click for details",
        "es": "clic para ver detalles",
    },
    "detail_waited_idle": {
        "de": "auf Leerlauf gewartet",
        "en": "waited for idle",
        "es": "esperó a la inactividad",
    },
    "detail_closed_codex": {
        "de": "Codex beendet",
        "en": "closed Codex",
        "es": "Codex cerrado",
    },
    "detail_restarted_codex": {
        "de": "Codex neu gestartet",
        "en": "restarted Codex",
        "es": "Codex reiniciado",
    },
    "detail_maintenance_status": {
        "de": "Wartung: {status}",
        "en": "Maintenance: {status}",
        "es": "Mantenimiento: {status}",
    },
    "fast_loop_group": {
        "de": "Loop-Modus",
        "en": "Loop mode",
        "es": "Modo Loop",
    },
    "fast_loop_interval": {
        "de": "Intervall:",
        "en": "Interval:",
        "es": "Intervalo:",
    },
    "fast_loop_interval_hours": {
        "de": "{hours} Stunden",
        "en": "{hours} hours",
        "es": "{hours} horas",
    },
    "fast_loop_interval_tooltip": {
        "de": "Wählt, wie oft der periodische Fast-Wartungsloop automatisch startet.",
        "en": "Choose how often the periodic fast maintenance loop starts automatically.",
        "es": "Elige la frecuencia con la que se iniciará automáticamente el ciclo periódico de mantenimiento rápido.",
    },
    "fast_loop_start": {
        "de": "Loop starten",
        "en": "Start loop",
        "es": "Iniciar bucle",
    },
    "fast_loop_stop": {
        "de": "Loop stoppen",
        "en": "Stop loop",
        "es": "Detener bucle",
    },
    "fast_loop_start_tooltip": {
        "de": "Aktiviert den periodischen Fast-Wartungsloop. Der erste Zyklus startet sofort.",
        "en": "Enables the periodic fast maintenance loop. The first cycle starts immediately.",
        "es": "Activa el ciclo periódico de mantenimiento rápido. El primer ciclo comenzará de inmediato.",
    },
    "fast_loop_stop_tooltip": {
        "de": "Stoppt nur künftige Loop-Zyklen. Ein bereits laufender Zyklus wird sauber beendet.",
        "en": "Stops future loop cycles only. A running cycle finishes cleanly.",
        "es": "Detiene únicamente los ciclos futuros del bucle. Un ciclo en curso finalizará limpiamente.",
    },
    "fast_loop_scheduled": {
        "de": "Loop aktiv: alle {hours} Stunden.",
        "en": "Loop enabled: every {hours} hours.",
        "es": "Modo bucle activo: cada {hours} horas.",
    },
    "fast_loop_disabled": {
        "de": "Loop gestoppt.",
        "en": "Loop stopped.",
        "es": "Bucle detenido.",
    },
    "fast_loop_running": {
        "de": "Loop-Zyklus läuft: Fast-Wartung, Codex-Neustart, gestaffelte Automationen.",
        "en": "Loop cycle running: fast maintenance, Codex restart, staggered automations.",
        "es": "Ciclo de bucle en curso: mantenimiento rápido, reinicio de Codex, reactivación escalonada de automatizaciones.",
    },
    "fast_loop_already_running": {
        "de": "Ein Loop-Zyklus läuft bereits.",
        "en": "A loop cycle is already running.",
        "es": "Ya se está ejecutando un ciclo de bucle.",
    },
    "fast_loop_toast_title": {
        "de": "CareCenter – Loop-Modus",
        "en": "CareCenter - loop mode",
        "es": "CareCenter – modo bucle",
    },
    "fast_loop_done_ok": {
        "de": "Loop-Zyklus abgeschlossen.",
        "en": "Loop cycle completed.",
        "es": "Ciclo de bucle completado.",
    },
    "fast_loop_done_partial": {
        "de": "Loop-Zyklus teilweise abgeschlossen. Details im Fenster.",
        "en": "Loop cycle partially completed. See window for details.",
        "es": "Ciclo de bucle completado parcialmente. Consulta la ventana para más detalles.",
    },
    "fast_loop_done_failed": {
        "de": "Loop-Zyklus fehlgeschlagen. Details im Fenster.",
        "en": "Loop cycle failed. See window for details.",
        "es": "Ciclo de bucle fallido. Consulta la ventana para más detalles.",
    },
    "fast_loop_skipped_busy": {
        "de": "Loop-Zyklus übersprungen: CareCenter ist bereits beschäftigt.",
        "en": "Loop cycle skipped: CareCenter is already busy.",
        "es": "Ciclo de bucle omitido: CareCenter ya está ocupado.",
    },
    "fast_loop_assess": {
        "de": "Loop prüft Codex-Zustand …",
        "en": "Loop checking Codex state ...",
        "es": "Bucle comprobando el estado de Codex …",
    },
    "fast_loop_pause": {
        "de": "Pausiere aktuell aktive Automatisierungen …",
        "en": "Pausing currently active automations ...",
        "es": "Pausando automatizaciones actualmente activas …",
    },
    "fast_loop_restart": {
        "de": "Starte Codex neu …",
        "en": "Restarting Codex ...",
        "es": "Reiniciando Codex …",
    },
    "fast_loop_restore": {
        "de": "Aktiviere Automatisierungen gestaffelt im 60-Sekunden-Takt …",
        "en": "Re-enabling automations staggered every 60 seconds ...",
        "es": "Reactivando automatizaciones de forma escalonada cada 60 segundos …",
    },
    "fast_loop_close_retry": {
        "de": "Codex ließ sich nicht vollständig beenden. Retry {attempt}/{max_attempts} in {seconds}s …",
        "en": "Codex could not be closed fully. Retry {attempt}/{max_attempts} in {seconds}s ...",
        "es": "No se pudo cerrar Codex por completo. Reintento {attempt}/{max_attempts} en {seconds}s …",
    },
    "fast_loop_safe_fallback": {
        "de": "Fast-Beenden blieb blockiert. Starte Safe-Nachholung bis zum nächsten regulären Fast-Termin …",
        "en": "Fast close stayed blocked. Starting Safe catch-up until the next regular Fast interval ...",
        "es": "El cierre rápido permaneció bloqueado. Iniciando recuperación Safe hasta el próximo intervalo regular Fast …",
    },
    "fast_loop_safe_fallback_due": {
        "de": "Reguläres Loop-Intervall ist fällig. Safe-Nachholung wird beendet; danach startet Fast erneut.",
        "en": "Regular loop interval is due. Safe catch-up is being stopped; Fast will run again next.",
        "es": "El intervalo regular del bucle ha vencido. Deteniendo la recuperación Safe; Fast se ejecutará a continuación.",
    },
    "codex_active_no_close": {
        "de": "Codex läuft und Schließen ist nicht freigegeben.",
        "en": "Codex is running and closing is not permitted.",
        "es": "Codex está en ejecución y no está permitido cerrarlo.",
    },
    "waiting_for_idle": {
        "de": "Wartung eingereiht — warte auf Codex-Leerlauf (CPU {cpu:.0f}%).",
        "en": "Maintenance queued — waiting for Codex idle (CPU {cpu:.0f}%).",
        "es": "Mantenimiento en cola — esperando a la inactividad de Codex (CPU {cpu:.0f}%).",
    },
    "idle_timeout": {
        "de": "Codex blieb aktiv; Wartung verschoben — kein Lauf abgebrochen.",
        "en": "Codex stayed active; maintenance deferred — no run interrupted.",
        "es": "Codex permaneció activo; mantenimiento pospuesto — ninguna ejecución interrumpida.",
    },
    "tray_start_message": {
        "de": "Tray läuft. Klick aufs Symbol öffnet Status & Fortschritt.",
        "en": "Tray is running. Click the icon to open status & progress.",
        "es": "La bandeja está activa. Haz clic en el icono para abrir estado y progreso.",
    },
    "process_check_blocked": {
        "de": "Codex-Desktop läuft (exakter Exe-Pfad erkannt). Wartung wird nicht gestartet.",
        "en": "Codex Desktop running (exact exe path matched). Maintenance will not start.",
        "es": "Codex Desktop en ejecución (ruta exacta de ejecutable coincidente). El mantenimiento no se iniciará.",
    },
    "process_check_ok": {
        "de": "Keine Codex-Desktop-Prozesse erkannt.",
        "en": "No Codex Desktop processes detected.",
        "es": "No se detectaron procesos de Codex Desktop.",
    },
    "process_check_fail_closed": {
        "de": "Prozessliste konnte nicht gelesen werden (fail-closed).",
        "en": "Process list could not be read (fail-closed).",
        "es": "No se pudo leer la lista de procesos (fail-closed).",
    },
    "process_check_step": {
        "de": "Codex-Prozessprüfung",
        "en": "Codex process check",
        "es": "Comprobación de procesos de Codex",
    },
    "watchdog_menu": {
        "de": "Auto-Wächter: Start- und MCP-Reste entfernen",
        "en": "Auto watchdog: remove start and MCP remnants",
        "es": "Auto-vigilante: eliminar restos de inicio y MCP",
    },
    "watchdog_tooltip": {
        "de": "Überwacht im Hintergrund: entfernt bei geschlossenem Codex alte Start-Reste und bereinigt sicher wiederholte Runtime-MCP-Prozessbäume auch bei aktiver Desktop-App. Die neueste MCP-Generation, aktive Sitzungen und die Codex-CLI bleiben geschützt. Benachrichtigt beim Aufräumen.",
        "en": "Watches in the background: removes old start remnants when Codex is closed and safely repeated runtime MCP process trees even while the desktop app is active. The newest MCP generation, active sessions and the Codex CLI remain protected. Notifies when cleanup happened.",
        "es": "Vigila en segundo plano: elimina restos antiguos de inicio al cerrarse Codex y árboles de procesos MCP repetidos de forma segura incluso con la app de escritorio activa. La generación más reciente de MCP, las sesiones activas y la CLI de Codex quedan protegidas. Notifica cuando se realiza una limpieza.",
    },
    "watchdog_codex_active": {
        "de": "Codex aktiv (Renderer vorhanden) — Wächter hält sich raus.",
        "en": "Codex active (renderer present) — watchdog standing down.",
        "es": "Codex activo (renderer presente) — vigilante en espera.",
    },
    "watchdog_idle": {
        "de": "Codex zu, keine hängenden Reste.",
        "en": "Codex closed, no hanging remnants.",
        "es": "Codex cerrado, no hay restos colgados.",
    },
    "watchdog_disabled": {
        "de": "Hängende Reste erkannt, aber der Wächter ist deaktiviert.",
        "en": "Hanging remnants detected, but watchdog is disabled.",
        "es": "Se detectaron restos colgados, pero el vigilante está desactivado.",
    },
    "watchdog_busy": {
        "de": "Codex-Baum arbeitet aktiv (CPU) — kein Eingriff.",
        "en": "Codex tree actively working (CPU) — no intervention.",
        "es": "Árbol de Codex trabajando activamente (CPU) — sin intervención.",
    },
    "watchdog_reaped": {
        "de": "{detail}. Du kannst Codex jetzt sauber starten.",
        "en": "{detail}. You can now start Codex cleanly.",
        "es": "{detail}. Ahora puedes iniciar Codex de forma limpia.",
    },
    "watchdog_reaped_short": {
        "de": "Hängende Codex-Reste entfernt.",
        "en": "Removed hanging Codex remnants.",
        "es": "Restos colgados de Codex eliminados.",
    },
    "watchdog_toast_title": {
        "de": "CareCenter – Start-Prävention",
        "en": "CareCenter - start prevention",
        "es": "CareCenter – prevención de arranque",
    },
    "watchdog_toggle_title": {
        "de": "Codex-Start-Prävention",
        "en": "Codex start prevention",
        "es": "Prevención de arranque de Codex",
    },
    "watchdog_enabled": {
        "de": "Auto-Wächter aktiv.",
        "en": "Auto watchdog enabled.",
        "es": "Auto-vigilante activado.",
    },
    "watchdog_disabled_toast": {
        "de": "Auto-Wächter deaktiviert.",
        "en": "Auto watchdog disabled.",
        "es": "Auto-vigilante desactivado.",
    },
    "repair_codex": {
        "de": "Codex reparieren",
        "en": "Repair Codex",
        "es": "Reparar Codex",
    },
    "repair_codex_tooltip": {
        "de": "Begrenzte Reparatur (ohne Admin): hängende Reste entfernen, ClipSVC, sanftes Re-Register, ein Reset-Fallback. Stoppt, sobald Codex startet. Schlägt bei Bedarf Reboot, Neustart als Administrator oder Store-Neuinstallation vor.",
        "en": "Bounded repair (no admin): remove hanging remnants, ClipSVC, gentle re-register, one reset fallback. Stops as soon as Codex starts. Suggests reboot, admin restart or Store reinstall only when needed.",
        "es": "Reparación delimitada (sin admin): eliminar restos colgados, ClipSVC, reinscripción suave, un fallback de reinicio. Se detiene en cuanto arranca Codex. Solo sugiere reiniciar, arranque admin o reinstalación desde Store cuando es necesario.",
    },
    "repair_running": {
        "de": "Läuft bereits.",
        "en": "Already running.",
        "es": "Ya en ejecución.",
    },
    "diagnose": {
        "de": "Diagnose",
        "en": "Diagnose",
        "es": "Diagnosticar",
    },
    "diagnose_tooltip": {
        "de": "Nur prüfen (read-only), nichts ändern.",
        "en": "Check only (read-only), change nothing.",
        "es": "Solo comprobar (solo lectura), no cambiar nada.",
    },
    "repair_light_state": {
        "de": "Codex-Reparatur: leichte Stufe (ohne Admin) …",
        "en": "Codex repair: light stage (no admin) ...",
        "es": "Reparación de Codex: fase ligera (sin admin) …",
    },
    "repair_light_prepare": {
        "de": "Lage prüfen und hängende Reste entfernen …",
        "en": "Checking state and removing hanging remnants ...",
        "es": "Comprobando estado y eliminando restos colgados …",
    },
    "repair_light_reap": {
        "de": "Leichte Stufe: hängende Codex-Reste entfernen (ohne Admin) …",
        "en": "Light stage: removing hanging Codex remnants (no admin) ...",
        "es": "Fase ligera: eliminando restos colgados de Codex (sin admin) …",
    },
    "repair_launch_wait": {
        "de": "Codex starten und auf Fenster warten …",
        "en": "Starting Codex and waiting for a window ...",
        "es": "Iniciando Codex y esperando ventana …",
    },
    "repair_light_ok": {
        "de": "Codex gestartet — leichte Reparatur genügte (kein Admin nötig).",
        "en": "Codex started — light repair was enough (no admin needed).",
        "es": "Codex ha arrancado — la reparación ligera fue suficiente (no se necesitó admin).",
    },
    "repair_light_escalate": {
        "de": "Leichte Stufe genügte nicht — volle Reparatur folgt …",
        "en": "Light stage was not enough — full repair follows ...",
        "es": "La fase ligera no fue suficiente — prosigue reparación completa …",
    },
    "repair_full_needed": {
        "de": "Volle Reparatur nötig …",
        "en": "Full repair needed ...",
        "es": "Se necesita reparación completa …",
    },
    "repair_escalating": {
        "de": "Eskaliere zur vollen Reparatur …",
        "en": "Escalating to full repair ...",
        "es": "Escalando a reparación completa …",
    },
    "repair_reinstall_hint": {
        "de": "→ Knopf 'Codex neu installieren' (öffnet die Store-Seite). Es ist Teil desselben Problems: ohne Installation kann nichts starten.",
        "en": "→ Use 'Reinstall Codex' (opens the Store page). It is the same problem: without an installation, nothing can start.",
        "es": "→ Usa el botón 'Reinstalar Codex' (abre la página de Store). Es parte del mismo problema: sin instalación, nada puede arrancar.",
    },
    "repair_toast_title": {
        "de": "CareCenter – Codex reparieren",
        "en": "CareCenter - repair Codex",
        "es": "CareCenter – reparar Codex",
    },
    "safe_start_check": {
        "de": "Safe Start prüfen",
        "en": "Check Safe Start",
        "es": "Comprobar Safe Start",
    },
    "safe_start_tooltip": {
        "de": "Zeigt Safe-Start-Snapshots, Start-Storm-Signale und seltene Catch-up-Kandidaten.",
        "en": "Shows Safe Start snapshots, start-storm signals and rare catch-up candidates.",
        "es": "Muestra instantáneas de Safe Start, señales de tormenta de arranque y candidatos infrecuentes a recuperación.",
    },
    "safe_start_install": {
        "de": "Safe Start installieren",
        "en": "Install Safe Start",
        "es": "Instalar Safe Start",
    },
    "safe_start_install_tooltip": {
        "de": "Installiert oder aktualisiert Safe Start for Codex über pip. Bevorzugt die lokale Schwesterquelle, sonst die commit-gepinnte GitHub-Quelle.",
        "en": "Installs or updates Safe Start for Codex via pip. Prefers the local sibling source, otherwise the commit-pinned GitHub source.",
        "es": "Instala o actualiza Safe Start for Codex mediante pip. Prefiere el origen hermano local, de lo contrario la fuente de GitHub fijada por commit.",
    },
    "safe_start_install_running": {
        "de": "Safe Start wird installiert oder aktualisiert …",
        "en": "Installing or updating Safe Start ...",
        "es": "Instalando o actualizando Safe Start …",
    },
    "safe_start_install_progress": {
        "de": "pip installiert Safe Start for Codex …",
        "en": "pip is installing Safe Start for Codex ...",
        "es": "pip está instalando Safe Start for Codex …",
    },
    "safe_start_install_ok": {
        "de": "Safe Start ist installiert oder aktualisiert.",
        "en": "Safe Start is installed or updated.",
        "es": "Safe Start está instalado o actualizado.",
    },
    "safe_start_install_failed": {
        "de": "Safe Start konnte nicht installiert werden.",
        "en": "Safe Start could not be installed.",
        "es": "No se pudo instalar Safe Start.",
    },
    "safe_start_active": {
        "de": "Safe Start ist aktiv; CareCenter hält Start-Gegenaktionen zurück.",
        "en": "Safe Start is active; CareCenter is holding back start counteractions.",
        "es": "Safe Start está activo; CareCenter retiene las contra-acciones de inicio.",
    },
    "safe_start_catchup": {
        "de": "{count} seltene Automation(en) für Catch-up priorisieren.",
        "en": "Prioritize {count} rare automation(s) for catch-up.",
        "es": "Priorizar {count} automatización(es) infrecuente(s) para recuperación.",
    },
    "safe_start_ok": {
        "de": "Keine Safe-Start-Auffälligkeiten.",
        "en": "No Safe Start findings.",
        "es": "Sin anomalías en Safe Start.",
    },
    "codex_safe_start": {
        "de": "Codex safe starten",
        "en": "Start Codex safely",
        "es": "Iniciar Codex en modo seguro",
    },
    "codex_safe_start_tooltip": {
        "de": "Startet Safe Start for Codex im eigenen Tray. Nutzt dessen config.json; falls sie fehlt, nimmt CareCenter 1 Minute Abstand.",
        "en": "Starts Safe Start for Codex in its own tray. Uses its config.json; if missing, CareCenter uses a 1-minute interval.",
        "es": "Inicia Safe Start for Codex en su propia bandeja. Usa su config.json; si falta, CareCenter usa un intervalo de 1 minuto.",
    },
    "codex_safe_start_ok": {
        "de": "Codex-Safe-Start wurde gestartet.",
        "en": "Codex Safe Start was launched.",
        "es": "Codex Safe Start fue iniciado.",
    },
    "codex_safe_start_already_running": {
        "de": "Safe Start läuft bereits; kein zweiter Start wurde ausgelöst.",
        "en": "Safe Start is already running; no second launch was triggered.",
        "es": "Safe Start ya está en ejecución; no se desencadenó un segundo inicio.",
    },
    "codex_safe_start_failed": {
        "de": "Codex-Safe-Start konnte nicht gestartet werden.",
        "en": "Codex Safe Start could not be launched.",
        "es": "No se pudo iniciar Codex Safe Start.",
    },
    "codex_start": {
        "de": "Codex starten",
        "en": "Start Codex",
        "es": "Iniciar Codex",
    },
    "codex_start_tooltip": {
        "de": "Startet Codex normal ohne Safe-Start-Gate.",
        "en": "Starts Codex normally without the Safe Start gate.",
        "es": "Inicia Codex normalmente sin el control de Safe Start.",
    },
    "codex_start_ok": {
        "de": "Codex wurde gestartet.",
        "en": "Codex was launched.",
        "es": "Codex fue iniciado.",
    },
    "codex_start_restored_safe_start": {
        "de": "Safe Start war aktiv; Automatisierungen wurden zurückgegeben. Codex wurde nicht erneut gestartet.",
        "en": "Safe Start was active; automations were restored. Codex was not launched again.",
        "es": "Safe Start estaba activo; las automatizaciones fueron devueltas. Codex no se inició de nuevo.",
    },
    "codex_start_restore_failed": {
        "de": "Safe-Start-Restore fehlgeschlagen. Codex wurde nicht gestartet.",
        "en": "Safe Start restore failed. Codex was not launched.",
        "es": "Fallo en la restauración de Safe Start. Codex no se inició.",
    },
    "codex_start_failed": {
        "de": "Codex konnte nicht gestartet werden.",
        "en": "Codex could not be launched.",
        "es": "No se pudo iniciar Codex.",
    },
    "automations_menu": {
        "de": "Automatisierungen",
        "en": "Automations",
        "es": "Automatizaciones",
    },
    "automations_pause_active": {
        "de": "Alle aktivierten Automatisierungen aus",
        "en": "Turn off all active automations",
        "es": "Desactivar todas las automatizaciones activas",
    },
    "automations_pause_active_tooltip": {
        "de": "Setzt alle aktuell aktiven Codex-Automatisierungen auf PAUSED und merkt sie als von CCC ausgeschaltet.",
        "en": "Sets all currently active Codex automations to PAUSED and remembers them as disabled by CCC.",
        "es": "Establece todas las automatizaciones de Codex actualmente activas a PAUSED y las anota como desactivadas por CCC.",
    },
    "automations_restore_ccc": {
        "de": "Alle von CCC ausgeschalteten Automatisierungen wieder an",
        "en": "Turn on automations disabled by CCC",
        "es": "Reactivar automatizaciones desactivadas por CCC",
    },
    "automations_restore_ccc_tooltip": {
        "de": "Aktiviert nur Automatisierungen, die CareCenter selbst ausgeschaltet hat.",
        "en": "Activates only automations that CareCenter disabled itself.",
        "es": "Activa solo las automatizaciones que CareCenter desactivó por sí mismo.",
    },
    "automations_restore_ccc_staggered": {
        "de": "Alle von CCC ausgeschalteten Automatisierungen gestaffelt aktivieren (1 Minute Abstand beim Start)",
        "en": "Stagger automations disabled by CCC (1 minute apart)",
        "es": "Reactivar de forma escalonada las automatizaciones desactivadas por CCC (1 minuto de intervalo al arrancar)",
    },
    "automations_restore_ccc_staggered_tooltip": {
        "de": "Aktiviert die von CCC ausgeschalteten Automatisierungen nacheinander mit einer Minute Abstand.",
        "en": "Activates automations disabled by CCC one after another, one minute apart.",
        "es": "Activa las automatizaciones desactivadas por CCC una tras otra, con un minuto de intervalo.",
    },
    "automations_activate_all": {
        "de": "Alle Automatisierungen sofort an",
        "en": "Turn on all automations now",
        "es": "Activar todas las automatizaciones de inmediato",
    },
    "automations_activate_all_tooltip": {
        "de": "Setzt jede gefundene Codex-Automatisierung sofort auf ACTIVE, auch wenn sie vorher nicht von CCC pausiert wurde.",
        "en": "Sets every found Codex automation to ACTIVE immediately, even if CCC did not pause it.",
        "es": "Establece cualquier automatización de Codex encontrada de inmediato en ACTIVE, aunque CCC no la haya pausado antes.",
    },
    "automations_activate_all_staggered": {
        "de": "Alle Automatisierungen gestaffelt an",
        "en": "Stagger all automations on",
        "es": "Activar todas las automatizaciones de forma escalonada",
    },
    "automations_activate_all_staggered_tooltip": {
        "de": "Setzt alle gefundenen Codex-Automatisierungen nacheinander mit einer Minute Abstand auf ACTIVE.",
        "en": "Sets all found Codex automations to ACTIVE one after another, one minute apart.",
        "es": "Establece todas las automatizaciones de Codex encontradas una tras otra en ACTIVE, con un minuto de intervalo.",
    },
    "automations_running": {
        "de": "Eine Automationsaktion läuft bereits.",
        "en": "An automation action is already running.",
        "es": "Ya se está ejecutando una acción de automatización.",
    },
    "automations_busy": {
        "de": "CareCenter arbeitet bereits. Bitte warte, bis der laufende Vorgang fertig ist.",
        "en": "CareCenter is already working. Please wait until the current operation finishes.",
        "es": "CareCenter ya está trabajando. Por favor, espera a que termine la operación actual.",
    },
    "automations_started": {
        "de": "Automationsaktion gestartet …",
        "en": "Automation action started ...",
        "es": "Acción de automatización iniciada …",
    },
    "automations_prepare": {
        "de": "Lese Codex-Automatisierungen …",
        "en": "Reading Codex automations ...",
        "es": "Leyendo automatizaciones de Codex …",
    },
    "automations_progress": {
        "de": "Aktiviere {current}/{total}: {automation_id}",
        "en": "Activating {current}/{total}: {automation_id}",
        "es": "Activando {current}/{total}: {automation_id}",
    },
    "automations_pause_done": {
        "de": "{count} aktive Automatisierung(en) ausgeschaltet.",
        "en": "Disabled {count} active automation(s).",
        "es": "{count} automatización(es) activa(s) desactivada(s).",
    },
    "automations_restore_done": {
        "de": "{count} von CCC ausgeschaltete Automatisierung(en) aktiviert.",
        "en": "Activated {count} automation(s) disabled by CCC.",
        "es": "{count} automatización(es) desactivada(s) por CCC activada(s).",
    },
    "automations_activate_all_done": {
        "de": "{count} Automatisierung(en) aktiviert.",
        "en": "Activated {count} automation(s).",
        "es": "{count} automatización(es) activada(s).",
    },
    "automations_none": {
        "de": "Keine passende Automatisierung gefunden.",
        "en": "No matching automation found.",
        "es": "No se encontró ninguna automatización coincidente.",
    },
    "automations_partial": {
        "de": "Teilweise abgeschlossen: {count} aktiviert/geändert, {errors} Fehler.",
        "en": "Partially completed: {count} activated/changed, {errors} error(s).",
        "es": "Completado parcialmente: {count} activadas/modificadas, {errors} error(es).",
    },
    "automations_failed": {
        "de": "Automationsaktion fehlgeschlagen: {errors} Fehler.",
        "en": "Automation action failed: {errors} error(s).",
        "es": "Fallo en la acción de automatización: {errors} error(es).",
    },
    "automations_result_detail": {
        "de": "Ziel: {target}; übersprungen: {skipped}; fehlend: {missing}",
        "en": "Target: {target}; skipped: {skipped}; missing: {missing}",
        "es": "Objetivo: {target}; omitidas: {skipped}; faltantes: {missing}",
    },
    "automations_toast_title": {
        "de": "CareCenter – Automatisierungen",
        "en": "CareCenter - automations",
        "es": "CareCenter – automatizaciones",
    },
    "diagnosis_start_blocker": {
        "de": "Startblockade erkannt (Status: {status}). Über 'Codex reparieren' beheben.",
        "en": "Start blocker detected (status: {status}). Fix via 'Repair Codex'.",
        "es": "Bloqueo de arranque detectado (estado: {status}). Solucionar mediante 'Reparar Codex'.",
    },
    "diagnosis_findings": {
        "de": "{count} Hinweis(e), Status: {status}.",
        "en": "{count} finding(s), status: {status}.",
        "es": "{count} aviso(s), estado: {status}.",
    },
    "diagnosis_ok": {
        "de": "Keine Startprobleme erkannt. Codex sollte normal starten.",
        "en": "No start problems detected. Codex should start normally.",
        "es": "No se detectaron problemas de arranque. Codex debería iniciar normalmente.",
    },
    "diagnosis_title": {
        "de": "Codex-Start-Diagnose",
        "en": "Codex start diagnosis",
        "es": "Diagnóstico de arranque de Codex",
    },
    "repair_running_state": {
        "de": "Reparatur läuft …",
        "en": "Repair running ...",
        "es": "Reparación en curso …",
    },
    "repair_searching": {
        "de": "Suche hängende Codex-Prozesse / verwaiste Lockfiles …",
        "en": "Searching hanging Codex processes / stale lockfiles ...",
        "es": "Buscando procesos colgados de Codex / archivos de bloqueo obsoletos …",
    },
    "repair_done": {
        "de": "Reparatur beendet.",
        "en": "Repair finished.",
        "es": "Reparación finalizada.",
    },
    "repair_state_status": {
        "de": "Reparatur: {status}",
        "en": "Repair: {status}",
        "es": "Reparación: {status}",
    },
    "repair_done_title": {
        "de": "Codex-Start-Reparatur — fertig",
        "en": "Codex start repair - done",
        "es": "Reparación de arranque de Codex — terminada",
    },
    "repair_done_status": {
        "de": "Reparatur beendet: {status}.",
        "en": "Repair finished: {status}.",
        "es": "Reparación finalizada: {status}.",
    },
    "repair_full": {
        "de": "Codex-Start-Reparatur (voll)",
        "en": "Codex start repair (full)",
        "es": "Reparación de arranque de Codex (completa)",
    },
    "repair_full_running": {
        "de": "Volle Reparatur läuft …",
        "en": "Full repair running ...",
        "es": "Reparación completa en curso …",
    },
    "repair_full_progress": {
        "de": "Volle Eskalation läuft …",
        "en": "Full escalation running ...",
        "es": "Escalación completa en curso …",
    },
    "repair_full_started": {
        "de": "Volle Eskalation gestartet.",
        "en": "Full escalation started.",
        "es": "Escalación completa iniciada.",
    },
    "repair_interrupted": {
        "de": "Reparatur unterbrochen",
        "en": "Repair interrupted",
        "es": "Reparación interrumpida",
    },
    "repair_interrupted_detail": {
        "de": "Die Reparatur wurde unterbrochen oder ist fehlgeschlagen. Bitte erneut versuchen.",
        "en": "The repair was interrupted or failed. Please try again.",
        "es": "La reparación fue interrumpida o ha fallado. Por favor, inténtalo de nuevo.",
    },
    "repair_admin_required": {
        "de": "CareCenter braucht für die Reparatur Admin-Rechte. Starte die App neu mit Admin-Rechten.",
        "en": "CareCenter needs admin rights for the repair. Restart the app with admin rights.",
        "es": "CareCenter necesita permisos de administrador para la reparación. Reinicia la aplicación como administrador.",
    },
    "repair_store_missing": {
        "de": "Store-Paket fehlt — Neuinstallation aus dem Store nötig (kein Reboot).",
        "en": "Store package missing — reinstall from the Store required (no reboot).",
        "es": "Falta el paquete de Store — se requiere reinstalación desde Store (sin reinicio del sistema).",
    },
    "repair_full_ok": {
        "de": "Codex-Start repariert — Fenster erschienen.",
        "en": "Codex start repaired — window appeared.",
        "es": "Arranque de Codex reparado — la ventana apareció.",
    },
    "repair_full_blocked": {
        "de": "Gestoppt — AppX-Engine verklemmt. Reboot empfohlen.",
        "en": "Stopped — AppX engine is stuck. Reboot recommended.",
        "es": "Detenido — el motor AppX está atascado. Se recomienda reiniciar el equipo.",
    },
    "repair_full_failed": {
        "de": "Reparatur erschöpft (sanftes Re-Register + Reset). Reboot empfohlen.",
        "en": "Repair exhausted (gentle re-register + reset). Reboot recommended.",
        "es": "Reparación agotada (re-registro suave + reset). Se recomienda reiniciar el equipo.",
    },
    "repair_admin_hint": {
        "de": "→ App als Administrator neu starten (Rechtsklick → 'Als Administrator ausführen').",
        "en": "→ Restart the app as administrator (right-click → 'Run as administrator').",
        "es": "→ Reiniciar la app como administrador (clic derecho → 'Ejecutar como administrador').",
    },
    "repair_reinstall_button_hint": {
        "de": "→ Knopf 'Codex neu installieren' im Fenster (öffnet die Store-Seite). Nur ein Vorschlag.",
        "en": "→ Use the 'Reinstall Codex' button in the window (opens the Store page). Suggestion only.",
        "es": "→ Usa el botón 'Reinstalar Codex' en la ventana (abre la página de Store). Solo una sugerencia.",
    },
    "repair_reboot_hint": {
        "de": "→ Reboot empfohlen (nur ein Vorschlag).",
        "en": "→ Reboot recommended (suggestion only).",
        "es": "→ Se recomienda reiniciar el equipo (solo una sugerencia).",
    },
    "repair_window_detected": {
        "de": "→ Codex-Fenster erkannt.",
        "en": "→ Codex window detected.",
        "es": "→ Ventana de Codex detectada.",
    },
    "repair_admin_tip": {
        "de": "Admin-Rechte nötig — App als Administrator neu starten.",
        "en": "Admin rights needed — restart app as administrator.",
        "es": "Permisos de admin necesarios — reiniciar la app como administrador.",
    },
    "repair_reinstall_tip": {
        "de": "Store-Paket fehlt — Knopf 'Codex neu installieren' im Fenster.",
        "en": "Store package missing — use 'Reinstall Codex' in the window.",
        "es": "Falta el paquete de Store — usa 'Reinstalar Codex' en la ventana.",
    },
    "repair_reboot_tip": {
        "de": "Reparatur gestoppt — Reboot empfohlen.",
        "en": "Repair stopped — reboot recommended.",
        "es": "Reparación detenida — se recomienda reiniciar el equipo.",
    },
    "zombie_detected": {
        "de": "Codex-Hauptprozess ohne Renderer erkannt (hängt/Fenster tot).",
        "en": "Codex main process without renderer detected (hanging/window dead).",
        "es": "Proceso principal de Codex sin renderer detectado (colgado/ventana muerta).",
    },
    "stale_lockfile": {
        "de": "Electron-Lockfile vorhanden, aber kein Codex-Hauptprozess läuft.",
        "en": "Electron lockfile present, but no Codex main process running.",
        "es": "Archivo de bloqueo de Electron presente, pero no hay proceso principal de Codex ejecutándose.",
    },
    "lockfile_removed": {
        "de": "Verwaistes Lockfile entfernt.",
        "en": "Stale lockfile removed.",
        "es": "Archivo de bloqueo obsoleto eliminado.",
    },
    "repair_nothing_to_do": {
        "de": "Keine Startblockaden erkannt.",
        "en": "No start blockers detected.",
        "es": "No se detectaron bloqueos de arranque.",
    },
    "store_repair": {
        "de": "Store-Update reparieren",
        "en": "Repair Store update",
        "es": "Reparar actualización de Store",
    },
    "store_repair_tooltip": {
        "de": "Store-Cache leeren und Codex-Paket neu registrieren.",
        "en": "Clear Store cache and re-register the Codex package.",
        "es": "Vaciar caché de Store y volver a registrar el paquete de Codex.",
    },
    "store_reinstall": {
        "de": "Codex neu installieren",
        "en": "Reinstall Codex",
        "es": "Reinstalar Codex",
    },
    "store_reinstall_tooltip": {
        "de": "Öffnet die Microsoft-Store-Seite der OpenAI-Codex-App.",
        "en": "Open the Microsoft Store page for the OpenAI Codex app.",
        "es": "Abre la página de Microsoft Store para la aplicación OpenAI Codex.",
    },
    "store_repair_running": {
        "de": "Store-Reparatur läuft …",
        "en": "Store repair running ...",
        "es": "Reparación de Store en curso …",
    },
    "store_repair_progress": {
        "de": "Store-Cache leeren und Codex-Paket neu registrieren …",
        "en": "Clearing Store cache and re-registering Codex package ...",
        "es": "Vaciando caché de Store y registrando de nuevo el paquete de Codex …",
    },
    "store_repair_toast_progress": {
        "de": "Leere Store-Cache und registriere das Codex-Paket neu …",
        "en": "Clearing Store cache and re-registering the Codex package ...",
        "es": "Vaciando caché de Store y registrando de nuevo el paquete de Codex …",
    },
    "store_repair_ok": {
        "de": "Store-Cache geleert und Codex-Paket neu registriert. Codex sollte wieder aktualisierbar sein.",
        "en": "Store cache cleared and Codex package re-registered. Codex should update again.",
        "es": "Caché de Store vaciada y paquete de Codex registrado de nuevo. Codex debería poder actualizarse de nuevo.",
    },
    "store_repair_failed": {
        "de": "Store-Reparatur: {status} — Details im Protokoll/Logfenster.",
        "en": "Store repair: {status} — details in the log/status window.",
        "es": "Reparación de Store: {status} — detalles en el registro/ventana de estado.",
    },
    "store_repair_done": {
        "de": "Store-Reparatur beendet.",
        "en": "Store repair finished.",
        "es": "Reparación de Store finalizada.",
    },
    "store_repair_done_title": {
        "de": "Store-Reparatur — fertig",
        "en": "Store repair - done",
        "es": "Reparación de Store — terminada",
    },
    "store_reinstall_title": {
        "de": "Codex aus dem Store neu installieren",
        "en": "Reinstall Codex from the Store",
        "es": "Reinstalar Codex desde Microsoft Store",
    },
    "store_product_missing": {
        "de": "Keine Store-Produkt-ID konfiguriert.",
        "en": "No Store product ID configured.",
        "es": "No hay ningún ID de producto de Store configurado.",
    },
    "store_page_opened": {
        "de": "Store-Seite geöffnet. Dort auf 'Installieren' klicken — danach ist Codex wieder Store-verwaltet (Auto-Updates).",
        "en": "Store page opened. Click 'Install' there — afterwards Codex is Store-managed again (auto-updates).",
        "es": "Página de Store abierta. Haz clic en 'Instalar' allí — después Codex volverá a estar administrado por Store (actualizaciones automáticas).",
    },
    "store_page_failed": {
        "de": "Store-Seite konnte nicht geöffnet werden: {detail}",
        "en": "Could not open Store page: {detail}",
        "es": "No se pudo abrir la página de Store: {detail}",
    },
    "store_reinstall_needed": {
        "de": "Keine Codex-Installation gefunden — Neuinstallation aus dem Microsoft Store nötig.",
        "en": "No Codex installation found — reinstall from Microsoft Store required.",
        "es": "No se encontró ninguna instalación de Codex — se requiere reinstalación desde Microsoft Store.",
    },
    "codex_already_running": {
        "de": "Codex läuft bereits — nichts zu tun.",
        "en": "Codex already running — nothing to do.",
        "es": "Codex ya está en ejecución — nada que hacer.",
    },
    "audit_title": {
        "de": "CareCenter – Config-Audit",
        "en": "CareCenter - config audit",
        "es": "CareCenter – auditoría de configuración",
    },
    "audit_done": {
        "de": "Config-Audit abgeschlossen",
        "en": "Config audit completed",
        "es": "Auditoría de configuración completada",
    },
    "audit_running": {
        "de": "Config-Audit läuft …",
        "en": "Config audit running …",
        "es": "Auditoría de configuración en curso …",
    },
    "audit_fixed_mcp": {
        "de": "Auto-Fix: {count} MCP-Duplikat(e) entfernt.",
        "en": "Auto-fix: removed {count} MCP duplicate(s).",
        "es": "Auto-fix: eliminado(s) {count} duplicado(s) de MCP.",
    },
    "audit_fixed_plugins": {
        "de": "Auto-Fix: {count} Plugin(s) deaktiviert.",
        "en": "Auto-fix: disabled {count} plugin(s).",
        "es": "Auto-fix: desactivado(s) {count} plugin(s).",
    },
    "audit_reaped_runtime_mcp": {
        "de": "Runtime-Bereinigung: {count} alte MCP-Prozessbäume entfernt.",
        "en": "Runtime cleanup: removed {count} old MCP process tree(s).",
        "es": "Limpieza de tiempo de ejecución: eliminados {count} árboles de procesos MCP antiguos.",
    },
    "audit_fixes_deferred": {
        "de": "Auto-Fix vorgemerkt: {count} Befund(e) werden automatisch behoben, sobald Codex geschlossen ist.",
        "en": "Auto-fix queued: {count} finding(s) will be fixed automatically after Codex closes.",
        "es": "Auto-fix programado: {count} hallazgo(s) se corregirán automáticamente en cuanto se cierre Codex.",
    },
    "audit_findings": {
        "de": "{count} Befund(e)",
        "en": "{count} finding(s)",
        "es": "{count} hallazgo(s)",
    },
    "audit_auto_fixed_suffix": {
        "de": ", {count} auto-korrigiert",
        "en": ", {count} auto-fixed",
        "es": ", {count} auto-corregido(s)",
    },
    "audit_no_findings": {
        "de": "Keine Auffälligkeiten.",
        "en": "No findings.",
        "es": "Sin anomalías.",
    },
    "audit_finding": {
        "de": "Config-Befund",
        "en": "Config finding",
        "es": "Hallazgo de configuración",
    },
    "config_exists": {
        "de": "Konfiguration existiert bereits: {path}",
        "en": "Configuration already exists: {path}",
        "es": "La configuración ya existe: {path}",
    },
    "config_written": {
        "de": "Konfiguration geschrieben: {path}",
        "en": "Configuration written: {path}",
        "es": "Configuración guardada: {path}",
    },
    "cli_config": {
        "de": "Konfiguration: {path}",
        "en": "Configuration: {path}",
        "es": "Configuración: {path}",
    },
    "cli_database": {
        "de": "Datenbank: {path}",
        "en": "Database: {path}",
        "es": "Base de datos: {path}",
    },
    "cli_database_exists": {
        "de": "Datenbank vorhanden: {exists}",
        "en": "Database exists: {exists}",
        "es": "Base de datos existente: {exists}",
    },
    "cli_codex_running": {
        "de": "Codex läuft:",
        "en": "Codex running:",
        "es": "Codex en ejecución:",
    },
    "cli_no_codex_processes": {
        "de": "Keine Codex-Prozesse erkannt.",
        "en": "No Codex processes detected.",
        "es": "No se detectaron procesos de Codex.",
    },
    "cli_screenshot_written": {
        "de": "Store-Screenshot geschrieben: {path}",
        "en": "Store screenshot written: {path}",
        "es": "Captura de pantalla de Store guardada: {path}",
    },
    "cli_log": {
        "de": "Log: {path}",
        "en": "Log: {path}",
        "es": "Registro: {path}",
    },
    "report_status": {
        "de": "Status",
        "en": "Status",
        "es": "Estado",
    },
    "report_dry_run": {
        "de": "Dry-Run",
        "en": "Dry run",
        "es": "Simulación",
    },
    "report_database": {
        "de": "Datenbank",
        "en": "Database",
        "es": "Base de datos",
    },
    "report_backup": {
        "de": "Backup",
        "en": "Backup",
        "es": "Copia de seguridad",
    },
    "report_codex_processes": {
        "de": "Codex-Prozesse",
        "en": "Codex processes",
        "es": "Procesos de Codex",
    },
    "report_steps": {
        "de": "Schritte",
        "en": "Steps",
        "es": "Pasos",
    },
    "report_error": {
        "de": "Fehler",
        "en": "Error",
        "es": "Error",
    },
    "maintenance_progress_start": {
        "de": "Wartung gestartet …",
        "en": "Maintenance started ...",
        "es": "Mantenimiento iniciado …",
    },
    "maintenance_terminal_blocked": {
        "de": "Wartung übersprungen (blockiert).",
        "en": "Maintenance skipped (blocked).",
        "es": "Mantenimiento omitido (bloqueado).",
    },
    "maintenance_terminal_failed": {
        "de": "Wartung fehlgeschlagen.",
        "en": "Maintenance failed.",
        "es": "Mantenimiento fallido.",
    },
    "maintenance_terminal_dry_run": {
        "de": "Dry-Run abgeschlossen.",
        "en": "Dry run completed.",
        "es": "Simulación completada.",
    },
    "maintenance_terminal_other": {
        "de": "Wartung beendet: {status}",
        "en": "Maintenance finished: {status}",
        "es": "Mantenimiento finalizado: {status}",
    },
    "step_exception": {
        "de": "Ausnahme",
        "en": "Exception",
        "es": "Excepción",
    },
    "step_database": {
        "de": "Datenbank",
        "en": "Database",
        "es": "Base de datos",
    },
    "step_onedrive": {
        "de": "OneDrive-Schutz",
        "en": "OneDrive protection",
        "es": "Protección de OneDrive",
    },
    "step_backup": {
        "de": "Backup",
        "en": "Backup",
        "es": "Copia de seguridad",
    },
    "step_state_backup": {
        "de": "State-DB-Backup",
        "en": "State DB backup",
        "es": "Copia de seguridad de State-DB",
    },
    "step_integrity": {
        "de": "Integritätscheck",
        "en": "Integrity check",
        "es": "Comprobación de integridad",
    },
    "step_archive": {
        "de": "Archivierung",
        "en": "Archiving",
        "es": "Archivado",
    },
    "step_codex_running": {
        "de": "Codex läuft",
        "en": "Codex running",
        "es": "Codex en ejecución",
    },
    "step_lock": {
        "de": "Wartungs-Lock",
        "en": "Maintenance lock",
        "es": "Bloqueo de mantenimiento",
    },
    "step_backup_retention": {
        "de": "Backup-Retention",
        "en": "Backup retention",
        "es": "Retención de copias de seguridad",
    },
    "step_wal_checkpoint": {
        "de": "WAL-Checkpoint",
        "en": "WAL checkpoint",
        "es": "Punto de control WAL",
    },
    "step_optimize": {
        "de": "Optimize",
        "en": "Optimize",
        "es": "Optimización",
    },
    "step_vacuum": {
        "de": "Vacuum",
        "en": "Vacuum",
        "es": "Compactación (Vacuum)",
    },
    "database_missing": {
        "de": "{path} wurde nicht gefunden.",
        "en": "{path} was not found.",
        "es": "{path} no fue encontrada.",
    },
    "database_found": {
        "de": "{path} vorhanden; {count} Datei(en) inklusive WAL/SHM gefunden.",
        "en": "{path} exists; found {count} file(s), including WAL/SHM.",
        "es": "{path} existe; se encontraron {count} archivo(s), incluidos WAL/SHM.",
    },
    "onedrive_blocked": {
        "de": "Datenbank liegt in OneDrive; OneDrive-Kontrolle ist nicht freigegeben.",
        "en": "Database is in OneDrive; OneDrive control is not allowed.",
        "es": "La base de datos está en OneDrive; el control de OneDrive no está permitido.",
    },
    "onedrive_ok": {
        "de": "Keine blockierende OneDrive-Lage erkannt.",
        "en": "No blocking OneDrive state detected.",
        "es": "No se detectó ningún estado bloqueante de OneDrive.",
    },
    "backup_planned": {
        "de": "Backup würde in einem Zeitstempelordner erstellt.",
        "en": "Backup would be created in a timestamped folder.",
        "es": "La copia de seguridad se crearía en una carpeta con marca temporal.",
    },
    "state_backup_planned": {
        "de": "state_5.sqlite würde mitgesichert (kein VACUUM).",
        "en": "state_5.sqlite would be backed up as well (no VACUUM).",
        "es": "state_5.sqlite también se respaldaría (sin VACUUM).",
    },
    "integrity_planned": {
        "de": "Integritätscheck würde auf dem Backup laufen.",
        "en": "Integrity check would run on the backup.",
        "es": "La comprobación de integridad se ejecutaría sobre la copia de seguridad.",
    },
    "optimize_planned": {
        "de": "PRAGMA optimize würde ausgeführt.",
        "en": "PRAGMA optimize would be executed.",
        "es": "Se ejecutaría PRAGMA optimize.",
    },
    "vacuum_planned": {
        "de": "VACUUM würde nach erfolgreichem Check laufen.",
        "en": "VACUUM would run after a successful check.",
        "es": "VACUUM se ejecutaría tras una comprobación satisfactoria.",
    },
    "archive_skipped": {
        "de": "Alte Logs werden ohne explizite Konfiguration nicht archiviert oder gelöscht.",
        "en": "Old logs are not archived or deleted without explicit configuration.",
        "es": "Los registros antiguos no se archivan ni eliminan sin configuración explícita.",
    },
    "lock_running": {
        "de": "Eine Wartung läuft bereits.",
        "en": "Maintenance already running.",
        "es": "Ya hay un mantenimiento en ejecución.",
    },
    "lock_set": {
        "de": "Lock gesetzt: {path}",
        "en": "Lock set: {path}",
        "es": "Bloqueo establecido: {path}",
    },
    "backup_progress_start": {
        "de": "Sicherung wird erstellt …",
        "en": "Creating backup ...",
        "es": "Creando copia de seguridad …",
    },
    "backup_progress": {
        "de": "Sicherung … {done} / {total} MB",
        "en": "Backup ... {done} / {total} MB",
        "es": "Copia de seguridad … {done} / {total} MB",
    },
    "backup_created": {
        "de": "Backup erstellt: {path}",
        "en": "Backup created: {path}",
        "es": "Copia de seguridad creada: {path}",
    },
    "integrity_progress": {
        "de": "Integritätscheck auf der Sicherung …",
        "en": "Integrity check on backup ...",
        "es": "Comprobación de integridad sobre la copia de seguridad …",
    },
    "integrity_ok": {
        "de": "SQLite meldet integrity_check=ok.",
        "en": "SQLite reports integrity_check=ok.",
        "es": "SQLite notifica integrity_check=ok.",
    },
    "state_backup_missing": {
        "de": "state_5.sqlite nicht gefunden.",
        "en": "state_5.sqlite not found.",
        "es": "state_5.sqlite no encontrada.",
    },
    "state_backup_ok": {
        "de": "state_5.sqlite gesichert ({mb:.1f} MB, {count} Datei(en)).",
        "en": "state_5.sqlite backed up ({mb:.1f} MB, {count} file(s)).",
        "es": "state_5.sqlite respaldada ({mb:.1f} MB, {count} archivo(s)).",
    },
    "backup_failed": {
        "de": "Backup fehlgeschlagen: {error}",
        "en": "Backup failed: {error}",
        "es": "Fallo en la copia de seguridad: {error}",
    },
    "retention_unlimited": {
        "de": "Aufbewahrung unbegrenzt (backup_keep<=0).",
        "en": "Retention unlimited (backup_keep<=0).",
        "es": "Retención ilimitada (backup_keep<=0).",
    },
    "retention_removed": {
        "de": "{removed} alte Backup(s) entfernt; behalte die neuesten {keep}.",
        "en": "Removed {removed} old backup(s); keeping the newest {keep}.",
        "es": "Eliminada(s) {removed} copia(s) de seguridad antigua(s); conservando las {keep} más recientes.",
    },
    "retention_ok": {
        "de": "Keine überzähligen Backups; behalte die neuesten {keep}.",
        "en": "No excess backups; keeping the newest {keep}.",
        "es": "Sin copias de seguridad sobrantes; conservando las {keep} más recientes.",
    },
    "archive_disabled": {
        "de": "Nicht aktiviert; es werden keine Logdaten gelöscht oder verschoben.",
        "en": "Not enabled; no log data is deleted or moved.",
        "es": "No activado; no se eliminan ni mueven datos de registro.",
    },
    "archive_not_implemented": {
        "de": "Archivierung ist freigegeben, aber noch nicht schemaspezifisch implementiert.",
        "en": "Archiving is allowed but not yet implemented for this schema.",
        "es": "El archivado está habilitado, pero aún no implementado para este esquema.",
    },
    "archive_progress": {
        "de": "Archivierung alter Log-Einträge …",
        "en": "Archiving old log entries ...",
        "es": "Archivando entradas antiguas de registro …",
    },
    "archive_dry_run": {
        "de": "{count} Eintrag/Einträge würden archiviert.",
        "en": "{count} entry/entries would be archived.",
        "es": "Se archivaría(n) {count} entrada(s).",
    },
    "archive_no_days": {
        "de": "archive_days nicht konfiguriert; Archivierung übersprungen.",
        "en": "archive_days not configured; archiving skipped.",
        "es": "archive_days no configurado; archivado omitido.",
    },
    "archive_result": {
        "de": "{archived} Eintrag/Einträge archiviert ({tables} Tabelle(n)).",
        "en": "{archived} entry/entries archived ({tables} table(s)).",
        "es": "Archivada(s) {archived} entrada(s) ({tables} tabla(s)).",
    },
    "archive_table_result": {
        "de": "Tabelle '{table}': {count} Eintrag/Einträge.",
        "en": "Table '{table}': {count} entry/entries.",
        "es": "Tabla '{table}': {count} entrada(s).",
    },
    "archive_nothing": {
        "de": "Keine archivierbaren Einträge gefunden (alle Einträge aktuell).",
        "en": "No archivable entries found (all entries are current).",
        "es": "No se encontraron entradas archivables (todas las entradas están vigentes).",
    },
    "archive_table_error": {
        "de": "Tabelle '{table}': Archivierungsfehler — {error}",
        "en": "Table '{table}': archiving error — {error}",
        "es": "Tabla '{table}': error de archivado — {error}",
    },
    "wal_progress": {
        "de": "WAL-Checkpoint …",
        "en": "WAL checkpoint ...",
        "es": "Punto de control WAL …",
    },
    "wal_ok": {
        "de": "PRAGMA wal_checkpoint(TRUNCATE) ausgeführt (Ergebnis {row}).",
        "en": "PRAGMA wal_checkpoint(TRUNCATE) executed (result {row}).",
        "es": "PRAGMA wal_checkpoint(TRUNCATE) ejecutado (resultado {row}).",
    },
    "step_disabled": {
        "de": "In der Konfiguration deaktiviert.",
        "en": "Disabled in configuration.",
        "es": "Desactivado en la configuración.",
    },
    "optimize_progress": {
        "de": "PRAGMA optimize …",
        "en": "PRAGMA optimize ...",
        "es": "PRAGMA optimize …",
    },
    "optimize_ok": {
        "de": "PRAGMA optimize ausgeführt.",
        "en": "PRAGMA optimize executed.",
        "es": "PRAGMA optimize ejecutado.",
    },
    "vacuum_progress": {
        "de": "VACUUM läuft … (kann 1–2 Minuten dauern)",
        "en": "VACUUM running ... (can take 1-2 minutes)",
        "es": "VACUUM en ejecución … (puede tardar 1–2 minutos)",
    },
    "vacuum_ok": {
        "de": "VACUUM abgeschlossen in {seconds:.1f}s.",
        "en": "VACUUM completed in {seconds:.1f}s.",
        "es": "VACUUM completado en {seconds:.1f}s.",
    },
    "vacuum_done_progress": {
        "de": "VACUUM abgeschlossen in {seconds:.0f}s",
        "en": "VACUUM completed in {seconds:.0f}s",
        "es": "VACUUM completado en {seconds:.0f}s",
    },
    "auto_assess": {
        "de": "Prüfe Codex-Zustand …",
        "en": "Checking Codex state ...",
        "es": "Comprobando estado de Codex …",
    },
    "auto_waiting_idle": {
        "de": "Wartung eingereiht — warte auf Codex-Leerlauf (CPU {cpu:.0f}%). Laufende Automatisierungen werden nicht unterbrochen.",
        "en": "Maintenance queued — waiting for Codex idle (CPU {cpu:.0f}%). Running automations are not interrupted.",
        "es": "Mantenimiento en cola — esperando a la inactividad de Codex (CPU {cpu:.0f}%). Las automatizaciones en curso no se interrumpen.",
    },
    "auto_timeout_step": {
        "de": "Codex blieb über {seconds}s aktiv (CPU {cpu:.0f}%); Wartung verschoben — kein Lauf abgebrochen.",
        "en": "Codex stayed active for more than {seconds}s (CPU {cpu:.0f}%); maintenance deferred — no run interrupted.",
        "es": "Codex permaneció activo más de {seconds}s (CPU {cpu:.0f}%); mantenimiento pospuesto — ninguna ejecución interrumpida.",
    },
    "auto_timeout_short": {
        "de": "Codex noch aktiv — Wartung verschoben.",
        "en": "Codex still active — maintenance deferred.",
        "es": "Codex aún activo — mantenimiento pospuesto.",
    },
    "auto_cancelled_step": {
        "de": "Safe-Wartung durch Nutzer abgebrochen; Codex wurde nicht geschlossen.",
        "en": "Safe maintenance cancelled by user; Codex was not closed.",
        "es": "Mantenimiento Safe cancelado por el usuario; Codex no fue cerrado.",
    },
    "auto_cancelled_short": {
        "de": "Safe-Wartung abgebrochen.",
        "en": "Safe maintenance cancelled.",
        "es": "Mantenimiento Safe cancelado.",
    },
    "auto_idle_ok": {
        "de": "Codex ist im Leerlauf (keine aktiven Automatisierungen).",
        "en": "Codex is idle (no active automations).",
        "es": "Codex está inactivo (sin automatizaciones activas).",
    },
    "auto_fast_mode": {
        "de": "Fast-Modus: ohne auf Leerlauf zu warten.",
        "en": "Fast mode: not waiting for idle.",
        "es": "Modo Fast: sin esperar a la inactividad.",
    },
    "auto_close_blocked": {
        "de": "Codex läuft und Schließen ist nicht freigegeben (auto_close_codex=False bzw. kein --close). Bitte Codex selbst beenden oder den Tray-Button nutzen.",
        "en": "Codex is running and closing is not permitted (auto_close_codex=False or no --close). Please close Codex yourself or use the tray button.",
        "es": "Codex está en ejecución y no está permitido cerrarlo (auto_close_codex=False o sin --close). Por favor, cierra Codex manualmente o usa el botón de la bandeja.",
    },
    "auto_close_blocked_short": {
        "de": "Codex läuft — Schließen nicht freigegeben.",
        "en": "Codex running — closing not permitted.",
        "es": "Codex en ejecución — no está permitido cerrarlo.",
    },
    "auto_close_planned": {
        "de": "Würde Codex beenden ({mode}-Modus) und Reste bereinigen.",
        "en": "Would close Codex ({mode} mode) and clean remnants.",
        "es": "Cerraría Codex (modo {mode}) y limpiaría restos.",
    },
    "auto_closing": {
        "de": "Beende Codex vollständig (inkl. Tray) …",
        "en": "Closing Codex completely (including tray) ...",
        "es": "Cerrando Codex por completo (incluida la bandeja) …",
    },
    "auto_closed": {
        "de": "Codex vollständig beendet.",
        "en": "Codex fully closed.",
        "es": "Codex cerrado por completo.",
    },
    "auto_abort_active": {
        "de": "Codex wurde wieder aktiv; Wartung abgebrochen.",
        "en": "Codex became active again; maintenance aborted.",
        "es": "Codex volvió a estar activo; mantenimiento abortado.",
    },
    "auto_abort_active_short": {
        "de": "Codex wieder aktiv — Wartung abgebrochen.",
        "en": "Codex active again — maintenance aborted.",
        "es": "Codex activo de nuevo — mantenimiento abortado.",
    },
    "auto_abort_not_closed": {
        "de": "Codex ließ sich nicht vollständig beenden; Wartung abgebrochen.",
        "en": "Codex could not be fully closed; maintenance aborted.",
        "es": "Codex no se pudo cerrar por completo; mantenimiento abortado.",
    },
    "auto_abort_not_closed_short": {
        "de": "Codex nicht beendbar — Wartung abgebrochen.",
        "en": "Codex cannot be closed — maintenance aborted.",
        "es": "No se puede cerrar Codex — mantenimiento abortado.",
    },
    "auto_maintain_start": {
        "de": "Starte Wartung …",
        "en": "Starting maintenance ...",
        "es": "Iniciando mantenimiento …",
    },
    "auto_restart": {
        "de": "Starte Codex neu …",
        "en": "Restarting Codex ...",
        "es": "Reiniciando Codex …",
    },
    "auto_restart_ok": {
        "de": "Codex neu gestartet (Fenster erkannt). {message}",
        "en": "Codex restarted (window detected). {message}",
        "es": "Codex reiniciado (ventana detectada). {message}",
    },
    "auto_restart_warn": {
        "de": "Codex gestartet, aber Fenster (Renderer) nicht innerhalb {seconds}s erkannt. {message}",
        "en": "Codex started, but no window (renderer) appeared within {seconds}s. {message}",
        "es": "Codex iniciado, pero no se detectó ventana (renderer) en {seconds}s. {message}",
    },
}

_current: Language = DEFAULT_LANGUAGE


def detect_language() -> Language:
    """Sprache aus System-Locale ableiten (Fallback: Deutsch)."""
    try:
        lang, _ = locale.getdefaultlocale()
        if lang:
            code = lang.lower()
            for prefix, mapped in (
                ("en", "en"),
                ("es", "es"),
                ("zh", "zh"),
                ("ja", "ja"),
                ("ru", "ru"),
                ("de", "de"),
            ):
                if code.startswith(prefix):
                    return mapped  # type: ignore[return-value]
    except (ValueError, TypeError):
        pass
    return DEFAULT_LANGUAGE


def normalize_language(lang: object) -> Language | None:
    """Prüfe und normalisiere einen externen Sprachwert."""
    if isinstance(lang, str):
        value = lang.strip().lower()
        base = value.split("_")[0].split("-")[0]
        if base in SUPPORTED_LANGUAGES:
            return base  # type: ignore[return-value]
    return None


def set_language(lang: Language | str) -> None:
    global _current
    _current = normalize_language(lang) or detect_language()


def get_language() -> Language:
    return _current


def t(key: str, **kwargs: object) -> str:
    """Übersetze einen Schlüssel in die aktive Sprache.

    Fallback-Kette (4-stufig): Zielsprache (_current) -> en -> de -> key.
    Unbekannte Keys werden direkt als key zurückgegeben.
    """
    entry = _CATALOG.get(key)
    if entry is None:
        text = key
    else:
        # 4-stufige Fallback-Kette: Zielsprache -> en -> de -> key
        text = key
        for candidate in (_current, "en", "de"):
            val = entry.get(candidate)
            if val:
                text = val
                break

    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def language_label(lang: Language | str) -> str:
    """Lokalisierter Name einer Sprache in der aktuell aktiven Sprache."""
    normalized = normalize_language(lang) or DEFAULT_LANGUAGE
    label = t(f"language_{normalized}")
    if label != f"language_{normalized}":
        return label
    return LANGUAGE_DISPLAY_NAMES.get(normalized, normalized)


def available_keys() -> list[str]:
    """Alle verfügbaren Übersetzungsschlüssel (für Tests)."""
    return sorted(_CATALOG.keys())


def get_locales_path() -> Path:
    """Ermittelt den Standardpfad zur externen translations.json Datei."""
    # 1. Project-root locales/ (wenn im Source-Checkout)
    root_locales = Path(__file__).resolve().parent.parent.parent / "locales" / "translations.json"
    if root_locales.is_file():
        return root_locales
    # 2. Package-interne locales/ (wenn installiert/packaged)
    pkg_locales = Path(__file__).resolve().parent / "locales" / "translations.json"
    if pkg_locales.is_file():
        return pkg_locales
    return root_locales


def load_translations_file(path: Path | str | None = None) -> int:
    """Lädt externe Übersetzungen aus einer JSON-Datei und aktualisiert _CATALOG.

    Gibt die Anzahl der geladenen/aktualisierten Schlüssel zurück.
    """
    p = get_locales_path() if path is None else Path(path)
    if not p.is_file():
        return 0
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        logger.warning("Konnte externe Übersetzungen aus %s nicht laden: %s", p, e)
        return 0

    if not isinstance(data, dict):
        return 0

    count = 0
    for k, v in data.items():
        if isinstance(v, dict):
            if k in _CATALOG:
                for lang_code, trans_val in v.items():
                    if isinstance(trans_val, str) and trans_val.strip():
                        _CATALOG[k][lang_code] = trans_val
            else:
                _CATALOG[k] = {
                    lang_code: trans_val
                    for lang_code, trans_val in v.items()
                    if isinstance(trans_val, str)
                }
            count += 1
    return count


def export_translations_json(path: Path | str | None = None) -> Path:
    """Exportiert den aktuellen Katalog nach locales/translations.json."""
    p = get_locales_path() if path is None else Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(_CATALOG, f, indent=2, ensure_ascii=False)
    return p


# Auto-Load externe Übersetzungen beim Modulimport, falls Datei existiert
_ext_path = get_locales_path()
if _ext_path.is_file():
    load_translations_file(_ext_path)
