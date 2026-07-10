"""Config-Audit und Thread-Analyse fuer Codex-Oekosystem-Gesundheit.

Erkennt:
- Doppelte MCP-Server in config.toml (6c)
- Ungenutzte/plattform-inkompatible Plugins (6c)
- Fehlerhafte CLI-Installation (nicht im PATH, Duplikate) (6c+)
- Leere Threads in state_5.sqlite (6d, #19969-Signatur)
"""

from __future__ import annotations

import contextlib
import json
import re
import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
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

    def add(
        self,
        category: str,
        severity: AuditSeverity,
        message: str,
        *,
        detail: str = "",
        auto_fixable: bool = False,
    ) -> None:
        self.findings.append(
            AuditFinding(category, severity, message, detail, auto_fixable)
        )

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


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(row["name"]) for row in conn.execute(f"PRAGMA table_info({_quote_identifier(table)})")]


def _first_column(columns: set[str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _json_blankish(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, list):
        return all(_json_blankish(item) for item in value)
    if isinstance(value, dict):
        if not value:
            return True
        content_keys = {
            "content", "text", "message", "body", "prompt", "response",
            "input", "output", "value", "parts",
        }
        relevant = [
            child for key, child in value.items()
            if str(key).lower() in content_keys
        ]
        if relevant:
            return all(_json_blankish(child) for child in relevant)
        return all(_json_blankish(child) for child in value.values())
    return False


def _blank_message_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8", errors="replace")
        except OSError:
            return False
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return True
        if stripped[:1] in "[{":
            try:
                return _json_blankish(json.loads(stripped))
            except ValueError:
                return False
    return False


def _content_columns(columns: set[str]) -> list[str]:
    strong = [
        column for column in (
            "first_user_message", "content", "text", "message", "body",
            "prompt", "response",
        )
        if column in columns
    ]
    if strong:
        return strong
    return [
        column for column in ("payload", "data", "json", "value")
        if column in columns
    ]


def _token_empty(row: sqlite3.Row, columns: set[str]) -> bool:
    token_columns = [
        column for column in (
            "total_tokens", "token_count", "tokens", "input_tokens", "output_tokens",
        )
        if column in columns
    ]
    if not token_columns:
        return True
    for column in token_columns:
        value = row[column]
        if value not in (None, 0, "0", ""):
            return False
    return True


def _row_empty_message(row: sqlite3.Row, content_columns: list[str]) -> bool:
    if not content_columns:
        return False
    return all(_blank_message_value(row[column]) for column in content_columns)


def _select_rows(conn: sqlite3.Connection, table: str, columns: set[str], *, limit: int) -> list[sqlite3.Row]:
    order_column = _first_column(columns, ("created_at", "updated_at", "timestamp", "ts"))
    order_sql = f" ORDER BY {_quote_identifier(order_column)} DESC" if order_column else ""
    query = f"SELECT * FROM {_quote_identifier(table)}{order_sql} LIMIT {int(limit)}"
    return list(conn.execute(query))


def find_empty_threads(config: MaintenanceConfig) -> list[EmptyThread]:
    """Findet leere Threads/Nachrichten in state_5.sqlite (#19969-Signatur).

    Liest read-only; keine Modifikation an state_5.sqlite.
    """
    state_path = config.state_db_path
    if not state_path.exists():
        return []

    empty: list[EmptyThread] = []
    try:
        conn = sqlite3.connect(f"file:{state_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

        tables = [str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        seen_ids: set[str] = set()

        if "threads" in tables:
            columns = set(_table_columns(conn, "threads"))
            id_column = _first_column(columns, ("id", "thread_id", "conversation_id", "chat_id"))
            name_column = _first_column(columns, ("name", "title", "summary"))
            created_column = _first_column(columns, ("created_at", "updated_at", "timestamp", "ts"))
            content_columns = _content_columns(columns)
            token_columns_present = any(
                column in columns
                for column in (
                    "total_tokens", "token_count", "tokens", "input_tokens", "output_tokens",
                )
            )
            if id_column is not None:
                for row in _select_rows(conn, "threads", columns, limit=500):
                    if not token_columns_present and not content_columns:
                        break
                    if not _token_empty(row, columns):
                        continue
                    if content_columns and not _row_empty_message(row, content_columns):
                        continue
                    thread_id = str(row[id_column] or "")
                    if not thread_id or thread_id in seen_ids:
                        continue
                    seen_ids.add(thread_id)
                    empty.append(EmptyThread(
                        thread_id=thread_id,
                        name=str(row[name_column] or "") if name_column else "",
                        created_at=str(row[created_column] or "") if created_column else "",
                    ))

        message_table_hints = ("message", "messages", "item", "items", "event", "events", "turn", "turns")
        for table in tables:
            if table == "threads" or not any(hint in table.lower() for hint in message_table_hints):
                continue
            columns = set(_table_columns(conn, table))
            content_columns = _content_columns(columns)
            if not content_columns:
                continue
            thread_column = _first_column(
                columns,
                ("thread_id", "conversation_id", "chat_id", "session_id", "parent_id", "thread"),
            )
            id_column = thread_column or _first_column(columns, ("id", "message_id"))
            if id_column is None:
                continue
            name_column = _first_column(columns, ("name", "title", "summary"))
            created_column = _first_column(columns, ("created_at", "updated_at", "timestamp", "ts"))
            for row in _select_rows(conn, table, columns, limit=1000):
                if not _row_empty_message(row, content_columns):
                    continue
                thread_id = str(row[id_column] or "")
                if not thread_id or thread_id in seen_ids:
                    continue
                seen_ids.add(thread_id)
                empty.append(EmptyThread(
                    thread_id=thread_id,
                    name=str(row[name_column] or "") if name_column else table,
                    created_at=str(row[created_column] or "") if created_column else "",
                ))
                if len(empty) >= 100:
                    break
            if len(empty) >= 100:
                break
        conn.close()
    except (sqlite3.Error, OSError):
        pass

    return empty[:100]


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

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
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
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
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
    for _package, names in package_map.items():
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

@dataclass(slots=True)
class AuditCycleResult:
    """Ergebnis eines Audit-Zyklus (fuer Watchdog-Integration)."""
    new_hash: str = ""
    notification: str | None = None
    mcp_fixed: int = 0
    plugins_fixed: int = 0
    fixes_deferred: int = 0


def run_audit_cycle(
    config: MaintenanceConfig,
    last_hash: str,
    renderer_present: bool,
) -> AuditCycleResult:
    """Reine Orchestrierungsfunktion fuer den periodischen Config-Audit.

    - Auto-fix nur wenn renderer_present=False (Codex geschlossen).
    - Notify entprellt via last_hash (nur bei neuem Befund).
    - Per-Kategorie gefiltert (off-Modi werden ignoriert).
    """
    result = AuditCycleResult()

    if config.audit_duplicate_mcp == "off" and config.audit_unused_plugins == "off":
        return result

    # Auto-Fix: nur wenn Codex geschlossen
    if not renderer_present:
        if config.audit_duplicate_mcp == "auto":
            result.mcp_fixed = fix_duplicate_mcp(config)
        if config.audit_unused_plugins == "auto":
            result.plugins_fixed = fix_unused_plugins(config)

    # Notify: entprellt, per-Kategorie gefiltert
    notify_mcp = config.audit_duplicate_mcp == "notify"
    notify_plugins = config.audit_unused_plugins == "notify"
    if notify_mcp or notify_plugins:
        report = audit_config_toml(config)
        relevant = [
            f for f in report.findings
            if f.auto_fixable and (
                (notify_mcp and f.category == "MCP-Duplikat")
                or (notify_plugins and f.category == "Ungenutztes Plugin")
            )
        ]
        if not relevant:
            result.new_hash = ""
            return result
        current_hash = "|".join(f.message for f in relevant)
        if current_hash == last_hash:
            result.new_hash = last_hash
            return result
        result.new_hash = current_hash
        result.notification = "\n".join(
            f"[{f.severity.upper()}] {f.category}: {f.message}" for f in relevant
        )

    return result


def run_manual_audit(
    config: MaintenanceConfig,
    *,
    renderer_present: bool,
) -> tuple[AuditReport, AuditCycleResult]:
    """Fuehrt einen manuellen Audit samt sicherem Auto-Fix aus.

    Das Ergebnis wird nach einer Mutation neu erhoben, damit bereits behobene
    Befunde nicht weiter als offen angezeigt werden. Bei laufendem Codex bleibt
    die config.toml unangetastet; reparierbare Auto-Befunde werden als
    aufgeschoben ausgewiesen und vom periodischen Audit nach dem Schliessen
    behoben.
    """
    before = run_full_audit(config)
    cycle = run_audit_cycle(config, last_hash="", renderer_present=renderer_present)

    auto_categories = set()
    if config.audit_duplicate_mcp == "auto":
        auto_categories.add("MCP-Duplikat")
    if config.audit_unused_plugins == "auto":
        auto_categories.add("Ungenutztes Plugin")

    if renderer_present:
        cycle.fixes_deferred = sum(
            1
            for finding in before.findings
            if finding.auto_fixable and finding.category in auto_categories
        )

    if cycle.mcp_fixed or cycle.plugins_fixed:
        return run_full_audit(config), cycle
    return before, cycle


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
