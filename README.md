<img src="assets/banner.svg" width="100%" alt="CareCenter for Codex — Keep your Codex app healthy" />

# CareCenter for Codex

> Unofficial Windows tray & CLI utility that keeps the OpenAI Codex desktop app healthy — repairs failed starts, removes hung leftovers, and safely maintains the local SQLite log database. Fully offline, no telemetry.

[![CareCenter tests](https://github.com/dev-bricks/CareCenter-for-Codex/actions/workflows/tests.yml/badge.svg)](https://github.com/dev-bricks/CareCenter-for-Codex/actions/workflows/tests.yml)
[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)](https://github.com/dev-bricks/CareCenter-for-Codex)

German documentation: [README.de.md](README.de.md)

> [!IMPORTANT]
> This is an independent community tool. It is not created by, affiliated with, endorsed by, or sponsored by OpenAI. "OpenAI" and "Codex" are trademarks of OpenAI and are used here only to describe compatibility.

## Why

On Windows, closing the Codex desktop window can leave a hung main process behind. That leftover process can hold the app singleton lock, so the next start appears to do nothing. CareCenter removes that first blocker safely: it only touches inactive ghost processes, stale lock files, and explicitly requested maintenance paths.

## Features

- Background watcher: checks every 60 seconds for old start blockers and duplicate runtime MCP process generations. Runtime cleanup is fail-closed: it only targets idle launcher trees repeated under the same Store desktop app-server, always keeps the newest launch cohort, and never touches the app-server itself or the node-based Codex CLI.
- Tray settings with language switching: choose English or German in the Settings area. The choice is saved in `config.json` and the visible tray UI is relabeled immediately.
- Tray automation controls: pause all currently active Codex automations, restore only automations disabled by CCC, or turn automations back on immediately or gradually. The spacing is configurable via `automation_stagger_delay_seconds` (default: 60 seconds).
- Thread inbox hygiene: mark every result as read, mark only unread threads older than a configurable number of days, and automatically archive threads older than a separate configurable age. Current Codex thread ages and archive flags come from `state_5.sqlite`; unread IDs come from `.codex-global-state.json`. Changes run only while Codex is closed, with database/state backups, atomic JSON writes, and transactional archive updates.
- Config audit cleanup has three independent `off` / `notify` / `auto` controls for duplicate MCP configuration entries, Windows-incompatible plugins, and empty threads. The manual audit additionally runs the conservative runtime MCP reaper even while the desktop renderer is present; configuration and thread mutations remain deferred until Codex is closed.
- Loop mode: choose 2, 3, 5, 7, 10, 12, or 24 hours. Each regular due cycle starts with Fast maintenance and retries Codex close failures up to three times by default. If closing still fails, Safe becomes an extended catch-up attempt and the normal loop timer starts over; if Safe finishes before that timer expires, the timer starts again from the successful maintenance plus verified Codex restart. If the timer expires while Safe is still waiting, Safe is cancelled and the next regular Fast cycle starts. Automations are paused only after maintenance has succeeded, and only those paused automations are restored in 60-second windows.
- Direct tray starts: "Codex safe starten" launches Safe Start for Codex in its own tray and reuses its `config.json`; if that config is missing, CareCenter uses a 1-minute interval for that launch. If Safe Start is already gating, the second safe-start click is a no-op. "Codex starten" starts Codex normally without the Safe Start gate; while Safe Start is active, CareCenter only restores the automations paused by Safe Start and does not open another Codex window.
- One-click Repair Codex action: runs a bounded escalation that stops as soon as Codex starts again. It begins with no-admin cleanup and only suggests admin restart, Store reinstall, or reboot when needed.
- Current Store-process compatibility: recognizes both legacy `Codex.exe` Electron trees and newer `ChatGPT.exe`-named Codex Store trees, including their embedded app-server, without confusing CareCenter itself with Codex.
- Safe and Fast maintenance modes:
  - Safe waits until the complete Codex process tree is idle, can be cancelled while waiting, closes Codex cleanly, runs maintenance, and restarts it.
  - Fast closes Codex immediately and then runs maintenance.
- Store tools: repair a stuck Microsoft Store update path and open the Store reinstall page for Codex.
- Conservative database maintenance: backup including WAL/SHM, integrity check on the backup, WAL checkpoint, `PRAGMA optimize`, `VACUUM`, and limited backup retention.
- Status window with progress bar, live tray tooltip, and persistent audit logs.
- Safe Start for Codex is shipped as a dependency and can be installed or updated from the CareCenter window, tray, or CLI. CareCenter uses it for release bursts, start storms, and catch-up hints.

## Screenshot

The tray status window shows current state, removed-leftover count, progress, maintenance controls with Safe cancellation, Loop mode, Store actions, Safe Start actions, automation controls, and settings.

![CareCenter status window](README/screenshots/main.png)

Regenerate the screenshot from the real PySide6 status window:

```powershell
$env:PYTHONPATH="src"
python -m codex_logdatenbank_wartung.cli store-screenshot
```

## Requirements

- Windows 10 or Windows 11
- Python 3.12+ when running from source
- [PySide6](https://pypi.org/project/PySide6/) for the tray UI

Packaged EXE builds do not require a separate Python installation.

## Install and Run

From source:

```powershell
$env:PYTHONPATH="$PWD\src"
pip install -r requirements.txt
python -m codex_logdatenbank_wartung.cli status
python -m codex_logdatenbank_wartung.cli tray
```

For the normal tray start from a checkout, use `start.bat`. It launches the tray
windowlessly through `pythonw.exe` and writes startup failures to
`%LOCALAPPDATA%\CareCenterForCodex\logs\app.log`. Use `debug.bat` when you want
the console to stay visible for troubleshooting.

Build a standalone EXE:

```powershell
build_exe.bat
```

By default, the build uses the public Safe Start GitHub source pinned to an exact
commit in `pyproject.toml`. This keeps the build reproducible without silently
bundling a dirty local sibling checkout. Only use a local Safe Start source on
purpose:

```powershell
$env:CARECENTER_SAFE_START_SOURCE = "C:\path\to\REL-PUB_safe-start-for-codex"
build_exe.bat
```

## CLI

```powershell
python -m codex_logdatenbank_wartung.cli doctor
python -m codex_logdatenbank_wartung.cli repair --dry-run
python -m codex_logdatenbank_wartung.cli repair --execute
python -m codex_logdatenbank_wartung.cli dry-run
python -m codex_logdatenbank_wartung.cli maintain --execute
python -m codex_logdatenbank_wartung.cli auto-maintain --mode safe --execute
python -m codex_logdatenbank_wartung.cli fast-loop-cycle --execute
python -m codex_logdatenbank_wartung.cli mark-runs-read --dry-run
python -m codex_logdatenbank_wartung.cli mark-runs-read --older-than-days 2
python -m codex_logdatenbank_wartung.cli mark-runs-read --older-than-days 2 --archive-older-than-days 10
python -m codex_logdatenbank_wartung.cli store-repair --level repair --execute
python -m codex_logdatenbank_wartung.cli store-materials
python -m codex_logdatenbank_wartung.cli safe-start-report
python -m codex_logdatenbank_wartung.cli safe-start-install
python -m codex_logdatenbank_wartung.cli schedule install --interval-minutes 180
```

The CLI reads `language` from `config.json` for runtime reports. The tray settings are the intended way to switch the persisted language.

In the tray settings, `0` disables an age rule. Set `auto_mark_threads_read_days` and
`auto_archive_threads_days` to independent values such as `2` and `10`. CareCenter applies
the rules during background watcher ticks as soon as Codex is fully closed.

## Configuration

Configuration, logs, and backups live outside cloud-synced folders by default:

```text
config:   %LOCALAPPDATA%\CareCenterForCodex\config.json
logs:     %LOCALAPPDATA%\CareCenterForCodex\logs\
backups:  %LOCALAPPDATA%\CareCenterForCodex\backups\
database: %USERPROFILE%\.codex\logs_2.sqlite
```

Codex paths are detected from `%LOCALAPPDATA%`, `%APPDATA%`, and `CODEX_HOME`. New installs also place CareCenter data under `%LOCALAPPDATA%\CareCenterForCodex` by default. Existing local setups under `C:\_Local_DEV\codex-maintenance\` are reused automatically as a legacy fallback. You can override every path in `config.json`.

Runtime MCP cleanup is enabled by default through `reap_runtime_mcp_duplicates`.
Its conservative defaults are a configurable 3600-second (one-hour) minimum age for
every candidate root, a 90-second launch-cohort
gap, a 30-second launcher window, at least two distinct repeated MCP signatures,
and a 1-second CPU activity sample. Each threshold can be overridden in `config.json`.

To use a different data root (useful in tests or alternative installations), set `CCC_DATA_ROOT` before launching:

```powershell
$env:CCC_DATA_ROOT = "D:\my-codex-maintenance"
python -m codex_logdatenbank_wartung.cli tray
```

When set, `config.json`, `logs\`, and `backups\` are placed under that path instead of the default `%LOCALAPPDATA%\CareCenterForCodex\`.

## Safety Model

- Conservative maintenance blocks while Codex is running.
- Scheduled maintenance never closes Codex.
- Safe auto-maintain only closes Codex after the full process tree is idle.
- Safe cancellation stops only the waiting phase before Codex is closed; active database operations are not force-interrupted.
- The watcher kills inactive ghosts without a renderer only after the configured age threshold.
- Duplicate runtime MCP cleanup always keeps the newest launch cohort and skips candidate trees whose CPU counters still advance.
- The Codex desktop app-server, unrelated child processes, the Codex CLI, and active desktop work are explicitly excluded.
- Destructive paths such as Store reset, admin repair, reinstall, and reboot are suggestions or explicit user actions, not automatic surprises.

## Windows Store Materials

The project includes Windows Store groundwork:

- `store_package.json`
- `STORE_LISTING.md`
- `PRIVACY_POLICY.md`
- `SUPPORT.md`
- `docs/privacy.md`
- `docs/support.md`

Planned public Store targets:

- Privacy: `https://dev-bricks.github.io/CareCenter-for-Codex/privacy`
- Support: `https://dev-bricks.github.io/CareCenter-for-Codex/support`

Validate them with:

```powershell
python -m codex_logdatenbank_wartung.cli store-materials
python -m codex_logdatenbank_wartung.cli store-materials --exe-path C:\_Local_DEV\codex-maintenance\bin
```

Without `--exe-path`, the check tries to discover the built EXE automatically from `build_exe.bat` (`DIST_DIR`). With `--exe-path`, you can pass either the exact `.exe` file or just the build directory.

The Store privacy/support URLs are prepared for GitHub Pages. `store-materials` also runs a temporary static Pages build and verifies `privacy/index.html`, `support/index.html`, `index.html`, and the build marker. You can still build the artifact explicitly with:

```powershell
python scripts\build_store_pages.py --output _site
```

The workflow `.github/workflows/pages.yml` publishes the generated `/privacy/` and `/support/` routes after GitHub Pages is configured to use GitHub Actions for this repository.

## Development

```powershell
$env:PYTHONPATH="src"
python -m pytest
python -m ruff check src tests
python -m compileall src tests
```

The test suite covers maintenance safety, repair escalation, Safe Start integration, automation control, Store material validation, configuration loading, i18n, and tray language persistence.

## License

CareCenter for Codex is licensed under [MIT](LICENSE). PySide6 is used under the LGPL; see [THIRD_PARTY_LICENSES.txt](THIRD_PARTY_LICENSES.txt).
