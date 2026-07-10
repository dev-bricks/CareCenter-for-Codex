# Changelog

## Unreleased

- Restored compatibility with Codex Store builds that use `ChatGPT.exe` for the
  Electron process tree and an embedded `codex.exe app-server`. CareCenter now
  detects the real renderer, never classifies the app-server as a zombie main
  process, and no longer reports its own `codex-maintenance` path as Codex.
- Fixed manual config-audit feedback: auto-fixes are followed by a fresh audit,
  while fixes deferred because Codex is still running are clearly reported and
  remain queued for the next closed-state watchdog cycle.
- Added Fast maintenance loop mode with 2/3/5/7/10/12/24-hour intervals: each cycle runs
  Fast maintenance, pauses currently active Codex automations, restarts Codex even if it
  was not running at cycle start, then restores only those paused automations in 60-second
  windows. If Codex cannot be closed fully, the loop retries the close/maintenance attempt;
  after exhausted close retries it switches to Safe catch-up and resets the regular timer.
  If Safe succeeds before the next regular interval, the timer resets again after successful
  maintenance plus verified restart; if that interval expires first, Safe is cancelled and
  the next Fast cycle starts. Automations are paused only after maintenance has succeeded.
- Broadened "mark automation runs read" so it clears all matching unread thread/chat/
  conversation Atom states instead of only `unread-thread-ids-by-host-v1`.
- Fixed empty-message detection in the config audit: whitespace-only first messages and
  empty JSON payloads in message tables are now detected read-only.
- Added schema-aware log archiving: `archive_old_logs` now detects timestamp columns via
  `PRAGMA table_info`, writes rows to per-table JSONL files before deletion (write-then-delete,
  no data loss on failure), commits per table, and supports dry-run and idempotent re-runs.
  New `archive_dir` config field, 7 new i18n keys, 17 regression tests.
- Moved the default CareCenter data root to `%LOCALAPPDATA%\CareCenterForCodex` for
  new installations, while automatically reusing existing legacy data under
  `C:\_Local_DEV\codex-maintenance`.
- Removed the last hardcoded tray startup error log path and aligned CLI defaults
  for `--config` and `schedule --script-path` with the dynamic data root.
- Extended `store-materials` so it auto-detects the built EXE from `build_exe.bat`
  (`DIST_DIR`) and also accepts a build directory via `--exe-path`.
- Added tray entries for starting Codex normally and starting it through Safe Start for Codex.
- Made CareCenter's staggered automation reactivation delay configurable via
  `automation_stagger_delay_seconds` (default: 60 seconds).
- Safe Start launches from CareCenter now reuse the Safe Start config when present and fall back
  to a one-minute release interval when no Safe Start config exists.
- Fixed the direct tray start guards: pressing "Codex safe starten" while Safe Start is already
  gating is now a no-op, and pressing "Codex starten" during an active Safe Start restores the
  automations paused by Safe Start without opening another Codex window.
- Added a shared busy guard for mutating tray actions so direct Codex starts, Safe Start install,
  Codex repair, Store repair, and full repair cannot be triggered while another CareCenter action
  is already running.
- Added a tray automation control submenu for pausing all active Codex automations, restoring only CCC-paused automations, and immediately or gradually activating all automations.
- Added published `docs/privacy.md` and `docs/support.md` pages plus Store metadata for the planned GitHub Pages privacy/support URLs.
- Extended the Store material preflight to warn when the published support/privacy pages are missing locally.
- Fixed tray running-state guards for start repair and Store repair actions, so concurrent tray operations stay blocked consistently.
- Fixed watchdog companion-orphan cleanup in both busy and disabled paths, with regression coverage for inactive companion process cleanup.
- Fixed config-audit backup names to include microseconds, preventing same-second backup filename collisions.
- Applied Ruff import-format cleanup in `config.py`.

## 0.8.0 - 2026-06-06

