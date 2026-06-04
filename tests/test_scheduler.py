from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from codex_logdatenbank_wartung.scheduler import (
    build_runner_script,
    install_scheduled_task,
    remove_scheduled_task,
    scheduled_task_status,
)


def ok_runner_factory(calls: list[list[str]]):
    def runner(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        return subprocess.CompletedProcess(["schtasks.exe", *arguments], 0, "OK", "")

    return runner


def missing_runner_factory(calls: list[list[str]]):
    def runner(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        return subprocess.CompletedProcess(
            ["schtasks.exe", *arguments],
            1,
            "",
            "ERROR: The system cannot find the file specified.",
        )

    return runner


def german_missing_runner_factory(calls: list[list[str]]):
    def runner(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        return subprocess.CompletedProcess(
            ["schtasks.exe", *arguments],
            1,
            "",
            "FEHLER: Das System kann die angegebene Datei nicht finden.",
        )

    return runner


def test_build_runner_script_contains_expected_command(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    script = build_runner_script(
        config_path=config_path,
        project_root=tmp_path / "project",
        python_executable=tmp_path / "python.exe",
    )
    assert 'set "PYTHONIOENCODING=utf-8"' in script
    assert 'set "PYTHONPATH=' in script
    assert '--trigger scheduled-task' in script
    assert f'--config "{config_path}"' in script


def test_install_scheduled_task_writes_script_and_calls_schtasks(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    script_path = tmp_path / "run-maintenance.cmd"
    config_path = tmp_path / "config.json"

    result = install_scheduled_task(
        interval_minutes=180,
        task_name="Codex-Testtask",
        script_path=script_path,
        config_path=config_path,
        runner=ok_runner_factory(calls),
    )

    assert result.status == "installed"
    assert script_path.exists()
    assert any(arg == "/Create" for arg in calls[0])
    assert f'"{script_path}"' in calls[0]
    assert script_path.read_text(encoding="utf-8").startswith("@echo off")


def test_install_rejects_too_small_interval(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        install_scheduled_task(
            interval_minutes=10,
            script_path=tmp_path / "run-maintenance.cmd",
            config_path=tmp_path / "config.json",
            runner=ok_runner_factory([]),
        )


def test_remove_reports_absent_without_failure(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    result = remove_scheduled_task(
        task_name="Codex-Testtask",
        script_path=tmp_path / "run-maintenance.cmd",
        runner=missing_runner_factory(calls),
    )
    assert result.status == "absent"
    assert calls[0][:2] == ["/Delete", "/TN"]


def test_status_reports_absent_without_failure(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    result = scheduled_task_status(
        task_name="Codex-Testtask",
        script_path=tmp_path / "run-maintenance.cmd",
        runner=missing_runner_factory(calls),
    )
    assert result.status == "absent"
    assert calls[0][:2] == ["/Query", "/TN"]


def test_status_reports_absent_for_german_windows_message(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    result = scheduled_task_status(
        task_name="Codex-Testtask",
        script_path=tmp_path / "run-maintenance.cmd",
        runner=german_missing_runner_factory(calls),
    )
    assert result.status == "absent"
    assert calls[0][:2] == ["/Query", "/TN"]
