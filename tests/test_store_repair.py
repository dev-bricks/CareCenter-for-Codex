from __future__ import annotations

from codex_logdatenbank_wartung.store_repair import (
    build_command,
    open_store_page,
    repair_store_codex,
    store_package_status,
    store_pdp_uri,
)


def recording_runner(returncode: int = 0, output: str = "ok"):
    calls: list[str] = []

    def run(command: str) -> tuple[int, str]:
        calls.append(command)
        return returncode, output

    return run, calls


def test_build_command_per_level() -> None:
    assert "wsreset.exe" in build_command("wsreset")
    repair = build_command("repair", "OpenAI.Codex")
    assert "Add-AppxPackage" in repair and "AppXManifest.xml" in repair and "OpenAI.Codex" in repair
    assert build_command("reset", "OpenAI.Codex") == "Get-AppxPackage OpenAI.Codex | Reset-AppxPackage"


def test_dry_run_does_not_call_runner() -> None:
    run, calls = recording_runner()
    result = repair_store_codex(level="reset", execute=False, runner=run)
    assert result.dry_run is True
    assert calls == []  # kein echter Eingriff
    assert result.status == "dry-run"
    assert any(s.status == "planned" for s in result.steps)


def test_execute_repair_calls_runner_with_register() -> None:
    run, calls = recording_runner(returncode=0, output="registriert")
    result = repair_store_codex(level="repair", execute=True, runner=run)
    assert len(calls) == 1
    assert "Add-AppxPackage" in calls[0]
    assert result.status == "ok"


def test_execute_failure_is_reported() -> None:
    run, calls = recording_runner(returncode=1, output="Zugriff verweigert")
    result = repair_store_codex(level="wsreset", execute=True, runner=run)
    assert result.status == "failed"
    assert any("Zugriff verweigert" in s.message for s in result.steps)


def test_status_is_readonly_query() -> None:
    run, calls = recording_runner(output="OpenAI.Codex 26.513.4821.0 Status=Ok")
    text = store_package_status(runner=run)
    assert "OpenAI.Codex" in text
    assert len(calls) == 1
    assert "Get-AppxPackage" in calls[0]


# ---------------------------------------------------------------------------
# Store-Neuinstallation (absentes Paket): nur die Produktseite oeffnen, kein Eingriff
# ---------------------------------------------------------------------------

def test_store_pdp_uri_for_codex() -> None:
    assert store_pdp_uri("9PLM9XGG6VKS") == "ms-windows-store://pdp/?ProductId=9PLM9XGG6VKS"


def test_open_store_page_launches_pdp_uri() -> None:
    run, calls = recording_runner(returncode=0, output="")
    ok, detail = open_store_page("9PLM9XGG6VKS", runner=run)
    assert ok is True
    assert len(calls) == 1
    assert "ms-windows-store://pdp/?ProductId=9PLM9XGG6VKS" in calls[0]
    assert "Start-Process" in calls[0]


def test_open_store_page_reports_failure() -> None:
    run, _calls = recording_runner(returncode=1, output="kein Handler")
    ok, detail = open_store_page("9PLM9XGG6VKS", runner=run)
    assert ok is False
    assert "kein Handler" in detail
