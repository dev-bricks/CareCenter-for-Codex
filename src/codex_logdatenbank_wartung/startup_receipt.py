"""Promptfreier, read-only Herkunftsbeleg für den ersten Codex-Rollout-Turn."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

SOURCE_ORDER = (
    "session_meta_base_instructions",
    "developer_bootstrap",
    "skills_catalog",
    "agents_injected_user",
    "pre_user_hook_messages",
    "user_prompt",
)
_SKILLS_BLOCK = re.compile(
    r"<skills_instructions>.*?</skills_instructions>",
    re.DOTALL,
)
_SESSION_METADATA_FIELDS = (
    "id",
    "session_id",
    "timestamp",
    "cwd",
    "originator",
    "cli_version",
    "source",
    "thread_source",
    "model_provider",
    "history_mode",
    "context_window",
)
_BASE_PROVENANCE_FIELDS = (
    "source",
    "origin",
    "kind",
    "type",
    "name",
    "path",
    "sha256",
    "version",
    "generated_at",
    "updated_at",
)


@dataclass(frozen=True, slots=True)
class SourceReceipt:
    category: str
    provenance: str
    present: bool
    occurrences: int
    characters: int
    utf8_bytes: int
    sha256: str | None
    event_lines: list[int]


@dataclass(frozen=True, slots=True)
class ExternalBootFileReceipt:
    label: str
    path: str
    present: bool
    characters: int
    utf8_bytes: int
    sha256: str | None
    injection_claim: bool = False


@dataclass(slots=True)
class StartupReceipt:
    status: str
    rollout: dict[str, object]
    session_metadata: dict[str, object]
    sources: list[SourceReceipt]
    external_boot_files: list[ExternalBootFileReceipt]
    errors: list[dict[str, object]]
    schema_version: int = 1

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "rollout": self.rollout,
            "session_metadata": self.session_metadata,
            "sources": [asdict(source) for source in self.sources],
            "external_boot_files": [asdict(item) for item in self.external_boot_files],
            "errors": self.errors,
        }

    def to_text(self) -> str:
        lines = [
            f"Startup-Receipt: {self.status.upper()}",
            f"Rollout: {self.rollout['path']}",
            (
                "Erster Turn: "
                f"{self.rollout.get('first_turn_lines', 0)} Zeilen, "
                f"{self.rollout.get('first_turn_bytes', 0)} Bytes, "
                f"SHA-256 {self.rollout.get('first_turn_sha256') or '-'}"
            ),
        ]
        for source in self.sources:
            lines.append(
                f"- {source.category}: {source.occurrences} Quelle(n), "
                f"{source.characters} Zeichen, {source.utf8_bytes} Bytes, "
                f"SHA-256 {source.sha256 or '-'}"
            )
        for item in self.external_boot_files:
            lines.append(
                f"- externe_bootdatei[{item.label}]: present={str(item.present).lower()}, "
                f"{item.characters} Zeichen, {item.utf8_bytes} Bytes, "
                f"SHA-256 {item.sha256 or '-'}, injection_claim=false, Pfad={item.path}"
            )
        for error in self.errors:
            lines.append(f"FEHLER {error['code']}: {error['message']}")
        return "\n".join(lines)


def _message_texts(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return []
    content = payload.get("content")
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []
    texts: list[str] = []
    for item in content:
        if isinstance(item, str):
            texts.append(item)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            texts.append(item["text"])
    return texts


def _split_skills(text: str) -> tuple[str, list[str]]:
    matches = [match.group(0) for match in _SKILLS_BLOCK.finditer(text)]
    return _SKILLS_BLOCK.sub("", text), matches


def _safe_base_provenance(base_instructions: dict[str, object]) -> dict[str, object]:
    provenance = base_instructions.get("provenance")
    if not isinstance(provenance, dict):
        return {}
    return {
        field: provenance[field]
        for field in _BASE_PROVENANCE_FIELDS
        if field in provenance and isinstance(provenance[field], (str, int, float, bool))
    }


def _source_receipts(
    content: dict[str, list[tuple[int, str]]],
) -> list[SourceReceipt]:
    provenance = {
        "session_meta_base_instructions": "session_meta.payload.base_instructions",
        "developer_bootstrap": "response_item.message.developer before turn_context",
        "skills_catalog": "marked <skills_instructions> block",
        "agents_injected_user": "marked AGENTS-injected response_item.user",
        "pre_user_hook_messages": "response_item.developer after turn_context before user",
        "user_prompt": "first unmarked response_item.user",
    }
    receipts: list[SourceReceipt] = []
    for category in SOURCE_ORDER:
        entries = content[category]
        encoded = [text.encode("utf-8") for _, text in entries]
        payload = b"".join(encoded)
        receipts.append(
            SourceReceipt(
                category=category,
                provenance=provenance[category],
                present=bool(entries),
                occurrences=len(entries),
                characters=sum(len(text) for _, text in entries),
                utf8_bytes=sum(len(item) for item in encoded),
                sha256=hashlib.sha256(payload).hexdigest().upper() if entries else None,
                event_lines=sorted({line for line, _ in entries}),
            )
        )
    return receipts


def _external_receipts(
    specifications: list[tuple[str, Path]],
    errors: list[dict[str, object]],
) -> list[ExternalBootFileReceipt]:
    receipts: list[ExternalBootFileReceipt] = []
    for label, source in specifications:
        path = Path(source)
        try:
            payload = path.read_bytes()
        except FileNotFoundError:
            receipts.append(ExternalBootFileReceipt(label, str(path), False, 0, 0, None))
            errors.append(
                {
                    "code": "BOOT_FILE_NOT_FOUND",
                    "path": str(path),
                    "message": f"Explizite Bootdatei fehlt: {path}",
                }
            )
            continue
        except OSError as exc:
            receipts.append(ExternalBootFileReceipt(label, str(path), False, 0, 0, None))
            errors.append(
                {
                    "code": "BOOT_FILE_UNREADABLE",
                    "path": str(path),
                    "message": f"Explizite Bootdatei ist nicht lesbar: {path} ({exc})",
                }
            )
            continue
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            receipts.append(
                ExternalBootFileReceipt(
                    label,
                    str(path),
                    True,
                    0,
                    len(payload),
                    hashlib.sha256(payload).hexdigest().upper(),
                )
            )
            errors.append(
                {
                    "code": "BOOT_FILE_INVALID_UTF8",
                    "path": str(path),
                    "message": f"Explizite Bootdatei ist kein gültiges UTF-8: {path}",
                }
            )
            continue
        receipts.append(
            ExternalBootFileReceipt(
                label=label,
                path=str(path),
                present=True,
                characters=len(text),
                utf8_bytes=len(payload),
                sha256=hashlib.sha256(payload).hexdigest().upper(),
            )
        )
    return receipts


def build_startup_receipt(
    rollout_path: Path,
    *,
    external_boot_files: list[tuple[str, Path]] | None = None,
) -> StartupReceipt:
    """Liest sequenziell nur bis zur ersten Assistant-Grenze des ersten Turns."""
    path = Path(rollout_path)
    errors: list[dict[str, object]] = []
    content: dict[str, list[tuple[int, str]]] = {category: [] for category in SOURCE_ORDER}
    external = _external_receipts(list(external_boot_files or ()), errors)
    rollout: dict[str, object] = {
        "path": str(path),
        "present": path.is_file(),
        "first_turn_lines": 0,
        "lines_scanned": 0,
        "first_turn_bytes": 0,
        "first_turn_sha256": None,
        "stop_reason": "input_error",
    }
    session_metadata: dict[str, object] = {}
    first_turn_hash = hashlib.sha256()
    first_turn_bytes = 0
    first_turn_lines = 0
    seen_turn_context = False
    seen_user_prompt = False
    seen_session_meta = False

    try:
        handle = path.open("rb")
    except FileNotFoundError:
        errors.append(
            {"code": "ROLLOUT_NOT_FOUND", "message": f"Rollout-Datei fehlt: {path}"}
        )
        return StartupReceipt(
            "error", rollout, session_metadata, _source_receipts(content), external, errors
        )
    except OSError as exc:
        errors.append(
            {
                "code": "ROLLOUT_UNREADABLE",
                "message": f"Rollout-Datei ist nicht lesbar: {path} ({exc})",
            }
        )
        return StartupReceipt(
            "error", rollout, session_metadata, _source_receipts(content), external, errors
        )

    with handle:
        for line_number, raw_line in enumerate(handle, start=1):
            rollout["lines_scanned"] = line_number
            if not raw_line.strip():
                first_turn_hash.update(raw_line)
                first_turn_bytes += len(raw_line)
                first_turn_lines += 1
                continue
            try:
                decoded = raw_line.decode("utf-8-sig")
            except UnicodeDecodeError:
                errors.append(
                    {
                        "code": "INVALID_UTF8",
                        "line": line_number,
                        "message": f"Ungültiges UTF-8 in Zeile {line_number}.",
                    }
                )
                break
            try:
                event = json.loads(decoded)
            except json.JSONDecodeError:
                errors.append(
                    {
                        "code": "INVALID_JSONL",
                        "line": line_number,
                        "message": f"Ungültiges JSON in Zeile {line_number}.",
                    }
                )
                break
            if not isinstance(event, dict):
                errors.append(
                    {
                        "code": "INVALID_EVENT",
                        "line": line_number,
                        "message": f"JSONL-Ereignis in Zeile {line_number} ist kein Objekt.",
                    }
                )
                break

            payload = event.get("payload")
            if not isinstance(payload, dict):
                payload = {}
            event_type = event.get("type")
            item_type = payload.get("type")
            role = payload.get("role")

            if (
                seen_user_prompt
                and event_type == "response_item"
                and item_type == "message"
                and role == "assistant"
            ):
                rollout["stop_reason"] = "first_assistant_boundary"
                break

            first_turn_hash.update(raw_line)
            first_turn_bytes += len(raw_line)
            first_turn_lines += 1

            if event_type == "session_meta":
                seen_session_meta = True
                session_metadata = {
                    field: payload[field]
                    for field in _SESSION_METADATA_FIELDS
                    if field in payload and not isinstance(payload[field], (dict, list))
                }
                base = payload.get("base_instructions")
                if isinstance(base, str):
                    content["session_meta_base_instructions"].append((line_number, base))
                elif isinstance(base, dict) and isinstance(base.get("text"), str):
                    content["session_meta_base_instructions"].append(
                        (line_number, base["text"])
                    )
                    if provenance := _safe_base_provenance(base):
                        session_metadata["base_instructions_provenance"] = provenance
                continue
            if event_type == "turn_context":
                seen_turn_context = True
                continue
            if event_type != "response_item" or item_type != "message":
                continue

            texts = _message_texts(payload)
            if role == "developer":
                destination = (
                    "pre_user_hook_messages"
                    if seen_turn_context and not seen_user_prompt
                    else "developer_bootstrap"
                )
                for text in texts:
                    remainder, skills = _split_skills(text)
                    if remainder:
                        content[destination].append((line_number, remainder))
                    content["skills_catalog"].extend((line_number, block) for block in skills)
            elif role == "user":
                if any("# AGENTS.md instructions" in text for text in texts):
                    content["agents_injected_user"].extend(
                        (line_number, text) for text in texts
                    )
                elif not seen_user_prompt:
                    content["user_prompt"].extend((line_number, text) for text in texts)
                    seen_user_prompt = True

    if rollout["stop_reason"] == "input_error" and not errors:
        rollout["stop_reason"] = "eof_after_user" if seen_user_prompt else "eof_before_user"
    rollout["first_turn_lines"] = first_turn_lines
    rollout["first_turn_bytes"] = first_turn_bytes
    rollout["first_turn_sha256"] = (
        first_turn_hash.hexdigest().upper() if first_turn_lines else None
    )
    if not errors and not seen_session_meta:
        errors.append(
            {"code": "SESSION_META_MISSING", "message": "session_meta fehlt im ersten Turn."}
        )
    if not errors and not seen_user_prompt:
        errors.append(
            {"code": "USER_PROMPT_MISSING", "message": "Echter User-Prompt fehlt im ersten Turn."}
        )
    status = "error" if errors else "ok"
    return StartupReceipt(
        status,
        rollout,
        session_metadata,
        _source_receipts(content),
        external,
        errors,
    )
