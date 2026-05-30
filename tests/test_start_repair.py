"""Tests fuer die Start-Eskalations-Klassifikation (reine Logik)."""

from __future__ import annotations

from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.start_repair import (
    classify_start_state,
    codex_installed_for_user,
)


def test_already_running_when_renderer_present() -> None:
    assert (
        classify_start_state(
            renderer_present=True, codex_installed=True, zombie_pids=[5], stale_lockfile=True
        )
        == "already_running"
    )


def test_needs_store_reinstall_when_not_installed() -> None:
    # Wurzel des Problems: gar kein Codex mehr -> frueher Reinstall-Vorschlag (kein UAC).
    assert (
        classify_start_state(
            renderer_present=False, codex_installed=False, zombie_pids=[], stale_lockfile=False
        )
        == "needs_store_reinstall"
    )


def test_reap_when_zombies_or_lockfile() -> None:
    assert (
        classify_start_state(
            renderer_present=False, codex_installed=True, zombie_pids=[111], stale_lockfile=False
        )
        == "reap"
    )
    assert (
        classify_start_state(
            renderer_present=False, codex_installed=True, zombie_pids=[], stale_lockfile=True
        )
        == "reap"
    )


def test_needs_escalation_when_installed_but_no_obvious_block() -> None:
    assert (
        classify_start_state(
            renderer_present=False, codex_installed=True, zombie_pids=[], stale_lockfile=False
        )
        == "needs_escalation"
    )


def test_installed_true_when_standalone_exe_exists(tmp_path) -> None:
    exe = tmp_path / "Codex.exe"
    exe.write_text("x", encoding="utf-8")
    config = MaintenanceConfig(codex_executable=str(exe))
    # Runner duerfte gar nicht erst gebraucht werden -> wuerde er, faellt der Test auf.
    def boom(_cmd: str) -> tuple[int, str]:
        raise AssertionError("Runner sollte bei vorhandener Standalone-Exe nicht aufgerufen werden")

    assert codex_installed_for_user(config, runner=boom) is True


def test_installed_via_store_package_when_no_standalone(tmp_path) -> None:
    config = MaintenanceConfig(codex_executable=str(tmp_path / "fehlt.exe"))
    assert codex_installed_for_user(config, runner=lambda _c: (0, "yes")) is True
    assert codex_installed_for_user(config, runner=lambda _c: (0, "no")) is False


def test_installed_conservative_true_on_runner_error(tmp_path) -> None:
    config = MaintenanceConfig(codex_executable=str(tmp_path / "fehlt.exe"))

    def boom(_cmd: str) -> tuple[int, str]:
        raise RuntimeError("PowerShell weg")

    assert codex_installed_for_user(config, runner=boom) is True