- Added cancellable Safe maintenance: the tray exposes an abort button while Safe mode is waiting for Codex idle, and the CLI handles Ctrl+C without a traceback.
- Added Safe Start install/update support via tray button and CLI command `safe-start-install`.
- Shipped Safe Start as a runtime dependency and added a PyInstaller hidden import so EXE builds bundle the dynamic integration module.
- Regenerated the README screenshot as widget-only German UI text without emoji or native title-bar glyphs.
- Completed English/German i18n for the tray-facing CareCenter UI and maintenance runtime reports.
- Added a language selector to the tray Settings area. The selected language is saved in `config.json` and visible UI labels update immediately.
- Localized key CLI runtime output through the existing configuration-driven language path.
- Split documentation into English `README.md` and German `README.de.md`.
- Added regression tests for language helpers, CLI language loading, and tray language persistence/retranslation.

## 0.7.2 - 2026-06-05

- Fixed the reproducible README/Store screenshot so it renders the normal status window with
  readable text and captures the native title bar on Windows.

## 0.7.1 - 2026-06-05

- Fixed Safe Start snapshot fallback typing so the new adapter passes isolated Mypy checks.
- Cleaned the new Safe Start status text path to keep German umlauts intact.

## 0.7.0 - 2026-06-04

- Added optional Safe Start for Codex integration: CareCenter can now read Safe Start snapshots,
  detect release bursts/start storms, and show rare catch-up candidates.
- Added CLI command `safe-start-report` with text and JSON output.
- The tray now includes "Safe Start prüfen" and shows Safe Start status in the existing status window.
- The background watcher defers its own start-counteractions while Safe Start is actively gating or
  releasing automations, so both tools do not work against each other.
- Added Safe Start config fields to CareCenter for catch-up lookback, catch-up limits, and storm thresholds.

## 0.6.3 - 2026-06-03

- Removed the dead legacy config flag `watcher_terminate_user_starts`, which was still loaded and
  written back although no runtime path consumed it.
- Added a regression test for config roundtrips so legacy watcher flags are dropped instead of being
  re-emitted into `config.json`.

## 0.6.2 - 2026-06-03

- Added a Windows GitHub Actions workflow for Python 3.12 and 3.13.
- Added `llms.txt` with machine-readable project context, safety boundaries, and verification commands.
- Synchronized package metadata with the current release line and documented the 179-test local verification path.
- Declared `tomlkit` as a runtime dependency and made the live repair runner injectable for hermetic CI tests.

## 0.6.1 - 2026-06-01

- Added a project-local **Windows Store groundwork** path: new `PORTIERUNGSPLAN.md`,
  `store_package.json`, `STORE_LISTING.md`, `PRIVACY_POLICY.md`, and `SUPPORT.md`.
- Added `store_release.py` plus CLI command
  `python -m codex_logdatenbank_wartung.cli store-materials` to validate Store
  materials, expected EXE naming, and missing public URLs before MSIX/WACK work.
- Added regression tests for Store material validation (`tests/test_store_release.py`)
  and CLI coverage for the new command.

## 0.6.0 - 2026-05-30

- **Renamed to "CareCenter for Codex"** (brand-first; "Codex" used only as a nominative
  compatibility reference). EXE `CareCenterForCodex.exe`. Internal Python package name unchanged.
- **Background start-prevention watcher** (`watchdog.py`): every 60 s, read-only; removes hung
  leftovers (ghost without a window / stale lockfile) only when Codex is closed, then notifies.
  **Critical safety:** a CPU activity gate (`observe_activity`) ensures a still-working background
  Codex tree is never killed ("no window" != idle); never kills an active session or the node CLI.
  Per-tick audit log in `logs/watchdog.log`. Tray toggle plus removed-remnants counter.
- **One unified "Repair Codex"** escalation (tray): light no-admin step first (remove leftovers →
  launch → check window), escalates to the elevated full repair only if needed, stops on success;
  absent package → Store-reinstall suggestion, exhausted → reboot suggestion.
- **Full hang-safe start repair** (`repair_workflow.py` / `repair_live.py`, CLI `repair`): S1–S7
  escalation with a hard "no deploy-op may hang" rule. New: detection of a **completely absent**
  Store package (P11) → honest stop with a reinstall suggestion instead of a useless reboot hint;
  persistent repair logs; removal-prevention (no `Remove -AllUsers` that could orphan the package).
- **Store reinstall** action (opens the verified OpenAI Codex product page) + `store-repair`.
- **Status window** opens for all manual actions, closable (work continues), re-openable.
- Codex paths now resolved from `%LOCALAPPDATA%`/`%APPDATA%`/`~/.codex` (no hardcoded user paths).
- 103 tests green. First public release.

