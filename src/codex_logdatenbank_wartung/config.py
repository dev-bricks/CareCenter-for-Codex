"""Konfiguration für die Codex-Logdatenbank-Wartung."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
from typing import Any


LOCAL_ROOT = Path(r"C:\_Local_DEV\codex-maintenance")
DEFAULT_CONFIG_PATH = LOCAL_ROOT / "config.json"


def default_codex_home() -> Path:
    """Liefere den Codex-Home-Pfad mit robuster Fallback-Logik."""
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


def default_database_path() -> Path:
    return default_codex_home() / "logs_2.sqlite"


def _local_appdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))


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
    backup_dir: str = str(LOCAL_ROOT / "backups")
    log_dir: str = str(LOCAL_ROOT / "logs")
    maintenance_lock_path: str = str(LOCAL_ROOT / "maintenance.lock")
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
    language: str = "de"
    # Hintergrund-Waechter (Start-Praevention): tickt periodisch read-only und raeumt bei
    # GESCHLOSSENEM Codex haengende Reste (Ghost-Hauptprozesse ohne Renderer + verwaistes
    # Lockfile) ab, damit der naechste Start sauber ist -- der Start-Block ist der erste
    # Dominostein der gesamten Fehlerkette. Beendet NIE eine aktive Sitzung (Renderer da)
    # und nie einen frischen Start (Altersschwelle zombie_min_age_seconds).
    watcher_enabled: bool = True
    watcher_terminate_user_starts: bool = False
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
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> "MaintenanceConfig":
        if not path.exists():
            config = cls()
            config.save(path)
            return config

        data = json.loads(path.read_text(encoding="utf-8"))
        known = {field_name for field_name in cls.__dataclass_fields__}
        filtered = {key: value for key, value in data.items() if key in known}
        return cls(**filtered)

    def save(self, path: Path = DEFAULT_CONFIG_PATH) -> None:
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
