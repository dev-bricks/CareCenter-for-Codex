"""Regressionstests für die Backup-Retention (`prune_backups`).

Hintergrund: `prune_backups` begrenzte ursprünglich nur die `logs_2-*`-Verzeichnisse.
`thread_hygiene` legt seine Sicherungen aber als *lose Dateien* direkt in
`backup_path` ab (`<db>.carecenter-thread-db-bak-<stamp>`) — die fielen durch den
Verzeichnis-Glob und wuchsen unbegrenzt (real: 122 Dateien / 2,5 GB). Das ist
dieselbe Bugklasse, gegen die `prune_backups` ursprünglich gebaut wurde.
"""
from __future__ import annotations

from pathlib import Path

from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.maintenance import (
    MaintenanceResult,
    MaintenanceRunner,
)


def make_config(tmp_path: Path, *, keep: int = 3) -> MaintenanceConfig:
    return MaintenanceConfig(
        database_path=str(tmp_path / "logs_2.sqlite"),
        backup_dir=str(tmp_path / "backups"),
        log_dir=str(tmp_path / "logs"),
        maintenance_lock_path=str(tmp_path / "maintenance.lock"),
        archive_dir=str(tmp_path / "archive"),
        backup_keep=keep,
    )


def make_result(db_path: Path) -> MaintenanceResult:
    return MaintenanceResult(
        status="ok",
        dry_run=False,
        started_at="",
        ended_at="",
        database_path=str(db_path),
    )


def seed_loose_backups(backup_path: Path, count: int, *, suffix: str = "thread-db-bak") -> list[Path]:
    """Legt `count` lose Backup-Dateien im Namensschema von `thread_hygiene` an."""
    backup_path.mkdir(parents=True, exist_ok=True)
    created = []
    for index in range(count):
        stamp = f"20260101-0000{index:02d}-000000"
        path = backup_path / f"state_5.sqlite.carecenter-{suffix}-{stamp}"
        path.write_bytes(b"x")
        created.append(path)
    return created


def test_loose_thread_backups_are_pruned(tmp_path: Path) -> None:
    config = make_config(tmp_path, keep=3)
    backup_path = Path(config.backup_dir)
    seed_loose_backups(backup_path, 10)

    runner = MaintenanceRunner(config, process_provider=lambda: [])
    runner.prune_backups(make_result(Path(config.database_path)))

    remaining = sorted(p.name for p in backup_path.glob("*-bak-*"))
    assert len(remaining) == 3, f"erwartet 3 verbleibende Backups, gefunden: {remaining}"
    # Die drei jüngsten (höchste Zeitstempel) müssen überleben.
    assert remaining == [
        "state_5.sqlite.carecenter-thread-db-bak-20260101-000007-000000",
        "state_5.sqlite.carecenter-thread-db-bak-20260101-000008-000000",
        "state_5.sqlite.carecenter-thread-db-bak-20260101-000009-000000",
    ]


def test_backup_types_do_not_evict_each_other(tmp_path: Path) -> None:
    """Pro Backup-Art wird getrennt aufbewahrt."""
    config = make_config(tmp_path, keep=2)
    backup_path = Path(config.backup_dir)
    seed_loose_backups(backup_path, 4, suffix="thread-db-bak")
    seed_loose_backups(backup_path, 4, suffix="thread-state-bak")

    runner = MaintenanceRunner(config, process_provider=lambda: [])
    runner.prune_backups(make_result(Path(config.database_path)))

    db_backups = list(backup_path.glob("*thread-db-bak-*"))
    state_backups = list(backup_path.glob("*thread-state-bak-*"))
    assert len(db_backups) == 2
    assert len(state_backups) == 2


def test_unlimited_retention_keeps_loose_backups(tmp_path: Path) -> None:
    """`backup_keep <= 0` heisst weiterhin: nichts anfassen."""
    config = make_config(tmp_path, keep=0)
    backup_path = Path(config.backup_dir)
    seed_loose_backups(backup_path, 5)

    runner = MaintenanceRunner(config, process_provider=lambda: [])
    runner.prune_backups(make_result(Path(config.database_path)))

    assert len(list(backup_path.glob("*-bak-*"))) == 5


