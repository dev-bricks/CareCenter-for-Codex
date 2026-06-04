"""Tests fuer die LIVE-Reparatur-Bausteine (repair_live).

Es wird NIE eine echte AppX-Operation ausgefuehrt: PowerShell-Aufrufe laufen ueber
einen injizierten Runner, und die Prozessdiagnose wird ueber einen gefakten
ProcessProvider bzw. ein gemocktes ``diagnose`` gespeist. Die hang-sichere
Eskalationslogik (``run_repair``) ist bereits in ``test_repair_workflow`` abgedeckt
und wird hier NICHT dupliziert.
"""

from __future__ import annotations

import json
from pathlib import Path

from codex_logdatenbank_wartung import cli, repair_live
from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.repair_live import (
    build_live_deps,
    parse_codex_packages,
    parse_package_absence,
)
from codex_logdatenbank_wartung.repair_workflow import AdminRequired, DeployTimeout

CODEX_EXE = r"C:\Users\dev\AppData\Local\Programs\Codex\Codex.exe"
USER_SID = "S-1-5-21-111-222-333-1001"


def make_config(tmp_path: Path) -> MaintenanceConfig:
    return MaintenanceConfig(
        database_path=str(tmp_path / "logs_2.sqlite"),
        backup_dir=str(tmp_path / "backups"),
        log_dir=str(tmp_path / "logs"),
        maintenance_lock_path=str(tmp_path / "maintenance.lock"),
        codex_executable=CODEX_EXE,
        codex_user_data_dir=str(tmp_path / "user-data"),
    )


# Eine getreue Projektion des dokumentierten staged-Wedge:
# neuere Version (26.519) ist fuer SYSTEM (S-1-5-18) 'Staged',
# der User ist nur auf der aelteren Version (26.513) 'Installed'.
def staged_wedge_json() -> str:
    return json.dumps(
        {
            "CurrentUserSid": USER_SID,
            "Packages": [
                {
                    "FullName": "OpenAI.Codex_26.513.0.0_x64__2p2nqsd0c76g0",
                    "Version": "26.513.0.0",
                    "Users": [{"Sid": USER_SID, "State": "Installed"}],
                },
                {
                    "FullName": "OpenAI.Codex_26.519.0.0_x64__2p2nqsd0c76g0",
                    "Version": "26.519.0.0",
                    "Users": [{"Sid": "S-1-5-18", "State": "Staged"}],
                },
            ],
        }
    )


def absent_json(windowsapps: bool | None = None) -> str:
    """Erfolgreiche, aber LEERE -AllUsers-Abfrage: gar kein Codex-Paket mehr da."""
    obj: dict[str, object] = {"CurrentUserSid": USER_SID, "Packages": []}
    if windowsapps is not None:
        obj["WindowsAppsPresent"] = windowsapps
    return json.dumps(obj)


def healthy_json() -> str:
    return json.dumps(
        {
            "CurrentUserSid": USER_SID,
            "Packages": [
                {
                    "FullName": "OpenAI.Codex_26.519.0.0_x64__2p2nqsd0c76g0",
                    "Version": "26.519.0.0",
                    "Users": [{"Sid": USER_SID, "State": "Installed"}],
                }
            ],
        }
    )


# ---------------------------------------------------------------------------
# parse_codex_packages (pure Funktion)
# ---------------------------------------------------------------------------

def test_parse_detects_staged_wedge() -> None:
    staged, registered, pfn = parse_codex_packages(staged_wedge_json())
    assert staged is True
    # Der User IST auf der aelteren Version registriert -> package_user_registered True.
    assert registered is True
    # Ziel fuer remove_staged_version = die neuere gestagte PFN.
    assert pfn == "OpenAI.Codex_26.519.0.0_x64__2p2nqsd0c76g0"


def test_parse_healthy_no_wedge() -> None:
    staged, registered, pfn = parse_codex_packages(healthy_json())
    assert staged is False
    assert registered is True
    assert pfn == ""


