"""Optionale Safe-Start-Integration für CareCenter."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType

import tomlkit

from .config import MaintenanceConfig

SAFE_START_PACKAGE_SPEC = "safe-start-for-codex>=1.1.2"
SAFE_START_SOURCE_ENV = "CARECENTER_SAFE_START_SOURCE"
CREATE_NO_WINDOW = 0x08000000
CARECENTER_SAFE_START_DEFAULT_INTERVAL_MINUTES = 1


@dataclass(slots=True)
class SafeStartStorm:
    status: str
    release_count: int
    window_minutes: int
    events_path: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class SafeStartStatus:
    available: bool
    config_path: str
    state_dir: str
    latest_snapshot: str | None
    latest_catchup_plan: str | None
    storm_status: str
    storm_release_count: int
    storm_window_minutes: int
    eligible_count: int
    eligible_ids: list[str]
    candidate_count: int
    notes: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_text(self) -> str:
        availability = "installiert" if self.available else "nicht installiert"
        lines = [
            f"Safe Start: {availability}",
            f"Config: {self.config_path}",
            f"Statusordner: {self.state_dir}",
            f"Start-Storm: {self.storm_status} ({self.storm_release_count} Freigaben im Fenster)",
            f"Seltene Catch-up-Kandidaten: {self.eligible_count}",
        ]
        if self.eligible_ids:
            lines.append("Früh priorisieren: " + ", ".join(self.eligible_ids))
        if self.latest_snapshot:
            lines.append(f"Letzter Snapshot: {self.latest_snapshot}")
        if self.latest_catchup_plan:
            lines.append(f"Letzter Catch-up-Plan: {self.latest_catchup_plan}")
        if self.notes:
            lines.append("Hinweise:")
            lines.extend(f"- {note}" for note in self.notes)
        return "\n".join(lines)


@dataclass(slots=True)
class SafeStartInstallResult:
    status: str
    target: str
    command: list[str]
    message: str
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_text(self) -> str:
        lines = [
            f"Status: {self.status}",
            f"Ziel: {self.target}",
            "Befehl: " + " ".join(self.command),
            self.message,
        ]
        if self.stdout.strip():
            lines.append("Ausgabe:")
            lines.append(self.stdout.strip())
        if self.stderr.strip():
            lines.append("Fehlerausgabe:")
            lines.append(self.stderr.strip())
        return "\n".join(lines)


@dataclass(slots=True)
class SafeStartLaunchResult:
    status: str
    command: list[str]
    message: str
    config_path: str
    used_config: bool
    pid: int | None = None
    fallback_interval_minutes: int | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_text(self) -> str:
        lines = [
            f"Status: {self.status}",
            "Befehl: " + " ".join(self.command),
            self.message,
            f"Config: {self.config_path} ({'vorhanden' if self.used_config else 'Fallback'})",
        ]
        if self.fallback_interval_minutes is not None:
            lines.append(f"Fallback-Abstand: {self.fallback_interval_minutes} Minute(n)")
        if self.pid is not None:
            lines.append(f"PID: {self.pid}")
        return "\n".join(lines)


@dataclass(slots=True)
class SafeStartRestoreResult:
    status: str
    latest_path: str | None
    snapshot_path: str | None
    message: str
    dry_run: bool = False
    target_count: int = 0
    restored_ids: list[str] = field(default_factory=list)
    skipped_ids: list[str] = field(default_factory=list)
    missing_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_text(self) -> str:
        lines = [
            f"Status: {self.status}",
            self.message,
        ]
        if self.latest_path:
            lines.append(f"Quelle: {self.latest_path}")
        if self.snapshot_path:
            lines.append(f"Snapshot: {self.snapshot_path}")
        lines.append(f"Ziel-Automatisierungen: {self.target_count}")
        if self.restored_ids:
            lines.append("Zurückgegeben: " + ", ".join(self.restored_ids))
        if self.skipped_ids:
            lines.append("Bereits aktiv: " + ", ".join(self.skipped_ids))
        if self.missing_ids:
            lines.append("Nicht mehr vorhanden: " + ", ".join(self.missing_ids))
        if self.errors:
            lines.append("Fehler:")
            lines.extend(f"- {error}" for error in self.errors)
        return "\n".join(lines)


def _no_window_kwargs() -> dict[str, object]:
    if os.name == "nt":
        return {"creationflags": CREATE_NO_WINDOW}
    return {}


def _safe_start_cli() -> ModuleType | None:
    try:
        return importlib.import_module("safe_start_for_codex.cli")
    except Exception:
        return None


def _local_safe_start_source() -> Path | None:
    env_path = os.environ.get(SAFE_START_SOURCE_ENV)
    if env_path:
        candidate = Path(env_path).expanduser()
        if (candidate / "pyproject.toml").exists():
            return candidate

    project_root = Path(__file__).resolve().parents[2]
    sibling = project_root.parent / "REL-PUB_safe-start-for-codex"
    if (sibling / "pyproject.toml").exists():
        return sibling
    return None


def safe_start_install_target() -> str:
    """Bevorzuge die lokale Schwesterquelle, sonst das veröffentlichte Paket."""
    local_source = _local_safe_start_source()
    if local_source is not None:
        return str(local_source)
    return SAFE_START_PACKAGE_SPEC


def _pip_command_candidates() -> list[list[str]]:
    candidates: list[list[str]] = []
    if not getattr(sys, "frozen", False):
        candidates.append([sys.executable, "-m", "pip"])
    candidates.extend((["py", "-3", "-m", "pip"], ["python", "-m", "pip"]))

    unique: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for candidate in candidates:
        key = tuple(candidate)
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def _python_command_candidates() -> list[list[str]]:
    candidates: list[list[str]] = []
    if not getattr(sys, "frozen", False):
        candidates.append([sys.executable])
    candidates.extend((["py", "-3"], ["python"]))

    unique: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for candidate in candidates:
        key = tuple(candidate)
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def _run_install_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def install_safe_start_package(
    *,
    target: str | None = None,
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
) -> SafeStartInstallResult:
    """Installiere oder aktualisiere Safe Start for Codex über pip.

    Das ist bewusst eine explizite Nutzeraktion. Der Tray nutzt dieselbe Funktion wie
    der CLI-Befehl; automatisch wird hier nichts nachinstalliert.
    """
    chosen_target = target or safe_start_install_target()
    run = runner or _run_install_command
    attempts: list[SafeStartInstallResult] = []
    for pip_command in _pip_command_candidates():
        command = [*pip_command, "install", "--upgrade", chosen_target]
        try:
            completed = run(command)
        except OSError as exc:
            attempts.append(
                SafeStartInstallResult(
                    status="failed",
                    target=chosen_target,
                    command=command,
                    message=str(exc),
                )
            )
            continue
        status = "ok" if completed.returncode == 0 else "failed"
        result = SafeStartInstallResult(
            status=status,
            target=chosen_target,
            command=command,
            message=(
                "Safe Start wurde installiert oder aktualisiert."
                if status == "ok"
                else f"pip endete mit Code {completed.returncode}."
            ),
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )
        if status == "ok":
            return result
        attempts.append(result)

    if attempts:
        last = attempts[-1]
        return SafeStartInstallResult(
            status="failed",
            target=chosen_target,
            command=last.command,
            message="Safe Start konnte nicht installiert werden.",
            stdout=last.stdout,
            stderr=last.stderr or last.message,
        )
    return SafeStartInstallResult(
        status="failed",
        target=chosen_target,
        command=[],
        message="Kein Python/pip-Befehl gefunden.",
    )


def safe_start_launch_arguments(config: MaintenanceConfig) -> tuple[list[str], bool]:
    """Baue die Safe-Start-Argumente fuer den CareCenter-Tray-Start."""
    config_path = config.safe_start_config_file
    args = ["tray", "--config", str(config_path)]
    config_exists = config_path.exists()
    if not config_exists:
        args.extend(
            [
                "--interval-minutes",
                str(CARECENTER_SAFE_START_DEFAULT_INTERVAL_MINUTES),
            ]
        )
    return args, config_exists


def _safe_start_env(config: MaintenanceConfig) -> dict[str, str]:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(config.codex_home)
    local_source = _local_safe_start_source()
    if local_source is not None:
        src = str(local_source / "src")
        old_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = src if not old_pythonpath else src + os.pathsep + old_pythonpath
    return env


def launch_safe_start_tray(
    config: MaintenanceConfig,
    *,
    popen: Callable[..., subprocess.Popen[str]] | None = None,
) -> SafeStartLaunchResult:
    args, config_exists = safe_start_launch_arguments(config)
    if safe_start_gate_active(config):
        return SafeStartLaunchResult(
            status="already-running",
            command=[],
            message="Safe Start läuft bereits; kein zweiter Start wurde ausgelöst.",
            config_path=str(config.safe_start_config_file),
            used_config=config_exists,
            fallback_interval_minutes=None
            if config_exists
            else CARECENTER_SAFE_START_DEFAULT_INTERVAL_MINUTES,
        )

    env = _safe_start_env(config)
    run = popen or subprocess.Popen
    last_error = ""
    last_command: list[str] = []

    for python_command in _python_command_candidates():
        command = [*python_command, "-m", "safe_start_for_codex", *args]
        last_command = command
        try:
            process = run(
                command,
                env=env,
                close_fds=True,
                **_no_window_kwargs(),
            )
        except OSError as exc:
            last_error = str(exc)
            continue
        pid = getattr(process, "pid", None)
        return SafeStartLaunchResult(
            status="ok",
            command=command,
            message="Safe Start for Codex wurde im eigenen Tray gestartet.",
            config_path=str(config.safe_start_config_file),
            used_config=config_exists,
            pid=int(pid) if isinstance(pid, int) else None,
            fallback_interval_minutes=None
            if config_exists
            else CARECENTER_SAFE_START_DEFAULT_INTERVAL_MINUTES,
        )

    return SafeStartLaunchResult(
        status="failed",
        command=last_command,
        message=last_error or "Kein Python-Befehl fuer Safe Start gefunden.",
        config_path=str(config.safe_start_config_file),
        used_config=config_exists,
        fallback_interval_minutes=None
        if config_exists
        else CARECENTER_SAFE_START_DEFAULT_INTERVAL_MINUTES,
    )


@contextmanager
def _temporary_codex_home(path: Path) -> Iterator[None]:
    old = os.environ.get("CODEX_HOME")
    os.environ["CODEX_HOME"] = str(path)
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = old


def _parse_timestamp(value: object, reference: datetime) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if reference.tzinfo is None and parsed.tzinfo is not None:
        return parsed.replace(tzinfo=None)
    if reference.tzinfo is not None and parsed.tzinfo is None:
        return parsed.replace(tzinfo=reference.tzinfo)
    if reference.tzinfo is not None and parsed.tzinfo is not None:
        return parsed.astimezone(reference.tzinfo)
    return parsed


def _load_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _list_count(value: object) -> int:
    return len(value) if isinstance(value, list) else 0


def detect_safe_start_storm(
    config: MaintenanceConfig,
    *,
    now: datetime | None = None,
) -> SafeStartStorm:
    current = now or datetime.now().astimezone()
    window_minutes = max(int(config.safe_start_storm_window_minutes), 1)
    threshold = max(int(config.safe_start_storm_release_threshold), 1)
    events_path = config.safe_start_state_dir / "events.jsonl"
    cutoff = current - timedelta(minutes=window_minutes)
    releases = 0

    if events_path.exists():
        try:
            for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict) or record.get("event") != "release":
                    continue
                stamp = _parse_timestamp(record.get("ts"), current)
                if stamp is not None and stamp >= cutoff:
                    releases += 1
        except OSError:
            pass

    status = "release_burst" if releases >= threshold else "ok"
    return SafeStartStorm(
        status=status,
        release_count=releases,
        window_minutes=window_minutes,
        events_path=str(events_path),
    )


def _snapshot_indicates_active_gate(snapshot: dict[str, object] | None) -> bool:
    if not snapshot:
        return False
    phase = str(snapshot.get("phase") or "")
    delayed = set(_string_list(snapshot.get("delayed_release_ids")))
    tool_paused = set(_string_list(snapshot.get("tool_paused_ids")))
    released = set(_string_list(snapshot.get("released_ids")))
    if phase == "paused":
        return bool(tool_paused)
    if phase == "release-queue":
        return bool(delayed or (tool_paused - released))
    return False


def safe_start_gate_active(config: MaintenanceConfig) -> bool:
    """True, wenn der letzte Safe-Start-Snapshot ein laufendes Gate beschreibt."""
    latest_snapshot = _load_json(config.safe_start_state_dir / "latest.json")
    return _snapshot_indicates_active_gate(latest_snapshot)


def _snapshot_restore_rows(snapshot: dict[str, object]) -> list[dict[str, object]]:
    rows = snapshot.get("items")
    if not isinstance(rows, list):
        return []
    result: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("tool_paused"):
            continue
        if str(row.get("original_status") or "").upper() == "ACTIVE":
            result.append(row)
    return result


def _set_automation_toml_status(path: Path, status: str) -> bool:
    document = tomlkit.parse(path.read_text(encoding="utf-8", errors="replace"))
    current = str(document.get("status") or "")
    if current == status:
        return False
    document["status"] = status
    if "updated_at" in document:
        document["updated_at"] = int(time.time() * 1000)
    path.write_text(tomlkit.dumps(document), encoding="utf-8", newline="")
    return True


def _write_carecenter_restore_snapshot(
    config: MaintenanceConfig,
    snapshot: dict[str, object],
    result: SafeStartRestoreResult,
) -> Path:
    state_dir = config.safe_start_state_dir
    state_dir.mkdir(parents=True, exist_ok=True)
    restored_or_skipped = set(result.restored_ids) | set(result.skipped_ids) | set(result.missing_ids)
    payload = dict(snapshot)
    rows = snapshot.get("items")
    if isinstance(rows, list):
        updated_rows: list[object] = []
        for row in rows:
            if not isinstance(row, dict):
                updated_rows.append(row)
                continue
            updated = dict(row)
            automation_id = str(updated.get("id") or "")
            if automation_id in restored_or_skipped and updated.get("tool_paused"):
                updated["status"] = "ACTIVE"
                updated["released"] = True
            updated_rows.append(updated)
        payload["items"] = updated_rows

    payload["phase"] = "restored"
    payload["created_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    payload["restored_by"] = "CareCenter for Codex"
    payload["carecenter_restore"] = {
        "status": result.status,
        "restored_ids": result.restored_ids,
        "skipped_ids": result.skipped_ids,
        "missing_ids": result.missing_ids,
        "target_count": result.target_count,
    }
    payload["released_ids"] = sorted(set(_string_list(payload.get("released_ids"))) | restored_or_skipped)
    payload["delayed_release_ids"] = []

    run_id = str(snapshot.get("run_id") or "safe-start")
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    path = state_dir / f"{run_id}-carecenter-restored-{stamp}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    (state_dir / "latest.json").write_text(text, encoding="utf-8")
    return path


def restore_safe_start_latest(
    config: MaintenanceConfig,
    *,
    dry_run: bool = False,
) -> SafeStartRestoreResult:
    """Gib Automatisierungen zurück, die Safe Start im letzten Snapshot pausiert hat."""
    latest_path = config.safe_start_state_dir / "latest.json"
    snapshot = _load_json(latest_path)
    if not snapshot:
        return SafeStartRestoreResult(
            status="nothing-to-do",
            latest_path=str(latest_path),
            snapshot_path=None,
            message="Kein Safe-Start-Snapshot vorhanden.",
            dry_run=dry_run,
        )

    rows = _snapshot_restore_rows(snapshot)
    result = SafeStartRestoreResult(
        status="ok",
        latest_path=str(latest_path),
        snapshot_path=None,
        message="Safe-Start-Automatisierungen wurden zurückgegeben.",
        dry_run=dry_run,
        target_count=len(rows),
    )
    if not rows:
        result.status = "nothing-to-do"
        result.message = "Der letzte Safe-Start-Snapshot enthält keine zurückzugebenden Automatisierungen."

    for row in rows:
        automation_id = str(row.get("id") or row.get("name") or "unknown")
        path_text = str(row.get("path") or "")
        if not path_text:
            result.missing_ids.append(automation_id)
            continue
        path = Path(path_text)
        if not path.exists():
            result.missing_ids.append(automation_id)
            continue
        try:
            changed = False if dry_run else _set_automation_toml_status(path, "ACTIVE")
        except (OSError, tomlkit.exceptions.ParseError) as exc:
            result.errors.append(f"{automation_id}: {exc}")
            continue
        if dry_run or changed:
            result.restored_ids.append(automation_id)
        else:
            result.skipped_ids.append(automation_id)

    if result.errors:
        result.status = (
            "partial"
            if result.restored_ids or result.skipped_ids or result.missing_ids
            else "failed"
        )
        result.message = "Safe-Start-Restore konnte nicht vollständig abgeschlossen werden."
        return result

    if not dry_run:
        restored_snapshot = _write_carecenter_restore_snapshot(config, snapshot, result)
        result.snapshot_path = str(restored_snapshot)
    return result


def build_safe_start_status(config: MaintenanceConfig) -> SafeStartStatus:
    state_dir = config.safe_start_state_dir
    latest_path = state_dir / "latest.json"
    latest_catchup_path = state_dir / "latest-catchup-plan.json"
    latest_snapshot = _load_json(latest_path)
    latest_catchup = _load_json(latest_catchup_path)
    storm = detect_safe_start_storm(config)
    storm_status = storm.status
    if storm_status == "ok" and _snapshot_indicates_active_gate(latest_snapshot):
        storm_status = "gate_active"

    notes: list[str] = []
    eligible_ids: list[str] = []
    candidate_count = 0
    available = False

    safe_start = _safe_start_cli()
    if safe_start is None:
        notes.append("Safe-Start-Paket nicht importierbar; nutze vorhandene Snapshots.")
        if latest_catchup:
            eligible_ids = _string_list(latest_catchup.get("eligible_ids"))
            candidate_count = _list_count(latest_catchup.get("candidates"))
    else:
        available = True
        try:
            with _temporary_codex_home(config.codex_home):
                report = safe_start.build_catchup_report(
                    lookback_days=config.safe_start_catchup_lookback_days,
                    min_period_hours=config.safe_start_catchup_min_period_hours,
                    max_per_start=config.safe_start_catchup_max_per_start,
                    state_db=config.state_db_path,
                )
            eligible_ids = [str(item) for item in report.eligible_ids]
            candidate_count = len(report.candidates)
            notes.extend(str(note) for note in report.notes)
        except (Exception, SystemExit) as exc:
            notes.append(f"Safe-Start-Catch-up-Plan konnte nicht erstellt werden: {exc}")
            if latest_catchup:
                eligible_ids = _string_list(latest_catchup.get("eligible_ids"))
                candidate_count = _list_count(latest_catchup.get("candidates"))

    if storm_status == "release_burst":
        notes.append("Start-Storm erkannt: CareCenter sollte keine zusätzliche Start-Reparatur anstoßen.")
    elif storm_status == "gate_active":
        notes.append("Safe Start Gate ist aktiv; Freigaben laufen kontrolliert gestaffelt.")

    return SafeStartStatus(
        available=available,
        config_path=str(config.safe_start_config_file),
        state_dir=str(state_dir),
        latest_snapshot=str(latest_path) if latest_path.exists() else None,
        latest_catchup_plan=str(latest_catchup_path) if latest_catchup_path.exists() else None,
        storm_status=storm_status,
        storm_release_count=storm.release_count,
        storm_window_minutes=storm.window_minutes,
        eligible_count=len(eligible_ids),
        eligible_ids=eligible_ids,
        candidate_count=candidate_count,
        notes=notes,
    )


def should_defer_for_safe_start(config: MaintenanceConfig) -> bool:
    storm = detect_safe_start_storm(config)
    if storm.status == "release_burst":
        return True
    return safe_start_gate_active(config)
