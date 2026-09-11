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
  Codex-**CLI** wird niemals als Beendigungsziel erfasst; ein breiter read-only Prozessnachweis
  blockiert jedoch Thread-Store-Mutationen, solange Desktop oder CLI aktiv sind.
- **Windows-AppX/Store:** Registrieren/Zurücksetzen des Codex-Store-Pakets (elevated), Öffnen der Store-Produktseite
- **Normale Laufzeit nur lokal:** keine Telemetrie, keine Cloud-Synchronisation,
  keine Hintergrund-Uploads und keine externen API-Aufrufe (das Öffnen der
  Microsoft-Store-Seite ist nur eine lokale Betriebssystemaktion). Der separate
  Befehl `store-materials --live-pages` ist ein ausdrücklich manueller Release-
  Vorabcheck; nur dieser Opt-in-Pfad ruft konfigurierte Store-URLs über HTTPS
  ab und liefert ein eigenes Warnungs-/Fehlerergebnis. Er wird nie vom Tray,
  Wächter, Wartungsloop oder den Standard-CLI-Befehlen aufgerufen.

### Reaktionszeit & Triage-SLA

- **Eingangsbestätigung (Response SLA):** Wir bestätigen den Eingang von Sicherheitsmeldungen verbindlich innerhalb von **48 Stunden** (48 hours).
- **Triage & Risikobewertung:** Eine erste technische Triage und Risikobewertung erfolgt innerhalb von **5 Werktagen** (5 business days).
- **Veröffentlichung:** Kritische Probleme werden priorisiert. Bitte geben Sie ausreichend Zeit für die Fehlerbehebung, bevor Details öffentlich gemacht werden.

### Unterstützte Versionen

| Version | Unterstützt | Sicherheits-Updates & SLA |
| ------- | ----------- | -------------------------- |
| 0.8.x   | :white_check_mark: Ja | Aktive Produktionsbasis; 48h-Antwort & 5-Werktage-Triage-SLA |
| < 0.8   | :x: Nein    | Nicht unterstützt; Upgrade erforderlich |

### Kontakt & Meldewege

1. **GitHub Security Advisories (bevorzugt):** [GitHub Private Vulnerability Reporting](https://github.com/dev-bricks/CareCenter-for-Codex/security/advisories)
2. **Direkter Sicherheitskontakt:**
   - `security@open-bricks.org`
   - `security@dev-bricks.org`
   - `support@lukasgeiger.com`
   - `lukas@open-bricks.org`

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
  node-based Codex **CLI** is never a termination target; broad read-only detection still blocks
  thread-store mutation while either Desktop or CLI activity is present.
- **Windows AppX/Store:** register/reset of the Codex Store package (elevated), opening the Store product page
- **Normal runtime is local-only:** no telemetry, cloud sync, background uploads,
  or external API calls (opening the Microsoft Store page is only a local OS
  action). The separate `store-materials --live-pages` command is an explicit
  manual release preflight; only that opt-in path requests configured Store URLs
  over HTTPS and returns its own warning/error result. It is never called by the
  tray, watcher, maintenance loop, or default CLI commands.

### Response Time & Triage SLA

- **Receipt Acknowledgment (Response SLA):** We commit to acknowledging receipt of security reports within **48 hours**.
- **Triage & Assessment:** An initial technical triage and risk assessment will be provided within **5 business days** (5 Werktagen).
- **Disclosure:** Critical issues are prioritized. Please allow reasonable time for remediation before public disclosure.

### Supported Versions

| Version | Supported | Security Updates & SLA |
| ------- | --------- | ---------------------- |
| 0.8.x   | :white_check_mark: Yes | Active release; 48h response & 5-business-day triage SLA |
| < 0.8   | :x: No    | Unsupported legacy release; upgrade required |

### Contact & Reporting Channels

1. **GitHub Security Advisories (Preferred):** [GitHub Private Vulnerability Reporting](https://github.com/dev-bricks/CareCenter-for-Codex/security/advisories)
2. **Direct Maintainer Contact:**
   - `security@open-bricks.org`
   - `security@dev-bricks.org`
   - `support@lukasgeiger.com`
   - `lukas@open-bricks.org`
