from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.zombie_killer_integration import (
    ZOMBIE_KILLER_PACKAGE_SPEC,
    ZOMBIE_KILLER_SOURCE_ENV,
    build_zombie_killer_status,
    install_zombie_killer_package,
    launch_zombie_killer_watch,
    stop_zombie_killer_watch,
    zombie_killer_install_target,
)


def make_config(tmp_path: Path) -> MaintenanceConfig:
    codex_home = tmp_path / ".codex"
    return MaintenanceConfig(database_path=str(codex_home / "logs_2.sqlite"))


def test_zombie_killer_state_dir_is_under_codex_home(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.zombie_killer_state_dir == config.codex_home / "zombie-killer-tray"


def test_install_target_falls_back_to_pinned_github_spec_without_local_source(
    monkeypatch,
) -> None:
    monkeypatch.delenv(ZOMBIE_KILLER_SOURCE_ENV, raising=False)
    monkeypatch.setattr(
        "codex_logdatenbank_wartung.zombie_killer_integration._local_zombie_killer_source",
        lambda: None,
    )
    assert zombie_killer_install_target() == ZOMBIE_KILLER_PACKAGE_SPEC


def test_install_target_prefers_local_source_env_override(tmp_path: Path, monkeypatch) -> None:
    local = tmp_path / "local-zkt"
    local.mkdir()
    (local / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    monkeypatch.setenv(ZOMBIE_KILLER_SOURCE_ENV, str(local))
    assert zombie_killer_install_target() == str(local)


def test_install_zombie_killer_package_reports_ok_on_zero_exit() -> None:
    calls: list[list[str]] = []

    def fake_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, returncode=0, stdout="installed", stderr="")

    result = install_zombie_killer_package(target="some-target", runner=fake_runner)

    assert result.status == "ok"
    assert result.target == "some-target"
    assert calls, "runner must have been invoked at least once"
    assert calls[0][-3:] == ["install", "--upgrade", "some-target"]


def test_install_zombie_killer_package_reports_failed_on_nonzero_exit() -> None:
    def fake_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, returncode=1, stdout="", stderr="boom")

    result = install_zombie_killer_package(target="some-target", runner=fake_runner)

    assert result.status == "failed"
    assert "boom" in result.stderr


def test_launch_zombie_killer_watch_invokes_module_with_expected_args(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    captured: dict[str, object] = {}

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["cwd"] = kwargs.get("cwd")
        captured["env"] = kwargs.get("env")
        return SimpleNamespace(pid=4242)

    result = launch_zombie_killer_watch(
        config, interval_seconds=42, min_age_seconds=99, popen=fake_popen
    )

    assert result.status == "ok"
    assert result.pid == 4242
    assert result.state_dir == str(config.zombie_killer_state_dir)
    command = captured["command"]
    assert "-m" in command
    assert "zombie_killer_tray" in command
    assert "watch" in command
    assert command.index("watch") > command.index("zombie_killer_tray")
    assert "--interval" in command and "42" in command
    assert "--min-age" in command and "99" in command
    assert "--yes" in command
    assert "--parent-pid" not in command, (
        "must NOT tie the watcher's lifetime to this (necessarily short-lived) "
        "caller's own PID -- it would die within ~1s of being spawned (review finding)"
    )
    assert captured["cwd"] == str(config.zombie_killer_state_dir)
    assert Path(captured["cwd"]).is_dir(), "launch must create the state dir before spawning"
    pid_payload = json.loads((config.zombie_killer_state_dir / "watch.pid").read_text(encoding="utf-8"))
    assert pid_payload["pid"] == 4242


def test_launch_uses_preview_mode_without_apply(tmp_path: Path) -> None:
    """Review finding: a test (or any caller) that only wants to exercise the
    watcher's lifecycle, not its actual reap behaviour, must be able to omit
    --yes -- otherwise a real watch subprocess can terminate real, qualifying
    orphans on whatever machine runs it."""
    config = make_config(tmp_path)

    def fake_popen(command, **kwargs):
        return SimpleNamespace(pid=1)

    result = launch_zombie_killer_watch(config, apply=False, popen=fake_popen)
    assert result.status == "ok"
    assert "--yes" not in result.command


def test_launch_refuses_a_second_start_while_the_first_watcher_is_verified_alive(
    tmp_path: Path, monkeypatch
) -> None:
    """Review finding: a second `watch` used to silently overwrite watch.pid,
    orphaning the first watcher (still running, now unreachable via stop)."""
    config = make_config(tmp_path)
    state_dir = config.zombie_killer_state_dir
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "watch.pid").write_text(
        json.dumps({"pid": 424242, "create_time": 123.0}), encoding="utf-8"
    )
    monkeypatch.setattr(
        "codex_logdatenbank_wartung.zombie_killer_integration._verify_watch_process",
        lambda pid, create_time: True,
    )
    called = False

    def fake_popen(command, **kwargs):
        nonlocal called
        called = True
        return SimpleNamespace(pid=1)

    result = launch_zombie_killer_watch(config, popen=fake_popen)

    assert result.status == "already-running"
    assert result.pid == 424242
    assert called is False, "must never spawn a second watcher over a verified-alive one"
    assert json.loads((state_dir / "watch.pid").read_text(encoding="utf-8"))["pid"] == 424242


