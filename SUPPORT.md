# Support

Stand: 2026-08-13

## Zweck

Diese Datei hält den aktuellen Supportpfad für den geplanten Windows-Store- und
GitHub-Release fest. Die öffentlichen URLs sind in `store_package.json`
eingetragen.

## Aktueller Status

- Das Projekt wird im öffentlichen GitHub-Repository gepflegt:
  `https://github.com/dev-bricks/CareCenter-for-Codex`
- `privacy_url` und `support_url` in `store_package.json` zeigen jetzt auf die
  geplanten GitHub-Pages-Ziele des Projekts.
- Der Check `python -m codex_logdatenbank_wartung.cli store-materials` prüft
  diesen Stand vor einer Store-Einreichung.
- Dieser Standardcheck bleibt lokal und kontaktiert keine Store-URL. Erst der
  ausdrücklich manuelle Opt-in-Aufruf `store-materials --live-pages` prüft die
  konfigurierten HTTPS-Seiten als separates Release-Gate. Der Aufruf gehört
  nicht zur normalen CareCenter-Laufzeit und ist keine Telemetrie.

## Öffentlicher Supportpfad

- Support: `https://dev-bricks.github.io/CareCenter-for-Codex/support`
- Datenschutz: `https://dev-bricks.github.io/CareCenter-for-Codex/privacy`
- Fallback-Repository: `https://github.com/dev-bricks/CareCenter-for-Codex`
- Issue-Tracker: `https://github.com/dev-bricks/CareCenter-for-Codex/issues`

Vor einer Windows-Store-Einreichung müssen Store-Listing, Screenshot und
MSIX/WACK-Stand auf dieselben URLs bezogen bleiben.

## Interner Support bis dahin

- Projektdokumentation: `README.md`, `README.de.md`, `ARCHITECTURE.md`, `CHANGELOG.md`
- Store-/Datenschutzunterlagen: `STORE_LISTING.md`, `PRIVACY_POLICY.md`,
  `SUPPORT.md`, `THIRD_PARTY_LICENSES.txt`
- Lokale Prüfung: `python -m pytest`
- Store-Material-Check: `python -m codex_logdatenbank_wartung.cli store-materials`
