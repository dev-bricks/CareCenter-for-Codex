from __future__ import annotations

from typing import Any

from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.repair_workflow import (
    AdminRequired,
    DeployTimeout,
    RepairDeps,
    RepairOutcome,
    RepairState,
    RepairStepResult,
    _default_run_with_timeout,
    prevention_check,
    run_repair,
)


def make_config(**kw: Any) -> MaintenanceConfig:
    base: dict[str, Any] = {"deploy_timeout_seconds": 75, "renderer_timeout_seconds": 120}
    base.update(kw)
    return MaintenanceConfig(**base)


def observe_const(state: RepairState):
    return lambda: state


def observe_sequence(items: list[RepairState]):
    """observe_fn, das die Liste durchlaeuft und den letzten Wert wiederholt."""
    box = {"i": 0}

    def fn() -> RepairState:
        i = min(box["i"], len(items) - 1)
        box["i"] += 1
        return items[i]

    return fn


# ---------------------------------------------------------------------------
# Baseline / Erfolg
# ---------------------------------------------------------------------------

def test_baseline_renderer_present_does_nothing() -> None:
    touched: list[str] = []
    deps = RepairDeps(
        observe=observe_const(RepairState(renderer_present=True)),
        kill_ghosts=lambda: touched.append("kill"),
        launch_codex=lambda: touched.append("launch"),
    )
    out = run_repair(make_config(), deps)
    assert out.status == "ok"
    assert out.reached_window is True
    assert out.recommend_reboot is False
    assert touched == []  # nichts angefasst


def test_s1_ghost_then_launch_succeeds() -> None:
    events: list[str] = []
    deps = RepairDeps(
        observe=observe_const(RepairState(ghost_pids=[111], stale_lockfile=True)),
        kill_ghosts=lambda: events.append("kill"),
        clear_lockfile=lambda: events.append("lock"),
        launch_codex=lambda: events.append("launch"),
        renderer_appears=lambda _t: True,
    )
    out = run_repair(make_config(), deps)
    assert out.status == "ok"
    assert out.reached_window is True
    # S1 beendet Ghost + Lockfile, dann genau ein Start, dann Erfolg.
    assert events == ["kill", "lock", "launch"]


def test_s2_clipsvc_then_launch_succeeds() -> None:
    events: list[str] = []
    deps = RepairDeps(
        observe=observe_const(RepairState(clipsvc_running=False)),
        ensure_clipsvc=lambda: events.append("clip"),
        launch_codex=lambda: events.append("launch"),
        # S1-Check scheitert (kein Renderer), S2-Check gelingt.
        renderer_appears=iter_appears([False, True]),
    )
    out = run_repair(make_config(), deps)
    assert out.status == "ok"
    assert "clip" in events


def test_s3_staged_wedge_complete_update_then_launch_succeeds() -> None:
    """Staged-Wedge: complete_staged_update laeuft (via run_with_timeout='ok'), dann Renderer -> 'ok'.

    Das pass-through run_with_timeout ruft das Dep WIRKLICH auf (fn()), damit nicht nur
    das Routing, sondern die tatsaechliche Ausfuehrung von complete_staged_update belegt ist.
    """
    events: list[str] = []
    deps = RepairDeps(
        observe=observe_const(RepairState(staged_update=True)),
        complete_staged_update=lambda: events.append("stage"),
        launch_codex=lambda: events.append("launch"),
        # S1-Start-Check scheitert (kein Renderer); S2 entfaellt (ClipSVC laeuft);
        # S3-Start-Check gelingt nach dem sanften RegisterByFamilyName.
        renderer_appears=iter_appears([False, True]),
        run_with_timeout=lambda fn, _s: ("ok", fn()),  # ruft das Dep tatsaechlich auf
    )
    out = run_repair(make_config(), deps)
    assert out.status == "ok"
    assert out.reached_window is True
    assert out.recommend_reboot is False
    # Belegt, dass die sanfte staged-Update-Behebung wirklich lief und der Erfolgspunkt war.
    assert "stage" in events
    assert any(
        step.status == "ok" and step.name.startswith("S3 Start-Check")
        for step in out.steps
    )


