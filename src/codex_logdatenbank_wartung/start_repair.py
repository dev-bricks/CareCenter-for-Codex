"""Klassifikation der Start-Lage fuer die EINE zusammengefasste 'Codex reparieren'-Eskalation.

Der Tray bietet nur noch einen Eintrag, der als Eskalationskette laeuft und stoppt, sobald
Codex startet (siehe CODEX-AUTO-DEBUG-DESIGN.md). Reihenfolge der Idee:

  1. Laeuft Codex schon (Renderer)?              -> nichts tun.
  2. Gibt es ueberhaupt eine Codex-Installation?  -> nein: frueh und OHNE UAC den
     Vorschlag 'aus dem Store neu installieren' (es ist Teil desselben Problems
     "Codex startet nicht" -- nur eben die Wurzel "es ist keins mehr da").
  3. Haengende Reste (Ghost/Lockfile)?            -> leichte Stufe OHNE UAC: reapen,
     starten, auf Renderer pruefen.
  4. sonst (installiert, aber Start scheitert)    -> begrenzte Reparatur OHNE UAC: ClipSVC,
     sanftes Re-Register (S3) + EIN Reset-Fallback; am Ende ggf. Reboot-, Admin- oder
     Store-Neuinstallations-Vorschlag (NIE Selbst-Elevation).

Diese Datei haelt die *reine*, testbare Entscheidung; die Tray-Schicht fuehrt sie aus.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from .config import MaintenanceConfig

StartDecision = Literal["already_running", "needs_store_reinstall", "reap", "needs_escalation"]

PowerShellRunner = Callable[[str], "tuple[int, str]"]


def classify_start_state(
    *,
    renderer_present: bool,
    codex_installed: bool,
    zombie_pids: list[int],
    stale_lockfile: bool,
) -> StartDecision:
    """Leite die naechste Eskalationsstufe aus der read-only Lage ab (pure Funktion)."""
    if renderer_present:
        return "already_running"
    if not codex_installed:
        # Wurzel des Start-Problems: es gibt gar kein Codex mehr -> Reinstall-Vorschlag.
        return "needs_store_reinstall"
    if zombie_pids or stale_lockfile:
        return "reap"
    return "needs_escalation"


def codex_installed_for_user(
    config: MaintenanceConfig, *, runner: PowerShellRunner | None = None
) -> bool:
    """Ist irgendeine Codex-Desktop-Installation fuer den User da? (nicht-elevated pruefbar)

    Wahr, wenn entweder die Standalone-Exe existiert ODER das Store-Paket fuer den
    aktuellen User registriert ist (``Get-AppxPackage OpenAI.Codex`` OHNE ``-AllUsers``,
    laeuft ohne Admin). Im Fehlerfall konservativ ``True`` -- lieber keinen faelschlichen
    Reinstall-Vorschlag, als den User unnoetig in den Store schicken.
    """
    try:
        if Path(config.codex_executable).exists():
            return True
    except OSError:
        pass
    from .store_repair import default_ps_runner

    runner = runner or default_ps_runner
    try:
        _rc, out = runner("$p = Get-AppxPackage OpenAI.Codex; if ($p) { 'yes' } else { 'no' }")
        return out.strip().lower().startswith("yes")
    except Exception:  # noqa: BLE001 -- im Zweifel als installiert behandeln
        return True
