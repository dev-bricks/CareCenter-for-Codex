"""Tests fuer den Hintergrund-Waechter (Start-Praevention).

Vollstaendig hermetisch: ``diagnose`` und ``repair_start`` werden injiziert, es laufen
keine echten Prozessabfragen und es wird nie etwas wirklich beendet.
"""

from __future__ import annotations

import types

from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.health import RepairResult
from codex_logdatenbank_wartung.watchdog import run_watchdog_tick


def activity(active: bool):
    """Fake fuer observe_activity: liefert ein Objekt mit .active."""
    return lambda _config: types.SimpleNamespace(active=active)


# Bequemer Default fuer Reap-Tests: Codex-Baum ist NICHT aktiv (echter Ghost).
INACTIVE = activity(False)


class _Report:
    """Minimaler HealthReport-Stand-in."""

    def __init__(
        self,
        *,
        renderer_present: bool = False,
        zombie_main_pids: list[int] | None = None,
        stale_lockfile: bool = False,
    ) -> None:
        self.renderer_present = renderer_present
        self.zombie_main_pids = zombie_main_pids or []
        self.stale_lockfile = stale_lockfile


def diagnose_returning(report: _Report):
    return lambda _config, _provider=None: report


def repair_recorder(status: str = "repaired"):
    calls: list[dict] = []

    def repair(config, provider, killer, *, execute, trigger, write_log):
        calls.append(
            {"execute": execute, "trigger": trigger, "write_log": write_log}
        )
        return RepairResult(
            status=status if execute else "dry-run",
            dry_run=not execute,
            started_at="t0",
            ended_at="t1",
            trigger=trigger,
        )

    return repair, calls


def make_config(**kw) -> MaintenanceConfig:
    return MaintenanceConfig(**kw)


# ---------------------------------------------------------------------------
# Codex aktiv / nichts zu tun: NIE ein Eingriff
# ---------------------------------------------------------------------------

def test_codex_active_does_nothing() -> None:
    repair, calls = repair_recorder()
    result = run_watchdog_tick(
        make_config(),
        diagnose_fn=diagnose_returning(_Report(renderer_present=True, zombie_main_pids=[5])),
        repair_fn=repair,
    )
    assert result.action == "codex_active"
    assert calls == []  # aktive Sitzung wird nie angefasst


def test_idle_when_no_leftovers() -> None:
    repair, calls = repair_recorder()
    result = run_watchdog_tick(
        make_config(),
        diagnose_fn=diagnose_returning(_Report()),
        repair_fn=repair,
    )
    assert result.action == "idle"
    assert calls == []


# ---------------------------------------------------------------------------
# Reap: bei geschlossenem Codex haengende Reste entfernen
# ---------------------------------------------------------------------------

def test_reaps_zombies_when_codex_closed() -> None:
    repair, calls = repair_recorder(status="repaired")
    result = run_watchdog_tick(
        make_config(),
        diagnose_fn=diagnose_returning(_Report(zombie_main_pids=[111, 222])),
        repair_fn=repair,
        activity_fn=INACTIVE,
    )
    assert result.action == "reaped"
    assert result.zombie_pids == [111, 222]
    assert result.repair_status == "repaired"
    assert len(calls) == 1
    assert calls[0]["execute"] is True
    assert calls[0]["trigger"] == "watchdog"
    assert calls[0]["write_log"] is True  # Reap wird persistent protokolliert
    assert result.relaunched is False  # Default: kein Auto-Neustart
    assert "starten" in result.message.lower()


def test_reaps_stale_lockfile_only() -> None:
    repair, calls = repair_recorder(status="repaired")
    result = run_watchdog_tick(
        make_config(),
        diagnose_fn=diagnose_returning(_Report(stale_lockfile=True)),
        repair_fn=repair,
    )
    assert result.action == "reaped"
    assert result.stale_lockfile is True
    assert len(calls) == 1


def test_dry_run_does_not_execute_kill() -> None:
    repair, calls = repair_recorder()
    result = run_watchdog_tick(
        make_config(),
        execute=False,
        diagnose_fn=diagnose_returning(_Report(zombie_main_pids=[9])),
        repair_fn=repair,
    )
    assert result.action == "reaped"
    assert calls[0]["execute"] is False
    assert calls[0]["write_log"] is False


# ---------------------------------------------------------------------------
# Gating: watcher_enabled=False -> nur melden, nicht killen
# ---------------------------------------------------------------------------

