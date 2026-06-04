# Support

Stand: 2026-06-01

## Zweck

Diese Datei hält den aktuellen Supportpfad für den geplanten Windows-Store- und
GitHub-Release fest. Die öffentlichen URLs sind in `store_package.json`
eingetragen.

## Aktueller Status

- Das Projekt wird im öffentlichen GitHub-Repository gepflegt:
  `https://github.com/dev-bricks/CareCenter-for-Codex`
- `privacy_url` und `support_url` in `store_package.json` zeigen auf die
  veröffentlichten Projektdateien.
- Der Check `python -m codex_logdatenbank_wartung.cli store-materials` prüft
  diesen Stand vor einer Store-Einreichung.

## Öffentlicher Supportpfad

- Support: `https://github.com/dev-bricks/CareCenter-for-Codex/blob/main/SUPPORT.md`
- Datenschutz: `https://github.com/dev-bricks/CareCenter-for-Codex/blob/main/PRIVACY_POLICY.md`

Vor einer Windows-Store-Einreichung müssen Store-Listing, Screenshot und
MSIX/WACK-Stand auf dieselben URLs bezogen bleiben.

## Interner Support bis dahin

- Projektdokumentation: `README.md`, `PORTIERUNGSPLAN.md`, `TODO.md`
- Lokale technische Doku: `ARCHITECTURE.md`, `STATE.md`, `DECISIONS.md`
- Lokale Prüfung: `python -m pytest`
- Store-Material-Check: `python -m codex_logdatenbank_wartung.cli store-materials`
