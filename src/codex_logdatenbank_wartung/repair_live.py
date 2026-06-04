"""Echte Windows-Implementierungen der mutierenden Reparatur-Bausteine (LIVE).

Dieses Modul belegt die injizierbaren Callables aus ``repair_workflow.RepairDeps``
mit *realen* PowerShell-/AppX-Operationen und reicht sie an ``run_repair`` weiter.
Es ist die Bruecke zwischen der vollstaendig getesteten, hang-sicheren Eskalations-
Engine (``repair_workflow.py``) und der Windows-Wirklichkeit.

Wichtige Annahmen (siehe CODEX-AUTO-DEBUG-DESIGN.md):

* **KEINE Elevation, NIEMALS Selbst-UAC.** Die App elevatet sich NIE selbst. Der fruehere
  UAC-Selbstaufruf verklemmte den Appinfo-Dienst (Application Information / Elevation) dauerhaft
  ('kein Fenster geoeffnet, dann nicht bestaetigt' -> Dienst haengt bis Reboot bei ~99% CPU).
  >>> WARNUNG: Hier KEINE Elevation (runas / ShellExecute -Verb / requireAdministrator-Manifest)
  wieder einbauen. <<< Reparaturen laufen mit den Rechten des aktuellen Prozesses. Scheitert eine
  Deploy-Op EINDEUTIG an fehlenden Rechten (Access Denied), bricht die Engine ab und meldet dem
  User 'als Administrator neu starten' (``needs_admin``) -- statt selbst zu elevaten.
* **Akkurate Beobachtung statt Datei-Glob.** ``observe()`` erhebt den staged-Wedge
  getreu ueber ``Get-AppxPackage -AllUsers OpenAI.Codex`` (Staged fuer S-1-5-18 neben
  einer aelteren Installed-Version fuer den aktuellen User) und ``Get-Service ClipSVC``.
* **Hang-Sicherheit bleibt die einzige harte Regel.** Die Beobachtung selbst darf
  niemals haengen oder den Lauf crashen lassen (z.B. bei verklemmter AppX-Engine);
  daher laeuft jeder PowerShell-Aufruf mit Timeout und faellt im Fehlerfall auf
  konservative Defaults zurueck (staged_update=False, package_user_registered=True).
* ``run_with_timeout`` und ``clock`` bleiben bewusst auf den Defaults aus
  ``repair_workflow`` (Daemon-Thread-Timeout) -- sie werden NICHT ueberschrieben.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import time as _time
from collections.abc import Callable

from .config import MaintenanceConfig
from .processes import (
    find_codex_processes_by_executable,
    no_window_kwargs,
    process_type,
)
from .repair_workflow import (
    AdminRequired,
    DeployTimeout,
    RepairDeps,
    RepairOutcome,
    RepairState,
    run_repair,
)

# Runner fuehrt einen PowerShell-Befehl aus und liefert (returncode, ausgabe).
PowerShellRunner = Callable[[str], "tuple[int, str]"]

# Codex-Store-Paketname (stabiler Familienname, versionsunabhaengig).
CODEX_PACKAGE = "OpenAI.Codex"
# SID des lokalen SYSTEM-Kontos -- fuer dieses Konto wird ein Store-Update gestaged.
SYSTEM_SID = "S-1-5-18"


def _tree_kill(pid: int) -> None:
    """Beende den Prozessbaum (powershell.exe + Kinder) hart -- ohne je zu haengen/crashen.

    Vorbild: watchdog Companion-Orphan-Reaper. ``taskkill /T`` killt den Baum, ``/F`` erzwingt.
    Eigener kurzer Timeout, alle Fehler geschluckt (Best-Effort-Aufraeumen).
    """
    with contextlib.suppress(Exception):  # noqa: BLE001 -- Aufraeumen darf den Lauf nie crashen
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(pid)],
            check=False,
            capture_output=True,
            timeout=10,
            **no_window_kwargs(),
        )


def default_ps_runner(command: str, *, timeout: float = 30.0) -> tuple[int, str]:
    """Fuehre einen PowerShell-Befehl ohne Konsolenfenster aus, mit hartem Timeout + Tree-Kill.

    Der Timeout ist Teil der Hang-Sicherheit: eine verklemmte AppX-Engine darf den
    aufrufenden Lauf nicht ewig blockieren. Reisst der Timeout, wird NICHT nur der direkte
    ``powershell.exe`` beendet (das tat ``subprocess.run(timeout=)`` frueher), sondern der
    ganze **Prozessbaum** (``taskkill /T /F``) -- so bleiben keine vom Deploy gestarteten
    Kindprozesse als Zombies zurueck (genau diese stapelten sich frueher bei voller Eskalation).

    EHRLICHE GRENZE: Der Tree-Kill verhindert NEUE Orphan-Kinder, HEILT aber keine bereits
    verklemmte AppX-Engine -- die laeuft im Dienst ``AppXSVC``, nicht als Kind von powershell.exe.
    Dafuer hilft nur ein Reboot (darum meldet die Engine bei Timeout ``recommend_reboot``).

    Rueckgabecode **124** signalisiert den Timeout (stabiler Vertrag mit ``classify_ps_outcome``
    -> ``DeployTimeout`` in der Engine). Nie eine Exception nach aussen.
    """
    try:
        proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **no_window_kwargs(),
        )
    except OSError as exc:
        # PowerShell nicht startbar -> sauberer Fehlschlag (kein Timeout, kein Crash).
        return 1, f"PowerShell-Start fehlgeschlagen: {exc}"
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _tree_kill(proc.pid)  # ganzen Baum hart beenden -> keine Zombie-PowerShell
        try:
            stdout, stderr = proc.communicate(timeout=5)  # Pipes leeren, Handles freigeben
        except Exception:  # noqa: BLE001 -- Prozess ist tot; Reste ignorieren
            stdout, stderr = "", ""
        return 124, "PowerShell-Timeout"
    output = ((stdout or "") + (stderr or "")).strip()
    return proc.returncode, output


# Eindeutige Access-Denied-Signale (DE+EN + HRESULT) -> Admin noetig.
# BEWUSST ENG gehalten: Korruptions-/Konflikt-Fehler (z.B. 0x80073CF9 'package could not be
# registered', 0x80073D02 'resources are currently in use') sind NICHT Admin -> 'unklar' ->
# Fallback. Lieber einmal zu wenig Admin melden (dann laeuft der Fallback) als faelschlich
# (dann falsche 'als Admin neu starten'-Meldung + uebersprungener, funktionierender Fallback).
_ACCESS_DENIED_MARKERS = (
    "access is denied",
    "zugriff verweigert",
    "requires elevation",
    "requires administrator",
    "run as administrator",
    "als administrator",
    "administratorrechte",
    "elevated permissions",
    "unauthorizedaccess",
    "0x80070005",  # E_ACCESSDENIED
)


def classify_ps_outcome(rc: int, output: str) -> str:
    """Klassifiziere ein PowerShell-Deploy-Ergebnis (reine, testbare Funktion).

    Rueckgabe: ``"ok" | "timeout" | "needs_admin" | "failed"``.
      * ``"timeout"``     -> rc == 124 (Timeout-Sentinel aus ``default_ps_runner``).
      * ``"needs_admin"`` -> Ausgabe enthaelt ein EINDEUTIGES Access-Denied-Signal (DE/EN/HRESULT).
      * ``"ok"``          -> rc == 0 und kein Admin-Signal.
      * ``"failed"``      -> alles andere (rc != 0, unklarer Fehler -> Fallback erlaubt).
    """
    if rc == 124:
        return "timeout"
    low = (output or "").lower()
    if any(marker in low for marker in _ACCESS_DENIED_MARKERS):
        return "needs_admin"
    if rc == 0:
        return "ok"
    return "failed"


def _raise_for_deploy(rc: int, output: str) -> None:
    """Wirf die passende Engine-Exception fuer ein klassifiziertes Deploy-Ergebnis.

    NUR auf das Ergebnis des *mutierenden* Befehls anwenden -- nicht auf interne
    observe-Reads (sonst wuerde eine reine Beobachtung faelschlich abbrechen).
    Bei "ok"/"failed" wird NICHT geworfen: ein sauberer, unklarer Fehlschlag bleibt 'failed'
    und erlaubt der Engine den einen Fallback.
    """
    verdict = classify_ps_outcome(rc, output)
    if verdict == "timeout":
        raise DeployTimeout(output or "PowerShell-Timeout")
    if verdict == "needs_admin":
        raise AdminRequired(output or "Zugriff verweigert")


def _coerce_list(raw: object) -> list[dict[str, object]]:
    """PowerShell faltet einelementige Arrays zu einem blossen Objekt -- hier wieder
    in eine Liste von Dicts normalisieren (analog ``processes._as_process_list``)."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