## 0.5.0 - 2026-05-29

- Neu: `store_repair.py` — Microsoft-Store-Reparatur für Codex in drei Stufen: `wsreset`
  (Store-Cache leeren), `repair` (Appx-Paket via `Add-AppxPackage -Register` neu registrieren,
  nicht-destruktiv), `reset` (`Reset-AppxPackage`, opt-in; `~/.codex` bleibt erhalten).
  Hintergrund: Codex-Desktop wird ausschließlich über den Store verteilt/aktualisiert (offiziell
  bestätigt); der Store hängt gelegentlich bei Updates und blockiert dann den Start.
- Neu: CLI `store-repair --level wsreset|repair|reset [--execute] [--status]`.
- Neu: Tray „Store-Update reparieren (Cache + Paket)" (wsreset + repair, nicht-destruktiv).
- **Dual-Pfad-Codex-Erkennung:** Tool erkennt jetzt sowohl die Standalone-Kopie als auch die
  Microsoft-Store-Version (`codex_store_marker`, stabiler `\WindowsApps\OpenAI.Codex`-Marker;
  versionsunabhängig) — so funktionieren Diagnose/Reparatur/auto-maintain unabhängig davon,
  welche Codex-Variante läuft (wichtig fürs Zurück-Wechseln auf die auto-updatende Store-Version).
