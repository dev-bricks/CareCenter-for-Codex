from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.maintenance import MaintenanceResult, ResultStatus
from codex_logdatenbank_wartung.orchestrator import (
    CodexActivity,
    auto_maintain,
    observe_activity,
)
from codex_logdatenbank_wartung.processes import ProcessInfo

CODEX_EXE = r"C:\Users\dev\AppData\Local\Programs\Codex\Codex.exe"


def make_config(**kw: Any) -> MaintenanceConfig:
    base: dict[str, Any] = {
        "codex_executable": CODEX_EXE,
        "idle_cpu_percent": 10.0,
        "idle_quiet_seconds": 180,
    }
    base.update(kw)
    return MaintenanceConfig(**base)


def fake_maintain(status: ResultStatus = "ok"):
    calls = []

    def fn() -> MaintenanceResult:
        calls.append(True)
        return MaintenanceResult(
            status=status, dry_run=False, started_at="t", ended_at="t", database_path="x"
        )

    return fn, calls


def observe_sequence(items: list[CodexActivity]):
    """observe_fn, das die Liste durchläuft und den letzten Wert wiederholt."""
    state = {"i": 0}

    def fn() -> CodexActivity:
        i = min(state["i"], len(items) - 1)
        state["i"] += 1
        return items[i]

    return fn


def noop_sleep(_s: float) -> None:
    pass


# ---------------------------------------------------------------------------
# observe_activity: CPU-Delta über den ganzen Baum (inkl. Worker-Kind)
# ---------------------------------------------------------------------------

def test_observe_active_when_child_worker_burns_cpu() -> None:
    config = make_config(activity_sample_seconds=2.0)
    main = ProcessInfo(100, "Codex.exe", CODEX_EXE, f'"{CODEX_EXE}"', parent_pid=10, cpu_ticks=1000)
    # python-Worker als Kind des Codex-Hauptprozesses (anderer Name!)
    worker0 = ProcessInfo(200, "python.exe", r"C:\py\python.exe", "python run.py", parent_pid=100, cpu_ticks=5000)
    worker1 = ProcessInfo(200, "python.exe", r"C:\py\python.exe", "python run.py", parent_pid=100, cpu_ticks=5000 + 50_000_000)
    snaps: Iterator[list[ProcessInfo]] = iter([[main, worker0], [main, worker1]])
    act = observe_activity(config, provider=lambda: next(snaps), sleeper=noop_sleep, db_quiet_fn=lambda: 9999.0)
    assert act.present is True
    assert act.active is True
    assert act.cpu_percent > 100  # ~250 %
    assert 200 in act.tree_pids  # Worker-Kind wird mitgezählt


def test_observe_idle_when_quiet() -> None:
    config = make_config(activity_sample_seconds=2.0)
    main = ProcessInfo(100, "Codex.exe", CODEX_EXE, f'"{CODEX_EXE}"', parent_pid=10, cpu_ticks=1000)
    snaps: Iterator[list[ProcessInfo]] = iter([[main], [main]])  # keine CPU-Änderung
    act = observe_activity(config, provider=lambda: next(snaps), sleeper=noop_sleep, db_quiet_fn=lambda: 9999.0)
    assert act.present is True
    assert act.active is False


def test_observe_absent_when_no_codex() -> None:
    config = make_config()
    snaps: Iterator[list[ProcessInfo]] = iter([[], []])
    act = observe_activity(config, provider=lambda: next(snaps), sleeper=noop_sleep, db_quiet_fn=lambda: 9999.0)
    assert act.present is False
    assert act.active is False


# ---------------------------------------------------------------------------
# auto_maintain: Modi und Sicherheitslogik
# ---------------------------------------------------------------------------

def _kit():
    killed: list[int] = []
    closed: list[int] = []
    launched: list[bool] = []
    return {
        "killer": lambda pid: (killed.append(pid) or (True, "ok")),
        "closer": lambda pid: (closed.append(pid) or (True, "ok")),
        "launcher": lambda: (launched.append(True) or (True, "ok")),
        "killed": killed,
        "closed": closed,
        "launched": launched,
    }


def test_no_codex_runs_maintenance_directly() -> None:
    config = make_config()
    k = _kit()
    mfn, calls = fake_maintain()
    res = auto_maintain(
        config, mode="safe", execute=True, allow_close=True,
        observe_fn=observe_sequence([CodexActivity(present=False, active=False)]),
        killer=k["killer"], graceful_closer=k["closer"], launcher=k["launcher"],
        maintain_fn=mfn, sleeper=noop_sleep,
    )
    assert calls == [True]
    assert res.closed_codex is False
    assert k["closed"] == [] and k["killed"] == []
    assert res.status == "ok"


