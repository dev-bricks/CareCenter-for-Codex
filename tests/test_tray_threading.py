"""Kein blockierender Aufruf im GUI-Thread (APP-RUNTIME-STANDARD 5c).

Der Fehler, den diese Tests festhalten, war NICHT ein fehlender `moveToThread`:
Alle Worker-Klassen waren korrekt ausgelagert. Blockiert hat ein Knopf-Handler,
der an den Workern vorbei synchron arbeitete — `run_config_audit()` rief
`diagnose()` direkt auf (gemessen ueber 10 Sekunden, Qt gilt ab ~100 ms als
haengend). Ein blosser Zaehl-Test Worker-gegen-moveToThread haette das nie
gefunden, weil die Zahlen stimmten. Deshalb pruefen wir beides.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import pytest

TRAY = Path(__file__).parent.parent / "src" / "codex_logdatenbank_wartung" / "tray.py"

# Funktionen, die messbar blockieren (subprocess.run, Dateisystem-Scans).
# Sie duerfen NUR in einer Worker-Klasse aufgerufen werden, nie im GUI-Thread.
# `default_launcher` fehlt hier bewusst: es startet nur per subprocess.Popen
# (fire-and-forget) und kehrt sofort zurueck — es blockiert nicht.
BLOCKING = {
    "diagnose",
    "run_manual_audit",
    "repair_start",
    "run_live_repair",
    "run_watchdog_tick",
    "repair_store_codex",
}


def _tree() -> ast.Module:
    return ast.parse(TRAY.read_text(encoding="utf-8"))


def _worker_classes(tree: ast.Module) -> list[ast.ClassDef]:
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.ClassDef) and n.name.endswith("Worker")]


def _spans(classes: list[ast.ClassDef]) -> list[tuple[int, int]]:
    return [(c.lineno, max(getattr(x, "lineno", c.lineno) for x in ast.walk(c)))
            for c in classes]


def test_no_blocking_call_outside_a_worker() -> None:
    """Der eigentliche Regressionstest: die Oberflaeche darf nicht einfrieren."""
    tree = _tree()
    spans = _spans(_worker_classes(tree))

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name not in BLOCKING:
            continue
        # Methodenaufrufe auf self (self.diagnose(...)) sind Starter, keine Arbeit.
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) \
                and node.func.value.id == "self":
            continue
        if not any(start <= node.lineno <= end for start, end in spans):
            offenders.append((node.lineno, name))

    assert not offenders, (
        "Blockierender Aufruf ausserhalb jeder Worker-Klasse — laeuft im GUI-Thread "
        f"und friert die Oberflaeche ein: {offenders}"
    )


def test_every_worker_is_moved_to_a_thread() -> None:
    """Die Pruefung, die APP-RUNTIME-STANDARD 5c ausdruecklich vorschreibt.

    Eine Worker-Klasse ohne `moveToThread` laeuft trotz ihres Namens im
    GUI-Thread. Klaffen die Zahlen auseinander, laeuft die Differenz dort.
    """
    tree = _tree()
    workers = _worker_classes(tree)
    moves = sum(1 for n in ast.walk(tree)
                if isinstance(n, ast.Call)
                and getattr(n.func, "attr", "") == "moveToThread")

    assert len(workers) == moves, (
        f"{len(workers)} Worker-Klassen, aber {moves} moveToThread-Aufrufe — "
        "die Differenz laeuft im GUI-Thread."
    )


def test_config_audit_worker_returns_its_result_via_signal() -> None:
    """Der Worker rechnet und meldet per Signal — er fasst kein Widget an."""
    from codex_logdatenbank_wartung.tray import ConfigAuditWorker

    config = object()
    report, cycle = object(), object()
    received = []

    with patch("codex_logdatenbank_wartung.health.diagnose") as diagnose, \
            patch("codex_logdatenbank_wartung.config_audit.run_manual_audit",
                  return_value=(report, cycle)) as audit:
        diagnose.return_value.renderer_present = True
        worker = ConfigAuditWorker(config)  # type: ignore[arg-type]
        worker.finished.connect(received.append)
        worker.run()

    diagnose.assert_called_once_with(config)
    audit.assert_called_once_with(config, renderer_present=True)
    assert received == [(report, cycle)]


def test_config_audit_worker_touches_no_widget() -> None:
    """Kein Widget-/Tray-Zugriff im Worker-Thread (Qt verzeiht das nicht zuverlaessig)."""
    tree = _tree()
    worker = next(c for c in _worker_classes(tree) if c.name == "ConfigAuditWorker")
    verboten = ("window", "tray", "showMessage", "setToolTip")
    hits = [n.attr for n in ast.walk(worker)
            if isinstance(n, ast.Attribute) and n.attr in verboten]
    assert not hits, f"ConfigAuditWorker fasst Widgets an: {hits}"