def test_parse_user_not_registered_at_all() -> None:
    # Nur eine gestagte SYSTEM-Version, User hat NICHTS installiert -> Wedge + nicht registriert.
    data = json.dumps(
        {
            "CurrentUserSid": USER_SID,
            "Packages": [
                {
                    "FullName": "OpenAI.Codex_26.519.0.0_x64__2p2nqsd0c76g0",
                    "Version": "26.519.0.0",
                    "Users": [{"Sid": "S-1-5-18", "State": "Staged"}],
                }
            ],
        }
    )
    staged, registered, pfn = parse_codex_packages(data)
    assert staged is True
    assert registered is False
    assert pfn == "OpenAI.Codex_26.519.0.0_x64__2p2nqsd0c76g0"


def test_parse_single_element_collapsed_object() -> None:
    # PowerShell faltet einelementige Arrays zu blossem Objekt -> muss toleriert werden.
    data = json.dumps(
        {
            "CurrentUserSid": USER_SID,
            "Packages": {
                "FullName": "OpenAI.Codex_26.519.0.0_x64__2p2nqsd0c76g0",
                "Version": "26.519.0.0",
                "Users": {"Sid": USER_SID, "State": "Installed"},
            },
        }
    )
    staged, registered, pfn = parse_codex_packages(data)
    assert staged is False
    assert registered is True


def test_parse_version_compared_numerically_not_lexically() -> None:
    # User auf 26.5 (Installed), SYSTEM staged 26.519 -> 26.519 > 26.5 numerisch (nicht lexikalisch).
    data = json.dumps(
        {
            "CurrentUserSid": USER_SID,
            "Packages": [
                {
                    "FullName": "OpenAI.Codex_26.5.0.0_x64__2p2nqsd0c76g0",
                    "Version": "26.5.0.0",
                    "Users": [{"Sid": USER_SID, "State": "Installed"}],
                },
                {
                    "FullName": "OpenAI.Codex_26.519.0.0_x64__2p2nqsd0c76g0",
                    "Version": "26.519.0.0",
                    "Users": [{"Sid": "S-1-5-18", "State": "Staged"}],
                },
            ],
        }
    )
    staged, _registered, pfn = parse_codex_packages(data)
    assert staged is True
    assert pfn == "OpenAI.Codex_26.519.0.0_x64__2p2nqsd0c76g0"


def test_parse_empty_or_garbage_is_conservative() -> None:
    for text in ("{}", "", "not-json", "[]"):
        staged, registered, pfn = parse_codex_packages(text)
        assert staged is False
        assert registered is True
        assert pfn == ""


# ---------------------------------------------------------------------------
# parse_package_absence: "Paket wirklich weg" von "Abfrage fehlgeschlagen" trennen
# ---------------------------------------------------------------------------

def test_absence_true_on_successful_empty_query() -> None:
    # Erfolgreiche AllUsers-Abfrage mit leerer Paketliste -> Paket absent.
    assert parse_package_absence(absent_json()) is True
    assert parse_package_absence(absent_json(windowsapps=False)) is True


def test_absence_false_when_windowsapps_dir_still_present() -> None:
    # Leere Paketliste, aber WindowsApps-Ordner existiert -> konservativ NICHT absent.
    assert parse_package_absence(absent_json(windowsapps=True)) is False


def test_absence_false_on_failed_or_garbage_query() -> None:
    # '{}' = catch-Fallback (Abfrage fehlgeschlagen, z.B. Zugriff verweigert) -> NICHT absent.
    for text in ("{}", "", "not-json", "[]"):
        assert parse_package_absence(text) is False


def test_absence_false_when_packages_present() -> None:
    assert parse_package_absence(staged_wedge_json()) is False
    assert parse_package_absence(healthy_json()) is False


def test_absence_handles_ps51_empty_serialization_forms() -> None:
    # Windows PowerShell 5.1 serialisiert eine leere '@()'-Liste je nach Lage als
    # [], null oder "". Alle drei muessen als "absent" gewertet werden.
    for empty in ("[]", "null", '""'):
        text = '{"CurrentUserSid":"' + USER_SID + '","Packages":' + empty + "}"
        assert parse_package_absence(text) is True, empty


# ---------------------------------------------------------------------------
# build_live_deps.observe (mit injiziertem Runner + gemocktem diagnose)
# ---------------------------------------------------------------------------