# ---------------------------------------------------------------------------
# Hang-Vermeidung: die einzige harte Regel
# ---------------------------------------------------------------------------

def test_deploy_timeout_blocks_and_stops_no_further_deploy() -> None:
    deploy_calls: list[object] = []

    def rwt(fn, _secs):
        deploy_calls.append(fn)
        return ("timeout", None)

    deps = RepairDeps(
        observe=observe_const(RepairState(staged_update=True)),
        launch_codex=lambda: None,
        renderer_appears=lambda _t: False,
        run_with_timeout=rwt,
    )
    out = run_repair(make_config(), deps)
    assert out.status == "blocked"
    assert out.recommend_reboot is True
    assert out.reached_window is False
    # ENTSCHEIDEND: nach dem Timeout darf KEINE weitere Deploy-Op gefeuert werden.
    assert len(deploy_calls) == 1
    assert any(step.status == "timeout" for step in out.steps)


def test_fallback_timeout_blocks_and_stops_after_clean_s3_failure() -> None:
    """S3 sauberer Fehlschlag -> EIN Fallback (reset); reisst der den Timeout -> blocked, STOPP."""
    deploy_calls: list[str] = []

    def tag(name):
        def f():
            return None
        f._tag = name
        return f

    def rwt(fn, _secs):
        name = getattr(fn, "_tag", "?")
        deploy_calls.append(name)
        # S3 schlaegt sauber fehl (kein Stopp) -> Fallback (reset); der reisst den Timeout.
        return ("timeout", None) if name == "reset" else ("failed", None)

    deps = RepairDeps(
        observe=observe_const(RepairState(staged_update=True)),
        complete_staged_update=tag("S3"),
        reset_package=tag("reset"),
        # diese werden vom begrenzten Workflow NICHT mehr aufgerufen:
        remove_staged_version=tag("S4"),
        reinstall_package=tag("S6"),
        launch_codex=lambda: None,
        renderer_appears=lambda _t: False,
        run_with_timeout=rwt,
    )
    out = run_repair(make_config(), deps)
    assert out.status == "blocked"
    assert out.recommend_reboot is True
    # Genau S3 dann EIN Fallback -- KEINE weitere Deploy-Op (S4/S6 entfallen).
    assert deploy_calls == ["S3", "reset"]
    assert out.steps[-1].status == "timeout"


def test_clean_failures_s3_and_fallback_then_abort_reboot() -> None:
    deploy_calls: list[str] = []

    def tag(name):
        def f():
            return None
        f._tag = name
        return f

    def rwt_fail(fn, _secs):
        deploy_calls.append(getattr(fn, "_tag", "?"))
        return ("failed", RuntimeError("kein timeout"))

    deps = RepairDeps(
        observe=observe_const(RepairState(clipsvc_running=False)),
        ensure_clipsvc=lambda: None,
        complete_staged_update=tag("S3"),
        reset_package=tag("reset"),
        remove_staged_version=tag("S4"),
        reinstall_package=tag("S6"),
        launch_codex=lambda: None,
        renderer_appears=lambda _t: False,
        run_with_timeout=rwt_fail,
    )
    out = run_repair(make_config(), deps)
    assert out.status == "failed"
    assert out.recommend_reboot is True
    assert out.needs_admin is False
    # Saubere Fehlschlaege: genau S3 + EIN Fallback (reset), dann Abbruch -- KEINE Volleskalation.
    assert deploy_calls == ["S3", "reset"]
    assert out.steps[-1].name == "Abschluss"


def test_s3_clean_success_launches() -> None:
    appears = iter_appears([False, True])  # S1-Check fail, danach S3-Start gelingt

    def rwt_ok(fn, _secs):
        return ("ok", "done")

    deps = RepairDeps(
        observe=observe_const(RepairState()),  # kein Ghost, kein staged Update
        launch_codex=lambda: None,
        renderer_appears=appears,
        run_with_timeout=rwt_ok,
    )
    out = run_repair(make_config(), deps)
    assert out.status == "ok"
    assert out.reached_window is True