def _version_tuple(version: str) -> tuple[int, ...]:
    """Versionsstring (z.B. '26.519.0.0') als Tupel von Ints fuer korrekten Vergleich.

    String-Vergleich waere falsch ('26.5' > '26.519'); daher numerisch vergleichen.
    """
    parts: list[int] = []
    for chunk in str(version).split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def parse_codex_packages(json_text: str) -> tuple[bool, bool, str]:
    """Werte die ``Get-AppxPackage -AllUsers``-Projektion aus (pure Funktion, testbar).

    Erwartet das von ``_OBSERVE_PACKAGES_PS`` projizierte Schema:
    ``{ "CurrentUserSid": str, "Packages": [ { "FullName", "Version",
    "Users": [ { "Sid", "State" } ] } ] }``.

    Rueckgabe ``(staged_update, package_user_registered, staged_pfn)``:
    * ``staged_update``: Die *neueste* Version ist fuer SYSTEM (S-1-5-18) 'Staged',
      waehrend der aktuelle User nur auf einer *aelteren* Version 'Installed' ist
      (oder gar nicht) -- das ist der dokumentierte staged-Wedge.
    * ``package_user_registered``: Der aktuelle User hat irgendeine Version 'Installed'.
    * ``staged_pfn``: PackageFullName der gestagten, NICHT user-registrierten (neuesten)
      Version -- Ziel fuer ``remove_staged_version``. Leer, wenn kein staged-Wedge.
    """
    try:
        data = json.loads(json_text)
    except (json.JSONDecodeError, TypeError):
        # Konservativ: kein erkannter Wedge, User gilt als registriert (nichts erzwingen).
        return False, True, ""
    if not isinstance(data, dict):
        return False, True, ""

    current_sid = str(data.get("CurrentUserSid") or "")
    packages = _coerce_list(data.get("Packages"))

    # Leeres Objekt ('{}' = PowerShell-catch-Fallback) ODER keine Pakete: konservativ
    # behandeln (nichts erzwingen) -- "konnte nicht ermittelt werden" != "nicht installiert".
    if not packages:
        return False, True, ""

    # Pro Paket: hoechste Version (Tupel), die States je SID.
    user_installed_versions: list[tuple[int, ...]] = []
    # Kandidaten fuer den staged-Wedge: (Version-Tupel, PackageFullName).
    system_staged: list[tuple[tuple[int, ...], str]] = []

    for pkg in packages:
        version = _version_tuple(str(pkg.get("Version") or ""))
        full_name = str(pkg.get("FullName") or "")
        users = _coerce_list(pkg.get("Users"))
        for user in users:
            sid = str(user.get("Sid") or "")
            state = str(user.get("State") or "")
            if sid == current_sid and state == "Installed":
                user_installed_versions.append(version)
            if sid == SYSTEM_SID and state == "Staged":
                system_staged.append((version, full_name))

    package_user_registered = bool(user_installed_versions)
    newest_user = max(user_installed_versions) if user_installed_versions else ()

    # staged-Wedge: es gibt eine gestagte SYSTEM-Version, die NEUER ist als alles,
    # was der User installiert hat (oder der User hat ueberhaupt nichts installiert).
    staged_update = False
    staged_pfn = ""
    if system_staged:
        newest_staged_version, newest_staged_pfn = max(system_staged, key=lambda item: item[0])
        if not user_installed_versions or newest_staged_version > newest_user:
            staged_update = True
            staged_pfn = newest_staged_pfn
    return staged_update, package_user_registered, staged_pfn


