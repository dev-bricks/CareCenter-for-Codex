"""Config-Audit und Thread-Analyse fuer Codex-Oekosystem-Gesundheit.

Erkennt:
- Doppelte MCP-Server in config.toml (6c)
- Ungenutzte/plattform-inkompatible Plugins (6c)
- Fehlerhafte CLI-Installation (nicht im PATH, Duplikate) (6c+)
- Leere Threads in state_5.sqlite (6d, #19969-Signatur)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import shutil
import sqlite3
from typing import Literal

from .config import MaintenanceConfig

AuditSeverity = Literal["info", "warning", "critical"]


@dataclass(slots=True)
class AuditFinding:
    category: str
    severity: AuditSeverity
    message: str
    detail: str = ""
    auto_fixable: bool = False


@dataclass(slots=True)
class AuditReport:
    findings: list[AuditFinding] = field(default_factory=list)

    def add(self, category: str, severity: AuditSeverity, message: str, **kw: object) -> None:
        self.findings.append(AuditFinding(category, severity, message, **kw))

    @property
    def has_warnings(self) -> bool:
        return any(f.severity in ("warning", "critical") for f in self.findings)

    def summary(self) -> str:
        if not self.findings:
            return "Keine Auffaelligkeiten."
        lines = []
        for f in self.findings:
            prefix = {"info": "INFO", "warning": "WARN", "critical": "CRIT"}[f.severity]
            lines.append(f"[{prefix}] {f.category}: {f.message}")
            if f.detail:
                lines.append(f"       {f.detail}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 6c: Config-TOML Audit (MCP-Duplikate + ungenutzte Plugins)
# ---------------------------------------------------------------------------

_KNOWN_PLATFORM_LOCKED_PLUGINS = frozenset({
    "build-ios-apps@openai-curated",
    "build-macos-apps@openai-curated",
})

_KNOWN_WINDOWS_IRRELEVANT_PLUGINS = _KNOWN_PLATFORM_LOCKED_PLUGINS


def _strip_inline_comment(value: str) -> str:
    """Entfernt TOML-Inline-Kommentare (# ...) ausserhalb von Strings."""
    in_string = False
    quote_char = ""
    for i, ch in enumerate(value):
        if in_string:
            if ch == quote_char:
                in_string = False
        elif ch in ('"', "'"):
            in_string = True
            quote_char = ch
        elif ch == "#":
            return value[:i].rstrip()
    return value


def _parse_toml_sections(text: str) -> dict[str, dict[str, str]]:
    """Minimaler TOML-Parser fuer [section]-basierte Key-Value-Paare."""
    sections: dict[str, dict[str, str]] = {}
    current_section = ""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        section_match = re.match(r'^\[(.+)\]$', line)
        if section_match:
            current_section = section_match.group(1)
            sections.setdefault(current_section, {})
            continue
        if "=" in line and current_section:
            key, _, value = line.partition("=")
            cleaned = _strip_inline_comment(value.strip()).strip('"').strip("'")
            sections.setdefault(current_section, {})[key.strip()] = cleaned
    return sections


def _extract_mcp_package(section_data: dict[str, str]) -> str | None:
    """Extrahiert den npm-Paketnamen aus MCP-Server-Konfiguration."""
    args_raw = section_data.get("args", "")
    if "node_modules" in args_raw:
        match = re.search(r'node_modules[/\\]([^/\\"]+(?:-mcp))[/\\]', args_raw)
        if match:
            return match.group(1)
    for candidate in re.findall(r'[\w@-]+-mcp\b', args_raw):
        return candidate
    return None


def audit_config_toml(config: MaintenanceConfig) -> AuditReport:
    """Prueft config.toml auf MCP-Duplikate und ungenutzte Plugins."""
    report = AuditReport()
    toml_path = config.config_toml_path
    if not toml_path.exists():
        report.add("config.toml", "warning", "config.toml nicht gefunden.", detail=str(toml_path))
        return report

    text = toml_path.read_text(encoding="utf-8", errors="replace")
    sections = _parse_toml_sections(text)

    # MCP-Duplikate erkennen
    mcp_servers: dict[str, list[str]] = {}
    for section_name, data in sections.items():
        if section_name.startswith("mcp_servers."):
            server_name = section_name.removeprefix("mcp_servers.")
            package = _extract_mcp_package(data)
            if package:
                mcp_servers.setdefault(package, []).append(server_name)

    for package, names in mcp_servers.items():
        if len(names) > 1:
            report.add(
                "MCP-Duplikat",
                "warning",
                f"Paket '{package}' ist {len(names)}x konfiguriert: {', '.join(names)}",
                detail="Duplikate verdoppeln den Speicherverbrauch pro Thread.",
                auto_fixable=True,
            )

    # Ungenutzte Plugins erkennen (plattform-inkompatibel auf Windows)
    for section_name, data in sections.items():
        if not section_name.startswith("plugins."):
            continue
        plugin_name = section_name.removeprefix("plugins.").strip('"')
        enabled = data.get("enabled", "").lower() == "true"
        if enabled and plugin_name in _KNOWN_WINDOWS_IRRELEVANT_PLUGINS:
            report.add(
                "Ungenutztes Plugin",
                "info",
                f"Plugin '{plugin_name}' ist aktiv aber auf Windows nicht nutzbar.",
                auto_fixable=True,
            )

    return report


# ---------------------------------------------------------------------------
# CLI-Installations-Audit
# ---------------------------------------------------------------------------

def audit_cli_installation() -> AuditReport:
    """Prueft ob codex CLI korrekt im PATH liegt und keine Konflikte existieren."""
    report = AuditReport()

    codex_path = shutil.which("codex")
    if codex_path is None:
        report.add(
            "CLI-PATH",
            "critical",
            "codex nicht im PATH gefunden — Companion-Plugin (codex:rescue) ist nicht funktionsfaehig.",
            detail="Fix: npm install -g @openai/codex",
        )
    else:
        report.add("CLI-PATH", "info", f"codex im PATH: {codex_path}")

    npm_global = Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "@openai" / "codex"
    embedded_dir = Path.home() / "AppData" / "Local" / "OpenAI" / "Codex" / "bin"
    installations: list[str] = []
    if npm_global.exists():
        installations.append("npm-global")
    if embedded_dir.exists():
        installations.append("embedded (Desktop)")

    store_marker = Path(r"C:\Program Files\WindowsApps")
    if store_marker.exists():
        try:
            store_dirs = [d for d in store_marker.iterdir() if "OpenAI.Codex" in d.name]
            if store_dirs:
                installations.append("Store")
        except PermissionError:
            pass

    if len(installations) > 1:
        report.add(
            "CLI-Installationen",
            "info",
            f"{len(installations)} Codex-Installationen erkannt: {', '.join(installations)}",
            detail="Normal: npm-global=Companion-PATH, embedded=Worker, Store=Desktop-App.",
        )

    return report


# ---------------------------------------------------------------------------
# 6d: Leere-Thread-Detektor (state_5.sqlite)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class EmptyThread:
    thread_id: str
    name: str
    created_at: str


def find_empty_threads(config: MaintenanceConfig) -> list[EmptyThread]:
    """Findet Threads in state_5.sqlite ohne User-Message / mit 0 Tokens (#19969).

    Liest read-only; keine Modifikation an state_5.sqlite.
    """
    state_path = config.state_db_path
    if not state_path.exists():
        return []

    empty: list[EmptyThread] = []
    try:
        conn = sqlite3.connect(f"file:{state_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

        # Tabellen-Existenz pruefen (Schema kann sich aendern)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "threads" not in tables:
            conn.close()
            return []

        # Threads mit 0 total_tokens oder ohne first_user_message
        cursor = conn.execute("""
            SELECT id, name, created_at
            FROM threads
            WHERE (total_tokens IS NULL OR total_tokens = 0)
              AND (first_user_message IS NULL OR first_user_message = '')
            ORDER BY created_at DESC
            LIMIT 100
        """)
        for row in cursor:
            empty.append(EmptyThread(
                thread_id=str(row["id"]),
                name=str(row["name"] or ""),
                created_at=str(row["created_at"] or ""),
            ))
        conn.close()
    except (sqlite3.Error, OSError):
        pass

    return empty


def audit_threads(config: MaintenanceConfig) -> AuditReport:
    """Erstellt einen Audit-Report ueber leere/tote Threads."""
    report = AuditReport()
    empty = find_empty_threads(config)
    if empty:
        report.add(
            "Leere Threads",
            "warning",
            f"{len(empty)} Thread(s) ohne Inhalt gefunden (0 Tokens, kein User-Prompt).",
            detail="Diese belegen MCP-Stacks beim Desktop-Start. Archivierung empfohlen.",
        )
    else:
        report.add("Leere Threads", "info", "Keine leeren Threads gefunden.")
    return report


# ---------------------------------------------------------------------------
# Auto-Fix: Sichere TOML-Manipulation via tomlkit (formaterhaltend)
# ---------------------------------------------------------------------------


def _backup_config_toml(toml_path: Path) -> Path:
    """Erstellt ein Zeitstempel-Backup von config.toml vor Mutation."""
    from datetime import datetime

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = toml_path.with_suffix(f".{stamp}.bak")
    backup.write_bytes(toml_path.read_bytes())
    return backup


def _atomic_write_toml(toml_path: Path, content: str) -> None:
    """Schreibt config.toml atomar (temp + os.replace, same-volume)."""
    import os
    import tempfile

    fd, tmp_name = tempfile.mkstemp(
        dir=str(toml_path.parent), prefix=".config_", suffix=".tmp"
    )
    closed = False
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        closed = True
        os.replace(tmp_name, str(toml_path))
    except BaseException:
        if not closed:
            os.close(fd)
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def fix_duplicate_mcp(config: MaintenanceConfig) -> int:
    """Entfernt doppelte MCP-Server-Eintraege aus config.toml.

    Bei gleichem Paket (npm-Name): behaelt den Eintrag mit dem laengeren/
    expliziten Pfad (node_modules > npx). Gibt die Anzahl entfernter
    Duplikate zurueck. Schreibt nur wenn etwas geaendert wurde.
    """
    import tomlkit

    toml_path = config.config_toml_path
    if not toml_path.exists():
        return 0

    text = toml_path.read_text(encoding="utf-8")
    doc = tomlkit.parse(text)

    mcp_table = doc.get("mcp_servers")
    if not isinstance(mcp_table, dict) or not mcp_table:
        return 0

    # Paketnamen zuordnen
    package_map: dict[str, list[str]] = {}
    for server_name, server_data in mcp_table.items():
        if not isinstance(server_data, dict):
            continue
        data_dict = {k: str(v) for k, v in server_data.items() if k != "env"}
        package = _extract_mcp_package(data_dict)
        if package:
            package_map.setdefault(package, []).append(server_name)

    to_remove: list[str] = []
    for package, names in package_map.items():
        if len(names) <= 1:
            continue
        # Behalte den Eintrag mit node_modules-Pfad (expliziter), entferne den Rest
        keep = names[0]
        for name in names:
            data = mcp_table.get(name, {})
            args_str = str(data.get("args", ""))
            if "node_modules" in args_str:
                keep = name
                break
        to_remove.extend(n for n in names if n != keep)

    if not to_remove:
        return 0

    _backup_config_toml(toml_path)
    for name in to_remove:
        del mcp_table[name]

    _atomic_write_toml(toml_path, tomlkit.dumps(doc))
    return len(to_remove)


def fix_unused_plugins(config: MaintenanceConfig) -> int:
    """Deaktiviert plattform-inkompatible Plugins in config.toml.

    Setzt enabled=false bei Plugins die auf Windows nicht nutzbar sind
    (build-ios-apps, build-macos-apps, test-android-apps). Gibt die Anzahl
    deaktivierter Plugins zurueck. Schreibt nur wenn etwas geaendert wurde.
    """
    import tomlkit

    toml_path = config.config_toml_path
    if not toml_path.exists():
        return 0

    text = toml_path.read_text(encoding="utf-8")
    doc = tomlkit.parse(text)

    plugins_table = doc.get("plugins")
    if not isinstance(plugins_table, dict) or not plugins_table:
        return 0

    fixed = 0
    for plugin_name, plugin_data in plugins_table.items():
        if not isinstance(plugin_data, dict):
            continue
        if plugin_name not in _KNOWN_PLATFORM_LOCKED_PLUGINS:
            continue
        enabled = plugin_data.get("enabled")
        if enabled is True:
            plugin_data["enabled"] = False
            fixed += 1

    if fixed == 0:
        return 0

    _backup_config_toml(toml_path)
    _atomic_write_toml(toml_path, tomlkit.dumps(doc))
    return fixed


# ---------------------------------------------------------------------------
# Gesamt-Audit
# ---------------------------------------------------------------------------

def run_full_audit(config: MaintenanceConfig) -> AuditReport:
    """Fuehrt alle Audits aus und kombiniert die Ergebnisse."""
    combined = AuditReport()
    for sub_report in [
        audit_config_toml(config),
        audit_cli_installation(),
        audit_threads(config),
    ]:
        combined.findings.extend(sub_report.findings)
    return combined