def test_fallback_reset_succeeds_after_clean_s3_failure() -> None:
    """S3 sauberer Fehlschlag, Codex startet nicht -> Fallback reset -> Renderer -> ok."""
    appears = iter_appears([False, False, True])  # S1-Check, S3-Check fail; Fallback-Check ok

    def tag(name):
        def f():
            return None
        f._tag = name
        return f

    def rwt(fn, _secs):
        name = getattr(fn, "_tag", "?")
        return ("ok", "reset done") if name == "reset" else ("failed", None)

    deps = RepairDeps(
        observe=observe_const(RepairState()),
        complete_staged_update=tag("S3"),
        reset_package=tag("reset"),
        launch_codex=lambda: None,
        renderer_appears=appears,
        run_with_timeout=rwt,
    )
    out = run_repair(make_config(), deps)
    assert out.status == "ok"
    assert out.reached_window is True


def test_s3_access_denied_aborts_with_needs_admin_no_fallback() -> None:
    """Access Denied bei S3 -> sofort needs_admin, KEIN Fallback (scheitert aus demselben Grund).

    Der gefakte run_with_timeout faengt NICHT (nur das echte _default_run_with_timeout tut das)
    -> Admin-Fehler als Exception-INSTANZ im ('failed', exc)-Kanal liefern (advisor-Konvention).
    """
    deploy_calls: list[str] = []

    def tag(name):
        def f():
            return None
        f._tag = name
        return f

    def rwt(fn, _secs):
        deploy_calls.append(getattr(fn, "_tag", "?"))
        return ("failed", AdminRequired("Add-AppxPackage: Access is denied"))

    deps = RepairDeps(
        observe=observe_const(RepairState()),
        complete_staged_update=tag("S3"),
        reset_package=tag("reset"),
        launch_codex=lambda: None,
        renderer_appears=lambda _t: False,
        run_with_timeout=rwt,
    )
    out = run_repair(make_config(), deps)
    assert out.status == "failed"
    assert out.needs_admin is True
    assert out.recommend_reboot is False  # Reboot hilft bei Admin-Problem NICHT
    assert deploy_calls == ["S3"]  # KEIN Fallback nach Admin-Fehler


def test_s3_deploy_timeout_instance_blocks_no_fallback() -> None:
    """rc=124 kommt als DeployTimeout-Instanz durch den ('failed', exc)-Kanal -> blocked, kein Fallback."""
    deploy_calls: list[str] = []

    def rwt(fn, _secs):
        deploy_calls.append("call")
        return ("failed", DeployTimeout("PowerShell-Timeout"))

    deps = RepairDeps(
        observe=observe_const(RepairState()),
        complete_staged_update=lambda: None,
        reset_package=lambda: None,
        launch_codex=lambda: None,
        renderer_appears=lambda _t: False,
        run_with_timeout=rwt,
    )
    out = run_repair(make_config(), deps)
    assert out.status == "blocked"
    assert out.recommend_reboot is True
    assert out.needs_admin is False
    assert deploy_calls == ["call"]  # kein Fallback nach Timeout


# ---------------------------------------------------------------------------
# Begrenzte Eskalation: destruktive/aggressive Ops entfallen ganz
# ---------------------------------------------------------------------------

def test_remove_and_reinstall_are_never_called() -> None:
    """S4 (remove, destruktiv) + S6 (reinstall) werden vom begrenzten Workflow NIE aufgerufen.

    Frueher loesten staged_update bzw. die Catch-all-Stufen diese aus -- genau sie stapelten
    weitere haengende PowerShell-Deploy-Ops. Jetzt: nur S3 + EIN Fallback (reset).
    """
    deploy_calls: list[str] = []

    def rwt(fn, _secs):
        deploy_calls.append(getattr(fn, "_tag", "?"))
        return ("failed", None)

    def tag(name):
        def f():
            return None
        f._tag = name
        return f

    deps = RepairDeps(
        observe=observe_const(RepairState(staged_update=True)),  # frueher haette das S4 getriggert
        complete_staged_update=tag("S3"),
        remove_staged_version=tag("S4"),
        reset_package=tag("reset"),
        reinstall_package=tag("S6"),
        launch_codex=lambda: None,
        renderer_appears=lambda _t: False,
        run_with_timeout=rwt,
    )
    out = run_repair(make_config(), deps)
    assert "S4" not in deploy_calls
    assert "S6" not in deploy_calls
    assert deploy_calls == ["S3", "reset"]
    assert out.status == "failed"