- Tests: `test_store_repair.py` (5) + Store-Pfad-Erkennung in `test_processes.py`; 36 Tests grün.
- Befund dokumentiert: Standalone unter `AppData\Local\Programs\Codex` ist eine byte-identische
  Kopie der Store-App (Geminis „Entkopplung" gegen einen hängenden Store-Update) ohne eigenen
  Updater — Updates kommen ausschließlich über den Store.

## 0.4.0 - 2026-05-29

- Neu: `orchestrator.py` — autonome Wartung mit zwei Modi (ein Tray):
  - **Safe:** Wartung wird eingereiht; wartet bis der GANZE Codex-Prozessbaum im Leerlauf ist
    (CPU < Schwelle UND DB ruhig — erfasst auch Worker-Kinder wie python/git/node), beendet dann
    Codex kontrolliert vollständig, wartet, danach Codex-Neustart. **Nie** Eingriff während Aktivität.
  - **Fast:** sofort beenden + Wartung ohne Warten.
- Neu: CLI `auto-maintain --mode safe|fast [--execute]`.
- Neu: Tray-**Status-Fenster mit Fortschrittsbalken** (Klick aufs Tray-Symbol) + **Live-Tooltip**
  („Wartung eingereiht — warte auf Codex-Leerlauf … / VACUUM … %"). Hintergrund: Windows-Toasts
  einer nicht im Startmenü registrierten App werden oft unterdrückt → zuverlässige Kanäle: Fenster + Tooltip.
- Aktivitätserkennung **empirisch kalibriert** (2026-05-29): aktive Automatisierung 25–500 % eines Kerns,
  Leerlauf-Rest <2 % → Schwelle `idle_cpu_percent=10`. `ProcessInfo.cpu_ticks` ergänzt; CPU-Stichprobe
  über zwei Snapshots des ganzen Baums.
- Sicherheit: Safe-Modus bricht **niemals** einen laufenden Lauf ab (empirisch bestätigt: Codex
  killt beim Schließen laufende Automatisierungen → daher erst bei echtem Leerlauf handeln).
  `auto_close_codex` ist nur für unbeaufsichtigte Pfade relevant und bleibt **default AUS**; der
  geplante Task nutzt weiterhin nur den konservativen `maintain`-Pfad (kein Auto-Close).
- Fortschritts-Callback im Wartungskern (`maintenance.py`): byte-genaue Backup-Kopie, Phasen-Prozente,
  VACUUM als „läuft …".
- Tests: `test_orchestrator.py` (9) — Modi, Idle-Warten, Timeout-ohne-Kill, Dry-Run, „blocked wenn
  Schließen nicht erlaubt", CPU-Erkennung inkl. Worker-Kind; alle 30 Tests grün.
- **No-Window:** alle Subprozesse (PowerShell-Provider, `taskkill`, `schtasks`, Codex-Launcher) laufen
  mit `CREATE_NO_WINDOW` → kein Aufblitzen von Konsolenfenstern aus der windowed Tray-EXE.
- **Echtes `auto_close_codex`-Gate:** `auto-maintain` schließt Codex nur bei expliziter Zustimmung
  (Tray-Klick / CLI `--close`) oder `auto_close_codex=True`; sonst blockiert es bei laufendem Codex,
  statt ungefragt zu beenden. (Korrigiert einen vorher wirkungslosen Flag-Claim.)
- **Neustart-Verifikation:** nach dem Codex-Neustart wird auf einen `--type=renderer` gewartet
  (`restart_verify_seconds`); sonst Warnung statt falscher Erfolgsmeldung.
- **Explizites Ende-Signal:** Tray-Leuchtpunkt (Icon-Wechsel) bei Abschluss + Toast „… — fertig" +
  eigene AppUserModelID, damit Windows-Benachrichtigungen zuverlässiger erscheinen. Reset beim Klick.
- Entfernt: totes Konfig-Feld `auto_close_codex_unattended`.

## 0.3.0 - 2026-05-29

- Neu: `scheduler.py` als optionaler Windows-Task-Scheduler-Helfer für periodische Wartung.
- Neu: CLI-Befehl `schedule install|status|remove`.
- Neu: `run-maintenance.cmd` wird reproduzierbar unter `C:\_Local_DEV\codex-maintenance` erzeugt
  und ruft `maintain --execute --trigger scheduled-task` auf.
- Tests ergänzt: `test_scheduler.py` prüft Install-, Status- und Remove-Pfade ohne echte
  `schtasks`-Änderungen.

## 0.2.0 - 2026-05-29

- Neu: Startup-Diagnose und gezielte Reparatur (`health.py`) — getrennt vom konservativen Wartungskern.
- Neu: CLI-Befehle `doctor` (read-only Startdiagnose) und `repair-start [--execute]`.
- Neu: Tray-Menü „Codex-Start prüfen (Diagnose)" und „Codex-Start reparieren".
- Zombie-Erkennung: Codex-Hauptprozess (Browser, kein `--type`) ohne Renderer im Prozessbaum
  und älter als `zombie_min_age_seconds` gilt als hängend und blockiert den Neustart.
- Sicherheitsgarantie: Reparatur beendet ausschließlich Zombies; aktive Sitzungen (mit Renderer)
  werden nie beendet. Präzises Kill-Targeting über den EXAKTEN Exe-Pfad + Prozessbaum (`/T`),
  nicht über Substrings.
- Erkennung verwaister Electron-Lockfiles (`AppData\Roaming\Codex\lockfile`) ohne laufenden Hauptprozess.
- Health-Schwellwerte: WAL-/DB-Aufblähung, freier Speicher, `.badstate`-Dateien.
- Update-Health: erkennt fehlende `Codex.exe` (Symptom eines fehlgeschlagenen Updates → Startblockade)
  und Update-Reste (`*.dead`, `pending`, `*.nupkg`, …) im Codex-Installations-/Profilpfad.
- Wartung: zusätzlicher `PRAGMA wal_checkpoint(TRUNCATE)`-Schritt gegen WAL-Aufblähung.
- Wartung: Backup-Retention (`backup_keep`, Default 3) gegen unbegrenztes Backup-Wachstum.
- `processes.py`: `ProcessInfo` um `parent_pid`/`created_at` erweitert; Klassifikation (`process_type`),
  exaktes Exe-Matching und Prozessbaum-Funktionen ergänzt.
- Tests ergänzt: `test_processes.py`, `test_health.py` (mit injiziertem Killer, keine echten Kills).

## 0.1.0 - 2026-05-26

- Erstes MVP für lokale Codex-Logdatenbank-Wartung.
- CLI mit `status`, `dry-run`, `maintain --execute`, `init-config` und `tray`.
- PySide6-Systemtray-App mit Single-Instance-Guard.
- Backup, Integritätscheck und `VACUUM` erst nach erfolgreicher Sicherheitsprüfung.
- PyInstaller-Build-Skript ergänzt; erste EXE lokal unter `C:\_Local_DEV\codex-maintenance\bin` gebaut.
- EXE-Startfehler behoben: direkter Tray-Einstieg nutzt jetzt absolute Imports und schreibt künftige Startup-Fehler nach `C:\_Local_DEV\codex-maintenance\logs`.
