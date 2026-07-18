"""Hilfen fuer die projektlokale Windows-Store-Vorbereitung."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from importlib import util as importlib_util
from pathlib import Path
from types import ModuleType
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STORE_PACKAGE_PATH = PROJECT_ROOT / "store_package.json"
BUILD_SCRIPT_PATH = PROJECT_ROOT / "build_exe.bat"
STORE_DOCS = (
    "STORE_LISTING.md",
    "PRIVACY_POLICY.md",
    "SUPPORT.md",
)
PUBLISHED_STORE_DOCS = (
    "docs/privacy.md",
    "docs/support.md",
)
PAGES_WORKFLOW_PATH = Path(".github") / "workflows" / "pages.yml"
PAGES_BUILD_SCRIPT_PATH = Path("scripts") / "build_store_pages.py"
PAGES_WORKFLOW_MARKERS = (
    "actions/configure-pages@",
    "actions/upload-pages-artifact@",
    "actions/deploy-pages@",
    "pages: write",
    "id-token: write",
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
DIST_DIR_PATTERN = re.compile(r'^\s*set\s+"DIST_DIR=(?P<value>[^"]+)"\s*$', re.IGNORECASE)


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


def _check_live_store_pages(
    payload: dict[str, object],
    timeout_seconds: float = 10.0,
) -> StoreCheck:
    problems: list[str] = []
    ok_fields: list[str] = []

    for field in URL_FIELDS:
        raw = str(payload.get(field, "")).strip()
        if not raw:
            problems.append(f"{field} fehlt")
            continue

        request = urlrequest.Request(
            raw,
            headers={"User-Agent": "CareCenter-for-Codex store-readiness"},
        )
        try:
            with urlrequest.urlopen(request, timeout=timeout_seconds) as response:
                status = int(response.status)
        except (urlerror.HTTPError, urlerror.URLError, TimeoutError, OSError) as exc:
            problems.append(f"{field}: {exc}")
            continue

        if status != 200:
            problems.append(f"{field}: HTTP {status}")
            continue
        ok_fields.append(field)

    if problems:
        return StoreCheck("Store-Webseiten-Live", "warning", "; ".join(problems))
    return StoreCheck("Store-Webseiten-Live", "ok", " / ".join(ok_fields))


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


def _check_pages_routes(payload: dict[str, object]) -> list[str]:
    expected_paths = {
        "privacy_url": "/carecenter-for-codex/privacy",
        "support_url": "/carecenter-for-codex/support",
    }
    problems: list[str] = []
    for field, expected_path in expected_paths.items():
        raw = str(payload.get(field, "")).strip()
        if not raw:
            continue
        parsed = urlparse(raw)
        path = parsed.path.rstrip("/").lower()
        if path != expected_path:
            problems.append(f"{field} endet nicht auf {expected_path}")
    return problems


def _check_published_store_docs(project_root: Path, payload: dict[str, object]) -> StoreCheck:
    problems: list[str] = []
    missing = [name for name in PUBLISHED_STORE_DOCS if not (project_root / name).exists()]
    if missing:
        problems.append("GitHub-Pages-Quelldokumente fehlen: " + ", ".join(missing))

    build_script = project_root / PAGES_BUILD_SCRIPT_PATH
    if not build_script.exists():
        problems.append(f"Pages-Builder fehlt: {PAGES_BUILD_SCRIPT_PATH.as_posix()}")

    workflow = project_root / PAGES_WORKFLOW_PATH
    if not workflow.exists():
        problems.append(f"Pages-Workflow fehlt: {PAGES_WORKFLOW_PATH.as_posix()}")
    else:
        try:
            workflow_text = workflow.read_text(encoding="utf-8")
        except OSError as exc:
            problems.append(f"Pages-Workflow unlesbar: {exc}")
        else:
            missing_markers = [marker for marker in PAGES_WORKFLOW_MARKERS if marker not in workflow_text]
            if missing_markers:
                problems.append("Pages-Workflow unvollstaendig: " + ", ".join(missing_markers))

    problems.extend(_check_pages_routes(payload))

    if problems:
        return StoreCheck("Store-Webseiten", "warning", "; ".join(problems))
    return StoreCheck(
        "Store-Webseiten",
        "ok",
        ", ".join(
            [
                *PUBLISHED_STORE_DOCS,
                PAGES_BUILD_SCRIPT_PATH.as_posix(),
                PAGES_WORKFLOW_PATH.as_posix(),
            ]
        ),
    )


def _load_pages_builder(build_script: Path) -> ModuleType:
    spec = importlib_util.spec_from_file_location("carecenter_store_pages_build_check", build_script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Pages-Builder kann nicht geladen werden: {build_script}")
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_store_pages_build(project_root: Path) -> StoreCheck:
    build_script = project_root / PAGES_BUILD_SCRIPT_PATH
    if not build_script.exists():
        return StoreCheck(
            "Store-Webseiten-Build",
            "warning",
            f"Pages-Builder fehlt: {PAGES_BUILD_SCRIPT_PATH.as_posix()}",
        )

    try:
        module = _load_pages_builder(build_script)
        build_pages = module.build_pages  # type: ignore[attr-defined]
    except (AttributeError, RuntimeError, OSError, SyntaxError) as exc:
        return StoreCheck("Store-Webseiten-Build", "warning", f"Pages-Builder unbrauchbar: {exc}")

    try:
        with tempfile.TemporaryDirectory(prefix="carecenter-store-pages-") as tmp_dir:
            output_dir = Path(tmp_dir) / "_site"
            written = [Path(path) for path in build_pages(project_root, output_dir)]
            expected = {
                output_dir / ".carecenter-pages-build",
                output_dir / "index.html",
                output_dir / "privacy" / "index.html",
                output_dir / "support" / "index.html",
            }
            missing = sorted(str(path.relative_to(output_dir)) for path in expected if not path.exists())
            if missing:
                return StoreCheck(
                    "Store-Webseiten-Build",
                    "warning",
                    "Gebautes Pages-Artefakt unvollstaendig: " + ", ".join(missing),
                )
            invalid = [
                str(path.relative_to(output_dir))
                for path in expected
                if path.suffix == ".html" and "<!doctype html>" not in path.read_text(encoding="utf-8").lower()
            ]
            if invalid:
                return StoreCheck(
                    "Store-Webseiten-Build",
                    "warning",
                    "Gebautes HTML ohne Doctype: " + ", ".join(sorted(invalid)),
                )
    except Exception as exc:  # noqa: BLE001 - Store gate should report builder failures, not crash.
        return StoreCheck("Store-Webseiten-Build", "warning", f"Pages-Build fehlgeschlagen: {exc}")

    return StoreCheck(
        "Store-Webseiten-Build",
        "ok",
        f"Temporärer Build ok ({len(written)} Dateien, privacy/support/index).",
    )


def _discover_build_dist_dir(project_root: Path) -> Path | None:
    build_script = project_root / BUILD_SCRIPT_PATH.name
    if not build_script.exists():
        return None
    try:
        content = build_script.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in content.splitlines():
        match = DIST_DIR_PATTERN.match(line)
        if not match:
            continue
        raw_value = os.path.expandvars(match.group("value").strip())
        if not raw_value:
            return None
        dist_dir = Path(raw_value)
        if not dist_dir.is_absolute():
            dist_dir = (project_root / dist_dir).resolve()
        return dist_dir
    return None


def _resolve_requested_executable(configured: str, exe_path: Path | None) -> Path | None:
    if exe_path is None:
        return None
    if exe_path.suffix.lower() == ".exe":
        return exe_path
    return exe_path / configured


def _candidate_executables(project_root: Path, configured: str) -> list[Path]:
    candidates: list[Path] = []

    dist_dir = _discover_build_dist_dir(project_root)
    if dist_dir is not None:
        candidates.append(dist_dir / configured)
    candidates.append(project_root / configured)

    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        key = candidate.resolve()
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(key)
    return unique_candidates


def _check_executable(project_root: Path, payload: dict[str, object], exe_path: Path | None) -> StoreCheck:
    configured = str(payload.get("executable", "")).strip()
    if not configured:
        return StoreCheck("Executable", "failed", "Kein EXE-Name konfiguriert.")

    resolved_path = _resolve_requested_executable(configured, exe_path)
    if resolved_path is not None:
        if resolved_path.name != configured:
            return StoreCheck(
                "Executable",
                "failed",
                f"EXE-Name stimmt nicht: erwartet {configured}, erhalten {resolved_path.name}",
            )
        if not resolved_path.exists():
            return StoreCheck("Executable", "failed", f"EXE fehlt: {resolved_path}")
        return StoreCheck("Executable", "ok", str(resolved_path.resolve()))

    for candidate in _candidate_executables(project_root, configured):
        if candidate.exists():
            return StoreCheck("Executable", "ok", f"Automatisch gefunden: {candidate}")

    candidates = _candidate_executables(project_root, configured)
    if not candidates:
        return StoreCheck(
            "Executable",
            "warning",
            f"Keine EXE-Autopfadregel gefunden; mit --exe-path {configured} oder dessen Ordner pruefen.",
        )
    tried = ", ".join(str(candidate) for candidate in candidates)
    return StoreCheck(
        "Executable",
        "warning",
        "Keine gebaute EXE gefunden. Geprueft: "
        f"{tried}. Mit --exe-path koennen Datei oder Build-Ordner explizit uebergeben werden.",
    )


def validate_store_materials(
    project_root: Path = PROJECT_ROOT,
    exe_path: Path | None = None,
    check_live_pages: bool = False,
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
    checks.append(_check_published_store_docs(project_root, payload))
    checks.append(_check_store_pages_build(project_root))
    if check_live_pages:
        checks.append(_check_live_store_pages(payload))
    checks.append(_check_screenshot(project_root))
    checks.append(_check_executable(project_root, payload, exe_path))
    return StoreMaterialsReport(checks)