def test_launch_refuses_a_second_start_when_verification_is_unavailable(
    tmp_path: Path, monkeypatch
) -> None:
    """Fail-closed applies to the double-start guard too: if we cannot tell
    whether the existing PID is still our watcher, refuse rather than risk a
    duplicate -- same direction as stop's fail-closed fix."""
    config = make_config(tmp_path)
    state_dir = config.zombie_killer_state_dir
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "watch.pid").write_text(
        json.dumps({"pid": 424242, "create_time": 123.0}), encoding="utf-8"
    )
    monkeypatch.setattr(
        "codex_logdatenbank_wartung.zombie_killer_integration._verify_watch_process",
        lambda pid, create_time: None,
    )
    called = False

    def fake_popen(command, **kwargs):
        nonlocal called
        called = True
        return SimpleNamespace(pid=1)

    result = launch_zombie_killer_watch(config, popen=fake_popen)

    assert result.status == "verification-unavailable"
    assert called is False


def test_launch_proceeds_when_the_existing_pid_file_is_stale(tmp_path: Path, monkeypatch) -> None:
    config = make_config(tmp_path)
    state_dir = config.zombie_killer_state_dir
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "watch.pid").write_text(
        json.dumps({"pid": 424242, "create_time": 123.0}), encoding="utf-8"
    )
    monkeypatch.setattr(
        "codex_logdatenbank_wartung.zombie_killer_integration._verify_watch_process",
        lambda pid, create_time: False,
    )

    def fake_popen(command, **kwargs):
        return SimpleNamespace(pid=99999)

    result = launch_zombie_killer_watch(config, popen=fake_popen)

    assert result.status == "ok"
    assert result.pid == 99999
    assert json.loads((state_dir / "watch.pid").read_text(encoding="utf-8"))["pid"] == 99999


def test_resolve_python_executable_uses_sys_executable_when_not_frozen() -> None:
    from codex_logdatenbank_wartung.zombie_killer_integration import (
        _resolve_watch_python_executable,
    )

    assert _resolve_watch_python_executable() == sys.executable


def test_resolve_python_executable_resolves_through_the_launcher_when_frozen(monkeypatch) -> None:
    """Review finding: in a frozen build, `sys.executable` is the packaged
    host app, not an interpreter, and launching via the bare `py -3`
    launcher would hand back the LAUNCHER's pid, not the worker's. The real
    interpreter path must be resolved once via the launcher's own stdout."""
    from codex_logdatenbank_wartung.zombie_killer_integration import (
        _resolve_watch_python_executable,
    )

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    real_path = sys.executable

    def fake_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        assert command[:2] == ["py", "-3"]
        return subprocess.CompletedProcess(command, returncode=0, stdout=real_path + "\n", stderr="")

    resolved = _resolve_watch_python_executable(runner=fake_runner)
    assert resolved == real_path


