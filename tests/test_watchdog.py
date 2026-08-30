"""Tests fuer den Hintergrund-Waechter (Start-Praevention).

Vollstaendig hermetisch: ``diagnose`` und ``repair_start`` werden injiziert, es laufen
keine echten Prozessabfragen und es wird nie etwas wirklich beendet.
"""

from __future__ import annotations

import logging
import os
import types
from datetime import datetime, timedelta
from pathlib import Path

from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.health import RepairResult
from codex_logdatenbank_wartung.watchdog import (
    reap_runtime_mcp_duplicates,
    reap_runtime_orphans,
    run_watchdog_tick,
)


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
    kw.setdefault("reap_runtime_mcp_duplicates", False)
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


# ---------------------------------------------------------------------------
# Companion-Orphan-Reaper (codex-plugin-cc #277)
# ---------------------------------------------------------------------------


def test_companion_orphans_reaped_when_idle() -> None:
    """Companion-Orphans werden bereinigt auch wenn Codex geschlossen und kein Ghost da ist."""
    from unittest.mock import patch

    from codex_logdatenbank_wartung.processes import ProcessInfo

    orphan = ProcessInfo(
        pid=99999,
        name="codex.exe",
        executable=r"C:\Users\Example\AppData\Roaming\npm\node_modules\@openai\codex\vendor\codex.exe",
        command_line=r"codex.exe app-server",
        created_at="2026-05-31T10:00:00",
    )

    repair, _calls = repair_recorder()
    with patch(
        "codex_logdatenbank_wartung.watchdog.find_companion_orphans",
        return_value=[orphan],
    ):
        killed_pids: list[int] = []

        def killer(pid: int) -> tuple[bool, str]:
            killed_pids.append(pid)
            return True, "ok"

        result = run_watchdog_tick(
            make_config(),
            diagnose_fn=diagnose_returning(_Report()),
            repair_fn=repair,
            killer=killer,
        )
    assert result.action == "idle"
    assert result.companion_orphans_reaped == 1
    assert 99999 in killed_pids


def test_companion_orphans_reaped_when_codex_active() -> None:
    """Companion-Orphans werden auch bei aktivem Codex bereinigt (unabhaengig)."""
    from unittest.mock import patch

    from codex_logdatenbank_wartung.processes import ProcessInfo

    orphan = ProcessInfo(
        pid=88888,
        name="codex.exe",
        executable=r"C:\Users\Example\AppData\Local\OpenAI\Codex\bin\abc123\codex.exe",
        command_line=r'"codex.exe" app-server --listen stdio://',
        created_at="2026-05-31T10:00:00",
    )

    repair, _calls = repair_recorder()
    with patch(
        "codex_logdatenbank_wartung.watchdog.find_companion_orphans",
        return_value=[orphan],
    ):
        killed_pids: list[int] = []

        def killer(pid: int) -> tuple[bool, str]:
            killed_pids.append(pid)
            return True, "ok"

        result = run_watchdog_tick(
            make_config(),
            diagnose_fn=diagnose_returning(_Report(renderer_present=True)),
            repair_fn=repair,
            killer=killer,
        )
    assert result.action == "codex_active"
    assert result.companion_orphans_reaped == 1
    assert 88888 in killed_pids


def test_companion_reaper_disabled_by_config() -> None:
    """reap_companion_orphans=False deaktiviert den Reaper."""
    from unittest.mock import patch

    from codex_logdatenbank_wartung.processes import ProcessInfo

    orphan = ProcessInfo(
        pid=77777,
        name="codex.exe",
        executable=r"C:\Users\Example\AppData\Roaming\npm\node_modules\@openai\codex\vendor\codex.exe",
        command_line=r"codex.exe app-server",
        created_at="2026-05-31T10:00:00",
    )

    repair, _calls = repair_recorder()
    with patch(
        "codex_logdatenbank_wartung.watchdog.find_companion_orphans",
        return_value=[orphan],
    ):
        result = run_watchdog_tick(
            make_config(reap_companion_orphans=False),
            diagnose_fn=diagnose_returning(_Report()),
            repair_fn=repair,
        )
    assert result.companion_orphans_reaped == 0