# ---------------------------------------------------------------------------
# Absentes Store-Paket: korrekter Abbruch statt sinnloser/gefaehrlicher Deploy-Ops
# ---------------------------------------------------------------------------

def test_package_absent_short_circuits_to_store_reinstall() -> None:
    """Store-Paket vollstaendig weg -> kein Deploy-Op, klare Store-Reinstall-Empfehlung.

    Lektion 29.05: Bei absentem Paket gibt es NICHTS zu registrieren/zuruecksetzen.
    Die Engine darf nicht durch alle Stufen no-oppen und faelschlich 'Reboot empfohlen'
    melden -- ein Reboot hilft hier nicht. Stattdessen: sofortiger, ehrlicher Abbruch.
    """
    touched: list[str] = []

    def tag(name):
        def f():
            touched.append(name)
        return f

    deps = RepairDeps(
        observe=observe_const(RepairState(package_absent=True, codex_exe_present=True)),
        kill_ghosts=tag("kill"),
        clear_lockfile=tag("lock"),
        ensure_clipsvc=tag("clip"),
        complete_staged_update=tag("S3"),
        remove_staged_version=tag("S4"),
        reset_package=tag("S5"),
        reinstall_package=tag("S6"),
        launch_codex=tag("launch"),
        renderer_appears=lambda _t: False,
        run_with_timeout=lambda fn, _s: ("ok", fn()),
    )
    out = run_repair(make_config(), deps)
    assert out.status == "failed"
    assert out.needs_store_reinstall is True
    # ENTSCHEIDEND: Ein Reboot wird NICHT empfohlen (waere die falsche Botschaft).
    assert out.recommend_reboot is False
    assert out.reached_window is False
    # Kein einziges mutierendes Dep -- weder Deploy-Op noch launch.
    assert touched == []
    assert any("Store" in step.message for step in out.steps)


def test_package_absent_in_planning_mode_reports_reinstall() -> None:
    muts: list[str] = []
    deps = RepairDeps(
        observe=observe_const(RepairState(package_absent=True)),
        complete_staged_update=lambda: muts.append("stage"),
        reset_package=lambda: muts.append("reset"),
        launch_codex=lambda: muts.append("launch"),
    )
    out = run_repair(make_config(), deps, dry_run=True)
    assert out.needs_store_reinstall is True
    assert muts == []


# ---------------------------------------------------------------------------
# Planungsmodus
# ---------------------------------------------------------------------------

def test_dry_run_calls_no_mutating_dep() -> None:
    muts: list[str] = []

    def run_with_timeout(fn, _seconds):
        muts.append("rwt")
        return "ok", None

    deps = RepairDeps(
        observe=observe_const(
            RepairState(ghost_pids=[1], staged_update=True, clipsvc_running=False)
        ),
        kill_ghosts=lambda: muts.append("kill"),
        ensure_clipsvc=lambda: muts.append("clip"),
        complete_staged_update=lambda: muts.append("stage"),
        reset_package=lambda: muts.append("reset"),
        launch_codex=lambda: muts.append("launch"),
        run_with_timeout=run_with_timeout,
    )
    out = run_repair(make_config(), deps, dry_run=True)
    assert out.status == "ok"
    assert muts == []  # kein einziges mutierendes Dep
    assert all(step.status == "skipped" for step in out.steps)


