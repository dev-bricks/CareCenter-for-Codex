"""Static contracts for TASKPLAN status, Safe Start pinning and bounded repair."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ci_and_build_extra_use_the_same_immutable_safe_start_revision():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    pin = "dcb369a64f403f6551bcb3bac16565c56ec79474"

    assert pin in pyproject
    assert pin in workflow
    assert "@main" not in workflow


def test_repair_entrypoint_states_the_bounded_automatic_contract():
    source = (ROOT / "src" / "codex_logdatenbank_wartung" / "repair_workflow.py").read_text(encoding="utf-8")

    assert "S1, S2,\nS3" in source
    assert "S4 removal and S6 reinstall\nare never started automatically" in source


def test_current_metadata_marks_old_handoff_as_historical_via_current_state():
    state = (ROOT / "STATE.md").read_text(encoding="utf-8")
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    assert "Stand: 2026-07-22 · Version 0.8.0" in state
    assert "version: 0.8.0" in claude