def test_disabled_watcher_reports_but_does_not_kill() -> None:
    repair, calls = repair_recorder()
    result = run_watchdog_tick(
        make_config(watcher_enabled=False),
        diagnose_fn=diagnose_returning(_Report(zombie_main_pids=[7])),
        repair_fn=repair,
    )
    assert result.action == "disabled"
    assert result.zombie_pids == [7]
    assert calls == []  # deaktiviert -> kein Eingriff


# ---------------------------------------------------------------------------
# Optionaler Neustart (Default AUS)
# ---------------------------------------------------------------------------

def test_relaunch_only_when_flag_set_and_repaired() -> None:
    relaunched: list[str] = []
    repair, _calls = repair_recorder(status="repaired")
    result = run_watchdog_tick(
        make_config(watcher_relaunch_after_reap=True),
        diagnose_fn=diagnose_returning(_Report(zombie_main_pids=[1])),
        repair_fn=repair,
        relauncher=lambda: relaunched.append("go"),
        activity_fn=INACTIVE,
    )
    assert result.relaunched is True
    assert relaunched == ["go"]


def test_no_relaunch_by_default() -> None:
    relaunched: list[str] = []
    repair, _calls = repair_recorder(status="repaired")
    result = run_watchdog_tick(
        make_config(),  # watcher_relaunch_after_reap default False
        diagnose_fn=diagnose_returning(_Report(zombie_main_pids=[1])),
        repair_fn=repair,
        relauncher=lambda: relaunched.append("go"),
        activity_fn=INACTIVE,
    )
    assert result.relaunched is False
    assert relaunched == []


def test_no_relaunch_when_repair_failed() -> None:
    relaunched: list[str] = []
    repair, _calls = repair_recorder(status="failed")
    result = run_watchdog_tick(
        make_config(watcher_relaunch_after_reap=True),
        diagnose_fn=diagnose_returning(_Report(zombie_main_pids=[1])),
        repair_fn=repair,
        relauncher=lambda: relaunched.append("go"),
        activity_fn=INACTIVE,
    )
    assert result.relaunched is False
    assert relaunched == []  # kein Neustart, wenn der Reap nicht erfolgreich war


# ---------------------------------------------------------------------------
# Aktivitaets-Gate: "kein Renderer != idle" -- arbeitenden Hintergrund-Codex schonen
# ---------------------------------------------------------------------------

def test_busy_codex_tree_is_not_reaped() -> None:
    # Kein Renderer, aber CPU aktiv (Hintergrund-Automation laeuft) -> NICHT killen.
    repair, calls = repair_recorder(status="repaired")
    result = run_watchdog_tick(
        make_config(),
        diagnose_fn=diagnose_returning(_Report(zombie_main_pids=[111])),
        repair_fn=repair,
        activity_fn=activity(True),
    )
    assert result.action == "busy"
    assert calls == []  # kein abgebrochener Hintergrundlauf


def test_busy_gate_is_conservative_on_activity_error() -> None:
    repair, calls = repair_recorder(status="repaired")

    def boom(_config):
        raise RuntimeError("CPU-Probe weg")

    result = run_watchdog_tick(
        make_config(),
        diagnose_fn=diagnose_returning(_Report(zombie_main_pids=[111])),
        repair_fn=repair,
        activity_fn=boom,
    )
    assert result.action == "busy"  # im Zweifel NICHT killen
    assert calls == []


def test_stale_lockfile_reaped_without_activity_probe() -> None:
    # Reines verwaistes Lockfile (kein Zombie) -> Aktivitaets-Gate entfaellt, wird gereapt.
    repair, calls = repair_recorder(status="repaired")
    def boom(_config):
        raise AssertionError("Aktivitaets-Probe sollte ohne Zombie nicht laufen")
    result = run_watchdog_tick(
        make_config(),
        diagnose_fn=diagnose_returning(_Report(stale_lockfile=True)),
        repair_fn=repair,
        activity_fn=boom,
    )
    assert result.action == "reaped"
    assert len(calls) == 1


def test_failed_reap_reported_as_failed_not_reaped() -> None:
    repair, _calls = repair_recorder(status="failed")
    result = run_watchdog_tick(
        make_config(),
        diagnose_fn=diagnose_returning(_Report(zombie_main_pids=[1])),
        repair_fn=repair,
        activity_fn=INACTIVE,
    )
    assert result.action == "failed"
    assert result.repair_status == "failed"


def test_nothing_to_do_reap_reported_as_idle() -> None:
    repair, _calls = repair_recorder(status="nothing-to-do")
    result = run_watchdog_tick(
        make_config(),
        diagnose_fn=diagnose_returning(_Report(zombie_main_pids=[1])),
        repair_fn=repair,
        activity_fn=INACTIVE,
    )
    assert result.action == "idle"
