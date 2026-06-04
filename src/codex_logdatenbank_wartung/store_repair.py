"""Reparatur von Microsoft-Store-Problemen fuer die Codex-Desktop-App.

Hintergrund: Die Codex-Desktop-App wird ausschliesslich ueber den Microsoft Store
verteilt und aktualisiert (offiziell bestaetigt). Der Store haengt gelegentlich bei
Updates ("aktualisiert ewig ohne Fortschritt") und kann dann sogar den Start
blockieren. Dieses Modul kapselt die ueblichen, abgestuften Reparaturen:

* ``wsreset``  -- Store-Cache leeren (harmlos).
* ``repair``   -- Codex-Appx-Paket neu registrieren (Add-AppxPackage -Register);
                  nicht-destruktiv, behaelt App-Daten.
* ``reset``    -- Codex-Appx-Paket zuruecksetzen (Reset-AppxPackage); setzt die
                  paketeigenen App-Daten zurueck. Bewusst opt-in. ``~/.codex``
                  (Logs/Sessions) liegt ausserhalb des Pakets und bleibt unberuehrt.

Alle PowerShell-Aufrufe laufen ohne Konsolenfenster und sind ueber einen
injizierbaren Runner testbar (keine echten Store-Eingriffe im Test).
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Literal

from .processes import no_window_kwargs

RepairLevel = Literal["wsreset", "repair", "reset"]

# Runner fuehrt einen PowerShell-Befehl aus und liefert (returncode, ausgabe).
PowerShellRunner = Callable[[str], "tuple[int, str]"]

DEFAULT_PACKAGE = "OpenAI.Codex"


def default_ps_runner(command: str) -> tuple[int, str]:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **no_window_kwargs(),
    )
    output = ((completed.stdout or "") + (completed.stderr or "")).strip()
    return completed.returncode, output


@dataclass(slots=True)
class StoreRepairStep:
    name: str
    status: str
    message: str


@dataclass(slots=True)
class StoreRepairResult:
    status: str
    level: RepairLevel
    dry_run: bool
    steps: list[StoreRepairStep] = field(default_factory=list)

    def add(self, name: str, status: str, message: str) -> None:
        self.steps.append(StoreRepairStep(name, status, message))

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_text(self) -> str:
        lines = [f"Status: {self.status}", f"Stufe: {self.level}", f"Dry-Run: {self.dry_run}", "Schritte:"]
        for step in self.steps:
            lines.append(f"  - [{step.status}] {step.name}: {step.message}")
        return "\n".join(lines)


def build_command(level: RepairLevel, package: str = DEFAULT_PACKAGE) -> str:
    """Erzeuge den PowerShell-Befehl fuer die gewuenschte Reparaturstufe."""
    if level == "wsreset":
        return "Start-Process -FilePath wsreset.exe -WindowStyle Hidden -Wait"
    if level == "repair":
        return (
            f"$p = Get-AppxPackage {package}; "
            "if ($p) { Add-AppxPackage -DisableDevelopmentMode -Register "
            "(Join-Path $p.InstallLocation 'AppXManifest.xml') } "
            f"else {{ Write-Error 'Paket {package} nicht gefunden' }}"
        )
    if level == "reset":
        return f"Get-AppxPackage {package} | Reset-AppxPackage"
    raise ValueError(f"Unbekannte Reparaturstufe: {level}")


def repair_store_codex(
    *,
    level: RepairLevel = "repair",
    execute: bool = False,
    package: str = DEFAULT_PACKAGE,
    runner: PowerShellRunner | None = None,
) -> StoreRepairResult:
    runner = runner or default_ps_runner
    result = StoreRepairResult(status="dry-run" if not execute else "ok", level=level, dry_run=not execute)
    command = build_command(level, package)

    if not execute:
        result.add(level, "planned", f"Würde ausführen: {command}")
        return result

    returncode, output = runner(command)
    if returncode == 0:
        result.add(level, "ok", output or "erfolgreich")
        result.status = "ok"
    else:
        result.add(level, "failed", output or f"Rückgabewert {returncode}")
        result.status = "failed"
    return result


def store_pdp_uri(product_id: str) -> str:
    """ms-windows-store-Deeplink auf die Produktseite (zum 1-Klick-Installieren)."""
    return f"ms-windows-store://pdp/?ProductId={product_id}"


def open_store_page(
    product_id: str, *, runner: PowerShellRunner | None = None
) -> tuple[bool, str]:
    """Oeffne die Store-Produktseite der App (nicht-elevated, KEIN Systemeingriff).

    Bewusst nur die Produktseite oeffnen (statt ``winget install ... --source msstore``):
    Das ist der robusteste Weg fuer den *absenten* Fall -- der User klickt im Store
    "Installieren", ohne Risiko durch ID-Raten oder interaktive winget-/MSA-Auth.
    Genutzt wird die in der Config verifizierte Produkt-ID der OpenAI-Codex-Desktop-App.
    """
    runner = runner or default_ps_runner
    uri = store_pdp_uri(product_id)
    rc, out = runner(f"Start-Process '{uri}'")
    return rc == 0, (out or uri)


def store_package_status(
    *, package: str = DEFAULT_PACKAGE, runner: PowerShellRunner | None = None
) -> str:
    """Kurzstatus des Store-Pakets (Version/Status) — read-only."""
    runner = runner or default_ps_runner
    command = (
        f"$p = Get-AppxPackage {package}; "
        "if ($p) { \"$($p.Name) $($p.Version) Status=$($p.Status)\" } "
        "else { 'nicht installiert' }"
    )
    _rc, output = runner(command)
    return output.strip()