def test_companion_orphans_reaped_in_busy_path() -> None:
    """Companion-Orphans werden auch im busy-Pfad bereinigt (unabhaengig von CPU-Aktivitaet)."""
    from unittest.mock import patch

    from codex_logdatenbank_wartung.processes import ProcessInfo

    orphan = ProcessInfo(
        pid=55555,
        name="codex.exe",
        executable=r"C:\Users\Example\AppData\Roaming\npm\node_modules\@openai\codex\vendor\codex.exe",
        command_line=r"codex.exe app-server",
        created_at="2026-05-31T10:00:00",
    )

    repair, calls = repair_recorder()
    with patch(
        "codex_logdatenbank_wartung.watchdog.find_companion_orphans",
        return_value=[orphan],
    ):
        killed_pids: list[int] = []

        def killer(pid: int) -> tuple[bool, str]:
            killed_pids.append(pid)
            return True, "ok"

        result = run_watchdog_tick(
            make_config(),
            diagnose_fn=diagnose_returning(_Report(zombie_main_pids=[111])),
            repair_fn=repair,
            activity_fn=activity(True),  # Codex-Baum aktiv -> busy
            killer=killer,
        )
    assert result.action == "busy"
    assert result.companion_orphans_reaped == 1
    assert 55555 in killed_pids
    assert calls == []  # Zombie-Kill bleibt aus, Companion-Reap passiert


def test_companion_orphans_reaped_in_disabled_path() -> None:
    """Companion-Orphans werden auch im disabled-Pfad bereinigt (unabhaengig von watcher_enabled)."""
    from unittest.mock import patch

    from codex_logdatenbank_wartung.processes import ProcessInfo

    orphan = ProcessInfo(
        pid=66666,
        name="codex.exe",
        executable=r"C:\Users\Example\AppData\Roaming\npm\node_modules\@openai\codex\vendor\codex.exe",
        command_line=r"codex.exe app-server",
        created_at="2026-05-31T10:00:00",
    )

    repair, _calls = repair_recorder()
    with patch(
        "codex_logdatenbank_wartung.watchdog.find_companion_orphans",
        return_value=[orphan],
    ):
        killed_pids: list[int] = []

        def killer(pid: int) -> tuple[bool, str]:
            killed_pids.append(pid)
            return True, "ok"

        result = run_watchdog_tick(
            make_config(watcher_enabled=False),
            diagnose_fn=diagnose_returning(_Report(zombie_main_pids=[7])),
            repair_fn=repair,
            killer=killer,
        )
    assert result.action == "disabled"
    assert result.companion_orphans_reaped == 1
    assert 66666 in killed_pids
    assert _calls == []  # Zombie-Kill bleibt aus, Companion-Reap passiert


# ---------------------------------------------------------------------------
# Runtime-MCP-Reaper (doppelte Desktop-Generationen)
# ---------------------------------------------------------------------------


def test_runtime_mcp_duplicates_reaped_while_desktop_is_active() -> None:
    from unittest.mock import patch

    from codex_logdatenbank_wartung.processes import ProcessInfo

    roots = [
        ProcessInfo(701, "node_repl.exe"),
        ProcessInfo(702, "cmd.exe", command_line="npx -y filecommander-mcp"),
        ProcessInfo(703, "node.exe", command_line="node ./mcp/server.mjs"),
    ]
    killed_pids: list[int] = []

    def killer(pid: int) -> tuple[bool, str]:
        killed_pids.append(pid)
        return True, "ok"

    with patch(
        "codex_logdatenbank_wartung.watchdog.find_runtime_mcp_duplicate_roots",
        return_value=roots,
    ):
        result = run_watchdog_tick(
            make_config(
                reap_runtime_mcp_duplicates=True,
                reap_companion_orphans=False,
            ),
            diagnose_fn=diagnose_returning(_Report(renderer_present=True)),
            killer=killer,
        )

    assert result.action == "codex_active"
    assert result.runtime_mcp_roots_reaped == 3
    assert killed_pids == [701, 702, 703]


def test_runtime_mcp_default_kill_uses_complete_process_tree() -> None:
    from unittest.mock import patch

    from codex_logdatenbank_wartung.processes import ProcessInfo

    root = ProcessInfo(704, "cmd.exe", command_line="npx -y filecommander-mcp")
    with patch(
        "codex_logdatenbank_wartung.watchdog.find_runtime_mcp_duplicate_roots",
        return_value=[root],
    ), patch("codex_logdatenbank_wartung.watchdog.subprocess.run") as run:
        run.return_value.returncode = 0
        reaped = reap_runtime_mcp_duplicates(
            make_config(
                reap_runtime_mcp_duplicates=True,
                runtime_mcp_activity_sample_seconds=0.0,
            ),
            execute=True,
            provider=lambda: [root],
        )

    assert reaped == 1
    command = run.call_args.args[0]
    assert command == ["taskkill", "/T", "/F", "/PID", "704"]


