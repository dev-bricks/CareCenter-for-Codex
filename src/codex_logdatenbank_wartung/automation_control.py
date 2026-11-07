"""CareCenter-Steuerung fuer lokale Codex-Automatisierungen.

Die Codex-App speichert Automatisierungen unter ``CODEX_HOME/automations`` als
``automation.toml``. Dieses Modul kapselt Statusaenderungen und merkt sich nur die
Automatisierungen, die CareCenter selbst pausiert hat, damit bestehend pausierte
Automatisierungen nicht versehentlich wieder aktiviert werden.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
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



class AutomationDefinitionError(ValueError):
    """Die Datei ist gueltiges TOML, aber keine brauchbare Automations-Definition.

    Die Meldung beginnt mit ``empty``, ``missing id`` oder ``id mismatch``.
    """


# Was beim Lesen einer automation.toml schiefgehen kann: Ein-/Ausgabe, kein gueltiges UTF-8,
# ein TOML-Fehler (tomlkit meldet doppelte Schluessel als ParseError) oder eine leere bzw. id-lose Definition.
_UNREADABLE = (OSError, UnicodeDecodeError, tomlkit.exceptions.TOMLKitError, AutomationDefinitionError)


@dataclass(slots=True)
class AutomationRecord:
    id: str
    name: str
    path: Path
    status: str


@dataclass(slots=True)
class UnparseableAutomation:
    """Eine ``automation.toml``, die sich nicht lesen laesst.

    CareCenter kann sie weder sehen noch aendern. ``id`` ist der Ordnername, denn die
    ``id`` steht in der unlesbaren Datei selbst.
    """

    id: str
    path: Path
    error: str


@dataclass(slots=True)
class AutomationFinding:
    """Eine im Baum gefundene ``automation.toml`` mit Tiefe relativ zu ``automations/``."""

    id: str
    path: Path
    depth: int

    @property
    def nested(self) -> bool:
        return self.depth > 1


@dataclass(slots=True)
class NestedAutomation:
    id: str
    path: Path
    depth: int


@dataclass(slots=True)
class DuplicateAutomationId:
    id: str
    paths: list[Path]


@dataclass(slots=True)
class AutomationAnomalyReport:
    """Read-only Befund ueber verschachtelte, id-duplizierte und unlesbare Automationen."""

    nested: list[NestedAutomation] = field(default_factory=list)
    duplicate_ids: list[DuplicateAutomationId] = field(default_factory=list)
    unparseable: list[UnparseableAutomation] = field(default_factory=list)

    @property
    def has_anomalies(self) -> bool:
        return bool(self.nested) or bool(self.duplicate_ids) or bool(self.unparseable)


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
    # Ordnernamen der Definitionen, die nicht lesbar waren und daher NICHT verarbeitet wurden.
    # Jede steht zusaetzlich mit Pfad und Fehlertext in ``errors``, damit ``status`` nie "ok" ist.
    unparseable_ids: list[str] = field(default_factory=list)

    @property
    def changed_count(self) -> int:
        return len(self.changed_ids)

    @property
    def unparseable_count(self) -> int:
        return len(self.unparseable_ids)

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
    # Bytes statt read_text: Zeilenenden (CRLF) bleiben erhalten, damit der Rueckschreibweg die
    # Datei nicht umformatiert. Strikt UTF-8: ersetzte Zeichen wuerden sonst beim Speichern
    # still in die Datei geschrieben.
    return tomlkit.parse(path.read_bytes().decode("utf-8"))


def _read_automation(path: Path, *, match_folder: bool = True) -> tomlkit.TOMLDocument:
    """Liest eine ``automation.toml`` und verlangt eine brauchbare Definition.

    Eine leere, abgeschnittene oder id-lose Datei parst als gueltiges TOML; ohne diese Pruefung galt sie
    als Datensatz mit Status UNKNOWN, und ``activate-all`` haette ``status = "ACTIVE"`` hineingeschrieben.
    ``match_folder=False`` laesst eine ``id`` zu, die vom Ordnernamen abweicht (die Doppel-id-Erkennung
    braucht genau diesen Fall); alles, was Dateien aendert, verlangt die Uebereinstimmung.
    """
    data = _read_toml(path)
    if not data:
        raise AutomationDefinitionError("empty: keine Schluessel (leere Datei, nur Kommentar oder nur Leerraum)")
    raw_id = data.get("id")
    automation_id = raw_id.strip() if isinstance(raw_id, str) else ""
    if not automation_id:
        raise AutomationDefinitionError("missing id: 'id' fehlt, ist leer oder keine Zeichenkette")
    if match_folder and automation_id.casefold() != path.parent.name.casefold():
        raise AutomationDefinitionError(
            f"id mismatch: id '{automation_id}' weicht vom Ordnernamen '{path.parent.name}' ab"
        )
    return data


def _write_toml(path: Path, document: tomlkit.TOMLDocument) -> None:
    """Schreibt atomar: erst vollstaendig kodieren, dann tmp im selben Ordner, fsync, ``os.replace``.

    Bricht der Vorgang ab, bleibt die Originaldatei unveraendert und die tmp-Datei wird entfernt.
    ``mkstemp`` legt die Datei mit 0600 an: die Rechte des Originals kommen vor dem Austausch auf die tmp-Datei.
    Ist ``path`` ein Link, wird sein Ziel ersetzt und der Link bleibt bestehen.
    """
    payload = tomlkit.dumps(document).encode("utf-8")
    target = Path(os.path.realpath(path))
    mode = stat.S_IMODE(target.stat().st_mode)
    descriptor, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f"{target.name}.", suffix=".tmp")
    temporary = Path(tmp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _quoted_string(value: object) -> str:
    return str(value or "")


def _unreadable_text(exc: Exception) -> str:
    if isinstance(exc, AutomationDefinitionError):
        return " ".join(str(exc).split())[:300]  # beginnt mit empty / missing id / id mismatch
    return f"{type(exc).__name__}: {' '.join(str(exc).split())}"[:300]


def scan_automations(
    config: MaintenanceConfig,
) -> tuple[list[AutomationRecord], list[UnparseableAutomation]]:
    """Liest alle Tiefe-1-Automationen; unlesbare Dateien kommen als eigene Liste zurueck.

    Eine ``automation.toml`` mit TOML-Fehler (etwa doppelten ``model``-Schluesseln) darf
    nicht still aus der Verwaltung fallen: Pausieren und Wiederherstellen wuerden sie sonst
    nie sehen und trotzdem Erfolg melden.
    """
    root = automations_dir(config)
    if not root.exists():
        return [], []

    records: list[AutomationRecord] = []
    unparseable: list[UnparseableAutomation] = []
    for toml_path in sorted(root.glob("*/automation.toml")):
        try:
            data = _read_automation(toml_path)
        except _UNREADABLE as exc:
            unparseable.append(
                UnparseableAutomation(
                    id=toml_path.parent.name, path=toml_path, error=_unreadable_text(exc)
                )
            )
            continue
        automation_id = _quoted_string(data.get("id")).strip()
        records.append(
            AutomationRecord(
                id=automation_id,
                name=_quoted_string(data.get("name")) or automation_id,
                path=toml_path,
                status=_quoted_string(data.get("status")).strip().upper() or "UNKNOWN",
            )
        )
    return records, unparseable


def load_automations(config: MaintenanceConfig) -> list[AutomationRecord]:
    """Nur die lesbaren Definitionen; die unlesbaren liefert ``scan_automations``."""
    return scan_automations(config)[0]


def find_automation_anomalies(config: MaintenanceConfig) -> AutomationAnomalyReport:
    """Read-only Detektor fuer verschachtelte, id-duplizierte und unlesbare Automationen.

    Sucht ALLE ``automation.toml`` unter ``automations/`` (rekursiv, robust gegen
    beliebige Verschachtelung), bestimmt ihre Tiefe und gruppiert die ``id``-Werte:

    * **verschachtelt** = Tiefe > 1 (ein verwaister Duplikat-Ordner wie
      ``automations/sync-check/sync-check/automation.toml``). Solche Ordner werden
      vom Tiefe-1-Scan (``load_automations``) nicht verwaltet, laufen also unsichtbar.
    * **doppelte id** = derselbe ``id``-Wert in mehreren ``automation.toml`` (ueber
      alle Tiefenebenen). Ein rekursiver Scan in der Codex-App zaehlt die Automation
      dadurch doppelt.
    * **unlesbar** = ``automation.toml`` mit TOML- oder Kodierungsfehler oder ohne brauchbare
      Definition (leer, nur Kommentar, ``id`` fehlt oder leer; Pfad und Fehlertext im Befund). Sie
      zaehlt weder bei Verschachtelung noch bei Duplikaten mit. Eine ``id``, die vom Ordnernamen
      abweicht, ist hier ein normaler Befund (Doppel-id), kein Lesefehler.

    Aendert nichts auf der Platte und laesst ``load_automations`` (Tiefe 1) unberuehrt.
    """
    report = AutomationAnomalyReport()
    root = automations_dir(config)
    if not root.exists():
        return report

    findings: list[AutomationFinding] = []
    for toml_path in sorted(root.rglob("automation.toml")):
        try:
            data = _read_automation(toml_path, match_folder=False)
        except _UNREADABLE as exc:
            report.unparseable.append(
                UnparseableAutomation(
                    id=toml_path.parent.name, path=toml_path, error=_unreadable_text(exc)
                )
            )
            continue
        try:
            depth = len(toml_path.parent.relative_to(root).parts)
        except ValueError:
            continue
        automation_id = _quoted_string(data.get("id")).strip()
        findings.append(AutomationFinding(id=automation_id, path=toml_path, depth=depth))

    report.nested = [
        NestedAutomation(id=finding.id, path=finding.path, depth=finding.depth)
        for finding in findings
        if finding.nested
    ]

    by_id: dict[str, list[Path]] = {}
    for finding in findings:
        by_id.setdefault(finding.id, []).append(finding.path)
    report.duplicate_ids = [
        DuplicateAutomationId(id=automation_id, paths=sorted(paths))
        for automation_id, paths in sorted(by_id.items())
        if len(paths) > 1
    ]
    return report


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
    data = _read_automation(record.path)  # erneut pruefen: die Datei kann seit dem Scan abgeschnitten worden sein
    current = _quoted_string(data.get("status")).strip().upper()
    if current == status.strip().upper():
        return False
    data["status"] = status
    if "updated_at" in data:
        data["updated_at"] = _now_ms()
    _write_toml(record.path, data)
    return True


def _record_unparseable(
    result: AutomationControlResult, unparseable: list[UnparseableAutomation]
) -> None:
    """Unlesbare Definitionen sind unverarbeitet: als Fehler mit Pfad und Text ausweisen.

    Der Fehlereintrag beginnt mit dem Ordnernamen, so wie ``activate_carecenter_paused_automations``
    ihn fuer die noch offenen IDs erwartet; ``result.status`` wird dadurch nie "ok".
    """
    result.unparseable_ids = [item.id for item in unparseable]
    result.errors.extend(
        f"{item.id}: nicht lesbar ({item.path}): {item.error}" for item in unparseable
    )


def _activate_records(
    records: list[AutomationRecord],
    *,
    action: AutomationAction,
    staggered: bool,
    delay_seconds: int,
    sleeper: Sleeper,
    progress: ProgressCallback | None,
    unparseable: list[UnparseableAutomation] | None = None,
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
        except _UNREADABLE as exc:
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
    _record_unparseable(result, unparseable or [])
    if result.errors:
        result.status = "partial" if result.changed_ids else "failed"
    return result


def pause_active_automations(config: MaintenanceConfig) -> AutomationControlResult:
    records, unparseable = scan_automations(config)
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
        except _UNREADABLE as exc:
            result.errors.append(f"{record.id}: {exc}")
    _record_unparseable(result, unparseable)
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
    records, unparseable = scan_automations(config)
    by_id = {record.id: record for record in records}
    carecenter_ids = set(load_carecenter_paused_ids(config))
    target_ids = sorted(carecenter_ids)
    # Eine unlesbare Definition ist nicht "fehlend": ihre ID bleibt gemerkt (siehe ``failed`` unten).
    missing_ids = sorted(carecenter_ids - set(by_id) - {item.id for item in unparseable})
    target_records = [by_id[item] for item in target_ids if item in by_id]
    action: AutomationAction = "restore-ccc-staggered" if staggered else "restore-ccc"
    result = _activate_records(
        target_records,
        action=action,
        staggered=staggered,
        delay_seconds=delay_seconds,
        sleeper=sleeper,
        progress=progress,
        unparseable=unparseable,
    )
    result.missing_ids = missing_ids
    completed = set(result.changed_ids) | set(result.skipped_ids) | set(missing_ids)
    failed = {
        error.split(":", 1)[0]
        for error in result.errors
        if ":" in error
    }
    # Eine unlesbare Definition, die CareCenter nie pausiert hat, wird NICHT vorgemerkt: sonst
    # wuerde ein spaeterer Restore sie nach der Reparatur aktivieren, obwohl der Nutzer sie pausiert hatte.
    failed -= {item.id for item in unparseable} - carecenter_ids
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
    records, unparseable = scan_automations(config)
    result = _activate_records(
        records,
        action=action,
        staggered=staggered,
        delay_seconds=delay_seconds,
        sleeper=sleeper,
        progress=progress,
        unparseable=unparseable,
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