def test_directory_backups_still_pruned(tmp_path: Path) -> None:
    """Das bisherige Verhalten für `logs_2-*`-Verzeichnisse bleibt erhalten."""
    config = make_config(tmp_path, keep=2)
    backup_path = Path(config.backup_dir)
    backup_path.mkdir(parents=True, exist_ok=True)
    for index in range(5):
        (backup_path / f"logs_2-2026010{index}-000000").mkdir()

    runner = MaintenanceRunner(config, process_provider=lambda: [])
    runner.prune_backups(make_result(Path(config.database_path)))

    remaining = sorted(p.name for p in backup_path.glob("logs_2-*"))
    assert remaining == ["logs_2-20260103-000000", "logs_2-20260104-000000"]


def seed_dir_backups(backup_path: Path, stamps: list[str]) -> list[Path]:
    """Legt `logs_2-<stamp>`-Verzeichnisse an; `stamp` im Schema `YYYYMMDD-HHMMSS`."""
    backup_path.mkdir(parents=True, exist_ok=True)
    created = []
    for stamp in stamps:
        path = backup_path / f"logs_2-{stamp}"
        path.mkdir()
        (path / "logs_2.sqlite").write_bytes(b"x")
        created.append(path)
    return created


def test_same_day_runs_do_not_evict_older_days(tmp_path: Path) -> None:
    """Mehrere Laeufe am selben Tag duerfen die Historie nicht verdraengen.

    Nutzerbefund 2026-07-26: Drei Wartungslaeufe an einem Vormittag hatten bei
    laufzaehlender Rotation alle aelteren Sicherungen geloescht -- es standen nur
    noch drei Staende desselben Tages. Erwartet wird stattdessen: pro Tag der
    juengste Lauf, insgesamt `keep` verschiedene Tage.
    """
    config = make_config(tmp_path, keep=3)
    backup_path = Path(config.backup_dir)
    seed_dir_backups(
        backup_path,
        [
            "20260724-010000",
            "20260725-010000",
            "20260726-053347",
            "20260726-054411",
            "20260726-124350",
        ],
    )

    runner = MaintenanceRunner(config, process_provider=lambda: [])
    runner.prune_backups(make_result(Path(config.database_path)))

    survivors = sorted(p.name for p in backup_path.glob("logs_2-*") if p.is_dir())
    assert survivors == [
        "logs_2-20260724-010000",
        "logs_2-20260725-010000",
        "logs_2-20260726-124350",
    ], survivors


def test_day_retention_never_keeps_more_than_keep(tmp_path: Path) -> None:
    """Die Tagesrotation darf nie mehr Verzeichnisse behalten als die Laufrotation.

    Absicherung gegen die Bugklasse, gegen die `prune_backups` gebaut wurde
    (unbegrenzte Backups fuellten einmal 123 GB).
    """
    config = make_config(tmp_path, keep=2)
    backup_path = Path(config.backup_dir)
    stamps = [f"2026070{day}-{hour:02d}0000" for day in range(1, 6) for hour in (1, 2, 3)]
    seed_dir_backups(backup_path, stamps)

    runner = MaintenanceRunner(config, process_provider=lambda: [])
    runner.prune_backups(make_result(Path(config.database_path)))

    survivors = sorted(p.name for p in backup_path.glob("logs_2-*") if p.is_dir())
    assert len(survivors) == 2, survivors
    assert survivors == ["logs_2-20260704-030000", "logs_2-20260705-030000"], survivors


def test_unknown_backup_names_are_not_grouped_into_one_day(tmp_path: Path) -> None:
    """Namen ausserhalb des Schemas duerfen sich nicht gegenseitig loeschen."""
    config = make_config(tmp_path, keep=3)
    backup_path = Path(config.backup_dir)
    seed_dir_backups(backup_path, ["manuell-vor-umzug", "kaputt", "20260726-010000"])

    runner = MaintenanceRunner(config, process_provider=lambda: [])
    runner.prune_backups(make_result(Path(config.database_path)))

    survivors = sorted(p.name for p in backup_path.glob("logs_2-*") if p.is_dir())
    assert len(survivors) == 3, survivors
