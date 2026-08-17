# Windows Store Prep - CareCenter for Codex

Stand: 2026-08-03

## Ziel

Windows-Store-Release (Target `windows_store`) als belastbare Baseline vorbereiten und Store-Readiness erreichen.

## Erledigt in diesem Schritt

- `store_package.json` mit Partner-Center-Publisher (`CN=52596601-BAB4-4F3F-B182-E8F3F273B202`), Display-Namen (`Lukas Geiger`), Identity-Namen (`LukasGeiger.CareCenterForCodex`), Version (`0.8.0.0`) sowie Privacy- & Support-Dokumentations-URLs konfiguriert.
- `STORE_LISTING.md` in Deutsch und Englisch mit Kurzbeschreibung, Features und Abgrenzung vorbereitet.
- `PRIVACY_POLICY.md` und `SUPPORT.md` sowie GitHub-Pages-Generator (`scripts/build_store_pages.py`) eingebunden.
- CLI-Befehl `codex-logwartung store-materials` um `--generate-manifest` (erzeugt valide `AppxManifest.xml`) und `--check-msix-sdk` (prüft `makeappx.exe`) erweitert.
- Preflight-Validierung via `validate_store_materials` inkl. Existenz- und Schema-Prüfung von `AppxManifest.xml`.
- Automatisierte Testsuite (`tests/test_store_release.py` und `tests/test_cli.py`) erweitert.

## Status vor Store-Submission

1. Metadaten in `store_package.json` und Doku vollständig. Preflight-Check via `codex-logwartung store-materials` bestanden.
2. Manifest-Generierung via `codex-logwartung store-materials --generate-manifest` einsatzbereit.
3. MSIX-Build-Erzeugung via Windows SDK `makeappx` / `WinStorePackager` im Partner Center bereit.