def test_runtime_mcp_reaper_skips_tree_with_cpu_activity() -> None:
    from unittest.mock import patch

    from codex_logdatenbank_wartung.processes import ProcessInfo

    before = [ProcessInfo(705, "node.exe", cpu_ticks=10)]
    after = [ProcessInfo(705, "node.exe", cpu_ticks=20)]
    with patch(
        "codex_logdatenbank_wartung.watchdog.find_runtime_mcp_duplicate_roots",
        return_value=before,
    ), patch("codex_logdatenbank_wartung.watchdog.subprocess.run") as run, patch(
        "codex_logdatenbank_wartung.watchdog.time.sleep"
    ):
        reaped = reap_runtime_mcp_duplicates(
            make_config(
                reap_runtime_mcp_duplicates=True,
                runtime_mcp_activity_sample_seconds=1.0,
            ),
            execute=True,
            provider=lambda: before,
            activity_provider=lambda: after,
        )

    assert reaped == 0
    run.assert_not_called()


def test_runtime_mcp_reaper_never_kills_fully_qualified_cohort_during_companion_turn() -> None:
    """Regressionstest T-20260816-50 (Ende-zu-Ende, ohne Mock der Erkennung).

    Belegter Vorfall 2026-08-16: der Watchdog toetete einen aktiv von einem
    Claude-Code-Companion-Turn (``codex-companion.mjs``) genutzten alten MCP-
    Launcher-Cohort mitten in einem ``fc_read_file``-Aufruf, weil die CPU-Tick-
    Stichprobe (I/O-lastiger MCP-Server) faelschlich "idle" zeigte. Dieser Test
    nutzt die ECHTE ``find_runtime_mcp_duplicate_roots``-Erkennung (kein Mock)
    mit einem Cohort, der ohne Companion-Schutz eindeutig reap-faehig waere
    (siehe test_processes.test_runtime_mcp_reaper_finds_duplicates_again_once_companion_turn_ends),
    und stellt sicher, dass bei aktivem Companion-Turn NICHTS getoetet wird --
    unabhaengig vom CPU-Tick-Ergebnis (``killer`` ist gesetzt, die Stichprobe
    wird also gar nicht erst durchlaufen).
    """
    from datetime import datetime, timedelta

    from codex_logdatenbank_wartung.processes import ProcessInfo

    now = datetime.now()

    def iso(delta_seconds: int) -> str:
        return (now + timedelta(seconds=delta_seconds)).isoformat()

    store_root = (
        r"C:\Program Files\WindowsApps\OpenAI.Codex_26.707.3563.0_x64__2p2nqsd0c76g0"
        r"\app\resources"
    )
    repl = r"C:\Users\Example\AppData\Local\OpenAI\Codex\runtimes\cua_node\abc\node_repl.exe"

    processes = [
        ProcessInfo(
            100, "codex.exe", store_root + r"\codex.exe",
            '"codex.exe" app-server --analytics-default-enabled',
            parent_pid=10, created_at=iso(-6000),
        ),
        # Alte, vollstaendig wiederholte Generation -- laenger als min_age (3600s) alt,
        # und wird gerade von einem Companion-Turn fuer fc_read_file benutzt.
        ProcessInfo(110, "node_repl.exe", repl, f'"{repl}"', 100, iso(-5900)),
        ProcessInfo(
            111, "cmd.exe", r"C:\Windows\System32\cmd.exe",
            'cmd.exe /c "npx.cmd -y ellmos-filecommander-mcp"', 100, iso(-5899),
        ),
        ProcessInfo(
            112, "node.exe", r"C:\Program Files\nodejs\node.exe",
            'node.exe ./mcp/server.mjs --stdio', 100, iso(-5898),
        ),
        # Neueste Generation liefert die Vergleichssignatur und schuetzt sich selbst.
        ProcessInfo(210, "node_repl.exe", repl, f'"{repl}"', 100, iso(-30)),
        ProcessInfo(
            211, "cmd.exe", r"C:\Windows\System32\cmd.exe",
            'cmd.exe /c "npx.cmd -y ellmos-filecommander-mcp"', 100, iso(-29),
        ),
        ProcessInfo(
            212, "node.exe", r"C:\Program Files\nodejs\node.exe",
            'node.exe ./mcp/server.mjs --stdio', 100, iso(-28),
        ),
        # Aktiver Companion-Turn -- ohne direkte Eltern-Kind-Beziehung zum App-Server.
        ProcessInfo(
            999, "node.exe", r"C:\Program Files\nodejs\node.exe",
            (
                r'node "C:\Users\dev\.claude\plugins\cache\openai-codex\codex\1.0.4'
                r'\scripts\codex-companion.mjs" task --write --effort high "..."'
            ),
            created_at=iso(-5),
        ),
    ]

    killed_pids: list[int] = []

    def killer(pid: int) -> tuple[bool, str]:
        killed_pids.append(pid)
        return True, "ok"

    reaped = reap_runtime_mcp_duplicates(
        make_config(reap_runtime_mcp_duplicates=True),
        execute=True,
        provider=lambda: processes,
        killer=killer,
    )

    assert reaped == 0
    assert killed_pids == []


