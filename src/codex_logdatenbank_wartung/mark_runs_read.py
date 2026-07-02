"""Automations-Ergebnisse (Ungelesen-Zähler) der Codex-Desktop-App als gelesen markieren.

Die Codex-Desktop-App zeigt in der Sidebar "Automatisierungen <N>" als Ungelesen-Zähler
für durchgeführte, noch nicht geöffnete Automations-Läufe. Dieser Zustand wird LOKAL in
``CODEX_HOME/.codex-global-state.json`` persistiert:

    { "electron-persisted-atom-state": {
        "unread-thread-ids-by-host-v1": { "local": [<thread-id>, ...], ... } } }

"Alle als gelesen markieren" = alle Atom-States mit unread/thread/chat/conversation-Bezug
leeren. Das deckt neben ``unread-thread-ids-by-host-v1`` auch neuere/abweichende Chat-Keys
ab. Andere Atom-States bleiben unberührt.

Pflicht-Sicherheit (die Datei war schon einmal als ``.badstate`` korrupt):
* Nur bei GESCHLOSSENEM Codex schreiben -- läuft Codex, überschreibt es die Datei aus
  dem Speicher und die Änderung wäre wirkungslos/racy. Daher bei laufendem Codex ABBRUCH.
* Vor dem Schreiben ein Backup neben der Datei anlegen.
* Nur bei valide parsebarem JSON schreiben; bei Parse-Fehler ABBRUCH (kein Überschreiben).
* Atomar schreiben: temporäre Datei im selben Verzeichnis + ``os.replace``.
* Idempotent: bereits leere Listen / fehlender Key -> "nichts zu tun", kein Fehler.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .config import MaintenanceConfig
from .processes import ProcessProvider, find_codex_processes_by_executable

ATOM_STATE_KEY = "electron-persisted-atom-state"
UNREAD_KEY = "unread-thread-ids-by-host-v1"
UNREAD_KEY_TOKENS = ("thread", "chat", "conversation", "run")

# Status-Werte (analog zu den übrigen Result-Objekten im Projekt).
STATUS_OK = "ok"
STATUS_BLOCKED = "blocked"
STATUS_NOTHING = "nothing"
STATUS_FAILED = "failed"


@dataclass(slots=True)
class MarkRunsReadResult:
    """Ergebnis von :func:`mark_all_automation_runs_read`.

    status:
        ``ok``      -- Listen geleert und atomar zurückgeschrieben.
        ``blocked`` -- Codex lief; keine Dateiänderung.
        ``nothing`` -- nichts zu tun (Datei/Key fehlt oder Listen schon leer).
        ``failed``  -- Datei nicht lesbar/parsebar oder Schreibfehler; keine Änderung.
    """

    status: str
    cleared_count: int = 0
    state_path: str = ""
    backup_path: str | None = None
    dry_run: bool = False
    message: str = ""
    host_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_text(self) -> str:
        lines = [
            f"Status: {self.status}",
            self.message,
            f"Datei: {self.state_path}",
            f"Geleerte Ungelesen-Einträge: {self.cleared_count}",
        ]
        if self.host_counts:
            detail = ", ".join(f"{host}: {count}" for host, count in self.host_counts.items())
            lines.append(f"Bereiche: {detail}")
        if self.dry_run:
            lines.append("Dry-Run: keine Datei geändert.")
        if self.backup_path:
            lines.append(f"Backup: {self.backup_path}")
        return "\n".join(line for line in lines if line)


def global_state_path(config: MaintenanceConfig) -> Path:
    """Pfad zu ``CODEX_HOME/.codex-global-state.json``."""
    return config.codex_home / ".codex-global-state.json"


def _atomic_write_json(path: Path, data: object) -> None:
    """Schreibt JSON atomar: temporäre Datei im selben Verzeichnis + ``os.replace``.

    Standard-JSON (die App liest gewöhnliches JSON). ``ensure_ascii=False`` ist hier
    unkritisch, weil Thread-IDs ASCII sind; die übrige Struktur bleibt unverändert.
    """
    tmp = path.with_name(path.name + ".carecenter-tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _is_unread_state_key(key: object) -> bool:
    normalized = str(key).lower().replace("_", "-")
    return "unread" in normalized and any(token in normalized for token in UNREAD_KEY_TOKENS)


def _is_count_key(key: object) -> bool:
    normalized = str(key).lower().replace("_", "-")
    return "count" in normalized or "unread" in normalized


def _clear_matched_value(value: object, location: str, counts: dict[str, int]) -> int:
    """Leert den Wert eines passenden unread-Keys defensiv und zaehlt entfernte Marker."""
    if isinstance(value, list):
        cleared = len(value)
        value.clear()
        if cleared:
            counts[location] = counts.get(location, 0) + cleared
        return cleared

    if isinstance(value, dict):
        total = 0
        for child_key, child_value in list(value.items()):
            child_location = f"{location}.{child_key}"
            if isinstance(child_value, list):
                cleared = len(child_value)
                if cleared:
                    counts[child_location] = counts.get(child_location, 0) + cleared
                value[child_key] = []
                total += cleared
            elif isinstance(child_value, dict):
                total += _clear_matched_value(child_value, child_location, counts)
            elif _is_count_key(child_key) and isinstance(child_value, (int, float)) and not isinstance(child_value, bool):
                cleared = int(child_value)
                if cleared:
                    counts[child_location] = counts.get(child_location, 0) + cleared
                value[child_key] = 0
                total += max(0, cleared)
        return total

    return 0


def _clear_unread_atom_state(atom_state: dict[str, object]) -> dict[str, int]:
    counts: dict[str, int] = {}

    def walk(node: object, location: str) -> None:
        if not isinstance(node, dict):
            return
        for key, value in list(node.items()):
            child_location = f"{location}.{key}" if location else str(key)
            if _is_unread_state_key(key):
                _clear_matched_value(value, child_location, counts)
            elif isinstance(value, dict):
                walk(value, child_location)

    walk(atom_state, "")
    return counts


def mark_all_automation_runs_read(
    config: MaintenanceConfig,
    *,
    process_provider: ProcessProvider | None = None,
    dry_run: bool = False,
) -> MarkRunsReadResult:
    """Leert alle Ungelesen-Listen der Codex-Automations-Läufe (alle als gelesen markieren).

    Bricht ab, wenn Codex läuft (Schutz vor wirkungsloser/racy Änderung). Liest die
    ``.codex-global-state.json``, leert jede Host-Liste unter
    ``electron-persisted-atom-state.unread-thread-ids-by-host-v1`` und schreibt mit Backup
    atomar zurück. Idempotent und fail-closed bei Parse-/Schreibfehlern.

    process_provider und dry_run sind für Testbarkeit bzw. eine reine Vorschau gedacht.
    """
    state_path = global_state_path(config)
    path_str = str(state_path)

    # 1) Schutz: nur bei GESCHLOSSENEM Codex arbeiten.
    codex = find_codex_processes_by_executable(config, provider=process_provider)
    if codex:
        return MarkRunsReadResult(
            status=STATUS_BLOCKED,
            state_path=path_str,
            message=(
                "Codex läuft -- bitte Codex vollständig schließen und erneut ausführen. "
                "CareCenter beendet Codex nicht selbst, um laufende Automationen nicht abzubrechen."
            ),
        )

    # 2) Datei lesen + parsen. Fehlt sie -> nichts zu tun. Nicht parsebar -> ABBRUCH (kein Schreiben).
    if not state_path.exists():
        return MarkRunsReadResult(
            status=STATUS_NOTHING,
            state_path=path_str,
            message="Keine .codex-global-state.json gefunden -- nichts zu tun.",
        )
    try:
        raw = state_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError) as exc:
        # ValueError fängt JSONDecodeError UND UnicodeDecodeError (abgebrochener
        # Multibyte-Schreibvorgang). Original-Datei bleibt UNVERÄNDERT.
        return MarkRunsReadResult(
            status=STATUS_FAILED,
            state_path=path_str,
            message=f"Datei nicht lesbar oder kein valides JSON -- keine Änderung: {exc}",
        )

    # 3) Ungelesen-State lokalisieren. Jede Stufe defensiv -- fehlt/passt nicht -> nichts zu tun.
    atom_state = data.get(ATOM_STATE_KEY) if isinstance(data, dict) else None
    if not isinstance(atom_state, dict):
        return MarkRunsReadResult(
            status=STATUS_NOTHING,
            state_path=path_str,
            message="Kein Ungelesen-Zähler in der Datei -- nichts zu tun.",
        )

    host_counts = _clear_unread_atom_state(atom_state)
    cleared = sum(host_counts.values())
    if cleared == 0:
        return MarkRunsReadResult(
            status=STATUS_NOTHING,
            state_path=path_str,
            host_counts=host_counts,
            message="Alle Automations-Ergebnisse sind bereits gelesen -- nichts zu tun.",
        )

    # 4) Dry-Run: nur melden, nichts schreiben.
    if dry_run:
        return MarkRunsReadResult(
            status=STATUS_OK,
            cleared_count=cleared,
            state_path=path_str,
            dry_run=True,
            host_counts=host_counts,
            message=f"Dry-Run: {cleared} Eintrag/Einträge würden als gelesen markiert.",
        )

    # 5) Backup NACH erfolgreichem Parse und nur wenn es etwas zu leeren gab.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = state_path.with_name(f"{state_path.name}.carecenter-bak-{stamp}")
    try:
        backup_path.write_text(raw, encoding="utf-8")
    except OSError as exc:
        return MarkRunsReadResult(
            status=STATUS_FAILED,
            state_path=path_str,
            host_counts=host_counts,
            message=f"Backup fehlgeschlagen -- keine Änderung: {exc}",
        )

    # 6) Atomar zurückschreiben.
    try:
        _atomic_write_json(state_path, data)
    except OSError as exc:
        return MarkRunsReadResult(
            status=STATUS_FAILED,
            state_path=path_str,
            backup_path=str(backup_path),
            host_counts=host_counts,
            message=f"Schreiben fehlgeschlagen -- Backup liegt unter {backup_path}: {exc}",
        )

    return MarkRunsReadResult(
        status=STATUS_OK,
        cleared_count=cleared,
        state_path=path_str,
        backup_path=str(backup_path),
        host_counts=host_counts,
        message=f"{cleared} Automations-Ergebnis(se) als gelesen markiert.",
    )
