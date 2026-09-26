from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.zombie_killer_integration import (
    ZOMBIE_KILLER_PACKAGE_SPEC,
    ZOMBIE_KILLER_SOURCE_ENV,
    build_zombie_killer_status,
    install_zombie_killer_package,
    launch_zombie_killer_watch,
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
    assert "--parent-pid" in command
    assert "--yes" in command
    assert captured["cwd"] == str(config.zombie_killer_state_dir)
    assert Path(captured["cwd"]).is_dir(), "launch must create the state dir before spawning"


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
