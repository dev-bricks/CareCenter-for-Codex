# Privacy

Canonical source: [PRIVACY_POLICY.md](../PRIVACY_POLICY.md)

## English

CareCenter for Codex is an offline Windows utility for diagnosing and
maintaining the local Codex desktop installation.

### Data collection

CareCenter for Codex does **not** collect, transmit, or sell personal data.
There is no telemetry, analytics, crash reporting, cloud sync, or background
network activity during normal runtime.

### Local processing

The app reads and writes only local files that are needed for its maintenance
workflow, such as:

- the local Codex SQLite log database
- local log files created by CareCenter for Codex
- optional local backup copies created before maintenance
- local Windows/AppX state required for Codex repair actions

All processing happens on the user's device.

### External services

Normal runtime does not call external APIs. Some actions may open the Microsoft
Store or a local Windows repair command, but the tool itself does not upload
data. The separately invoked `store-materials --live-pages` command is an
explicit manual release preflight; only it requests the configured Store pages
over HTTPS and reports reachability with release-gate warnings. It is not
telemetry and is not part of normal runtime.

### Contact

Support and privacy contact paths are published on the support page:
[Support](./support.md)

---

## Deutsch

CareCenter for Codex ist ein offline nutzbares Windows-Werkzeug zur Diagnose
und Wartung der lokalen Codex-Desktop-Installation.

### Datenerhebung

CareCenter for Codex erhebt, überträgt oder verkauft **keine**
personenbezogenen Daten. Es gibt keine Telemetrie, keine Analysefunktionen,
keine Absturzberichte, keine Cloud-Synchronisation und keine
Hintergrund-Netzwerkaktivität im normalen Betrieb.

### Lokale Verarbeitung

Die Anwendung liest und schreibt nur lokale Dateien, die für den
Wartungsablauf erforderlich sind, zum Beispiel:

- die lokale Codex-SQLite-Logdatenbank
- lokale Protokolldateien von CareCenter for Codex
- optionale lokale Sicherungskopien vor einer Wartung
- lokale Windows-/AppX-Zustände für Codex-Reparaturschritte

Die gesamte Verarbeitung findet ausschließlich auf dem Gerät des Nutzers statt.

### Externe Dienste

Im normalen Betrieb ruft das Tool keine externen APIs auf. Einige Aktionen
können den Microsoft Store oder lokale Windows-Reparaturbefehle öffnen, aber
das Tool selbst lädt keine Daten hoch. Der separat gestartete Befehl
`store-materials --live-pages` ist ein ausdrücklich manueller Release-
Vorabcheck; nur dieser Opt-in-Pfad ruft die konfigurierten Store-Seiten über
HTTPS ab und meldet die Erreichbarkeit mit eigenen Gate-Warnungen. Er ist keine
Telemetrie und gehört nicht zur normalen Laufzeit.

### Kontakt

Support- und Datenschutzkontakte sind auf der Support-Seite veröffentlicht:
[Support](./support.md)