# ---------------------------------------------------------------------------
# Runtime-Orphan-Reaper: T-20260829-890385764
# ---------------------------------------------------------------------------


def test_runtime_orphan_reaper_spares_live_detached_codex_exec(tmp_path: Path) -> None:
    """Fall b: CPU-, Rollout- oder Output-Lebenszeichen schützen ``codex exec``."""
    from codex_logdatenbank_wartung.processes import ProcessInfo

    now = datetime.now()
    executable = (
        r"C:\Users\Example\AppData\Roaming\npm\node_modules\@openai\codex"
        r"\node_modules\@openai\codex-win32-x64\vendor\codex.exe"
    )
    killed_pids: list[int] = []

    def run_case(
        case_name: str,
        pid: int,
        *,
        later_cpu_ticks: int,
        fresh_session: bool,
        output_exists: bool,
        include_output_flag: bool = True,
        session_age_seconds: int = 0,
        configured_freshness_seconds: int = 120,
    ) -> None:
        case_dir = tmp_path / case_name
        output_path = case_dir / "last-message.txt"
        if output_exists:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("done\n", encoding="utf-8")
        if fresh_session:
            session = case_dir / "sessions" / "2026" / "08" / "30" / "rollout.jsonl"
            session.parent.mkdir(parents=True, exist_ok=True)
            session.write_text('{"type":"event_msg"}\n', encoding="utf-8")
            session_mtime = now.timestamp() - session_age_seconds
            os.utime(session, (session_mtime, session_mtime))

        command_line = f'"{executable}" exec -'
        if include_output_flag:
            command_line = (
                f'"{executable}" exec --output-last-message "{output_path}" -'
            )
        before = ProcessInfo(
            pid,
            "codex.exe",
            executable,
            command_line,
            parent_pid=19848,
            created_at=(now - timedelta(minutes=31)).isoformat(),
            cpu_ticks=100,
        )
        after = ProcessInfo(
            pid,
            "codex.exe",
            executable,
            command_line,
            parent_pid=19848,
            created_at=before.created_at,
            cpu_ticks=later_cpu_ticks,
        )
        snapshots = iter([[before], [after]])

        reaped = reap_runtime_orphans(
            make_config(
                database_path=str(case_dir / "logs_2.sqlite"),
                companion_orphan_min_age_seconds=1800,
                companion_orphan_activity_sample_seconds=5.0,
                companion_orphan_session_fresh_seconds=configured_freshness_seconds,
            ),
            provider=lambda: next(snapshots),
            killer=lambda killed_pid: (not killed_pids.append(killed_pid), "ok"),
            sleeper=lambda _seconds: None,
            now=now,
        )

        assert reaped == 0
        assert list(snapshots) == []  # zwei echte Messpunkte wurden verbraucht

    run_case(
        "cpu-active",
        81001,
        later_cpu_ticks=125,
        fresh_session=False,
        output_exists=True,
    )
    run_case(
        "io-wait-fresh-session",
        81002,
        later_cpu_ticks=100,
        fresh_session=True,
        output_exists=True,
        session_age_seconds=60,
        configured_freshness_seconds=1,
    )
    run_case(
        "io-wait-output-pending",
        81003,
        later_cpu_ticks=100,
        fresh_session=False,
        output_exists=False,
    )
    run_case(
        "io-wait-no-output-contract",
        81004,
        later_cpu_ticks=100,
        fresh_session=False,
        output_exists=False,
        include_output_flag=False,
    )

    # Ende-zu-Ende: Der Tick darf den gecachten Start-Snapshot nicht als
    # CPU-Zweitmessung recyceln, sonst würde er diesen aktiven Lauf beenden.
    tick_dir = tmp_path / "watchdog-tick"
    tick_dir.mkdir()
    output_path = tick_dir / "last-message.txt"
    output_path.write_text("old\n", encoding="utf-8")
    command_line = f'codex.exe exec --output-last-message "{output_path}" -'
    before = ProcessInfo(
        81101,
        "codex.exe",
        command_line=command_line,
        parent_pid=19848,
        created_at=(now - timedelta(minutes=31)).isoformat(),
        cpu_ticks=100,
    )
    after = ProcessInfo(
        81101,
        "codex.exe",
        command_line=command_line,
        parent_pid=19848,
        created_at=before.created_at,
        cpu_ticks=125,
    )
    snapshots = iter([[before], [after]])
    killed_pids: list[int] = []

    result = run_watchdog_tick(
        make_config(
            database_path=str(tick_dir / "logs_2.sqlite"),
            reap_runtime_mcp_duplicates=False,
        ),
        provider=lambda: next(snapshots),
        killer=lambda pid: (not killed_pids.append(pid), "ok"),
        diagnose_fn=diagnose_returning(_Report()),
    )

    assert result.action == "idle"
    assert result.companion_orphans_reaped == 0
    assert list(snapshots) == []
    assert killed_pids == []