def fake_runner(packages_json: str, clipsvc: str = "Running"):
    """Runner-Fake: liefert je nach Befehl die ClipSVC- oder die Paket-Projektion."""
    calls: list[str] = []

    def run(command: str) -> tuple[int, str]:
        calls.append(command)
        if "ClipSVC" in command and "Get-Service" in command:
            return 0, clipsvc
        if "Get-AppxPackage" in command:
            return 0, packages_json
        return 0, ""

    return run, calls


class _Report:
    """Minimaler HealthReport-Stand-in fuer den observe-Test."""

    main_pids: list[int] = []
    renderer_present = False
    zombie_main_pids: list[int] = [4242]
    stale_lockfile = True
    codex_exe_present = True


def test_observe_detects_staged_wedge(tmp_path: Path, monkeypatch) -> None:
    config = make_config(tmp_path)
    run, _calls = fake_runner(staged_wedge_json(), clipsvc="Stopped")
    # diagnose hermetisch halten (keine echten Prozesse abfragen).
    monkeypatch.setattr(
        "codex_logdatenbank_wartung.health.diagnose", lambda _cfg: _Report()
    )

    deps = build_live_deps(config, runner=run)
    state = deps.observe()

    assert state.staged_update is True
    assert state.package_user_registered is True
    assert state.clipsvc_running is False  # 'Stopped' -> nicht laufend
    assert state.ghost_pids == [4242]
    assert state.stale_lockfile is True


def test_observe_healthy(tmp_path: Path, monkeypatch) -> None:
    config = make_config(tmp_path)
    run, _calls = fake_runner(healthy_json(), clipsvc="Running")

    class _Clean:
        main_pids: list[int] = [10]
        renderer_present = True
        zombie_main_pids: list[int] = []
        stale_lockfile = False
        codex_exe_present = True

    monkeypatch.setattr(
        "codex_logdatenbank_wartung.health.diagnose", lambda _cfg: _Clean()
    )
    deps = build_live_deps(config, runner=run)
    state = deps.observe()
    assert state.staged_update is False
    assert state.clipsvc_running is True
    assert state.renderer_present is True


def test_observe_detects_absent_package(tmp_path: Path, monkeypatch) -> None:
    config = make_config(tmp_path)
    run, _calls = fake_runner(absent_json(windowsapps=False), clipsvc="Stopped")
    monkeypatch.setattr(
        "codex_logdatenbank_wartung.health.diagnose", lambda _cfg: _Report()
    )
    deps = build_live_deps(config, runner=run)
    state = deps.observe()
    assert state.package_absent is True
    assert state.staged_update is False


def test_observe_not_absent_when_query_fails(tmp_path: Path, monkeypatch) -> None:
    # Runner liefert '{}' (z.B. nicht-elevated 'Zugriff verweigert') -> NICHT als absent werten.
    run, _calls = fake_runner("{}", clipsvc="Running")
    monkeypatch.setattr(
        "codex_logdatenbank_wartung.health.diagnose", lambda _cfg: _Report()
    )
    deps = build_live_deps(make_config(tmp_path), runner=run)
    state = deps.observe()
    assert state.package_absent is False


def test_reinstall_package_never_removes(tmp_path: Path, monkeypatch) -> None:
    """Orphan-Sicherheit festnageln: reinstall_package darf NIE 'Remove-AppxPackage' ausfuehren.

    Lektion 29.05: Ein Remove (auch ohne -AllUsers) loescht die letzte Paket-Referenz und damit
    die Payload -- danach kann 'Add' nichts mehr registrieren. Das hardening-Versprechen lautet:
    nur idempotentes Re-Register, kein destruktiver Schritt.
    """
    recorded: list[str] = []

    def run(command: str) -> tuple[int, str]:
        recorded.append(command)
        return 0, "ok"

    monkeypatch.setattr(
        "codex_logdatenbank_wartung.health.diagnose", lambda _cfg: _Report()
    )
    deps = build_live_deps(make_config(tmp_path), runner=run)
    deps.reinstall_package()
    joined = " ".join(recorded)
    assert "Remove-AppxPackage" not in joined  # nie destruktiv
    assert "RegisterByFamilyName" in joined  # aber: registriert idempotent neu