def parse_package_absence(json_text: str) -> bool:
    """True NUR, wenn das Store-Paket nachweislich vollstaendig abwesend ist.

    Entscheidend ist die Unterscheidung **erfolgreich-aber-leer** (Paket wirklich weg)
    von **Abfrage fehlgeschlagen** (z.B. nicht-elevated 'Zugriff verweigert', Timeout):

    * Erfolg projiziert immer ein Objekt mit ``Packages`` (und ``CurrentUserSid``);
      eine leere ``Packages``-Liste heisst dann: fuer NIEMANDEN registriert/gestaged.
    * Der catch-Fallback der Projektion ist ``'{}'`` -- ohne ``Packages``-Schluessel.
      Den (sowie ``'[]'``, ``''`` und Garbage) NICHT als absent werten -> konservativ False.
    * Falls ``WindowsAppsPresent`` projiziert ist, gilt absent nur, wenn auch KEIN
      ``OpenAI.Codex*``-Ordner unter ``WindowsApps`` existiert (Zusatzguard gegen
      inkonsistente Paket-DB bei real noch vorhandenen Dateien).

    Lieber einmal zu wenig absent melden als faelschlich (sonst empfiehlt die Engine eine
    unnoetige Store-Neuinstallation, wo ein simples RegisterByFamilyName gereicht haette).
    """
    try:
        data = json.loads(json_text)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(data, dict) or "Packages" not in data:
        return False
    if _coerce_list(data.get("Packages")):
        return False  # Pakete vorhanden -> nicht absent
    windowsapps_present = data.get("WindowsAppsPresent")
    if windowsapps_present is None:
        return True  # erfolgreich-leer, kein Zusatzguard projiziert
    return not bool(windowsapps_present)


