# Windows Store Prep - CareCenter for Codex

Stand: 2026-10-08 (Store Readiness Audit & Packaging Staging)

## 1. Ziel & Status

Windows-Store-Release (Target `windows_store`) vollständig auditiert, gehärtet und für Einreichung bereitgestellt (**Status: BEREIT / STAGED**).

## 2. Erledigte Meilensteine

- **Metadaten (`store_package.json`):**
  - Publisher-DN: `CN=52596601-BAB4-4F3F-B182-E8F3F273B202` (Lukas Geiger)
  - Identität: `LukasGeiger.CareCenterForCodex`
  - Version: `0.8.0.0`
  - Lizenz: `MIT`
  - Fähigkeiten: `runFullTrust`
  - Kategorie: `Developer Tools`
  - Altersfreigabe: `3+` (IARC)
  - Sprachen: `["de-DE", "en-US", "es-ES", "zh-CN", "ja-JP", "ru-RU"]` (Tier-2 6-Sprachen-Parität)
  - Execution Alias: `carecenter.exe`
  - URLs: `https://dev-bricks.github.io/CareCenter-for-Codex/privacy` und `/support`
- **Desktop-Bridge `AppxManifest.xml`:**
  - Standorte: Root und `store_package/CareCenter for Codex/AppxManifest.xml`
  - Properties Logo: Auf kanonische 50x50 Kachel `<Logo>icons\StoreLogo.png</Logo>` gehärtet
  - TargetDeviceFamily: `Windows.Desktop` (MinVersion `10.0.17763.0`, MaxVersionTested `10.0.26100.0`)
  - Execution-Alias deklariert für `carecenter.exe`
- **Kachel- und Tile-Assets:**
  - In allen Zielverzeichnissen bereitgestellt (`store_package/CareCenter for Codex/icons/`, `store_assets/`, `assets/icons/`, `releases/windowsstore/`):
    - `StoreLogo.png` (50x50 Pixel)
    - `icon_44x44.png` / `Square44x44Logo.png`
    - `icon_50x50.png` / `Square50x50Logo.png`
    - `icon_150x150.png` / `Square150x150Logo.png`
    - `icon_310x150.png` / `Wide310x150Logo.png`
    - `icon_310x310.png` / `Square310x310Logo.png`
- **Store-Screenshots (16:9, 1920x1080 Full-HD):**
  - Unter `releases/windowsstore/screenshots/` und `screenshots/store/`:
    - `01_dashboard_status.png`: Dashboard mit Systemstatus, Zombie-Zähler und Wartungsübersicht
    - `02_database_maintenance.png`: SQLite-Datenbankanalyse mit Integritätsprüfung und Backup-Status
    - `03_process_cleanup.png`: Prozess- und Lockfile-Diagnose mit Bereinigungsstatus
    - `04_audit_settings.png`: Automations- und Audit-Einstellungen (MCP- und Plugin-Wartung, Scheduler)
- **Store-Listings & Richtlinie 10.1.3 Compliance:**
  - `STORE_LISTING.md`, `releases/windowsstore/store_listing_de.md`, `releases/windowsstore/store_listing_en.md`
  - Exakt 7 Suchbegriffe je Sprache, echte deutsche Umlaute (ä, ö, ü, ß), keine Markenrechtsverletzungen.
- **Packaging-Staging (`releases/windowsstore/`):**
  - Vollständiges Staging mit `BUILD.md`, `WACK_PROTOCOL.md`, `store_settings.json`, Store-Listings DE/EN, `StoreLogo.png`, `screenshots/` und `test_reports/`.
- **WACK-Preflight & Runner:**
  - `scripts/run_windows_wack.py` implementiert; Preflight generiert Berichte `releases/windowsstore/test_reports/wack_preflight_20261008.xml` und `.json` (6 PASS / 0 FAIL / 0 WARNING).
- **Automatisierte Qualitätssicherung & Vertragstests:**
  - Preflight-Auditor `scripts/check_store_readiness.py`: **AUDIT PASSED (6/6 Checks OK - Vorbereitung vollständig)**.
  - Vertragstestsuite `tests/test_store_materials.py`: 11/11 Tests bestanden (100% grün).
  - Gesamt-Testsuite: 500 passed (100% grün).

## 3. Nächste Schritte

1. Binären MSIX-Build ausführen via `_STORE/msstore_build_msix.ps1` oder Windows SDK `makeappx.exe`.
2. Submission im Microsoft Partner Center unter der reservierten App-Identität anlegen und einreichen.
