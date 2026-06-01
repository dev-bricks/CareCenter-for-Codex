# Store Listing - CareCenter for Codex

## Deutsch

### Kurzbeschreibung
Repariert Codex-Starts und wartet die lokale Codex-Datenbank sicher und offline.

### Beschreibung
CareCenter for Codex ist ein lokales Windows-Tray- und CLI-Werkzeug für die
OpenAI-Codex-Desktop-App. Die Anwendung hilft dabei, hängende Restprozesse,
verwaiste Lockfiles und festhängende Store-Zustände zu erkennen und kontrolliert
zu bereinigen, ohne Telemetrie oder Cloud-Abhängigkeiten.

**Was CareCenter for Codex kann:**

- Startprobleme der Codex-Desktop-App diagnostizieren und reparieren
- Hängende Ghost-Prozesse und verwaiste Lockfiles sicher entfernen
- Lokale SQLite-Logdatenbank konservativ warten: Backup, Integritätscheck,
  WAL-Checkpoint, `PRAGMA optimize`, `VACUUM`
- Microsoft-Store-bezogene Codex-Probleme über `wsreset`, Paket-Reparatur und
  Resetpfade unterstützen
- Geplante Wartung über einen optionalen Windows-Task anstoßen
- Jeden Lauf lokal protokollieren, damit Eingriffe nachvollziehbar bleiben

**Warum nur Windows?**

Das Tool arbeitet gezielt mit Windows-spezifischen Pfaden, dem Microsoft Store,
AppX-Paketen, dem Task Scheduler und der lokalen Codex-Installation. Es ist
deshalb keine plattformübergreifende Tray-App, sondern ein bewusst fokussiertes
Windows-Werkzeug.

**Wichtige Grenzen:**

- Keine Telemetrie, kein Cloud-Service, keine Hintergrund-Uploads
- Keine Eingriffe, solange aktive Codex-Prozesse oder laufende Automatisierungen
  erkannt werden
- Keine Verwaltung der Codex-CLI außerhalb der dafür sicheren Prüfpfade

### Schlüsselwörter
Codex, Windows, Tray, Store, SQLite, Wartung, Reparatur, AppX, Offline, Developer Tools

### Kategorie
Developer Tools

---

## English

### Short Description
Repairs Codex startup issues and safely maintains the local Codex database offline.

### Description
CareCenter for Codex is a local Windows tray and CLI utility for the OpenAI
Codex desktop app. It helps diagnose and clean up hung leftovers, stale
lockfiles, and Microsoft Store related states without telemetry or cloud
dependencies.

**What CareCenter for Codex does:**

- Diagnose and repair Codex desktop startup issues
- Safely remove hung ghost processes and stale lockfiles
- Conservatively maintain the local SQLite log database: backup, integrity
  check, WAL checkpoint, `PRAGMA optimize`, `VACUUM`
- Assist with Codex Microsoft Store states through `wsreset`, package repair,
  and reset paths
- Trigger scheduled maintenance through an optional Windows scheduled task
- Record local audit logs so every action remains reviewable

**Why Windows only?**

The tool intentionally depends on Windows-specific paths, Microsoft Store/AppX,
Task Scheduler, and the local Codex desktop installation. It is therefore a
focused Windows utility, not a cross-platform tray clone.

**Important boundaries:**

- No telemetry, no cloud service, no background uploads
- No maintenance while active Codex processes or automations are detected
- No unsafe manipulation of the Codex CLI

### Keywords
Codex, Windows, tray, Store, SQLite, maintenance, repair, AppX, offline, developer tools

### Category
Developer Tools