# ---------------------------------------------------------------------------
# PowerShell-Bausteine
# ---------------------------------------------------------------------------

# Read-only Projektion der AppX-Paketlage in ein stabiles JSON-Schema.
# Bewusst KEIN ConvertTo-Json auf das rohe AppxPackage-Objekt (PackageUserInformation
# ist ein Spezialtyp, InstallState ein Enum -- Standard-Serialisierung ist instabil).
_OBSERVE_PACKAGES_PS = (
    "$ErrorActionPreference='Stop'; "
    "try { "
    f"$pkgs = Get-AppxPackage -AllUsers {CODEX_PACKAGE}; "
    # WindowsApps-Zusatzguard fuers absent-Signal: existiert ein OpenAI.Codex*-Ordner?
    # Bei Lesefehler (z.B. nicht-elevated) konservativ True -> kein faelschliches 'absent'.
    "$wa = $false; "
    "try { if (Get-ChildItem 'C:\\Program Files\\WindowsApps' -Directory -ErrorAction Stop | "
    f"Where-Object {{ $_.Name -like '{CODEX_PACKAGE}*' }}) {{ $wa = $true }} }} catch {{ $wa = $true }}; "
    "[pscustomobject]@{ "
    "CurrentUserSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value; "
    "WindowsAppsPresent = $wa; "
    "Packages = @(foreach ($p in $pkgs) { [pscustomobject]@{ "
    "FullName = [string]$p.PackageFullName; "
    "Version = [string]$p.Version; "
    "Users = @(foreach ($u in $p.PackageUserInformation) { [pscustomobject]@{ "
    "Sid = [string]$u.UserSecurityId.Sid; State = [string]$u.InstallState } }) } }) "
    "} | ConvertTo-Json -Depth 6 -Compress "
    "} catch { '{}' }"
)

# Read-only: laeuft ClipSVC? (verhindert Aktivierungsfehler 0x8000001A)
_CLIPSVC_STATUS_PS = (
    "$ErrorActionPreference='Stop'; "
    "try { (Get-Service ClipSVC).Status.ToString() } catch { 'Unknown' }"
)


def _family_name(aumid: str) -> str:
    """AUMID-Familienname (vor dem '!') aus der konfigurierten Store-AppID ableiten.

    Beispiel: 'OpenAI.Codex_2p2nqsd0c76g0!App' -> 'OpenAI.Codex_2p2nqsd0c76g0'.
    """
    return (aumid or "").split("!", 1)[0]


