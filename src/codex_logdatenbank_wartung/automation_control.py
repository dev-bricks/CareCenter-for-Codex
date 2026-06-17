"""CareCenter-Steuerung fuer lokale Codex-Automatisierungen.

Die Codex-App speichert Automatisierungen unter ``CODEX_HOME/automations`` als
``automation.toml``. Dieses Modul kapselt Statusaenderungen und merkt sich nur die
Automatisierungen, die CareCenter selbst pausiert hat, damit bestehend pausierte
Automatisierungen nicht versehentlich wieder aktiviert werden.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import tomlkit

from .config import MaintenanceConfig

ACTIVE = "ACTIVE"
PAUSED = "PAUSED"

AutomationAction = Literal[
    "pause-active",
    "restore-ccc",
    "restore-ccc-staggered",
    "activate-all",
    "activate-all-staggered",
]
ProgressCallback = Callable[[int, int, str], None]
Sleeper = Callable[[float], None]


@dataclass(slots=True)
class AutomationRecord:
    id: str
    name: str
    path: Path
    status: str


@dataclass(slots=True)
class AutomationControlResult:
    action: AutomationAction
    status: str
    target_count: int = 0
    changed_ids: list[str] = field(default_factory=list)
    skipped_ids: list[str] = field(default_factory=list)
    missing_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    delay_seconds: int = 0

    @property
    def changed_count(self) -> int:
        return len(self.changed_ids)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def automations_dir(config: MaintenanceConfig) -> Path:
    return config.codex_home / "automations"


def control_state_dir(config: MaintenanceConfig) -> Path:
    return config.codex_home / "carecenter-automation-control"


def control_state_path(config: MaintenanceConfig) -> Path:
    return control_state_dir(config) / "paused-by-carecenter.json"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _read_toml(path: Path) -> tomlkit.TOMLDocument:
    return tomlkit.parse(path.read_text(encoding="utf-8", errors="replace"))


def _write_toml(path: Path, document: tomlkit.TOMLDocument) -> None:
    path.write_text(tomlkit.dumps(document), encoding="utf-8", newline="")


def _quoted_string(value: object) -> str:
    return str(value or "")


def load_automations(config: MaintenanceConfig) -> list[AutomationRecord]:
    root = automations_dir(config)
    if not root.exists():
        return []

    records: list[AutomationRecord] = []
    for toml_path in sorted(root.glob("*/automation.toml")):
        try:
            data = _read_toml(toml_path)
        except (OSError, tomlkit.exceptions.ParseError):
            continue
        automation_id = _quoted_string(data.get("id")) or toml_path.parent.name
        records.append(
            AutomationRecord(
                id=automation_id,
                name=_quoted_string(data.get("name")) or automation_id,
                path=toml_path,
                status=_quoted_string(data.get("status")) or "UNKNOWN",
            )
        )
    return records


def load_carecenter_paused_ids(config: MaintenanceConfig) -> list[str]:
    path = control_state_path(config)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    ids = data.get("paused_by_carecenter_ids") if isinstance(data, dict) else None
    if not isinstance(ids, list):
        return []
    return sorted({str(item) for item in ids if item})


def _save_carecenter_paused_ids(config: MaintenanceConfig, ids: set[str]) -> None:
    path = control_state_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "tool": "CareCenter for Codex",
        "updated_at": _now_iso(),
        "paused_by_carecenter_ids": sorted(ids),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_event(config: MaintenanceConfig, result: AutomationControlResult) -> None:
    path = control_state_dir(config) / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": _now_iso(),
        **result.to_dict(),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _set_status(record: AutomationRecord, status: str) -> bool:
    data = _read_toml(record.path)
    current = _quoted_string(data.get("status"))
    if current == status:
        return False
    data["status"] = status
    if "updated_at" in data:
        data["updated_at"] = _now_ms()
    _write_toml(record.path, data)
    return True


def _activate_records(
    records: list[AutomationRecord],
    *,
    action: AutomationAction,
    staggered: bool,
    delay_seconds: int,
    sleeper: Sleeper,
    progress: ProgressCallback | None,
) -> AutomationControlResult:
    result = AutomationControlResult(
        action=action,
        status="ok",
        target_count=len(records),
        delay_seconds=delay_seconds if staggered else 0,
    )
    targets = [record for record in records if record.status != ACTIVE]
    total = len(targets)
    for index, record in enumerate(targets, start=1):
        try:
            changed = _set_status(record, ACTIVE)
        except (OSError, tomlkit.exceptions.ParseError) as exc:
            result.errors.append(f"{record.id}: {exc}")
            continue
        if changed:
            result.changed_ids.append(record.id)
            if progress is not None:
                progress(index, total, record.id)
            if staggered and index < total:
                sleeper(float(delay_seconds))
        else:
            result.skipped_ids.append(record.id)

    already_active = [record.id for record in records if record.status == ACTIVE]
    result.skipped_ids.extend(already_active)
    if result.errors:
        result.status = "partial" if result.changed_ids else "failed"
    return result


def pause_active_automations(config: MaintenanceConfig) -> AutomationControlResult:
    records = load_automations(config)
    active_records = [record for record in records if record.status == ACTIVE]
    result = AutomationControlResult(
        action="pause-active",
        status="ok",
        target_count=len(active_records),
    )
    carecenter_ids = set(load_carecenter_paused_ids(config))
    for record in active_records:
        try:
            if _set_status(record, PAUSED):
                result.changed_ids.append(record.id)
                carecenter_ids.add(record.id)
            else:
                result.skipped_ids.append(record.id)
        except (OSError, tomlkit.exceptions.ParseError) as exc:
            result.errors.append(f"{record.id}: {exc}")
    if result.errors:
        result.status = "partial" if result.changed_ids else "failed"
    _save_carecenter_paused_ids(config, carecenter_ids)
    _append_event(config, result)
    return result


def activate_carecenter_paused_automations(
    config: MaintenanceConfig,
    *,
    staggered: bool = False,
    delay_seconds: int = 60,
    sleeper: Sleeper = time.sleep,
    progress: ProgressCallback | None = None,
) -> AutomationControlResult:
    records = load_automations(config)
    by_id = {record.id: record for record in records}
    carecenter_ids = set(load_carecenter_paused_ids(config))
    target_ids = sorted(carecenter_ids)
    missing_ids = sorted(carecenter_ids - set(by_id))
    target_records = [by_id[item] for item in target_ids if item in by_id]
    action: AutomationAction = "restore-ccc-staggered" if staggered else "restore-ccc"
    result = _activate_records(
        target_records,
        action=action,
        staggered=staggered,
        delay_seconds=delay_seconds,
        sleeper=sleeper,
        progress=progress,
    )
    result.missing_ids = missing_ids
    completed = set(result.changed_ids) | set(result.skipped_ids) | set(missing_ids)
    failed = {
        error.split(":", 1)[0]
        for error in result.errors
        if ":" in error
    }
    _save_carecenter_paused_ids(config, failed | (carecenter_ids - completed))
    _append_event(config, result)
    return result


def activate_all_automations(
    config: MaintenanceConfig,
    *,
    staggered: bool = False,
    delay_seconds: int = 60,
    sleeper: Sleeper = time.sleep,
    progress: ProgressCallback | None = None,
) -> AutomationControlResult:
    action: AutomationAction = "activate-all-staggered" if staggered else "activate-all"
    result = _activate_records(
        load_automations(config),
        action=action,
        staggered=staggered,
        delay_seconds=delay_seconds,
        sleeper=sleeper,
        progress=progress,
    )
    if not result.errors:
        _save_carecenter_paused_ids(config, set())
    _append_event(config, result)
    return result


def run_automation_action(
    config: MaintenanceConfig,
    action: AutomationAction,
    *,
    sleeper: Sleeper = time.sleep,
    progress: ProgressCallback | None = None,
    stagger_delay_seconds: int = 60,
) -> AutomationControlResult:
    if action == "pause-active":
        return pause_active_automations(config)
    if action == "restore-ccc":
        return activate_carecenter_paused_automations(config)
    if action == "restore-ccc-staggered":
        return activate_carecenter_paused_automations(
            config,
            staggered=True,
            delay_seconds=stagger_delay_seconds,
            sleeper=sleeper,
            progress=progress,
        )
    if action == "activate-all":
        return activate_all_automations(config)
    if action == "activate-all-staggered":
        return activate_all_automations(
            config,
            staggered=True,
            delay_seconds=stagger_delay_seconds,
            sleeper=sleeper,
            progress=progress,
        )
    raise ValueError(f"Unbekannte Automationsaktion: {action}")