def test_runtime_orphan_reaper_kills_idle_dead_parent_language_server_and_logs(
    tmp_path: Path,
    caplog,
) -> None:
    """Fall a: Alter, inaktiver language_server-Waise bleibt reap-fähig und auditierbar."""
    from codex_logdatenbank_wartung.processes import ProcessInfo

    now = datetime.now()
    executable = r"C:\Tools\Codex\language_server_windows_x64.exe"
    command_line = f'"{executable}" --stdio'
    orphan = ProcessInfo(
        82001,
        "language_server_windows_x64.exe",
        executable,
        command_line,
        parent_pid=19848,
        created_at=(now - timedelta(days=8)).isoformat(),
        cpu_ticks=700,
    )
    snapshots = iter([[orphan], [orphan]])
    killed_pids: list[int] = []
    caplog.set_level(logging.WARNING, logger="CareCenterForCodex.watchdog")

    reaped = reap_runtime_orphans(
        make_config(
            database_path=str(tmp_path / "logs_2.sqlite"),
            companion_orphan_min_age_seconds=1800,
            companion_orphan_activity_sample_seconds=5.0,
            companion_orphan_session_fresh_seconds=120,
        ),
        provider=lambda: next(snapshots),
        killer=lambda pid: (not killed_pids.append(pid), "ok"),
        sleeper=lambda _seconds: None,
        now=now,
    )

    assert reaped == 1
    assert killed_pids == [82001]
    assert list(snapshots) == []
    assert "pid=82001" in caplog.text
    assert "language_server_windows_x64.exe" in caplog.text
    assert (
        "criterion=kind=language_server,parent=dead,age>=1800s,cpu=idle"
        in caplog.text
    )

    # Auch eine bestehende Legacy-Config mit 300 Sekunden darf die neue feste
    # 30-Minuten-Karenz nicht unterschreiten.
    young_orphan = ProcessInfo(
        82002,
        "language_server_windows_x64.exe",
        executable,
        command_line,
        parent_pid=19848,
        created_at=(now - timedelta(minutes=20)).isoformat(),
        cpu_ticks=700,
    )
    young_snapshots = iter([[young_orphan], [young_orphan]])
    not_reaped = reap_runtime_orphans(
        make_config(
            database_path=str(tmp_path / "logs_2.sqlite"),
            companion_orphan_min_age_seconds=300,
        ),
        provider=lambda: next(young_snapshots),
        killer=lambda pid: (not killed_pids.append(pid), "ok"),
        sleeper=lambda _seconds: None,
        now=now,
    )

    assert not_reaped == 0
    assert killed_pids == [82001]
    assert list(young_snapshots) == [[young_orphan]]  # keine CPU-Probe vor 30 Minuten