def test_launch_zombie_killer_watch_falls_back_to_config_defaults(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.zombie_killer_watch_interval_seconds = 777
    config.zombie_killer_min_age_seconds = 888
    captured: dict[str, object] = {}

    def fake_popen(command, **kwargs):
        captured["command"] = command
        return SimpleNamespace(pid=1)

    launch_zombie_killer_watch(config, popen=fake_popen)

    command = captured["command"]
    assert "777" in command
    assert "888" in command


def test_launch_zombie_killer_watch_reports_failure_when_no_python_found(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    def failing_popen(command, **kwargs):
        raise OSError("no interpreter")

    result = launch_zombie_killer_watch(config, popen=failing_popen)

    assert result.status == "failed"
    assert "no interpreter" in result.message


def test_build_zombie_killer_status_reads_last_cycle_from_events_log(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    state_dir = config.zombie_killer_state_dir
    state_dir.mkdir(parents=True)
    events = state_dir / "zombie_events.jsonl"
    with events.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({"cycle_at": 111.0, "apply": False, "count": 0}) + "\n")
        handle.write(json.dumps({"cycle_at": 222.0, "apply": True, "count": 3}) + "\n")
        handle.write(json.dumps({"event": "broker-superseded-idle", "root_pid": 5}) + "\n")

    status = build_zombie_killer_status(config)

    assert status.last_cycle_at == 222.0
    assert status.last_cycle_count == 3
    assert status.state_dir == str(state_dir)


def test_build_zombie_killer_status_handles_missing_log(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    status = build_zombie_killer_status(config)

    assert status.last_cycle_at is None
    assert status.last_cycle_count is None


def test_stop_reports_not_running_without_a_pid_file(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    result = stop_zombie_killer_watch(config)
    assert result.status == "not-running"


def test_stop_reports_not_found_for_a_stale_pid_reused_by_something_else(tmp_path: Path) -> None:
    pytest.importorskip("psutil")
    config = make_config(tmp_path)
    state_dir = config.zombie_killer_state_dir
    state_dir.mkdir(parents=True, exist_ok=True)
    # PID of the current test process itself -- definitely alive, definitely
    # NOT a zombie-killer-tray process (wrong cmdline AND, deliberately, a
    # create_time far from its real one), so this exercises the reuse check
    # refusing to kill an unrelated process that happens to reuse the pid.
    (state_dir / "watch.pid").write_text(
        json.dumps({"pid": os.getpid(), "create_time": 1.0}), encoding="utf-8"
    )

    result = stop_zombie_killer_watch(config)

    assert result.status == "not-found"
    assert not (state_dir / "watch.pid").exists(), "stale/wrong pid file must be cleaned up"


def test_stop_fails_closed_when_verification_is_unavailable(tmp_path: Path, monkeypatch) -> None:
    """Review finding (blocking): stop used to fail-OPEN when verification
    returned None (psutil unavailable) -- it killed the PID anyway. A stale,
    verification-less PID file could then terminate an unrelated process
    that happened to reuse the PID. It must instead refuse and leave the
    process untouched."""
    config = make_config(tmp_path)
    state_dir = config.zombie_killer_state_dir
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "watch.pid").write_text(
        json.dumps({"pid": 999999999, "create_time": 123.0}), encoding="utf-8"
    )
    killed: list[int] = []
    monkeypatch.setattr(
        "codex_logdatenbank_wartung.zombie_killer_integration._verify_watch_process",
        lambda pid, create_time: None,
    )
    monkeypatch.setattr(os, "kill", lambda pid, sig: killed.append(pid))

    result = stop_zombie_killer_watch(config)

    assert result.status == "verification-unavailable"
    assert killed == [], "must NOT signal the pid when verification is unavailable (fail-closed)"
    assert (state_dir / "watch.pid").exists(), "an unresolved pid file is left in place, not deleted"


def test_stop_reports_already_stopped_for_a_verified_but_dead_pid(tmp_path: Path, monkeypatch) -> None:
    config = make_config(tmp_path)
    state_dir = config.zombie_killer_state_dir
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "watch.pid").write_text(
        json.dumps({"pid": 999999999, "create_time": 123.0}), encoding="utf-8"
    )
    monkeypatch.setattr(
        "codex_logdatenbank_wartung.zombie_killer_integration._verify_watch_process",
        lambda pid, create_time: True,
    )
    monkeypatch.setattr(os, "kill", lambda pid, sig: (_ for _ in ()).throw(OSError("gone")))

    result = stop_zombie_killer_watch(config)

    assert result.status == "already-stopped"
    assert not (state_dir / "watch.pid").exists()


@pytest.mark.timeout(30)
def test_real_watch_subprocess_outlives_its_launcher_and_stop_terminates_it(
    tmp_path: Path,
) -> None:
    """No mocked Popen -- a genuinely real subprocess, spawned exactly the way
    production code does it. This is the direct regression test for the
    review finding: the old design passed --parent-pid <this process's own
    PID>, and zombie-killer-tray's watch_parent thread kills the watcher
    within ~1s of whatever PID it was given exiting. Since THIS test process
    is what would have been passed as --parent-pid, and it obviously keeps
    running throughout this test, the old bug would never have reproduced
    here either -- which is exactly why the original review used a real,
    separately-invoked CLI process to catch it, and why this test proves the
    fix by asserting on the watcher's presence/absence, not merely that
    --parent-pid is absent from the command (already covered separately).
    """
    psutil = pytest.importorskip("psutil")
    pytest.importorskip("zombie_killer_tray")
    config = make_config(tmp_path)

    # apply=False (preview/no --yes): review finding -- with --yes, this real
    # subprocess would actually reap real, qualifying orphan processes on
    # whatever machine runs this test (including CI). Lifecycle behaviour
    # (survives its launcher, responds to stop) does not require apply=True.
    result = launch_zombie_killer_watch(
        config, interval_seconds=3, min_age_seconds=30, apply=False
    )
    assert result.status == "ok", result.message
    assert "--yes" not in result.command
    pid = result.pid
    assert pid is not None

    try:
        time.sleep(2.0)
        assert psutil.pid_exists(pid), (
            "the watcher must still be running 2s after launch returned -- "
            "with the old --parent-pid design it would already be dead"
        )

        stop_result = stop_zombie_killer_watch(config)
        assert stop_result.status == "ok"
        assert stop_result.pid == pid

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and psutil.pid_exists(pid):
            time.sleep(0.2)
        assert not psutil.pid_exists(pid), "the watcher must actually exit after being stopped"
    finally:
        if psutil.pid_exists(pid):
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGTERM)
