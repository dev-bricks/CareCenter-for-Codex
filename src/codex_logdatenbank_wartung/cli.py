"""CLI-Einstieg für die Codex-Logdatenbank-Wartung."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Protocol

from .config import MaintenanceConfig, default_config_path, local_root
from .i18n import normalize_language, set_language, t
from .maintenance import MaintenanceRunner
from .processes import describe_processes, find_codex_processes


class _RepairLogResult(Protocol):
    def to_dict(self) -> dict[str, object]: ...

    def to_text(self) -> str: ...


def load_config(args: argparse.Namespace) -> MaintenanceConfig:
    return MaintenanceConfig.load(Path(args.config))


def cmd_init_config(args: argparse.Namespace) -> int:
    path = Path(args.config)
    if path.exists() and not args.force:
        print(t("config_exists", path=path))
        return 0
    config = MaintenanceConfig()
    config.save(path)
    print(t("config_written", path=path))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    config = load_config(args)
    db_path = config.db_path
    print(t("cli_config", path=Path(args.config)))
    print(t("cli_database", path=db_path))
    print(t("cli_database_exists", exists=db_path.exists()))
    processes = find_codex_processes(config)
    if processes:
        print(t("cli_codex_running"))
        print(describe_processes(processes))
        return 2
    print(t("cli_no_codex_processes"))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config(args)
    dry_run = not args.execute
    result = MaintenanceRunner(config).run(dry_run=dry_run, trigger=args.trigger)
    print(result.to_text())
    if dry_run and result.status == "blocked":
        return 0
    return {"ok": 0, "dry-run": 0, "blocked": 2, "failed": 1}[result.status]


def cmd_doctor(args: argparse.Namespace) -> int:
    from .health import diagnose

    config = load_config(args)
    report = diagnose(config)
    print(report.to_text())
    return 0 if report.status == "ok" else 2


def cmd_repair_start(args: argparse.Namespace) -> int:
    from .health import repair_start

    config = load_config(args)
    result = repair_start(
        config, execute=args.execute, trigger=args.trigger, write_log=args.execute
    )
    print(result.to_text())
    return {
        "dry-run": 0,
        "nothing-to-do": 0,
        "repaired": 0,
        "ok": 0,
        "failed": 1,
    }.get(result.status, 0)


def cmd_auto_maintain(args: argparse.Namespace) -> int:
    from .orchestrator import auto_maintain

    config = load_config(args)
    try:
        result = auto_maintain(
            config,
            mode=args.mode,
            execute=args.execute,
            allow_close=True if args.close else None,
        )
    except KeyboardInterrupt:
        print(t("auto_cancelled_short"))
        return 130
    print(result.to_text())
    return {"ok": 0, "dry-run": 0, "blocked": 2, "cancelled": 130, "failed": 1}.get(
        result.status, 0
    )


def cmd_fast_loop_cycle(args: argparse.Namespace) -> int:
    from .orchestrator import fast_maintenance_loop_cycle

    config = load_config(args)
    try:
        result = fast_maintenance_loop_cycle(
            config,
            execute=args.execute,
            interval_hours=args.interval_hours,
        )
    except KeyboardInterrupt:
        print(t("auto_cancelled_short"))
        return 130
    print(result.to_text())
    return {
        "ok": 0,
        "dry-run": 0,
        "partial": 2,
        "blocked": 2,
        "cancelled": 130,
        "failed": 1,
    }.get(result.status, 1)


def cmd_store_repair(args: argparse.Namespace) -> int:
    from .store_repair import repair_store_codex, store_package_status

    if args.status:
        print(store_package_status())
        return 0
    result = repair_store_codex(level=args.level, execute=args.execute)
    print(result.to_text())
    return {"ok": 0, "dry-run": 0, "failed": 1}.get(result.status, 0)


def cmd_store_materials(args: argparse.Namespace) -> int:
    from .store_release import validate_store_materials

    exe_path = Path(args.exe_path) if args.exe_path else None
    report = validate_store_materials(project_root=Path(args.project_root), exe_path=exe_path)
    print(report.to_text())
    return {"ok": 0, "warning": 2, "failed": 1}[report.status]


def cmd_store_screenshot(args: argparse.Namespace) -> int:
    from .store_screenshot import render_store_screenshot

    output_path = render_store_screenshot(Path(args.output))
    print(t("cli_screenshot_written", path=output_path))
    return 0


def _persist_repair_log(config: MaintenanceConfig, result: _RepairLogResult) -> Path | None:
    """Schreibe das Reparatur-Ergebnis dauerhaft nach ``log_dir`` (JSON + Text).

    Blind-Spot-Fix (30.05): Der Tray-Volllauf schrieb bisher nur in eine temporaere
    ``--out``-Datei, die er danach loescht -- ein gescheiterter Lauf war damit spurlos.
    Hier wird zusaetzlich ein zeitgestempelter, persistenter Log abgelegt, analog zu
    ``maintain``/``repair-start``. Fehler beim Schreiben duerfen den Lauf nie kippen.
    """
    import json as _json
    from datetime import datetime

    try:
        logs = config.logs_path
        logs.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        json_path = logs / f"repair-{stamp}.json"
        text_path = logs / f"repair-{stamp}.txt"
        json_path.write_text(
            _json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        text_path.write_text(result.to_text(), encoding="utf-8")
        return text_path
    except OSError:
        return None


def cmd_repair(args: argparse.Namespace) -> int:
    """Begrenzte, hang-sichere Codex-Start-Reparatur (S1+S2+S3+1 Fallback, KEIN UAC).

    ``--dry-run`` (oder kein ``--execute``) plant nur und ruft KEIN mutierendes Dep auf.
    ``--execute`` fuehrt den echten Lauf aus -- mit den Rechten des aktuellen Prozesses;
    es wird NIE selbst elevated. Scheitert eine Deploy-Op an fehlenden Rechten, meldet das
    Ergebnis ``needs_admin`` (-> als Administrator neu starten), statt UAC auszuloesen.

    Mit ``--out`` wird das Ergebnis als JSON geschrieben. Laeuft ``progress`` (bei
    ``--execute``), wird jede Stufe sofort als eigene JSON-Zeile angehaengt (Live-Tailing);
    die letzte Zeile ist das vollstaendige ``RepairOutcome.to_dict()``.
    """
    import json as _json

    from .repair_live import run_live_repair

    config = load_config(args)
    dry_run = bool(args.dry_run) or not bool(args.execute)
    out_path = Path(args.out) if args.out else None

    # Out-Datei zu Beginn leeren, damit ein alter Stand nicht falsch getailt wird.
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("", encoding="utf-8")

    progress = None
    if out_path is not None and not dry_run:
        def progress(step: object) -> None:
            # Jede Stufe als eigene JSON-Zeile anhaengen (Live-Tailing durch den Tray).
            payload = step.to_dict() if hasattr(step, "to_dict") else {"step": str(step)}
            with out_path.open("a", encoding="utf-8") as handle:
                handle.write(_json.dumps(payload, ensure_ascii=False) + "\n")

    result = run_live_repair(config, execute=args.execute, dry_run=dry_run, progress=progress)

    if out_path is not None:
        # Letzte Zeile = vollstaendiges Ergebnis (eindeutiger Endmarker fuers Tailing).
        with out_path.open("a", encoding="utf-8") as handle:
            handle.write(_json.dumps(result.to_dict(), ensure_ascii=False) + "\n")

    # Echte Laeufe IMMER persistent protokollieren (nicht nur in die fluechtige --out-Datei).
    if args.execute and not dry_run:
        log_path = _persist_repair_log(config, result)
        if log_path is not None:
            print(t("cli_log", path=log_path))

    print(result.to_text())
    return {"ok": 0, "blocked": 2, "failed": 1}.get(result.status, 1)


def cmd_audit(args: argparse.Namespace) -> int:
    from .config_audit import run_full_audit

    config = load_config(args)
    report = run_full_audit(config)
    print(report.summary())
    return 1 if report.has_warnings else 0


def cmd_safe_start_report(args: argparse.Namespace) -> int:
    import json as _json

    from .safe_start_integration import build_safe_start_status

    config = load_config(args)
    status = build_safe_start_status(config)
    if args.json:
        print(_json.dumps(status.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(status.to_text())
    return 0


def cmd_safe_start_install(args: argparse.Namespace) -> int:
    import json as _json

    from .safe_start_integration import install_safe_start_package

    result = install_safe_start_package(target=args.target)
    if args.json:
        print(_json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(result.to_text())
    return 0 if result.status == "ok" else 1


def cmd_mark_runs_read(args: argparse.Namespace) -> int:
    from .mark_runs_read import mark_all_automation_runs_read

    config = load_config(args)
    result = mark_all_automation_runs_read(config, dry_run=args.dry_run)
    print(result.to_text())
    return {"ok": 0, "nothing": 0, "blocked": 2, "failed": 1}.get(result.status, 1)


def cmd_tray(args: argparse.Namespace) -> int:
    from .tray import run_tray

    return run_tray(Path(args.config))


def cmd_schedule_install(args: argparse.Namespace) -> int:
    from .scheduler import install_scheduled_task

    result = install_scheduled_task(
        interval_minutes=args.interval_minutes,
        task_name=args.task_name,
        script_path=Path(args.script_path),
        config_path=Path(args.config),
    )
    print(result.to_text())
    return 0


def cmd_schedule_remove(args: argparse.Namespace) -> int:
    from .scheduler import remove_scheduled_task

    result = remove_scheduled_task(
        task_name=args.task_name,
        script_path=Path(args.script_path),
    )
    print(result.to_text())
    return 0


def cmd_schedule_status(args: argparse.Namespace) -> int:
    from .scheduler import scheduled_task_status

    result = scheduled_task_status(
        task_name=args.task_name,
        script_path=Path(args.script_path),
    )
    print(result.to_text())
    return 0 if result.status == "installed" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-logwartung",
        description="Sichere Offline-Wartung der lokalen Codex-Logdatenbank.",
    )
    parser.add_argument(
        "--config",
        default=str(default_config_path()),
        help="Pfad zur lokalen Konfigurationsdatei.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-config", help="Standardkonfiguration anlegen.")
    init_parser.add_argument("--force", action="store_true", help="Vorhandene Konfiguration ersetzen.")
    init_parser.set_defaults(func=cmd_init_config)

    status_parser = subparsers.add_parser("status", help="Datenbank- und Prozessstatus prüfen.")
    status_parser.set_defaults(func=cmd_status)

    dry_parser = subparsers.add_parser("dry-run", help="Wartung ohne Änderungen durchspielen.")
    dry_parser.add_argument("--trigger", default="dry-run")
    dry_parser.set_defaults(func=cmd_run, execute=False)

    maintain_parser = subparsers.add_parser("maintain", help="Wartung ausführen oder simulieren.")
    maintain_parser.add_argument(
        "--execute",
        action="store_true",
        help="Echte Wartung starten. Ohne diese Option läuft nur ein Dry-Run.",
    )
    maintain_parser.add_argument("--trigger", default="cli")
    maintain_parser.set_defaults(func=cmd_run)

    doctor_parser = subparsers.add_parser(
        "doctor", help="Startprobleme diagnostizieren (read-only, keine Änderungen)."
    )
    doctor_parser.set_defaults(func=cmd_doctor)

    repair_parser = subparsers.add_parser(
        "repair-start",
        help="Startblockaden beheben: Zombie-Prozesse beenden, verwaistes Lockfile entfernen.",
    )
    repair_parser.add_argument(
        "--execute",
        action="store_true",
        help="Reparatur wirklich ausführen. Ohne diese Option nur Dry-Run.",
    )
    repair_parser.add_argument("--trigger", default="cli")
    repair_parser.set_defaults(func=cmd_repair_start)

    auto_parser = subparsers.add_parser(
        "auto-maintain",
        help="Autonome Wartung: auf Codex-Leerlauf warten (safe) oder sofort (fast), Codex schließen, warten, neu starten.",
    )
    auto_parser.add_argument(
        "--mode", choices=["safe", "fast"], default="safe",
        help="safe = auf Leerlauf warten (Standard); fast = sofort.",
    )
    auto_parser.add_argument(
        "--execute", action="store_true",
        help="Wirklich ausführen. Ohne diese Option nur Dry-Run.",
    )
    auto_parser.add_argument(
        "--close", action="store_true",
        help="Codex bei Bedarf schließen erlauben (sonst gilt config.auto_close_codex, default AUS).",
    )
    auto_parser.set_defaults(func=cmd_auto_maintain)

    fast_loop_parser = subparsers.add_parser(
        "fast-loop-cycle",
        help="Einen Loop-Zyklus ausführen: Fast-Wartung, aktive Automationen pausieren, Codex neu starten, gestaffelt reaktivieren.",
    )
    fast_loop_parser.add_argument(
        "--execute", action="store_true",
        help="Wirklich ausführen. Ohne diese Option nur Dry-Run.",
    )
    fast_loop_parser.add_argument(
        "--interval-hours",
        type=int,
        choices=[2, 3, 5, 7, 10, 12, 24],
        default=None,
        help="Dokumentiertes Loop-Intervall für Ausgabe/Planung.",
    )
    fast_loop_parser.set_defaults(func=cmd_fast_loop_cycle)

    store_parser = subparsers.add_parser(
        "store-repair",
        help="Microsoft-Store-Probleme für Codex beheben (Cache leeren, Paket reparieren/zurücksetzen).",
    )
    store_parser.add_argument(
        "--level", choices=["wsreset", "repair", "reset"], default="repair",
        help="wsreset = Store-Cache leeren; repair = Paket neu registrieren (nicht-destruktiv); "
             "reset = Paket-Daten zurücksetzen (~/.codex bleibt erhalten).",
    )
    store_parser.add_argument("--execute", action="store_true", help="Wirklich ausführen (sonst Dry-Run).")
    store_parser.add_argument("--status", action="store_true", help="Nur Paket-Status anzeigen (read-only).")
    store_parser.set_defaults(func=cmd_store_repair)

    store_materials_parser = subparsers.add_parser(
        "store-materials",
        help="Windows-Store-Materialien im Projekt pruefen (store_package.json, Doku, EXE-Name).",
    )
    store_materials_parser.add_argument(
        "--project-root",
        default=str(Path(__file__).resolve().parents[2]),
        help="Projektwurzel mit den Store-Dateien.",
    )
    store_materials_parser.add_argument(
        "--exe-path",
        default=None,
        help="Optionaler Pfad zur gebauten EXE fuer einen konkreten Existenzcheck.",
    )
    store_materials_parser.set_defaults(func=cmd_store_materials)

    store_screenshot_parser = subparsers.add_parser(
        "store-screenshot",
        help="Reproduzierbaren README-/Store-Screenshot des Statusfensters erzeugen.",
    )
    store_screenshot_parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parents[2] / "README" / "screenshots" / "main.png"),
        help="Zielpfad fuer den PNG-Screenshot.",
    )
    store_screenshot_parser.set_defaults(func=cmd_store_screenshot)

    repair_parser = subparsers.add_parser(
        "repair",
        help="Begrenzte, hang-sichere Codex-Start-Reparatur (S1+S2+S3+1 Fallback, kein UAC).",
    )
    repair_parser.add_argument(
        "--dry-run", action="store_true",
        help="Nur planen (kein mutierendes Dep).",
    )
    repair_parser.add_argument(
        "--execute", action="store_true",
        help="Echter Lauf mit den Rechten des aktuellen Prozesses (kein UAC; meldet ggf. needs_admin).",
    )
    repair_parser.add_argument(
        "--out", default=None,
        help="Ergebnis als JSON dorthin schreiben (bei --execute zusaetzlich pro Stufe eine JSON-Zeile).",
    )
    repair_parser.set_defaults(func=cmd_repair)

    audit_parser = subparsers.add_parser(
        "audit",
        help="Config-Audit: MCP-Duplikate, ungenutzte Plugins, CLI-Status, leere Threads pruefen.",
    )
    audit_parser.set_defaults(func=cmd_audit)

    safe_start_parser = subparsers.add_parser(
        "safe-start-report",
        help="Safe-Start-Status, Start-Storm und seltene Catch-up-Kandidaten prüfen.",
    )
    safe_start_parser.add_argument("--json", action="store_true", help="Status als JSON ausgeben.")
    safe_start_parser.set_defaults(func=cmd_safe_start_report)

    safe_start_install_parser = subparsers.add_parser(
        "safe-start-install",
        help="Safe Start for Codex installieren oder aktualisieren.",
    )
    safe_start_install_parser.add_argument(
        "--target",
        default=None,
        help="Optionales pip-Ziel. Ohne Angabe: lokale Schwesterquelle, sonst safe-start-for-codex>=1.1.2.",
    )
    safe_start_install_parser.add_argument(
        "--json", action="store_true", help="Ergebnis als JSON ausgeben."
    )
    safe_start_install_parser.set_defaults(func=cmd_safe_start_install)

    mark_runs_parser = subparsers.add_parser(
        "mark-runs-read",
        help="Automations-Ergebnisse als gelesen markieren (Ungelesen-Zähler leeren). "
             "Nur bei geschlossenem Codex.",
    )
    mark_runs_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur zählen und melden, nichts schreiben.",
    )
    mark_runs_parser.set_defaults(func=cmd_mark_runs_read)

    tray_parser = subparsers.add_parser("tray", help="Systemtray-App starten.")
    tray_parser.set_defaults(func=cmd_tray)

    schedule_parser = subparsers.add_parser(
        "schedule",
        help="Optionalen Windows-Task fuer regelmaessige Wartung verwalten.",
    )
    schedule_parser.add_argument(
        "--task-name",
        default="CodexLogdatenbankWartung-Autowartung",
        help="Name des geplanten Windows-Tasks.",
    )
    schedule_parser.add_argument(
        "--script-path",
        default=str(local_root() / "run-maintenance.cmd"),
        help="Pfad fuer das lokale Hilfsskript des geplanten Tasks.",
    )
    schedule_subparsers = schedule_parser.add_subparsers(dest="schedule_command", required=True)

    schedule_install = schedule_subparsers.add_parser(
        "install", help="Geplanten Windows-Task fuer die Wartung anlegen oder ersetzen."
    )
    schedule_install.add_argument(
        "--interval-minutes",
        type=int,
        default=180,
        help="Intervall fuer den Task. Minimum 15 Minuten.",
    )
    schedule_install.set_defaults(func=cmd_schedule_install)

    schedule_remove = schedule_subparsers.add_parser(
        "remove", help="Geplanten Windows-Task entfernen."
    )
    schedule_remove.set_defaults(func=cmd_schedule_remove)

    schedule_status = schedule_subparsers.add_parser(
        "status", help="Pruefen, ob der geplante Windows-Task vorhanden ist."
    )
    schedule_status.set_defaults(func=cmd_schedule_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    if config_path.exists():
        try:
            config = MaintenanceConfig.load(config_path)
            set_language(normalize_language(config.language) or config.language)
        except (ValueError, OSError):
            pass

    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
