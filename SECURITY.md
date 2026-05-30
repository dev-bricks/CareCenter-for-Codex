# Sicherheitsrichtlinie / Security Policy

## Deutsch

### Sicherheitslücken melden

Wenn Sie eine Sicherheitslücke finden, melden Sie diese bitte verantwortungsvoll:

1. **Kein öffentliches Issue eröffnen**
2. **GitHub Private Vulnerability Reporting verwenden** (`Security` → `Advisories` → `New`)
3. Beschreibung, Reproduktionsschritte und potenzielle Auswirkungen angeben

Falls Private Vulnerability Reporting noch nicht aktiviert ist, kontaktieren Sie
die Maintainer direkt über GitHub und veröffentlichen Sie keine Details in einem
öffentlichen Issue.

### Geltungsbereich

Dieses Tool führt sicherheitsrelevante lokale Operationen aus:
- **Dateisystem:** Lesen/Schreiben der lokalen SQLite-Logdatenbank, Backups, Konfiguration und Logs
- **Prozesse:** gezieltes Beenden hängender Codex-**Desktop**-Prozesse (Prozessbaum). Die node-basierte
  Codex-**CLI** wird über exakte Pfad-Erkennung bewusst nie erfasst.
- **Windows-AppX/Store:** Registrieren/Zurücksetzen des Codex-Store-Pakets (elevated), Öffnen der Store-Produktseite
- **Kein Netzwerk:** keine Telemetrie, keine externen API-Aufrufe (außer dem lokalen Öffnen der Store-Seite)

### Reaktionszeit

Bei kleineren Einzelprojekten können Reaktionszeiten variieren. Kritische
Probleme werden priorisiert. Bitte geben Sie ausreichend Zeit, bevor Sie
Details öffentlich machen.

---

## English

### Reporting a Vulnerability

If you find a security vulnerability, please report it responsibly:

1. **Do not open a public issue**
2. **Use GitHub Private Vulnerability Reporting** (`Security` → `Advisories` → `New`)
3. Include a description, reproduction steps, and potential impact

If private vulnerability reporting is not enabled yet, contact the maintainers
through GitHub and do not publish details in a public issue.

### Scope

This tool performs security-relevant local operations:
- **File system:** reads/writes the local SQLite log database, backups, configuration and logs
- **Processes:** targeted termination of hung Codex **desktop** processes (process tree). The
  node-based Codex **CLI** is deliberately never matched (exact executable-path detection).
- **Windows AppX/Store:** register/reset of the Codex Store package (elevated), opening the Store product page
- **No network:** no telemetry, no external API calls (other than locally opening the Store page)

### Response Time

For smaller solo projects, response times may vary. Critical issues will be
prioritized. Please allow reasonable time before public disclosure.
