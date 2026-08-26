from __future__ import annotations

import json
from pathlib import Path

from codex_logdatenbank_wartung.cli import main
from codex_logdatenbank_wartung.startup_receipt import build_startup_receipt

SECRETS = {
    "base": "BASE-INSTRUCTION-CONTENT",
    "developer": "DEVELOPER-BOOTSTRAP-CONTENT",
    "skills": "SKILL-CATALOG-CONTENT",
    "agents": "AGENTS-INJECTED-CONTENT",
    "hook": "PRE-USER-HOOK-CONTENT",
    "user": "REAL-USER-PROMPT-CONTENT",
    "assistant": "ASSISTANT-FIRST-ANSWER",
    "external": "EXTERNAL-BOOT-FILE-CONTENT",
}


def _event(event_type: str, payload: dict[str, object]) -> str:
    return json.dumps({"type": event_type, "payload": payload}, ensure_ascii=False)


def _message(role: str, text: str) -> str:
    return _event(
        "response_item",
        {"type": "message", "role": role, "content": [{"type": "input_text", "text": text}]},
    )


def _write_rollout(path: Path, *, invalid_after_first_turn: bool = False) -> None:
    lines = [
        _event(
            "session_meta",
            {
                "id": "thread-123",
                "timestamp": "2026-08-26T07:00:00Z",
                "cwd": r"C:\work",
                "originator": "codex_cli_rs",
                "cli_version": "1.2.3",
                "source": "cli",
                "model_provider": "openai",
                "base_instructions": SECRETS["base"],
            },
        ),
        _event("event_msg", {"type": "task_started"}),
        _message(
            "developer",
            SECRETS["developer"]
            + "<skills_instructions>"
            + SECRETS["skills"]
            + "</skills_instructions>",
        ),
        _message(
            "user",
            "# AGENTS.md instructions\n<INSTRUCTIONS>"
            + SECRETS["agents"]
            + "</INSTRUCTIONS><environment_context></environment_context>",
        ),
        _event("turn_context", {"turn_id": "turn-1", "cwd": r"C:\work"}),
        _message("developer", SECRETS["hook"]),
        _message("user", SECRETS["user"]),
        _event("event_msg", {"type": "user_message", "message": SECRETS["user"]}),
        _message("assistant", SECRETS["assistant"]),
    ]
    if invalid_after_first_turn:
        lines.append("{not-json-after-boundary")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _sources(report) -> dict[str, object]:
    return {source.category: source for source in report.sources}


def test_receipt_separates_first_turn_sources_without_exposing_content(tmp_path: Path) -> None:
    rollout = tmp_path / "rollout.jsonl"
    boot = tmp_path / "GPT.md"
    _write_rollout(rollout, invalid_after_first_turn=True)
    boot.write_text(SECRETS["external"], encoding="utf-8")

    report = build_startup_receipt(rollout, external_boot_files=[("GPT", boot)])
    encoded = json.dumps(report.to_dict(), ensure_ascii=False)
    sources = _sources(report)

    assert report.status == "ok"
    assert set(sources) == {
        "session_meta_base_instructions",
        "developer_bootstrap",
        "skills_catalog",
        "agents_injected_user",
        "pre_user_hook_messages",
        "user_prompt",
    }
    assert sources["skills_catalog"].characters == len(
        "<skills_instructions>" + SECRETS["skills"] + "</skills_instructions>"
    )
    assert report.external_boot_files[0].injection_claim is False
    assert report.external_boot_files[0].characters == len(SECRETS["external"])
    for secret in SECRETS.values():
        assert secret not in encoded


def test_receipt_stops_before_invalid_data_after_first_assistant_boundary(tmp_path: Path) -> None:
    rollout = tmp_path / "rollout.jsonl"
    _write_rollout(rollout, invalid_after_first_turn=True)

    report = build_startup_receipt(rollout)

    assert report.status == "ok"
    assert report.errors == []


def test_receipt_supports_structured_base_instructions_without_provenance_content(
    tmp_path: Path,
) -> None:
    rollout = tmp_path / "structured-base.jsonl"
    provenance_secret = "PROVENANCE-MUST-NOT-LEAK"
    lines = [
        _event(
            "session_meta",
            {
                "id": "structured",
                "base_instructions": {
                    "text": SECRETS["base"],
                    "provenance": {
                        "source": "codex-runtime",
                        "version": "1",
                        "content": provenance_secret,
                        "nested": {"text": provenance_secret},
                    },
                },
            },
        ),
        _event("turn_context", {"turn_id": "turn-1"}),
        _message("user", SECRETS["user"]),
        _message("assistant", SECRETS["assistant"]),
    ]
    rollout.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = build_startup_receipt(rollout)
    sources = _sources(report)
    encoded = json.dumps(report.to_dict(), ensure_ascii=False)

    assert sources["session_meta_base_instructions"].characters == len(SECRETS["base"])
    assert report.session_metadata["base_instructions_provenance"] == {
        "source": "codex-runtime",
        "version": "1",
    }
    assert SECRETS["base"] not in encoded
    assert provenance_secret not in encoded


def test_receipt_reports_invalid_json_before_user_prompt_deterministically(tmp_path: Path) -> None:
    rollout = tmp_path / "broken.jsonl"
    rollout.write_text(
        _event("session_meta", {"id": "broken", "base_instructions": "base"})
        + "\n{broken\n",
        encoding="utf-8",
    )

    report = build_startup_receipt(rollout)

    assert report.status == "error"
    assert report.errors == [
        {"code": "INVALID_JSONL", "line": 2, "message": "Ungültiges JSON in Zeile 2."}
    ]


def test_cli_json_is_read_only_and_reports_missing_explicit_boot_file(
    tmp_path: Path, capsys
) -> None:
    rollout = tmp_path / "rollout.jsonl"
    _write_rollout(rollout)
    before = rollout.stat().st_mtime_ns

    rc = main(
        [
            "startup-receipt",
            str(rollout),
            "--boot-file",
            f"CLAUDE={tmp_path / 'missing-CLAUDE.md'}",
            "--format",
            "json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert rc == 1
    assert rollout.stat().st_mtime_ns == before
    assert payload["errors"][0]["code"] == "BOOT_FILE_NOT_FOUND"
    assert payload["external_boot_files"][0]["present"] is False


def test_cli_text_never_prints_prompt_contents(tmp_path: Path, capsys) -> None:
    rollout = tmp_path / "rollout.jsonl"
    _write_rollout(rollout)

    rc = main(["startup-receipt", str(rollout), "--format", "text"])
    output = capsys.readouterr().out

    assert rc == 0
    assert "Startup-Receipt" in output
    for secret in SECRETS.values():
        assert secret not in output
