"""Hilfen fuer die projektlokale Windows-Store-Vorbereitung."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STORE_PACKAGE_PATH = PROJECT_ROOT / "store_package.json"
STORE_DOCS = (
    "STORE_LISTING.md",
    "PRIVACY_POLICY.md",
    "SUPPORT.md",
)
REQUIRED_FIELDS = (
    "app_name",
    "publisher",
    "publisher_display",
    "identity_name",
    "version",
    "description",
    "executable",
    "capabilities",
    "category",
    "age_rating",
)
URL_FIELDS = ("privacy_url", "support_url")
PLACEHOLDER_HOSTS = {
    "example.com",
    "example.invalid",
    "todo.invalid",
}
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+\.\d+$")


@dataclass(slots=True)
class StoreCheck:
    name: str
    status: str
    message: str


@dataclass(slots=True)
class StoreMaterialsReport:
    checks: list[StoreCheck]

    @property
    def status(self) -> str:
        if any(check.status == "failed" for check in self.checks):
            return "failed"
        if any(check.status == "warning" for check in self.checks):
            return "warning"
        return "ok"

    def to_text(self) -> str:
        lines = [f"Store-Materialien: {self.status}"]
        for check in self.checks:
            lines.append(f"- [{check.status}] {check.name}: {check.message}")
        return "\n".join(lines)


def _load_store_package(path: Path) -> tuple[dict[str, object] | None, StoreCheck]:
    if not path.exists():
        return None, StoreCheck("store_package.json", "failed", f"Datei fehlt: {path.name}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, StoreCheck("store_package.json", "failed", f"JSON unlesbar: {exc}")

    if not isinstance(payload, dict):
        return None, StoreCheck("store_package.json", "failed", "Top-Level muss ein Objekt sein.")
    return payload, StoreCheck("store_package.json", "ok", "JSON-Konfiguration lesbar.")


def _check_required_fields(payload: dict[str, object]) -> StoreCheck:
    missing = [field for field in REQUIRED_FIELDS if not str(payload.get(field, "")).strip()]
    if missing:
        return StoreCheck(
            "Pflichtfelder",
            "failed",
            "Fehlen in store_package.json: " + ", ".join(missing),
        )
    return StoreCheck("Pflichtfelder", "ok", "Alle Pflichtfelder sind gesetzt.")


def _check_version(payload: dict[str, object]) -> StoreCheck:
    version = str(payload.get("version", "")).strip()
    if not VERSION_PATTERN.fullmatch(version):
        return StoreCheck(
            "Version",
            "failed",
            f"Windows-Store-Version muss vierteilig sein, gefunden: {version or '<leer>'}",
        )
    return StoreCheck("Version", "ok", version)


def _check_capabilities(payload: dict[str, object]) -> StoreCheck:
    capabilities = {part.strip() for part in str(payload.get("capabilities", "")).split(",") if part.strip()}
    if "runFullTrust" not in capabilities:
        return StoreCheck(
            "Capabilities",
            "failed",
            "runFullTrust fehlt; fuer Tray-/Win32-Verhalten bleibt es Pflicht.",
        )
    return StoreCheck("Capabilities", "ok", ", ".join(sorted(capabilities)))


def _check_urls(payload: dict[str, object]) -> StoreCheck:
    problems: list[str] = []
    ok_fields: list[str] = []

    for field in URL_FIELDS:
        raw = str(payload.get(field, "")).strip()
        if not raw:
            problems.append(f"{field} fehlt")
            continue
        parsed = urlparse(raw)
        if parsed.scheme != "https" or not parsed.netloc:
            problems.append(f"{field} ist keine gueltige HTTPS-URL")
            continue
        if parsed.netloc.lower() in PLACEHOLDER_HOSTS:
            problems.append(f"{field} zeigt noch auf Platzhalter {parsed.netloc}")
            continue
        ok_fields.append(field)

    if problems:
        return StoreCheck("Store-URLs", "warning", "; ".join(problems))
    return StoreCheck("Store-URLs", "ok", " / ".join(ok_fields))


def _check_docs(project_root: Path) -> StoreCheck:
    missing = [name for name in STORE_DOCS if not (project_root / name).exists()]
    if missing:
        return StoreCheck("Store-Dokumente", "failed", "Fehlen: " + ", ".join(missing))
    return StoreCheck("Store-Dokumente", "ok", ", ".join(STORE_DOCS))


def _check_screenshot(project_root: Path) -> StoreCheck:
    screenshot = project_root / "README" / "screenshots" / "main.png"
    if screenshot.exists():
        return StoreCheck("README-Screenshot", "ok", str(screenshot))
    return StoreCheck(
        "README-Screenshot",
        "warning",
        "README/screenshots/main.png fehlt noch fuer Store-/README-Visuals.",
    )


def _check_executable(payload: dict[str, object], exe_path: Path | None) -> StoreCheck:
    configured = str(payload.get("executable", "")).strip()
    if not configured:
        return StoreCheck("Executable", "failed", "Kein EXE-Name konfiguriert.")
    if exe_path is None:
        return StoreCheck(
            "Executable",
            "warning",
            f"Nur Name geprueft ({configured}); kein --exe-path uebergeben.",
        )

    if exe_path.name != configured:
        return StoreCheck(
            "Executable",
            "failed",
            f"EXE-Name stimmt nicht: erwartet {configured}, erhalten {exe_path.name}",
        )
    if not exe_path.exists():
        return StoreCheck("Executable", "failed", f"EXE fehlt: {exe_path}")
    return StoreCheck("Executable", "ok", str(exe_path))


def validate_store_materials(
    project_root: Path = PROJECT_ROOT,
    exe_path: Path | None = None,
) -> StoreMaterialsReport:
    checks: list[StoreCheck] = []
    payload, config_check = _load_store_package(project_root / STORE_PACKAGE_PATH.name)
    checks.append(config_check)
    if payload is None:
        return StoreMaterialsReport(checks)

    checks.append(_check_required_fields(payload))
    checks.append(_check_version(payload))
    checks.append(_check_capabilities(payload))
    checks.append(_check_urls(payload))
    checks.append(_check_docs(project_root))
    checks.append(_check_screenshot(project_root))
    checks.append(_check_executable(payload, exe_path))
    return StoreMaterialsReport(checks)