def test_safe_waits_for_idle_then_closes_maintains_restarts() -> None:
    config = make_config(restart_codex_after=True)
    k = _kit()
    mfn, calls = fake_maintain()
    seq = [
        CodexActivity(present=True, active=True, cpu_percent=200, main_pids=[100]),   # assess -> aktiv
        CodexActivity(present=True, active=False, main_pids=[100]),                   # loop re-check -> idle
        CodexActivity(present=True, active=False, main_pids=[100]),                   # refresh vor close
        CodexActivity(present=False, active=False),                                   # leftover nach close
        CodexActivity(present=False, active=False),                                   # guard
        CodexActivity(present=True, active=False, renderer_present=True, main_pids=[101]),  # Neustart verifiziert
    ]
    res = auto_maintain(
        config, mode="safe", execute=True, allow_close=True,
        observe_fn=observe_sequence(seq),
        killer=k["killer"], graceful_closer=k["closer"], launcher=k["launcher"],
        maintain_fn=mfn, sleeper=noop_sleep,
    )
    assert res.waited is True
    assert k["closed"] == [100]       # sanft geschlossen
    assert res.closed_codex is True
    assert calls == [True]            # Wartung lief
    assert res.restarted_codex is True   # Renderer nach Neustart erkannt
    assert k["launched"] == [True]
    assert res.status == "ok"


def test_safe_blocks_on_timeout_without_killing_active_run() -> None:
    config = make_config(idle_wait_timeout_seconds=1, activity_poll_seconds=0)
    k = _kit()
    mfn, calls = fake_maintain()
    base = datetime(2026, 5, 29, 19, 0, 0)
    times = iter([base, base + timedelta(seconds=10), base + timedelta(seconds=20)])
    res = auto_maintain(
        config, mode="safe", execute=True, allow_close=True,
        observe_fn=observe_sequence([CodexActivity(present=True, active=True, cpu_percent=300, main_pids=[100])]),
        killer=k["killer"], graceful_closer=k["closer"], launcher=k["launcher"],
        maintain_fn=mfn, sleeper=noop_sleep, clock=lambda: next(times),
    )
    assert res.status == "blocked"
    assert calls == []                # Wartung NICHT gelaufen
    assert k["killed"] == [] and k["closed"] == []   # aktiver Lauf NICHT abgebrochen


def test_fast_mode_closes_immediately_without_waiting() -> None:
    config = make_config(restart_codex_after=False)
    k = _kit()
    mfn, calls = fake_maintain()
    seq = [
        CodexActivity(present=True, active=True, cpu_percent=200, main_pids=[100]),  # assess (fast ignoriert aktiv)
        CodexActivity(present=True, active=True, main_pids=[100]),                   # refresh vor close
        CodexActivity(present=False, active=False),                                  # leftover
        CodexActivity(present=False, active=False),                                  # guard
    ]
    res = auto_maintain(
        config, mode="fast", execute=True, allow_close=True,
        observe_fn=observe_sequence(seq),
        killer=k["killer"], graceful_closer=k["closer"], launcher=k["launcher"],
        maintain_fn=mfn, sleeper=noop_sleep,
    )
    assert res.waited is False
    assert k["closed"] == [100]
    assert calls == [True]
    assert res.status == "ok"


def test_blocks_when_close_not_allowed() -> None:
    config = make_config(auto_close_codex=False)
    k = _kit()
    mfn, calls = fake_maintain()
    res = auto_maintain(
        config, mode="safe", execute=True, allow_close=False,
        observe_fn=observe_sequence([CodexActivity(present=True, active=False, main_pids=[100])]),
        killer=k["killer"], graceful_closer=k["closer"], launcher=k["launcher"],
        maintain_fn=mfn, sleeper=noop_sleep,
    )
    assert res.status == "blocked"
    assert calls == []                # keine Wartung
    assert k["closed"] == [] and k["killed"] == []   # Codex NICHT angefasst
    assert res.closed_codex is False


def test_fast_mode_closes_without_explicit_allow_close_flag() -> None:
    """Bug-Fix: Fast-Modus ohne --close-Flag beendet Codex (effective_allow=True via Modus)."""
    config = make_config(auto_close_codex=False, restart_codex_after=False)
    k = _kit()
    mfn, calls = fake_maintain()
    seq = [
        CodexActivity(present=True, active=True, cpu_percent=300, main_pids=[100]),
        CodexActivity(present=True, active=True, main_pids=[100]),
        CodexActivity(present=False, active=False),
        CodexActivity(present=False, active=False),
    ]
    res = auto_maintain(
        config, mode="fast", execute=True, allow_close=None,
        observe_fn=observe_sequence(seq),
        killer=k["killer"], graceful_closer=k["closer"], launcher=k["launcher"],
        maintain_fn=mfn, sleeper=noop_sleep,
    )
    assert res.status == "ok"
    assert k["closed"] == [100]
    assert calls == [True]
    assert res.closed_codex is True
    assert res.waited is False


