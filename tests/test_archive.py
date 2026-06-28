"""Regressionstests für die schema-bewusste Log-Archivierung."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from codex_logdatenbank_wartung.config import MaintenanceConfig
from codex_logdatenbank_wartung.maintenance import (
    MaintenanceResult,
    MaintenanceRunner,
    _archive_table,
    _column_info,
    _cutoff_value,
    _detect_ts_column,
    _table_names,
)

# Feste Testdaten: vor 100 Tagen (sicher archivierbar) und morgen (bleibt in DB).
OLD_TS = int((datetime.now() - timedelta(days=100)).timestamp())
NEW_TS = int((datetime.now() + timedelta(days=1)).timestamp())


def make_db(path: Path) -> Path:
    """Erstellt eine Test-DB mit logs- und meta-Tabelle (ohne Timestamp-Spalte)."""
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE logs (id INTEGER PRIMARY KEY AUTOINCREMENT, msg TEXT, ts INTEGER NOT NULL)"
    )
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO logs (msg, ts) VALUES ('old entry', ?)", (OLD_TS,))
    conn.execute("INSERT INTO logs (msg, ts) VALUES ('new entry', ?)", (NEW_TS,))
    conn.execute("INSERT INTO meta (key, value) VALUES ('version', '1')")
    conn.commit()
    conn.close()
    return path


def make_config(tmp_path: Path, db_path: Path) -> MaintenanceConfig:
    return MaintenanceConfig(
        database_path=str(db_path),
        backup_dir=str(tmp_path / "backups"),
        log_dir=str(tmp_path / "logs"),
        maintenance_lock_path=str(tmp_path / "maintenance.lock"),
        archive_dir=str(tmp_path / "archive"),
        allow_archive_old_logs=True,
        archive_days=30,
    )


def make_result(*, dry_run: bool, db_path: Path) -> MaintenanceResult:
    return MaintenanceResult(
        status="dry-run" if dry_run else "ok",
        dry_run=dry_run,
        started_at="",
        ended_at="",
        database_path=str(db_path),
    )


# ── Einheitstests der Hilfsfunktionen ──────────────────────────────────────────

class TestDetectTsColumn:
    def test_findet_ts(self):
        cols = [("id", "INTEGER"), ("msg", "TEXT"), ("ts", "INTEGER")]
        assert _detect_ts_column(cols) == ("ts", "INTEGER")

    def test_findet_created_at(self):
        cols = [("id", "INTEGER"), ("body", "TEXT"), ("created_at", "TEXT")]
        assert _detect_ts_column(cols) == ("created_at", "TEXT")

    def test_ts_nanos_kein_treffer(self):
        """ts_nanos darf ts nicht als Teilstring matchen — exakter Vergleich."""
        cols = [("key", "TEXT"), ("value", "TEXT"), ("ts_nanos", "INTEGER")]
        assert _detect_ts_column(cols) is None

    def test_keine_ts_spalte(self):
        cols = [("key", "TEXT"), ("value", "TEXT")]
        assert _detect_ts_column(cols) is None


class TestCutoffValue:
    def test_integer_gibt_int_zurueck(self):
        cutoff = _cutoff_value("INTEGER", 30)
        assert isinstance(cutoff, int)
        expected = int((datetime.now() - timedelta(days=30)).timestamp())
        assert abs(cutoff - expected) < 5  # 5 Sekunden Toleranz

    def test_bigint_gibt_int_zurueck(self):
        assert isinstance(_cutoff_value("BIGINT", 30), int)

    def test_text_gibt_iso_string_zurueck(self):
        cutoff = _cutoff_value("TEXT", 30)
        assert isinstance(cutoff, str)
        datetime.fromisoformat(cutoff)  # kein ValueError = valides ISO-Format

    def test_timestamp_typ_gibt_string_zurueck(self):
        assert isinstance(_cutoff_value("TIMESTAMP", 30), str)


# ── Tests für _archive_table ───────────────────────────────────────────────────

class TestArchiveTable:
    def test_jsonl_vor_delete_geschrieben(self, tmp_path: Path):
        """Write-then-delete: JSONL-Datei entsteht, bevor Zeile aus DB entfernt wird."""
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE logs (id INTEGER PRIMARY KEY, ts INTEGER NOT NULL, msg TEXT)"
        )
        conn.execute("INSERT INTO logs VALUES (1, ?, 'old')", (OLD_TS,))
        conn.commit()

        archive_file = tmp_path / "archive" / "logs.jsonl"
        cutoff = int(datetime.now().timestamp())
        count = _archive_table(conn, "logs", "ts", cutoff, archive_file)
        conn.close()

        assert count == 1
        assert archive_file.exists()
        record = json.loads(archive_file.read_text(encoding="utf-8").strip())
        assert record["msg"] == "old"
        assert record["id"] == 1

    def test_dry_run_schreibt_nicht(self, tmp_path: Path):
        """Dry-Run: keine JSONL-Datei, keine DB-Änderung."""
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE logs (id INTEGER PRIMARY KEY, ts INTEGER NOT NULL)")
        conn.execute("INSERT INTO logs VALUES (1, ?)", (OLD_TS,))
        conn.commit()

        archive_file = tmp_path / "archive" / "logs.jsonl"
        cutoff = int(datetime.now().timestamp())
        count = _archive_table(conn, "logs", "ts", cutoff, archive_file, dry_run=True)
        conn.close()

        assert count == 1
        assert not archive_file.exists()
        # Zeile noch in DB vorhanden
        conn2 = sqlite3.connect(str(db))
        remaining = conn2.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
        conn2.close()
        assert remaining == 1

    def test_idempotent_zweiter_lauf_findet_nichts(self, tmp_path: Path):
        """Zweiter Lauf nach Archivierung findet keine Zeilen mehr (idempotent)."""
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE logs (id INTEGER PRIMARY KEY, ts INTEGER NOT NULL)")
        conn.execute("INSERT INTO logs VALUES (1, ?)", (OLD_TS,))
        conn.commit()

        archive_file = tmp_path / "archive" / "logs.jsonl"
        cutoff = int(datetime.now().timestamp())
        count1 = _archive_table(conn, "logs", "ts", cutoff, archive_file)
        count2 = _archive_table(conn, "logs", "ts", cutoff, archive_file)
        conn.close()

        assert count1 == 1
        assert count2 == 0  # zweiter Lauf: nichts mehr zu archivieren

    def test_neue_zeilen_bleiben_in_db(self, tmp_path: Path):
        """Neue Zeilen (ts > cutoff) werden nicht archiviert."""
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE logs (id INTEGER PRIMARY KEY, ts INTEGER NOT NULL, msg TEXT)"
        )
        conn.execute("INSERT INTO logs VALUES (1, ?, 'new')", (NEW_TS,))
        conn.commit()

        archive_file = tmp_path / "archive" / "logs.jsonl"
        cutoff = int(datetime.now().timestamp())
        count = _archive_table(conn, "logs", "ts", cutoff, archive_file)
        conn.close()

        assert count == 0
        assert not archive_file.exists()


# ── Integrationstests für archive_old_logs ────────────────────────────────────

class TestArchiveOldLogs:
    def test_alter_eintrag_archiviert_neuer_bleibt(self, tmp_path: Path):
        """Integration: alter Eintrag wird in JSONL archiviert, neuer bleibt in DB."""
        db_path = tmp_path / "logs_2.sqlite"
        make_db(db_path)
        config = make_config(tmp_path, db_path)
        runner = MaintenanceRunner(config, process_provider=lambda: [])
        result = make_result(dry_run=False, db_path=db_path)

        runner.archive_old_logs(result)

        archive_file = tmp_path / "archive" / "logs.jsonl"
        assert archive_file.exists()
        lines = [json.loads(ln) for ln in archive_file.read_text(encoding="utf-8").splitlines()]
        assert len(lines) == 1
        assert lines[0]["msg"] == "old entry"

        conn = sqlite3.connect(str(db_path))
        remaining = conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
        conn.close()
        assert remaining == 1  # nur der neue Eintrag verbleibt

    def test_dry_run_meldet_anzahl_ohne_aenderung(self, tmp_path: Path):
        """Dry-Run: meldet archivierbare Einträge im Schritt-Ergebnis, ändert nichts."""
        db_path = tmp_path / "logs_2.sqlite"
        make_db(db_path)
        config = make_config(tmp_path, db_path)
        runner = MaintenanceRunner(config, process_provider=lambda: [])
        result = make_result(dry_run=True, db_path=db_path)

        runner.archive_old_logs(result)

        assert not (tmp_path / "archive" / "logs.jsonl").exists()
        step = result.steps[-1]
        assert step.status == "planned"
        assert "1" in step.message  # 1 archivierbarer Eintrag im Meldungstext

    def test_deaktiviert_wenn_not_allowed(self, tmp_path: Path):
        """Keine Archivierung wenn allow_archive_old_logs=False."""
        db_path = tmp_path / "logs_2.sqlite"
        make_db(db_path)
        config = make_config(tmp_path, db_path)
        config.allow_archive_old_logs = False
        runner = MaintenanceRunner(config, process_provider=lambda: [])
        result = make_result(dry_run=False, db_path=db_path)

        runner.archive_old_logs(result)

        step = result.steps[-1]
        assert step.status == "skipped"
        assert not (tmp_path / "archive" / "logs.jsonl").exists()

    def test_meta_tabelle_ohne_ts_spalte_uebersprungen(self, tmp_path: Path):
        """Tabellen ohne erkannte Timestamp-Spalte (meta) werden nicht archiviert."""
        db_path = tmp_path / "logs_2.sqlite"
        make_db(db_path)
        config = make_config(tmp_path, db_path)
        runner = MaintenanceRunner(config, process_provider=lambda: [])
        result = make_result(dry_run=False, db_path=db_path)

        runner.archive_old_logs(result)

        assert not (tmp_path / "archive" / "meta.jsonl").exists()

    def test_archive_days_null_uberspringt(self, tmp_path: Path):
        """archive_days=0 überspringt die Archivierung."""
        db_path = tmp_path / "logs_2.sqlite"
        make_db(db_path)
        config = make_config(tmp_path, db_path)
        config.archive_days = 0
        runner = MaintenanceRunner(config, process_provider=lambda: [])
        result = make_result(dry_run=False, db_path=db_path)

        runner.archive_old_logs(result)

        step = result.steps[-1]
        assert step.status == "skipped"
