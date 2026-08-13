# Support

Canonical source: [SUPPORT.md](../SUPPORT.md)

## English

### Public support path

- Project repository:
  [dev-bricks/CareCenter-for-Codex](https://github.com/dev-bricks/CareCenter-for-Codex)
- Issues:
  [github.com/dev-bricks/CareCenter-for-Codex/issues](https://github.com/dev-bricks/CareCenter-for-Codex/issues)
- Privacy page:
  [Privacy](./privacy.md)

### Scope

CareCenter for Codex is a local Windows utility. Support covers installation,
repair flows, Windows Store readiness materials, and reproducible local checks.
The regular checks are local-only. `store-materials --live-pages` is a separate
explicit manual release preflight that requests configured HTTPS pages; it is
not part of normal runtime and is not telemetry.

### Local verification

- `python -m pytest`
- `python -m codex_logdatenbank_wartung.cli store-materials`

---

## Deutsch

### Öffentlicher Supportpfad

- Projekt-Repository:
  [dev-bricks/CareCenter-for-Codex](https://github.com/dev-bricks/CareCenter-for-Codex)
- Issues:
  [github.com/dev-bricks/CareCenter-for-Codex/issues](https://github.com/dev-bricks/CareCenter-for-Codex/issues)
- Datenschutz-Seite:
  [Privacy](./privacy.md)

### Umfang

CareCenter for Codex ist ein lokales Windows-Werkzeug. Der Support deckt
Installation, Reparaturpfade, Windows-Store-Materialien und reproduzierbare
lokale Prüfungen ab. Die regulären Prüfungen arbeiten nur lokal.
`store-materials --live-pages` ist ein separater, ausdrücklich manueller
Release-Vorabcheck, der konfigurierte HTTPS-Seiten abruft; er gehört nicht zur
normalen Laufzeit und ist keine Telemetrie.

### Lokale Verifikation

- `python -m pytest`
- `python -m codex_logdatenbank_wartung.cli store-materials`
