from __future__ import annotations

import sqlite3
from pathlib import Path

from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.health import diagnose, repair_start
from codex_logdatenbank_wartung.processes import ProcessInfo


CODEX_EXE = r"C:\Users\dev\AppData\Local\Programs\Codex\Codex.exe"


def make_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE logs (id INTEGER PRIMARY KEY, message TEXT)")
        connection.execute("INSERT INTO logs (message) VALUES ('ok')")


def make_config(tmp_path: Path) -> MaintenanceConfig:
    db_path = tmp_path / "logs_2.sqlite"
    make_db(db_path)
    return MaintenanceConfig(
        database_path=str(db_path),
        backup_dir=str(tmp_path / "backups"),
        log_dir=str(tmp_path / "logs"),
        maintenance_lock_path=str(tmp_path / "maintenance.lock"),
        codex_executable=CODEX_EXE,
        codex_user_data_dir=str(tmp_path / "user-data"),
    )


def healthy_tree() -> list[ProcessInfo]:
    return [
        ProcessInfo(100, "Codex.exe", CODEX_EXE, f'"{CODEX_EXE}"', parent_pid=10, created_at="2026-05-29T08:00:00"),
        ProcessInfo(101, "Codex.exe", CODEX_EXE, f"{CODEX_EXE} --type=gpu-process", parent_pid=100, created_at="2026-05-29T08:00:00"),
        ProcessInfo(102, "Codex.exe", CODEX_EXE, f"{CODEX_EXE} --type=renderer", parent_pid=100, created_at="2026-05-29T08:00:00"),
    ]


def zombie_tree() -> list[ProcessInfo]:
    # Hauptprozess + Helfer, ABER kein Renderer -> Fenster tot = Zombie
    return [
        ProcessInfo(200, "Codex.exe", CODEX_EXE, f'"{CODEX_EXE}"', parent_pid=10, created_at="2026-05-29T08:00:00"),
        ProcessInfo(201, "Codex.exe", CODEX_EXE, f"{CODEX_EXE} --type=gpu-process", parent_pid=200, created_at="2026-05-29T08:00:00"),
        ProcessInfo(202, "Codex.exe", CODEX_EXE, f"{CODEX_EXE} --type=utility", parent_pid=200, created_at="2026-05-29T08:00:00"),
    ]


def test_diagnose_healthy_when_renderer_present(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    report = diagnose(config, lambda: healthy_tree())
    assert report.renderer_present is True
    assert report.zombie_main_pids == []
    assert 100 in report.main_pids


def test_diagnose_detects_zombie_without_renderer(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    report = diagnose(config, lambda: zombie_tree())
    assert report.zombie_main_pids == [200]
    assert report.renderer_present is False
    assert report.status in {"warn", "critical"}


def test_diagnose_detects_stale_lockfile(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    lock = Path(config.lockfile_path)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("", encoding="utf-8")
    # keine Codex-Prozesse -> Lockfile ist verwaist
    report = diagnose(config, lambda: [])
    assert report.stale_lockfile is True


def test_repair_kills_only_zombies_via_injected_killer(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    killed: list[int] = []

    result = repair_start(
        config,
        provider=lambda: zombie_tree(),
        killer=lambda pid: (killed.append(pid) or (True, "ok")),
        execute=True,
    )
    assert killed == [200]
    assert result.status in {"ok", "repaired"}


def test_repair_never_kills_active_codex_with_renderer(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    killed: list[int] = []

    result = repair_start(
        config,
        provider=lambda: healthy_tree(),
        killer=lambda pid: (killed.append(pid) or (True, "ok")),
        execute=True,
    )
    assert killed == []
    assert result.status in {"ok", "nothing-to-do"}


def test_repair_dry_run_does_not_kill(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    killed: list[int] = []

    result = repair_start(
        config,
        provider=lambda: zombie_tree(),
        killer=lambda pid: (killed.append(pid) or (True, "ok")),
        execute=False,
    )
    assert killed == []
    assert result.dry_run is True


def test_diagnose_detects_missing_codex_exe(tmp_path: Path) -> None:
    # Fehlgeschlagenes Update kann die Codex.exe entfernen -> harte Startblockade.
    # Nur relevant ohne Store-Installation (kein Store-AUMID konfiguriert).
    config = make_config(tmp_path)
    config.codex_executable = str(tmp_path / "Programs" / "Codex" / "Codex.exe")
    config.codex_install_dir = str(tmp_path / "Programs" / "Codex")
    config.codex_store_aumid = ""
    report = diagnose(config, lambda: [])
    assert report.codex_exe_present is False
    assert report.status == "critical"
    assert any(issue.code == "codex-exe-fehlt" for issue in report.issues)


def test_diagnose_no_exe_critical_when_store_installed(tmp_path: Path) -> None:
    # Store-Installation vorhanden (AUMID gesetzt) -> kein "Codex.exe fehlt"-Fehlalarm,
    # auch wenn die (entfernte) Standalone-Exe nicht existiert.
    config = make_config(tmp_path)
    config.codex_executable = str(tmp_path / "Programs" / "Codex" / "Codex.exe")
    config.codex_store_aumid = "OpenAI.Codex_2p2nqsd0c76g0!App"
    report = diagnose(config, lambda: [])
    assert report.codex_exe_present is False
    assert not any(issue.code == "codex-exe-fehlt" for issue in report.issues)


def test_diagnose_install_ok_when_exe_present(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    install = tmp_path / "Programs" / "Codex"
    install.mkdir(parents=True)
    exe = install / "Codex.exe"
    exe.write_text("binary", encoding="utf-8")
    config.codex_executable = str(exe)
    config.codex_install_dir = str(install)
    report = diagnose(config, lambda: [])
    assert report.codex_exe_present is True
    assert not any(issue.code == "codex-exe-fehlt" for issue in report.issues)


def test_repair_clears_stale_lockfile_on_execute(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    lock = Path(config.lockfile_path)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("", encoding="utf-8")

    repair_start(config, provider=lambda: [], killer=lambda pid: (True, "ok"), execute=True)
    assert not lock.exists()


def test_repair_clears_lockfile_after_zombie_kill_same_pass(tmp_path: Path) -> None:
    """Regressions-Test: Nach dem Killen von Zombie-Prozessen muss das Lockfile
    im SELBEN Durchlauf entfernt werden (nicht erst beim naechsten Watchdog-Tick).

    Vor dem Fix war report.stale_lockfile=False wenn Zombies existierten (weil mains
    nicht leer war), sodass das Lockfile nach dem Kill stehen blieb.
    """
    config = make_config(tmp_path)
    lock = Path(config.lockfile_path)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("", encoding="utf-8")

    killed: list[int] = []
    result = repair_start(
        config,
        provider=lambda: zombie_tree(),
        killer=lambda pid: (killed.append(pid) or (True, "ok")),
        execute=True,
    )
    assert killed == [200]
    assert not lock.exists(), "Lockfile muss nach Zombie-Kill im selben Pass entfernt werden"
    assert result.status == "repaired"
    assert any("Lockfile entfernt" in step.message for step in result.steps)
