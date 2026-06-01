# CareCenter for Codex

A local Windows tray + CLI utility that keeps the **OpenAI Codex desktop app** healthy:
it repairs failed starts, cleans up hung leftover processes, and safely maintains Codex's
local SQLite log database — all offline, with no telemetry.

*Deutsch: Ein lokales Windows-Tray- und CLI-Werkzeug, das die **OpenAI-Codex-Desktop-App**
gesund hält: Start-Reparatur, Aufräumen hängender Reste und sichere Wartung der lokalen
Codex-Logdatenbank — komplett offline.*

> [!IMPORTANT]
> **Unofficial / Inoffiziell.** This is an independent, community tool. It is **not** created by,
> affiliated with, endorsed by, or sponsored by OpenAI. *"OpenAI"* and *"Codex"* are trademarks of
> OpenAI; they are used here only to describe what this tool is compatible with (nominative use).
> Dieses Werkzeug stammt **nicht** von OpenAI und ist nicht mit OpenAI verbunden.

---

## Why

Closing the Codex window often leaves a hung main process behind (a known Codex-on-Windows
behavior). That ghost holds the singleton lock, so the **next start silently fails**. A failed
start is the first domino: it tempts a Store "repair/update" that can hang and cascade into
deeper breakage. CareCenter removes that first domino automatically and keeps the start clean.

## Features

- **Background start-prevention watcher** — every 60 s (read-only) it checks: if Codex is
  **closed** and hung leftovers exist (ghost process without a window / stale lockfile), it
  removes them so the next start is clean, and notifies you. It **never** touches an active
  session, **never** the node-based Codex CLI, and **never** a process tree that is still busy
  (CPU activity gate). A 🧟 counter shows how many leftovers were cleared since start.
- **One-click "Repair Codex"** — a single escalation that stops as soon as Codex starts: first a
  light, no-admin step (remove leftovers → launch → check for a window); only if needed it
  escalates (elevated: ClipSVC, complete a staged Store update, reset, re-register). If the
  package is completely gone it suggests a Store reinstall; if everything is exhausted it suggests
  a reboot — both only as suggestions.
- **Two maintenance modes** (tray + CLI `auto-maintain`):
  - **Safe** — queue maintenance, wait until the *entire* Codex process tree is truly idle
    (CPU + DB), then close Codex cleanly, maintain, restart. Never interrupts a running automation.
  - **Fast** — close immediately, then maintain.
- **Store tools** — repair a stuck Microsoft-Store update (`wsreset` / re-register / reset) and a
  one-click "reinstall Codex from the Store".
- **Conservative DB maintenance** — backup (incl. `-wal`/`-shm`), SQLite integrity check on the
  backup, `wal_checkpoint(TRUNCATE)`, `PRAGMA optimize`, `VACUUM`. Refuses to run while Codex is
  running. Limited backup retention.
- **Status window with progress bar** — opens for every manual action, is closable (work keeps
  running in the background), and re-opens from the tray. Plus a live tooltip.
- **Audit log** — every watcher tick is recorded in `logs/watchdog.log`, so it is never ambiguous
  whether the watcher touched anything.
- Dual detection of Codex (Standalone **and** Microsoft-Store), single-instance guard, no console
  window flashes.

## Screenshot

The tray's status window shows the current state, a 🧟 leftovers-cleared counter, a progress bar,
and one-click buttons (Repair Codex, Diagnose, Safe/Fast maintenance, Store tools). A screenshot
will be added here (`README/screenshots/main.png`).

## Requirements