def test_execute_false_is_planning_mode() -> None:
    muts: list[str] = []
    deps = RepairDeps(
        observe=observe_const(RepairState(ghost_pids=[1])),
        kill_ghosts=lambda: muts.append("kill"),
        launch_codex=lambda: muts.append("launch"),
    )
    out = run_repair(make_config(), deps, execute=False)
    assert out.status == "ok"
    assert muts == []


# ---------------------------------------------------------------------------
# prevention_check (read-only)
# ---------------------------------------------------------------------------

def test_prevention_check_all_green() -> None:
    deps = RepairDeps(observe=observe_const(RepairState()))
    steps = prevention_check(make_config(), deps)
    assert len(steps) == 6
    assert all(step.status == "ok" for step in steps)


def test_prevention_check_flags_problems() -> None:
    touched: list[str] = []
    deps = RepairDeps(
        observe=observe_const(
            RepairState(
                ghost_pids=[9],
                clipsvc_running=False,
                staged_update=True,
                package_user_registered=False,
                codex_exe_present=False,
                package_absent=True,
            )
        ),
        kill_ghosts=lambda: touched.append("kill"),
    )
    steps = prevention_check(make_config(), deps)
    assert {s.status for s in steps} == {"failed"}
    assert touched == []  # read-only: kein mutierendes Dep


def test_prevention_check_flags_absent_store_package() -> None:
    """Standalone-Exe da, aber Store-Paket weg -> muss als Problem auffallen (Blind-Spot-Fix)."""
    deps = RepairDeps(
        observe=observe_const(RepairState(codex_exe_present=True, package_absent=True)),
    )
    steps = prevention_check(make_config(), deps)
    absent_step = next(s for s in steps if "Store-Paket" in s.name)
    assert absent_step.status == "failed"


# ---------------------------------------------------------------------------
# Serialisierung
# ---------------------------------------------------------------------------

def test_outcome_to_dict_and_to_text() -> None:
    out = RepairOutcome(status="ok", reached_window=True)
    out.add("S1", "ok", "fertig")
    data = out.to_dict()
    assert data["status"] == "ok"
    assert data["reached_window"] is True
    steps = data["steps"]
    assert isinstance(steps, list)
    first_step = steps[0]
    assert isinstance(first_step, dict)
    assert first_step["name"] == "S1"
    text = out.to_text()
    assert "Status: ok" in text
    assert "S1" in text


def test_outcome_needs_store_reinstall_serialized() -> None:
    out = RepairOutcome(status="failed", needs_store_reinstall=True)
    data = out.to_dict()
    assert data["needs_store_reinstall"] is True
    assert "Store-Neuinstallation" in out.to_text()


def test_step_result_to_dict() -> None:
    step = RepairStepResult("S5 reset_package", "timeout", "verklemmt")
    assert step.to_dict() == {
        "name": "S5 reset_package",
        "status": "timeout",
        "message": "verklemmt",
    }


# ---------------------------------------------------------------------------
# Default run_with_timeout: ok / failed / timeout (echte Thread-Implementierung)
# ---------------------------------------------------------------------------

def test_default_run_with_timeout_ok() -> None:
    assert _default_run_with_timeout(lambda: 42, 2.0) == ("ok", 42)


def test_default_run_with_timeout_failed() -> None:
    def boom():
        raise ValueError("boom")

    status, result = _default_run_with_timeout(boom, 2.0)
    assert status == "failed"
    assert isinstance(result, ValueError)


def test_default_run_with_timeout_returns_fast_on_timeout() -> None:
    import time

    started = time.time()
    status, _ = _default_run_with_timeout(lambda: time.sleep(5), 0.3)
    elapsed = time.time() - started
    assert status == "timeout"
    assert elapsed < 1.5  # kehrt sofort zurueck, blockiert NICHT bis zum sleep-Ende


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------

def iter_appears(values: list[bool]):
    """renderer_appears-Fake, das die Liste durchlaeuft (letzter Wert wiederholt)."""
    box = {"i": 0}

    def fn(_timeout: float) -> bool:
        i = min(box["i"], len(values) - 1)
        box["i"] += 1
        return values[i]

    return fn