def test_observe_runner_failure_falls_back_safely(tmp_path: Path, monkeypatch) -> None:
    config = make_config(tmp_path)

    def boom(_command: str) -> tuple[int, str]:
        raise RuntimeError("PowerShell verklemmt")

    monkeypatch.setattr(
        "codex_logdatenbank_wartung.health.diagnose", lambda _cfg: _Report()
    )
    deps = build_live_deps(config, runner=boom)
    state = deps.observe()
    # Beobachtung darf nie crashen -> konservative Defaults.
    assert state.staged_update is False
    assert state.package_user_registered is True
    assert state.clipsvc_running is True


# ---------------------------------------------------------------------------
# Fehlerart-Klassifikation der Deploy-Ops (intelligenter Prozess, 2026-06-01)
# ---------------------------------------------------------------------------

def test_classify_ps_outcome_timeout() -> None:
    assert repair_live.classify_ps_outcome(124, "PowerShell-Timeout") == "timeout"


def test_classify_ps_outcome_ok() -> None:
    assert repair_live.classify_ps_outcome(0, "") == "ok"
    assert repair_live.classify_ps_outcome(0, "Deployment operation completed") == "ok"


def test_classify_ps_outcome_admin_de_en_hresult() -> None:
    # Eindeutige Access-Denied-Signale (DE/EN/HRESULT) -> needs_admin.
    assert repair_live.classify_ps_outcome(1, "Access is denied.") == "needs_admin"
    assert repair_live.classify_ps_outcome(1, "Zugriff verweigert") == "needs_admin"
    assert repair_live.classify_ps_outcome(1, "Add-AppxPackage : Fehler 0x80070005") == "needs_admin"
    assert repair_live.classify_ps_outcome(1, "This operation requires elevation.") == "needs_admin"


def test_classify_ps_outcome_corruption_is_failed_not_admin() -> None:
    # 0x80073CF9 'package could not be registered' = Korruption, NICHT Admin -> failed -> Fallback.
    assert (
        repair_live.classify_ps_outcome(1, "error 0x80073CF9: package could not be registered")
        == "failed"
    )
    assert repair_live.classify_ps_outcome(1, "irgendein unklarer Fehler") == "failed"


def test_raise_for_deploy_admin_timeout_and_clean() -> None:
    import pytest

    with pytest.raises(DeployTimeout):
        repair_live._raise_for_deploy(124, "PowerShell-Timeout")
    with pytest.raises(AdminRequired):
        repair_live._raise_for_deploy(1, "Access is denied")
    # ok/failed (unklar) -> KEIN raise (Fallback bleibt moeglich).
    repair_live._raise_for_deploy(0, "ok")
    repair_live._raise_for_deploy(1, "0x80073CF9 corruption")


def test_complete_staged_update_raises_admin_on_access_denied(tmp_path: Path, monkeypatch) -> None:
    """Die LIVE-Deploy-Op wirft AdminRequired, wenn der mutierende Befehl Access Denied liefert."""
    import pytest

    def run(command: str) -> tuple[int, str]:
        if "RegisterByFamilyName" in command:
            return 1, "Add-AppxPackage : Access is denied"
        return 0, ""

    monkeypatch.setattr(
        "codex_logdatenbank_wartung.health.diagnose", lambda _cfg: _Report()
    )
    deps = build_live_deps(make_config(tmp_path), runner=run)
    with pytest.raises(AdminRequired):
        deps.complete_staged_update()


def test_reset_package_raises_timeout_on_rc124(tmp_path: Path, monkeypatch) -> None:
    """reset_package wirft DeployTimeout, wenn der Runner den Timeout-Sentinel (124) liefert."""
    import pytest

    def run(_command: str) -> tuple[int, str]:
        return 124, "PowerShell-Timeout"

    monkeypatch.setattr(
        "codex_logdatenbank_wartung.health.diagnose", lambda _cfg: _Report()
    )
    deps = build_live_deps(make_config(tmp_path), runner=run)
    with pytest.raises(DeployTimeout):
        deps.reset_package()


# ---------------------------------------------------------------------------
# default_ps_runner: hang-hart (Tree-Kill bei Timeout, rc=124-Vertrag)
# ---------------------------------------------------------------------------