def build_live_deps(
    config: MaintenanceConfig,
    *,
    runner: PowerShellRunner | None = None,
) -> RepairDeps:
    """Erzeuge ``RepairDeps`` mit ECHTEN Windows-Implementierungen.

    Alle mutierenden Deps sind zero-arg (so verlangt es das ``RepairDeps``-Protokoll)
    und leiten ihr jeweiliges Ziel selbst aus der aktuellen Lage ab -- ``RepairState``
    transportiert bewusst keine PIDs/PackageFullNames.

    Es wird NIE eine Elevation/UAC ausgeloest: der Lauf nutzt die Rechte des aktuellen
    Prozesses. Scheitert eine Deploy-Op an fehlenden Rechten, signalisiert sie das ueber
    ``AdminRequired`` an die Engine (-> ``needs_admin`` -> 'als Administrator neu starten').
    """
    from .health import default_tree_killer, diagnose
    from .orchestrator import default_launcher

    runner = runner or default_ps_runner
    family = _family_name(getattr(config, "codex_store_aumid", "") or "")
    launcher = default_launcher(config)

    def observe() -> RepairState:
        # Prozesszustand getreu aus der bestehenden Diagnose.
        report = diagnose(config)
        store_installed = bool(getattr(config, "codex_store_aumid", "") or "")

        # ClipSVC-Status (read-only, mit Timeout -> nie haengend).
        clipsvc_running = True
        try:
            _rc, clip_out = runner(_CLIPSVC_STATUS_PS)
            clipsvc_running = clip_out.strip() == "Running"
        except Exception:  # noqa: BLE001 -- Beobachtung darf den Lauf nie crashen
            clipsvc_running = True

        # AppX-Paketlage: staged-Wedge + User-Registrierung + absent (read-only, mit Timeout).
        staged_update = False
        package_user_registered = True
        package_absent = False
        try:
            _rc, pkg_out = runner(_OBSERVE_PACKAGES_PS)
            staged_update, package_user_registered, _pfn = parse_codex_packages(pkg_out)
            package_absent = parse_package_absence(pkg_out)
        except Exception:  # noqa: BLE001 -- konservative Defaults im Fehlerfall
            staged_update = False
            package_user_registered = True
            package_absent = False

        return RepairState(
            codex_present=bool(report.main_pids),
            renderer_present=report.renderer_present,
            ghost_pids=list(report.zombie_main_pids),
            stale_lockfile=report.stale_lockfile,
            clipsvc_running=clipsvc_running,
            staged_update=staged_update,
            package_user_registered=package_user_registered,
            codex_exe_present=report.codex_exe_present or store_installed,
            package_absent=package_absent,
        )

    def kill_ghosts() -> str:
        # Ziel selbst aus der aktuellen Diagnose ableiten (RepairState traegt keine PIDs).
        report = diagnose(config)
        beendet: list[int] = []
        for pid in report.zombie_main_pids:
            ok, _msg = default_tree_killer(pid)
            if ok:
                beendet.append(pid)
        return f"Ghost-Prozesse beendet: {beendet}" if beendet else "keine Ghost-PIDs"

    def clear_lockfile() -> str:
        lockfile = config.lockfile_path
        try:
            lockfile.unlink()
            return f"Lockfile entfernt: {lockfile}"
        except FileNotFoundError:
            return "kein Lockfile vorhanden"

    def ensure_clipsvc() -> str:
        rc, out = runner("Start-Service ClipSVC")
        return out or ("ClipSVC gestartet" if rc == 0 else f"Start-Service ClipSVC rc={rc}")

    def complete_staged_update() -> str:
        # Sanfte, historisch korrekte Behebung des staged-Wedge: nur registrieren.
        if not family:
            return "kein Store-Familienname konfiguriert -- uebersprungen"
        rc, out = runner(
            f"Add-AppxPackage -RegisterByFamilyName -MainPackage \"{family}\""
        )
        # Fehlerart des MUTIERENDEN Befehls an die Engine durchreichen (Timeout/Admin).
        _raise_for_deploy(rc, out)
        return out or f"RegisterByFamilyName rc={rc}"

    def remove_staged_version() -> str:
        # Gestagte, NICHT user-registrierte (neueste) Version ermitteln und entfernen.
        _rc, pkg_out = runner(_OBSERVE_PACKAGES_PS)
        _staged, _registered, staged_pfn = parse_codex_packages(pkg_out)
        if not staged_pfn:
            return "keine gestagte Ueberschuss-Version gefunden"
        rc, out = runner(f"Remove-AppxPackage -Package \"{staged_pfn}\" -AllUsers")
        return out or f"Remove-AppxPackage {staged_pfn} rc={rc}"

    def reset_package() -> str:
        rc, out = runner(f"Get-AppxPackage {CODEX_PACKAGE} | Reset-AppxPackage")
        # Fehlerart des MUTIERENDEN Befehls an die Engine durchreichen (Timeout/Admin).
        _raise_for_deploy(rc, out)
        return out or f"Reset-AppxPackage rc={rc}"

    def reinstall_package() -> str:
        if not family:
            return "kein Store-Familienname konfiguriert -- uebersprungen"
        # PRAEVENTION (Root-Cause 29.05): GAR KEIN destruktives Remove. Jedes 'Remove-AppxPackage'
        # -- auch ohne '-AllUsers' -- verwaist das Paket, sobald es die LETZTE Referenz ist
        # (User-only installiert, KEINE SYSTEM-Staged-Kopie als Quelle, der haeufigste Fall):
        # Windows loescht dann die Payload-Dateien, und das anschliessende 'Add' findet nichts
        # mehr. Ein destruktiver Schritt brachte hier ohnehin KEINE zusaetzliche Recovery-Kraft
        # (S6 wird nur erreicht, wenn S3-Register und S5-Reset schon erfolglos waren; 'Add' ist
        # dasselbe Register wie S3), nur Orphan-Risiko. Daher reines, idempotentes Re-Register aus
        # den vorhandenen Dateien -- es repariert eine kaputte Registrierung und loescht NIE.
        # '-ForceApplicationShutdown' betrifft nur Prozesse des AppX-Pakets OpenAI.Codex, NICHT
        # die node-basierten npm-CLI-codex.exe (User-Regel: CLI-Prozesse muessen ueberleben).
        rc, out = runner(
            f"Add-AppxPackage -RegisterByFamilyName -MainPackage \"{family}\" -ForceApplicationShutdown"
        )
        return out or f"Reinstall (idempotentes Re-Register, kein Remove) rc={rc}"

    def launch_codex() -> str:
        ok, msg = launcher()
        return msg if ok else f"Start fehlgeschlagen: {msg}"

    def renderer_appears(timeout: float) -> bool:
        # Leichtgewichtiges Polling: bis zum Deadline pruefen, ob ein Codex-Renderer
        # erscheint. Bewusst kein observe_activity (doppelte CPU-Stichprobe waere zu schwer).
        deadline = _time.monotonic() + max(0.0, float(timeout))
        interval = 2.5
        while True:
            procs = find_codex_processes_by_executable(config)
            if any(process_type(p) == "renderer" for p in procs):
                return True
            if _time.monotonic() >= deadline:
                return False
            _time.sleep(interval)

    return RepairDeps(
        observe=observe,
        kill_ghosts=kill_ghosts,
        clear_lockfile=clear_lockfile,
        ensure_clipsvc=ensure_clipsvc,
        complete_staged_update=complete_staged_update,
        remove_staged_version=remove_staged_version,
        reset_package=reset_package,
        reinstall_package=reinstall_package,
        launch_codex=launch_codex,
        renderer_appears=renderer_appears,
        sleeper=_time.sleep,
        # run_with_timeout + clock bleiben bewusst auf den RepairDeps-Defaults.
    )


def run_live_repair(
    config: MaintenanceConfig,
    *,
    execute: bool = False,
    dry_run: bool = False,
    progress: Callable[[object], None] | None = None,
) -> RepairOutcome:
    """Fuehre die volle, hang-sichere Eskalation mit ECHTEN Windows-Deps aus.

    Duenne Huelle um ``run_repair`` mit ``build_live_deps``. ``dry_run`` bzw.
    ``execute=False`` ruft kein mutierendes Dep auf (nur Planung, keine Elevation noetig).
    """
    return run_repair(
        config,
        build_live_deps(config),
        execute=execute,
        dry_run=dry_run,
        progress=progress,
    )