def test_safe_mode_waits_before_blocking_when_no_allow() -> None:
    """Bug-Fix: Safe-Modus wartet (kein Sofort-Abbruch) auch ohne allow_close."""
    config = make_config(auto_close_codex=False, idle_wait_timeout_seconds=1, activity_poll_seconds=0)
    k = _kit()
    mfn, calls = fake_maintain()
    base = datetime(2026, 6, 5, 10, 0, 0)
    times = iter([base, base + timedelta(seconds=10)])
    res = auto_maintain(
        config, mode="safe", execute=True, allow_close=False,
        observe_fn=observe_sequence([CodexActivity(present=True, active=True, cpu_percent=200, main_pids=[100])]),
        killer=k["killer"], graceful_closer=k["closer"], launcher=k["launcher"],
        maintain_fn=mfn, sleeper=noop_sleep, clock=lambda: next(times),
    )
    assert res.status == "blocked"
    assert res.waited is True
    assert calls == []
    assert k["closed"] == [] and k["killed"] == []


def test_dry_run_does_not_touch_codex() -> None:
    config = make_config()
    k = _kit()
    mfn, calls = fake_maintain(status="dry-run")
    seq = [
        CodexActivity(present=True, active=False, main_pids=[100]),  # assess (idle)
        CodexActivity(present=True, active=False, main_pids=[100]),  # refresh vor close
    ]
    res = auto_maintain(
        config, mode="safe", execute=False, allow_close=True,
        observe_fn=observe_sequence(seq),
        killer=k["killer"], graceful_closer=k["closer"], launcher=k["launcher"],
        maintain_fn=mfn, sleeper=noop_sleep,
    )
    assert res.dry_run is True
    assert k["closed"] == [] and k["killed"] == [] and k["launched"] == []
    assert calls == [True]            # Dry-Run-Wartung lief (ohne Änderungen)
    assert res.closed_codex is False


# ---------------------------------------------------------------------------
# End-to-End: Safe-Modus mit echtem MaintenanceRunner (nicht fake_maintain)
# ---------------------------------------------------------------------------

def test_safe_mode_reaches_real_maintenance_despite_cli_noise(tmp_path) -> None:
    """Regressions-Test fuer den gemeldeten Bug: Safe-Modus erreicht die echte
    Wartung auch wenn CLI-Prozesse (node mit .codex-Pfad, node_repl) laufen.

    Vor dem Fix blockierte MaintenanceRunner.find_codex_processes (breiter Matcher)
    die Wartung, obwohl der Orchestrator per striktem Matcher bereits bestaetigte,
    dass keine Desktop-App laeuft.
    """
    import sqlite3

    from codex_logdatenbank_wartung.maintenance import MaintenanceRunner

    db_path = tmp_path / "logs_2.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE logs (id INTEGER PRIMARY KEY, msg TEXT)")
        conn.execute("INSERT INTO logs (msg) VALUES ('test')")

    config = MaintenanceConfig(
        codex_executable=CODEX_EXE,
        database_path=str(db_path),
        backup_dir=str(tmp_path / "backups"),
        log_dir=str(tmp_path / "logs"),
        maintenance_lock_path=str(tmp_path / "maintenance.lock"),
    )

    def cli_noise():
        return [
            ProcessInfo(500, "node.exe", r"C:\Program Files\nodejs\node.exe",
                        r"node C:\Users\dev\.codex\run.js"),
            ProcessInfo(501, "node_repl.exe", r"C:\tools\node_repl.exe", ""),
        ]

    def real_maintain():
        return MaintenanceRunner(config, cli_noise).run(
            dry_run=False, trigger="auto-maintain")

    res = auto_maintain(
        config, mode="safe", execute=True, allow_close=True,
        observe_fn=observe_sequence([CodexActivity(present=False, active=False)]),
        killer=lambda pid: (True, "ok"),
        graceful_closer=lambda pid: (True, "ok"),
        launcher=lambda: (True, "ok"),
        maintain_fn=real_maintain, sleeper=noop_sleep,
    )

    assert res.status == "ok"
    assert res.maintenance is not None
    assert res.maintenance["status"] == "ok"