- Windows 10/11
- Python 3.10+ (for running from source) — packaged EXE has no Python requirement
- [PySide6](https://pypi.org/project/PySide6/) (LGPL) for the tray GUI

## Install / Run

From source:

```powershell
$env:PYTHONPATH="$PWD\src"
pip install -r requirements.txt
python -m codex_logdatenbank_wartung.cli status
python -m codex_logdatenbank_wartung.cli tray      # start the tray app
```

Build a standalone EXE (PyInstaller):

```powershell
build_exe.bat
```

## Usage (CLI)

```powershell
python -m codex_logdatenbank_wartung.cli doctor                 # diagnose start problems (read-only)
python -m codex_logdatenbank_wartung.cli repair --dry-run       # plan the full start repair
python -m codex_logdatenbank_wartung.cli repair --execute       # run it (needs admin for AppX steps)
python -m codex_logdatenbank_wartung.cli dry-run                # DB maintenance preview
python -m codex_logdatenbank_wartung.cli maintain --execute     # DB maintenance (blocks if Codex runs)
python -m codex_logdatenbank_wartung.cli auto-maintain --mode safe --execute
python -m codex_logdatenbank_wartung.cli store-repair --level repair --execute
python -m codex_logdatenbank_wartung.cli store-materials        # check project-local Store materials
python -m codex_logdatenbank_wartung.cli schedule install --interval-minutes 180
```

## Windows Store path

The project now carries its own Windows Store groundwork:

- `PORTIERUNGSPLAN.md` documents why **Windows Store** is the only active platform track.
- `store_package.json`, `STORE_LISTING.md`, `PRIVACY_POLICY.md`, and `SUPPORT.md` hold the
  project-local Store materials.
- `python -m codex_logdatenbank_wartung.cli store-materials` validates those materials and can
  optionally check a built `CareCenterForCodex.exe` via `--exe-path`.

## Configuration

Configuration, logs and backups live in a local folder outside any cloud-synced directory
(default `C:\_Local_DEV\codex-maintenance`, configurable in `config.json`). Codex paths are
auto-detected from `%LOCALAPPDATA%` / `%APPDATA%` / `~/.codex` and can be overridden.

```text
config:   <data-dir>\config.json
logs:     <data-dir>\logs\
backups:  <data-dir>\backups\
database: ~\.codex\logs_2.sqlite   (override via CODEX_HOME or config)
```

## Safety

- The conservative `maintain` path and the optional scheduled task **never** close Codex; they
  block while Codex runs. Only the explicitly triggered `auto-maintain` (or tray "Safe/Fast") may
  close Codex — in Safe mode only when no automation is active.
- The watcher kills **only** an inactive ghost (no window, idle, older than a threshold) — proven
  by a CPU activity gate ("no window" ≠ idle) — and never the Codex CLI.

---

## Deutsch (Kurzfassung)

**CareCenter for Codex** ist ein lokales Windows-Tray- und CLI-Werkzeug für die OpenAI-Codex-Desktop-App:

- **Hintergrund-Wächter (Start-Prävention):** entfernt bei geschlossenem Codex hängende Reste
  (Ghost ohne Fenster / verwaistes Lockfile), damit der nächste Start sauber ist — nie eine aktive
  Sitzung, nie die Codex-CLI, nie einen noch arbeitenden Prozessbaum (CPU-Gate). 🧟-Zähler im Tray.
- **Ein „Codex reparieren"** als Eskalation (Stopp bei Erfolg): erst leicht & ohne Admin
  (Reste entfernen → starten → Fenster prüfen), nur wenn nötig elevated weiter; bei fehlendem
  Paket Reinstall-Vorschlag, bei Erschöpfung Reboot-Vorschlag.
- **Wartung Safe/Fast**, **Store-Reparatur/-Neuinstallation**, **konservative DB-Wartung**
  (Backup → Integrität → WAL-Checkpoint → optimize → VACUUM; blockiert bei laufendem Codex).
- **Status-Fenster mit Fortschrittsbalken** (öffnet bei jeder manuellen Aktion, schließbar, läuft
  im Hintergrund weiter), Live-Tooltip, **Audit-Log** (`logs/watchdog.log`).

Konfiguration/Logs/Backups liegen lokal (Standard `C:\_Local_DEV\codex-maintenance`, konfigurierbar).
Codex-Pfade werden automatisch über `%LOCALAPPDATA%`/`%APPDATA%`/`~/.codex` erkannt.

## License

[MIT](LICENSE) for this tool's own code. PySide6 is used under the LGPL; see
[`THIRD_PARTY_LICENSES.txt`](THIRD_PARTY_LICENSES.txt). *"OpenAI"* and *"Codex"* are trademarks of
OpenAI and are used here for compatibility/identification purposes only.
