"""Konfiguration für die Codex-Logdatenbank-Wartung."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_DATA_DIR_NAME = "CareCenterForCodex"
LEGACY_LOCAL_ROOT = Path(r"C:\_Local_DEV\codex-maintenance")


def _local_appdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))


def local_root() -> Path:
    """Daten-Root mit Env-Override, AppData-Default und Legacy-Fallback.

    Neue Installationen nutzen `%LOCALAPPDATA%\\CareCenterForCodex`, damit die
    Veröffentlichung keinen benutzerspezifischen oder manuell vorbereiteten Pfad
    voraussetzt. Bestehende lokale Setups unter `C:\\_Local_DEV\\codex-maintenance`
    bleiben kompatibel, solange dieser Legacy-Pfad bereits existiert.
    """
    if env := os.environ.get("CCC_DATA_ROOT"):
        return Path(env)
    appdata_root = _local_appdata() / DEFAULT_DATA_DIR_NAME
    if appdata_root.exists() or not LEGACY_LOCAL_ROOT.exists():
        return appdata_root
    return LEGACY_LOCAL_ROOT


def default_config_path() -> Path:
    return local_root() / "config.json"


# Import-Zeit-Aliase für Abwärtskompatibilität (cli.py, scheduler.py, tray_app.py).
LOCAL_ROOT = local_root()
DEFAULT_CONFIG_PATH = default_config_path()


def default_codex_home() -> Path:
    """Liefere den Codex-Home-Pfad mit robuster Fallback-Logik."""
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


def default_database_path() -> Path:
    return default_codex_home() / "logs_2.sqlite"


def _roaming_appdata() -> Path:
    return Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))


def default_codex_install_dir() -> Path:
    """Standardpfad der Codex-Standalone-Installation (nutzerunabhaengig ueber %LOCALAPPDATA%)."""
    return _local_appdata() / "Programs" / "Codex"


def default_codex_executable() -> Path:
    return default_codex_install_dir() / "Codex.exe"


def default_codex_user_data_dir() -> Path:
    """Electron-Profilordner der Codex-App (nutzerunabhaengig ueber %APPDATA%)."""
    return _roaming_appdata() / "Codex"


@dataclass(slots=True)
class MaintenanceConfig:
    """Persistente Konfiguration der Wartungssoftware."""

    database_path: str = field(default_factory=lambda: str(default_database_path()))
    backup_dir: str = field(default_factory=lambda: str(local_root() / "backups"))
    log_dir: str = field(default_factory=lambda: str(local_root() / "logs"))
    maintenance_lock_path: str = field(default_factory=lambda: str(local_root() / "maintenance.lock"))
    codex_executable: str = field(default_factory=lambda: str(default_codex_executable()))
    codex_install_dir: str = field(default_factory=lambda: str(default_codex_install_dir()))
    # Stabiler Pfad-Marker der Store-Version (versionsabhaengiger WindowsApps-Pfad).
    # So wird Codex erkannt, egal ob Standalone-Kopie oder Microsoft-Store-App laeuft.
    codex_store_marker: str = r"\WindowsApps\OpenAI.Codex"
    # Stabile Store-AppID (AUMID) zum Starten der Store-Version -- ueberlebt Versions-Updates.
    # Wenn gesetzt, ist Codex als Store-App installiert (kein "Codex.exe fehlt"-Fehlalarm).
    codex_store_aumid: str = "OpenAI.Codex_2p2nqsd0c76g0!App"
    # Microsoft-Store-Produkt-ID der offiziellen OpenAI-Codex-Desktop-App (verifiziert
    # 2026-05-30 via 'winget show 9PLM9XGG6VKS --source msstore' -> Herausgeber OpenAI).
    # Ziel fuer die Store-Neuinstallation, wenn das Paket vollstaendig abwesend ist
    # (RegisterByFamilyName kann dann nichts mehr registrieren -- nur ein frischer
    # Store-Download hilft). 'OpenAI.Codex' in winget ist dagegen die CLI, NICHT die App.
    codex_store_product_id: str = "9PLM9XGG6VKS"
    codex_user_data_dir: str = field(default_factory=lambda: str(default_codex_user_data_dir()))
    codex_process_names: list[str] = field(
        default_factory=lambda: ["Codex", "codex", "node_repl"]
    )
    allow_stop_codex: bool = False
    allow_force_stop_codex: bool = False
    allow_onedrive_control: bool = False
    allow_vacuum: bool = True
    allow_optimize: bool = True
    allow_wal_checkpoint: bool = True
    allow_archive_old_logs: bool = False
    archive_days: int = 0
    archive_dir: str = field(default_factory=lambda: str(local_root() / "archive"))
    language: str = "de"
    # Hintergrund-Waechter (Start-Praevention): tickt periodisch read-only und raeumt bei
    # GESCHLOSSENEM Codex haengende Reste (Ghost-Hauptprozesse ohne Renderer + verwaistes
    # Lockfile) ab, damit der naechste Start sauber ist -- der Start-Block ist der erste
    # Dominostein der gesamten Fehlerkette. Beendet NIE eine aktive Sitzung (Renderer da)
    # und nie einen frischen Start (Altersschwelle zombie_min_age_seconds).
    watcher_enabled: bool = True
    watcher_interval_seconds: int = 60  # Poll-Intervall des Hintergrund-Waechters
    # Nach erfolgreichem Reapen Codex automatisch neu starten? Default AUS (User-Wahl
    # 2026-05-30): nur aufraeumen + benachrichtigen, der User startet selbst -- so wird
    # Codex nie gegen den Willen wieder geoeffnet, wenn es bewusst geschlossen wurde.
    watcher_relaunch_after_reap: bool = False
    # Startup-Reparatur (Goal 2): bewusst getrennt von der konservativen DB-Wartung.
    # allow_repair_zombies betrifft NUR Hauptprozesse OHNE Renderer (totes Fenster).
    # Eine aktive Codex-Sitzung (mit Renderer) wird nie beendet.
    allow_repair_zombies: bool = True
    allow_clear_lockfile: bool = True
    zombie_min_age_seconds: int = 120
    # state_5.sqlite Backup: bei jeder Wartung mitsichern (Automations-Schutz).
    # KEIN VACUUM auf state_5 -- Korruption dort wedgt den Start (#21750).
    backup_state_db: bool = True
    # Companion-Orphan-Reaper: bereinigt verwaiste app-server-Prozesse die vom
    # codex-companion.mjs (Claude-Code-Plugin codex-plugin-cc) zurueckbleiben (#277).
    # Laeuft unabhaengig vom Desktop-Zustand bei jedem Watchdog-Tick.
    reap_companion_orphans: bool = True
    companion_orphan_min_age_seconds: int = 300  # 5 Minuten Karenzzeit nach Task-Ende
    # Safe Start for Codex bleibt ein eigenständiges Werkzeug. CareCenter liest dessen
    # Config/Snapshots optional aus und zeigt Start-Storm- sowie Catch-up-Hinweise an.
    safe_start_config_path: str = field(
        default_factory=lambda: str(default_codex_home() / "automation-safe-start" / "config.json")
    )
    safe_start_catchup_lookback_days: int = 30
    safe_start_catchup_max_per_start: int = 1
    safe_start_catchup_min_period_hours: int = 24
    safe_start_storm_window_minutes: int = 10
    safe_start_storm_release_threshold: int = 3
    # Abstand fuer CareCenter-eigene gestaffelte Automations-Freigaben.
    # Safe Start selbst nutzt seine eigene config.json (Default dort: 3 sofort, dann 5 Minuten).
    automation_stagger_delay_seconds: int = 60
    # Config-Audit: erkennt Duplikate und ungenutzte MCP-Server/Plugins in config.toml.
    # Modus: "notify" = nur melden, "auto" = automatisch bereinigen/deaktivieren.
    audit_duplicate_mcp: str = "notify"  # "off", "notify", "auto"
    audit_unused_plugins: str = "off"  # "off", "notify", "auto"
    # Health-Schwellwerte fuer die Diagnose.
    wal_warn_mb: int = 64
    db_warn_mb: int = 2048
    disk_min_gb: int = 10
    # Backup-Aufbewahrung (Lektion: unbegrenzte Backups fuellten frueher 123 GB).
    backup_keep: int = 3
    # Autonome Wartung (auto-maintain) -- bewusst opt-in und vom geplanten Task NICHT genutzt.
    # Hintergrund: Die Codex-Windows-App beendet sich beim Fenster-Schliessen oft nicht
    # vollstaendig (bekannter Bug); Reste sind meist ruhende Ghosts, koennen aber auch ein
    # auslaufender Hintergrund-Task sein. Daher: nach AKTIVITAET (DB-Schreibzugriffe)
    # unterscheiden -- aktiv => warten + informieren; lange ruhig => beenden.
    # Gate fuer den CLI/unbeaufsichtigten auto-maintain-Pfad: ohne dies (oder --close bzw.
    # Tray-Klick) schliesst auto-maintain Codex NICHT, sondern blockiert bei laufendem Codex.
    # Der geplante Task nutzt ohnehin nur den konservativen `maintain`-Pfad.
    auto_close_codex: bool = False
    restart_codex_after: bool = True  # nach Wartung Codex wieder starten, wenn wir es schlossen
    idle_quiet_seconds: int = 180  # DB so lange ohne Schreibzugriff => Leerlauf (grosszuegig)
    idle_wait_timeout_seconds: int = 1800  # max. Wartezeit auf Leerlauf, dann Abbruch
    activity_poll_seconds: int = 15  # Poll-Intervall fuer Aktivitaet/Leerlauf
    restart_verify_seconds: int = 20  # nach Neustart so lange auf Renderer warten
    # Codex-Start-Reparatur (repair_workflow) -- bewusst getrennt von der DB-Wartung.
    # deploy_timeout_seconds: harte Obergrenze fuer EINE Deployment-Op (z.B. staged
    # Update via RegisterByFamilyName). Reisst sie den Timeout, gilt die AppX-Engine als
    # verklemmt -> sofort STOPP, Reboot empfehlen, keine weitere Deploy-Op (iatrogener
    # Wedge-Schutz, siehe CODEX-AUTO-DEBUG-DESIGN.md).
    deploy_timeout_seconds: int = 75
    # renderer_timeout_seconds: Erfolgskriterium je Eskalationsstufe -- ein
    # "--type=renderer"-Prozess muss binnen dieser Zeit erscheinen, sonst weiter eskalieren.
    renderer_timeout_seconds: int = 120
    # CPU-Schwelle (% eines Kerns) fuer "aktiv". Empirisch kalibriert (2026-05-29):
    # aktive Automatisierung 25-500 %, Leerlauf-Rest <2 %. Ganzer Codex-Baum inkl. Worker-Kinder.
    idle_cpu_percent: float = 10.0
    activity_sample_seconds: float = 2.0  # Messfenster fuer die CPU-Stichprobe

    @classmethod
    def load(cls, path: Path | None = None) -> MaintenanceConfig:
        if path is None:
            path = default_config_path()
        if not path.exists():
            config = cls()
            config.save(path)
            return config

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            # ValueError faengt JSONDecodeError UND UnicodeDecodeError (abgebrochener
            # Multibyte-Schreibvorgang, Disk-Korruption) ab. OSError fuer Lesefehler.
            # Sicher auf Defaults zurueckfallen, damit der Tray-Start nicht crasht.
            return cls()
        if not isinstance(data, dict):
            return cls()
        known = set(cls.__dataclass_fields__)
        filtered = {key: value for key, value in data.items() if key in known}
        # Typsicherung: Felder mit falschem Typ (z.B. backup_keep="drei" statt 3) werden
        # verworfen und erhalten ihren Default -- verhindert spaete TypeErrors (keep<=0 etc.).
        # JSON liefert fuer Dezimalfelder manchmal int (z.B. 25 statt 25.0) -- das ist ok.
        # bool ist Unterklasse von int -- strikt behandeln, damit True/False nicht als int zaehlt.
        def _type_ok(val: object, default: object) -> bool:
            if isinstance(val, bool):
                return isinstance(default, bool)
            if isinstance(default, float):
                return isinstance(val, (int, float))
            return isinstance(val, type(default))

        defaults = cls()
        safe = {
            key: val for key, val in filtered.items()
            if _type_ok(val, getattr(defaults, key))
        }
        try:
            return cls(**safe)
        except Exception:
            return defaults

    def save(self, path: Path | None = None) -> None:
        if path is None:
            path = default_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def db_path(self) -> Path:
        return Path(self.database_path).expanduser()

    @property
    def backup_path(self) -> Path:
        return Path(self.backup_dir).expanduser()

    @property
    def archive_path(self) -> Path:
        return Path(self.archive_dir).expanduser()

    @property
    def logs_path(self) -> Path:
        return Path(self.log_dir).expanduser()

    @property
    def lock_path(self) -> Path:
        return Path(self.maintenance_lock_path).expanduser()

    @property
    def install_dir_path(self) -> Path:
        return Path(self.codex_install_dir).expanduser()

    @property
    def user_data_path(self) -> Path:
        return Path(self.codex_user_data_dir).expanduser()

    @property
    def lockfile_path(self) -> Path:
        """Electron-Singleton-Lockfile der Codex-Desktop-App."""
        return self.user_data_path / "lockfile"

    @property
    def codex_home(self) -> Path:
        """Verzeichnis der Logdatenbank (dort liegen auch *.badstate-Dateien)."""
        return self.db_path.parent

    @property
    def state_db_path(self) -> Path:
        """Pfad zu state_5.sqlite (Automations-/Thread-State)."""
        return self.codex_home / "state_5.sqlite"

    @property
    def safe_start_state_dir(self) -> Path:
        """Safe-Start-Arbeitsverzeichnis unterhalb von CODEX_HOME."""
        return self.codex_home / "automation-safe-start"

    @property
    def safe_start_config_file(self) -> Path:
        """Pfad zur Safe-Start-Konfiguration."""
        return Path(self.safe_start_config_path).expanduser()

    @property
    def config_toml_path(self) -> Path:
        """Pfad zu config.toml (MCP-Server, Plugins, Einstellungen)."""
        return self.codex_home / "config.toml"
