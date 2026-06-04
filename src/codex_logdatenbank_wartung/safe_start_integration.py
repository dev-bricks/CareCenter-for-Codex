"""Optionale Safe-Start-Integration für CareCenter."""

from __future__ import annotations

import importlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType

from .config import MaintenanceConfig


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


def _safe_start_cli() -> ModuleType | None:
    try:
        return importlib.import_module("safe_start_for_codex.cli")
    except Exception:
        return None


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
    delayed = snapshot.get("delayed_release_ids") or []
    tool_paused = snapshot.get("tool_paused_ids") or []
    released = snapshot.get("released_ids") or []
    return phase == "release-queue" and bool(delayed or (tool_paused and not released))


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
    latest_snapshot = _load_json(config.safe_start_state_dir / "latest.json")
    return _snapshot_indicates_active_gate(latest_snapshot)
