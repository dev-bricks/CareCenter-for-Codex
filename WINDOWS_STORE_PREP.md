# Windows Store Prep - CareCenter for Codex

Stand: 2026-08-28

## Ziel

Windows-Store-Release (Target `windows_store`) als belastbare Baseline vorbereiten und Store-Readiness erreichen.

## Erledigt in diesem Schritt

- `store_package.json` mit Partner-Center-Publisher (`CN=52596601-BAB4-4F3F-B182-E8F3F273B202`), Display-Namen (`Lukas Geiger`), Identity-Namen (`LukasGeiger.CareCenterForCodex`), Version (`0.8.0.0`) sowie Privacy- & Support-Dokumentations-URLs konfiguriert.
- `STORE_LISTING.md` in Deutsch und Englisch mit Kurzbeschreibung, Features und Abgrenzung vorbereitet.
- `PRIVACY_POLICY.md` und `SUPPORT.md` sowie GitHub-Pages-Generator (`scripts/build_store_pages.py`) eingebunden.
- CLI-Befehl `codex-logwartung store-materials` um `--generate-manifest` (erzeugt valide `AppxManifest.xml`) und `--check-msix-sdk` (prüft `makeappx.exe`) erweitert.
- Die vier vom zentralen MSIX-Builder erwarteten Paketlogos unter
  `store_assets/` sind aus dem vorhandenen App-Icon erzeugt. Der Builder kopiert
  sie beim Staging nach `icons/`; genau diese Paketpfade referenziert das Manifest.
- Preflight-Validierung via `validate_store_materials` inkl. XML-Parsing,
  Abgleich von Identity, Publisher, Version, Executable und DisplayName mit
  `store_package.json` sowie Prüfung aller referenzierten Logo-Dateien.
- Automatisierte Testsuite (`tests/test_store_release.py` und `tests/test_cli.py`) erweitert.

## Status vor Store-Submission

1. Metadaten, Doku, Manifest und die vier kanonischen `store_assets/`-Paketlogos
   vollständig. Der lokale Manifest-/Quellmaterialvertrag via
   `codex-logwartung store-materials` ist bestanden.
2. Manifest-Generierung via `codex-logwartung store-materials --generate-manifest` einsatzbereit.
3. Restgates: Windows SDK mit `makeappx.exe` installieren; anschließend den
   zentralen `_STORE/msstore_build_msix.ps1`-Staging-/Buildpfad tatsächlich
   ausführen und erst danach MSIX, WACK und Partner Center attestieren.
