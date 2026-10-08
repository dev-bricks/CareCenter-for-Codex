#!/usr/bin/env python3
"""
generate_store_assets.py - Multi-Resolution Windows Store Tile Assets and 16:9 Screenshots for CareCenter for Codex.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

os.environ["QT_QPA_PLATFORM"] = "offscreen"


def generate_tile_icons() -> None:
    """Generiert alle geforderten Kachel-Icons aus der Master-Grafik."""
    master_path = PROJECT_ROOT / "CareCenter.png"
    if not master_path.exists():
        master_path = PROJECT_ROOT / "assets" / "CareCenter.png"
    if not master_path.exists():
        master_path = PROJECT_ROOT / "icon.png"

    with Image.open(master_path) as base_img:
        base = base_img.convert("RGBA")

        target_dirs = [
            PROJECT_ROOT / "store_package" / "CareCenter for Codex" / "icons",
            PROJECT_ROOT / "store_assets",
            PROJECT_ROOT / "assets" / "icons",
            PROJECT_ROOT / "releases" / "windowsstore",
        ]
        for d in target_dirs:
            d.mkdir(parents=True, exist_ok=True)

        sizes = {
            "icon_44x44.png": (44, 44),
            "icon_50x50.png": (50, 50),
            "icon_150x150.png": (150, 150),
            "icon_310x310.png": (310, 310),
            "StoreLogo.png": (50, 50),
        }

        for name, size in sizes.items():
            resized = base.resize(size, Image.Resampling.LANCZOS)
            for d in target_dirs:
                resized.save(d / name, format="PNG")

        # 310x150 Wide Tile (Zentrierte Kachel auf 310x150 Canvas)
        wide = Image.new("RGBA", (310, 150), (15, 23, 42, 255))
        icon_fit = base.resize((120, 120), Image.Resampling.LANCZOS)
        offset_x = (310 - 120) // 2
        offset_y = (150 - 120) // 2
        wide.paste(icon_fit, (offset_x, offset_y), icon_fit)
        for d in target_dirs:
            wide.save(d / "icon_310x150.png", format="PNG")

        # Standard-Aliasse
        aliases = {
            "Square44x44Logo.png": "icon_44x44.png",
            "Square50x50Logo.png": "icon_50x50.png",
            "Square150x150Logo.png": "icon_150x150.png",
            "Wide310x150Logo.png": "icon_310x150.png",
            "Square310x310Logo.png": "icon_310x310.png",
        }
        for alias_name, src_name in aliases.items():
            for d in target_dirs:
                src_file = d / src_name
                if src_file.exists():
                    shutil_img = Image.open(src_file)
                    shutil_img.save(d / alias_name, format="PNG")

        print("Tile icons generated successfully across all targets.")


def _render_ui_capture(state_text: str, result_text: str, progress_val: int, progress_label: str, zombies: int) -> Image.Image:
    """Rendert ein StatusWindow offscreen mit authentischen Zuständen."""
    from PySide6.QtWidgets import QApplication

    from codex_logdatenbank_wartung.tray import StatusWindow

    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication(["carecenter-screenshot-builder"])

    window = StatusWindow()
    window.set_state(state_text)
    window.set_zombie_count(zombies)
    window.set_progress(progress_val, progress_label, False)
    window.set_result(result_text)
    window.set_audit_settings("auto", "auto", "auto")
    window.resize(520, 580)
    window.show()
    for _ in range(4):
        app.processEvents()

    pixmap = window.grab()
    window.close()
    if owns_app:
        app.quit()

    temp_path = PROJECT_ROOT / ".pytest_temp" / "temp_ui_grab.png"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(str(temp_path))
    with Image.open(temp_path) as im:
        return im.convert("RGBA")


def generate_store_screenshots() -> None:
    """Erzeugt 4 1920x1080 Full-HD Screenshots im 16:9-Verhältnis für den Microsoft Store."""
    dest_dirs = [
        PROJECT_ROOT / "releases" / "windowsstore" / "screenshots",
        PROJECT_ROOT / "screenshots" / "store",
    ]
    for d in dest_dirs:
        d.mkdir(parents=True, exist_ok=True)

    master_icon_path = PROJECT_ROOT / "store_assets" / "Square150x150Logo.png"
    with Image.open(master_icon_path) as mi:
        app_logo_small = mi.convert("RGBA").resize((72, 72), Image.Resampling.LANCZOS)

    shots = [
        {
            "name": "01_dashboard_status.png",
            "aliases": ["01-dashboard-status.png", "shot-1-dashboard.png"],
            "title": "CareCenter for Codex — Systemdiagnose & Status",
            "subtitle": "Sofortige Überwachung aktiver Prozesse, Lockfiles und des Codex-Desktop-Zustands",
            "tag": "SYSTEMSTATUS",
            "tag_color": (2, 132, 199, 255),  # sky-600
            "state_text": "System bereit. Keine blockierenden Lockfiles gefunden.",
            "result_text": "Systemprüfung:\n• Codex Desktop: Nicht aktiv (Sicher für Wartung)\n• Lockfiles: 0 verwaist\n• MCP-Server: 0 Zombies\n• Status: Normal",
            "progress_val": 100,
            "progress_label": "Vollständige Systemanalyse abgeschlossen",
            "zombies": 0,
        },
        {
            "name": "02_database_maintenance.png",
            "aliases": ["02-database-maintenance.png", "shot-2-database.png"],
            "title": "Lokale SQLite-Wartungszentrale & Backups",
            "subtitle": "Konservative Logdatenbank-Wartung: Backup, WAL-Checkpoint, PRAGMA optimize & VACUUM",
            "tag": "SQLITE-DATENBANK",
            "tag_color": (16, 185, 129, 255),  # emerald-500
            "state_text": "SQLite-Wartung erfolgreich ausgeführt.",
            "result_text": "Wartungsprotokoll:\n• Backup erstellt: codex_log_backup_20261008.db\n• Integritätsprüfung: OK (0 Fehler)\n• WAL-Checkpoint: PASS (TRUNCATE)\n• Speicherbereinigung: 14.2 MB freigegeben",
            "progress_val": 100,
            "progress_label": "Integritätsprüfung & Optimierung erfolgreich",
            "zombies": 0,
        },
        {
            "name": "03_process_cleanup.png",
            "aliases": ["03-process-cleanup.png", "shot-3-cleanup.png"],
            "title": "Sichere Restprozess- & Ghost-Bereinigung",
            "subtitle": "Schutz vor Zombie-Prozessen und hängenden MCP-Servern ohne Datenverlust",
            "tag": "PROZESS-SCHUTZ",
            "tag_color": (245, 158, 11, 255),  # amber-500
            "state_text": "Hintergrundbereinigung abgeschlossen.",
            "result_text": "Prozessdiagnose:\n• Aktive Codex-Hauptinstanz: Geschützt\n• Verwaiste Hilfsprozesse: 0 erkannt\n• Stale PID-Locks: Bereinigt\n• CPU-Auslastung: Normal (<1%)",
            "progress_val": 100,
            "progress_label": "Prozessbaum verifiziert und bereinigt",
            "zombies": 0,
        },
        {
            "name": "04_audit_settings.png",
            "aliases": ["04-audit-settings.png", "shot-4-settings.png"],
            "title": "Transparente Auditierung & Wartungseinstellungen",
            "subtitle": "100% Offline-First, konfigurierbare Intervalle, lokale Protokolle ohne Telemetrie",
            "tag": "AUDIT & EINSTELLUNGEN",
            "tag_color": (139, 92, 246, 255),  # violet-500
            "state_text": "Wächter und Audit-Loop aktiv.",
            "result_text": "Audit-Konfiguration:\n• MCP-Modus: auto (automatische Erkennung)\n• Plugin-Modus: auto (konservativ)\n• Intervall: Alle 15 Minuten (Hintergrund)\n• Zero-Egress: 100% Offline (Keine Telemetrie)",
            "progress_val": 100,
            "progress_label": "Audit-Wächter läuft planmäßig",
            "zombies": 0,
        },
    ]

    canvas_w, canvas_h = 1920, 1080
    bg_dark = (15, 23, 42, 255)  # slate-900
    border_col = (51, 65, 85, 255)  # slate-700

    try:
        font_title = ImageFont.truetype("arial.ttf", 40)
        font_sub = ImageFont.truetype("arial.ttf", 22)
        font_tag = ImageFont.truetype("arialbd.ttf", 16)
        font_foot = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_tag = ImageFont.load_default()
        font_foot = ImageFont.load_default()

    for item in shots:
        canvas = Image.new("RGBA", (canvas_w, canvas_h), bg_dark)
        draw = ImageDraw.Draw(canvas)

        # Dezenter Farbverlauf / Glow oben
        for y in range(240):
            alpha = int(40 * (1 - y / 240))
            draw.line([(0, y), (canvas_w, y)], fill=(item["tag_color"][0], item["tag_color"][1], item["tag_color"][2], alpha))

        # Header-Bereich
        header_x = 100
        canvas.paste(app_logo_small, (header_x, 60), app_logo_small)

        # Badge
        draw.rounded_rectangle([header_x + 95, 60, header_x + 95 + 180, 86], radius=6, fill=item["tag_color"])
        draw.text((header_x + 105, 64), item["tag"], fill=(255, 255, 255, 255), font=font_tag)

        # Titel & Subtitel
        draw.text((header_x + 95, 96), item["title"], fill=(255, 255, 255, 255), font=font_title)
        draw.text((header_x + 95, 148), item["subtitle"], fill=(148, 163, 184, 255), font=font_sub)

        # UI Fenster rendern
        ui_img = _render_ui_capture(
            item["state_text"],
            item["result_text"],
            item["progress_val"],
            item["progress_label"],
            item["zombies"],
        )

        # UI zentriert im unteren Bereich platzieren mit Schatten und Rand
        ui_w, ui_h = ui_img.size
        target_ui_h = 760
        scale = target_ui_h / ui_h
        target_ui_w = int(ui_w * scale)
        ui_scaled = ui_img.resize((target_ui_w, target_ui_h), Image.Resampling.LANCZOS)

        pos_x = (canvas_w - target_ui_w) // 2
        pos_y = 220

        # Schatten
        shadow_rect = [pos_x - 12, pos_y - 8, pos_x + target_ui_w + 12, pos_y + target_ui_h + 16]
        draw.rounded_rectangle(shadow_rect, radius=12, fill=(0, 0, 0, 100))

        # Rahmen
        frame_rect = [pos_x - 3, pos_y - 3, pos_x + target_ui_w + 3, pos_y + target_ui_h + 3]
        draw.rounded_rectangle(frame_rect, radius=10, fill=border_col)

        canvas.paste(ui_scaled, (pos_x, pos_y), ui_scaled)

        # Footer
        footer_text = "100% Offline-First • Keine Telemetrie • Zero-Egress • Open Source (MIT) • Lukas Geiger"
        draw.text((header_x, canvas_h - 45), footer_text, fill=(100, 116, 139, 255), font=font_foot)

        # Als RGB PNG speichern
        final_png = canvas.convert("RGB")
        for d in dest_dirs:
            target_file = d / item["name"]
            final_png.save(target_file, format="PNG")
            for alias in item["aliases"]:
                final_png.save(d / alias, format="PNG")

        print(f"Generated screenshot: {item['name']} (1920x1080)")

    print("All store screenshots generated successfully.")


def main():
    print("--- CareCenter for Codex Store Assets Generation ---")
    generate_tile_icons()
    generate_store_screenshots()
    print("--- Done ---")


if __name__ == "__main__":
    main()
