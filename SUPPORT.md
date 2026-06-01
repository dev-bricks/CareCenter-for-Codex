# Support

Stand: 2026-06-01

## Zweck

Diese Datei hält den aktuellen Supportpfad für den geplanten Windows-Store- und
GitHub-Release fest, solange noch keine endgültigen öffentlichen URLs in
`store_package.json` eingetragen sind.

## Aktueller Status

- Das Projekt ist lokal entwickelt und noch nicht öffentlich eingereicht.
- `privacy_url` und `support_url` in `store_package.json` bleiben bewusst leer,
  bis der reale Veröffentlichungsort feststeht.
- Der neue Check `python -m codex_logdatenbank_wartung.cli store-materials`
  meldet diesen Zustand als Warnung statt als stillen Fehler.

## Geplanter öffentlicher Supportpfad

Vor einer echten Windows-Store-Einreichung müssen diese Punkte ergänzt werden:

1. Öffentliche Support-URL festlegen.
2. Öffentliche Datenschutz-URL festlegen.
3. Store-Listing, Screenshot und MSIX/WACK-Stand auf dieselben URLs beziehen.

## Interner Support bis dahin

- Projektdokumentation: `README.md`, `PORTIERUNGSPLAN.md`, `TODO.md`
- Lokale technische Doku: `ARCHITECTURE.md`, `STATE.md`, `DECISIONS.md`
- Lokale Prüfung: `python -m pytest`
- Store-Material-Check: `python -m codex_logdatenbank_wartung.cli store-materials`