def test_default_ps_runner_timeout_returns_124_and_tree_kills(monkeypatch) -> None:
    import subprocess as sp

    killed: list[int] = []

    class FakeProc:
        pid = 4321

        def communicate(self, timeout=None):
            raise sp.TimeoutExpired(cmd="powershell", timeout=timeout)

    monkeypatch.setattr(sp, "Popen", lambda *a, **k: FakeProc())
    monkeypatch.setattr(repair_live, "_tree_kill", lambda pid: killed.append(pid))

    rc, out = repair_live.default_ps_runner("Start-Sleep 999", timeout=0.01)
    assert rc == 124
    assert killed == [4321]  # ganzer Prozessbaum hart beendet


def test_default_ps_runner_success_returns_rc_and_output(monkeypatch) -> None:
    import subprocess as sp

    class FakeProc:
        pid = 1
        returncode = 0

        def communicate(self, timeout=None):
            return ("hello", "")

    monkeypatch.setattr(sp, "Popen", lambda *a, **k: FakeProc())
    rc, out = repair_live.default_ps_runner("Write-Output hi")
    assert rc == 0
    assert out == "hello"


# ---------------------------------------------------------------------------
# Familienname-Ableitung
# ---------------------------------------------------------------------------

def test_family_name_from_aumid() -> None:
    assert repair_live._family_name("OpenAI.Codex_2p2nqsd0c76g0!App") == "OpenAI.Codex_2p2nqsd0c76g0"
    assert repair_live._family_name("") == ""


# ---------------------------------------------------------------------------
# CLI repair --dry-run: Plan ohne Mutation
# ---------------------------------------------------------------------------

def test_cli_repair_dry_run_plans_without_mutation(tmp_path: Path, monkeypatch) -> None:
    config = make_config(tmp_path)
    config_path = tmp_path / "config.json"
    config.save(config_path)

    mutated: list[str] = []

    # diagnose hermetisch; staged-Wedge vorhanden, ClipSVC gestoppt.
    monkeypatch.setattr(
        "codex_logdatenbank_wartung.health.diagnose", lambda _cfg: _Report()
    )
    run, _calls = fake_runner(staged_wedge_json(), clipsvc="Stopped")
    # Den Default-Runner durch den Fake ersetzen -> kein echtes PowerShell im Test.
    monkeypatch.setattr(repair_live, "default_ps_runner", run)

    # Falls trotz Dry-Run ein mutierendes Dep liefe, wuerde es hier auffallen.
    def record_mutation(pid: int) -> tuple[bool, str]:
        mutated.append(f"kill:{pid}")
        return True, "x"

    monkeypatch.setattr(
        "codex_logdatenbank_wartung.health.default_tree_killer",
        record_mutation,
    )

    out_file = tmp_path / "repair-out.json"
    code = cli.main(
        ["--config", str(config_path), "repair", "--dry-run", "--out", str(out_file)]
    )

    assert code == 0  # Planung selbst ist erfolgreich (status='ok')
    assert mutated == []  # kein mutierendes Dep im Dry-Run

    data = json.loads(out_file.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert data["status"] == "ok"
    # Alle Stufen sind im Plan nur 'skipped' (nichts ausgefuehrt).
    assert data["steps"]
    assert all(step["status"] == "skipped" for step in data["steps"])


# ---------------------------------------------------------------------------
# Log-Persistenz: ein Volllauf darf NIE spurlos bleiben (Blind-Spot-Fix 30.05)
# ---------------------------------------------------------------------------

def test_persist_repair_log_writes_json_and_text(tmp_path: Path) -> None:
    from codex_logdatenbank_wartung.repair_workflow import RepairOutcome

    config = make_config(tmp_path)
    outcome = RepairOutcome(status="failed", needs_store_reinstall=True)
    outcome.add("Store-Paket", "failed", "absent -- Store-Neuinstallation noetig")

    path = cli._persist_repair_log(config, outcome)

    assert path is not None
    assert path.exists()
    logs = list(config.logs_path.glob("repair-*.json"))
    assert logs, "kein persistenter repair-*.json Log geschrieben"
    data = json.loads(logs[0].read_text(encoding="utf-8"))
    assert data["status"] == "failed"
    assert data["needs_store_reinstall"] is True
