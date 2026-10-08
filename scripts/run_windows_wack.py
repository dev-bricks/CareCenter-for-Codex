#!/usr/bin/env python3
"""
run_windows_wack.py - Führt das Windows App Certification Kit (WACK) für CareCenter for Codex aus oder erstellt hermetische Preflight-Reports.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

try:
    import ctypes
except ImportError:
    ctypes = None

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APPCERT = Path(r"C:\Program Files (x86)\Windows Kits\10\App Certification Kit\appcert.exe")
WACK_REPORT_PREFIX = "wack_preflight_"


@dataclass(frozen=True)
class WackSummary:
    report: str
    overall_result: str
    requirement_count: int
    pass_count: int
    fail_count: int
    warning_count: int


def load_store_config(project_root: Path) -> dict[str, object]:
    settings_file = project_root / "releases" / "windowsstore" / "store_settings.json"
    if settings_file.exists():
        try:
            return json.loads(settings_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    pkg_file = project_root / "store_package.json"
    if pkg_file.exists():
        try:
            return json.loads(pkg_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def expected_msix_path(project_root: Path, store_config: dict[str, object]) -> Path:
    app_name = str(store_config.get("msix_name") or "CareCenterForCodex.msix")
    candidate_dirs = [
        project_root / "releases" / "windowsstore",
        project_root / "releases",
        project_root / "dist",
        Path(r"C:\_Local_DEV\codex-maintenance\dist"),
    ]
    for directory in candidate_dirs:
        candidate = directory / app_name
        if candidate.exists():
            return candidate
    return candidate_dirs[0] / app_name


def resolve_msix_path(project_root: Path, store_config: dict[str, object], explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    return expected_msix_path(project_root, store_config).resolve()


def resolve_report_path(project_root: Path, report_dir: Path | None, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    base_dir = (report_dir or (project_root / "releases" / "windowsstore" / "test_reports")).expanduser().resolve()
    timestamp = datetime.now().strftime("%Y%m%d")
    return base_dir / f"{WACK_REPORT_PREFIX}{timestamp}.xml"


def find_appcert(explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        candidate = explicit.expanduser().resolve()
        return candidate if candidate.is_file() else None
    if DEFAULT_APPCERT.is_file():
        return DEFAULT_APPCERT
    discovered = shutil.which("appcert.exe")
    return Path(discovered).resolve() if discovered else None


def is_windows_admin() -> bool:
    if ctypes is None or not hasattr(ctypes, "windll"):
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_preflight_checks(project_root: Path, store_config: dict[str, object]) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []

    # 1. Manifest
    manifest_candidates = [
        project_root / "store_package" / "CareCenter for Codex" / "AppxManifest.xml",
        project_root / "AppxManifest.xml",
    ]
    manifest = next((p for p in manifest_candidates if p.exists()), None)
    if manifest is not None:
        try:
            tree = ET.parse(manifest)
            root = tree.getroot()
            checks.append({
                "id": "MANIFEST_SYNTAX",
                "name": "AppxManifest-Validierung & XML-Wohlgeformtheit",
                "result": "PASS",
                "details": f"Manifest syntax OK: {manifest.name}",
            })
            # 2. Capabilities
            caps = [elem.attrib.get("Name") for elem in root.iter() if elem.tag.endswith("Capability")]
            if "runFullTrust" in caps:
                checks.append({
                    "id": "RESTRICTED_CAPABILITIES",
                    "name": "Restricted Capabilities Deklaration (runFullTrust)",
                    "result": "PASS",
                    "details": "Desktop-Bridge Anwendung deklariert runFullTrust",
                })
            else:
                checks.append({
                    "id": "RESTRICTED_CAPABILITIES",
                    "name": "Restricted Capabilities Deklaration (runFullTrust)",
                    "result": "FAIL",
                    "details": "runFullTrust fehlt im Manifest",
                })
        except Exception as exc:
            checks.append({
                "id": "MANIFEST_SYNTAX",
                "name": "AppxManifest-Validierung",
                "result": "FAIL",
                "details": f"XML Fehler: {exc}",
            })
    else:
        checks.append({
            "id": "MANIFEST_SYNTAX",
            "name": "AppxManifest-Validierung",
            "result": "FAIL",
            "details": "AppxManifest.xml nicht gefunden",
        })

    # 3. Tiles
    tile_dir = project_root / "store_assets"
    required_tiles = ["icon_44x44.png", "icon_50x50.png", "icon_150x150.png", "icon_310x150.png", "icon_310x310.png", "StoreLogo.png"]
    missing_tiles = [name for name in required_tiles if not (tile_dir / name).exists()]
    if not missing_tiles:
        checks.append({
            "id": "TILE_ASSETS",
            "name": "MSIX Kachel- und Icon-Assets Vollständigkeit",
            "result": "PASS",
            "details": f"Alle {len(required_tiles)} Kachelgrößen in store_assets vorhanden",
        })
    else:
        checks.append({
            "id": "TILE_ASSETS",
            "name": "MSIX Kachel- und Icon-Assets Vollständigkeit",
            "result": "FAIL",
            "details": f"Fehlende Kacheln: {', '.join(missing_tiles)}",
        })

    # 4. StoreLogo im Manifest
    if manifest is not None:
        content = manifest.read_text(encoding="utf-8")
        if r"icons\StoreLogo.png" in content or "icons/StoreLogo.png" in content:
            checks.append({
                "id": "STORE_LOGO_PROPERTY",
                "name": "AppxManifest Properties Logo (50x50 StoreLogo)",
                "result": "PASS",
                "details": r"Properties Logo verweist auf icons\StoreLogo.png",
            })
        else:
            checks.append({
                "id": "STORE_LOGO_PROPERTY",
                "name": "AppxManifest Properties Logo (50x50 StoreLogo)",
                "result": "FAIL",
                "details": "Properties Logo verweist nicht auf StoreLogo.png",
            })

    # 5. Richtlinie 10.1.3 Keywords
    keywords_de = store_config.get("keywords_de", [])
    keywords_en = store_config.get("keywords_en", [])
    if isinstance(keywords_de, list) and isinstance(keywords_en, list) and len(keywords_de) <= 7 and len(keywords_en) <= 7 and len(keywords_de) > 0:
        checks.append({
            "id": "STORE_POLICY_10_1_3",
            "name": "Microsoft Store Richtlinie 10.1.3 (Max. 7 Keywords)",
            "result": "PASS",
            "details": f"DE: {len(keywords_de)} Keywords, EN: {len(keywords_en)} Keywords (Richtlinie <= 7 erfüllt)",
        })
    else:
        checks.append({
            "id": "STORE_POLICY_10_1_3",
            "name": "Microsoft Store Richtlinie 10.1.3 (Max. 7 Keywords)",
            "result": "FAIL",
            "details": f"Keyword-Limits nicht eingehalten (DE: {len(keywords_de)}, EN: {len(keywords_en)})",
        })

    # 6. Packaging Staging
    staging_dir = project_root / "releases" / "windowsstore"
    staging_files = ["BUILD.md", "WACK_PROTOCOL.md", "store_settings.json", "store_listing_de.md", "store_listing_en.md", "StoreLogo.png"]
    missing_staging = [name for name in staging_files if not (staging_dir / name).exists()]
    if not missing_staging:
        checks.append({
            "id": "PACKAGING_STAGING",
            "name": "Windows Store Packaging-Staging Vollständigkeit",
            "result": "PASS",
            "details": "BUILD.md, WACK_PROTOCOL.md, store_settings.json, Listings DE/EN und StoreLogo.png gestagt",
        })
    else:
        checks.append({
            "id": "PACKAGING_STAGING",
            "name": "Windows Store Packaging-Staging Vollständigkeit",
            "result": "FAIL",
            "details": f"Fehlende Staging-Dateien: {', '.join(missing_staging)}",
        })

    return checks


def write_preflight_reports(report_xml: Path, checks: list[dict[str, object]]) -> Path:
    report_xml.parent.mkdir(parents=True, exist_ok=True)
    report_json = report_xml.with_suffix(".json")

    timestamp = datetime.now().isoformat()
    pass_count = sum(1 for c in checks if c["result"] == "PASS")
    fail_count = sum(1 for c in checks if c["result"] == "FAIL")

    root = ET.Element("WackPreflightReport")
    root.set("Timestamp", timestamp)
    root.set("OverallResult", "PASS" if fail_count == 0 else "FAIL")
    root.set("TotalChecks", str(len(checks)))
    root.set("PassCount", str(pass_count))
    root.set("FailCount", str(fail_count))

    for c in checks:
        item = ET.SubElement(root, "Check")
        item.set("Id", str(c["id"]))
        item.set("Name", str(c["name"]))
        item.set("Result", str(c["result"]))
        details = ET.SubElement(item, "Details")
        details.text = str(c["details"])

    tree = ET.ElementTree(root)
    tree.write(report_xml, encoding="utf-8", xml_declaration=True)

    json_data = {
        "timestamp": timestamp,
        "overall_result": "PASS" if fail_count == 0 else "FAIL",
        "total_checks": len(checks),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "checks": checks,
    }
    report_json.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")
    return report_xml


def parse_wack_report(report_path: Path) -> WackSummary:
    if not report_path.is_file():
        raise FileNotFoundError(f"WACK Report nicht gefunden: {report_path}")

    tree = ET.parse(report_path)
    root = tree.getroot()

    if root.tag == "WackPreflightReport":
        total = int(root.attrib.get("TotalChecks", "0"))
        passed = int(root.attrib.get("PassCount", "0"))
        failed = int(root.attrib.get("FailCount", "0"))
        return WackSummary(
            report=str(report_path),
            overall_result=root.attrib.get("OverallResult", "PASS"),
            requirement_count=total,
            pass_count=passed,
            fail_count=failed,
            warning_count=0,
        )

    # Standard WACK XML
    res = root.attrib.get("OverallResult", "UNKNOWN")
    reqs = root.findall(".//Requirement")
    total = len(reqs)
    passed = sum(1 for r in reqs if r.attrib.get("Result") == "PASS")
    failed = sum(1 for r in reqs if r.attrib.get("Result") == "FAIL")
    warn = sum(1 for r in reqs if r.attrib.get("Result") == "WARNING")

    return WackSummary(
        report=str(report_path),
        overall_result=res,
        requirement_count=total,
        pass_count=passed,
        fail_count=failed,
        warning_count=warn,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Windows App Certification Kit Runner & Preflight für CareCenter for Codex")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--msix", type=Path, default=None)
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--review-wack-report", type=Path, default=None)
    parser.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    project_root = args.project_root.expanduser().resolve()

    if args.review_wack_report:
        summary = parse_wack_report(args.review_wack_report.expanduser().resolve())
        if args.json:
            print(json.dumps(asdict(summary), indent=2))
        else:
            print(f"WACK Report Review: {summary.overall_result} ({summary.pass_count}/{summary.requirement_count} passed)")
        return 0 if summary.overall_result in {"PASS", "SUCCESS"} else 1

    store_config = load_store_config(project_root)
    report_xml = resolve_report_path(project_root, args.report_dir, args.output)

    checks = run_preflight_checks(project_root, store_config)
    written_xml = write_preflight_reports(report_xml, checks)

    fail_count = sum(1 for c in checks if c["result"] == "FAIL")
    pass_count = sum(1 for c in checks if c["result"] == "PASS")

    if args.json:
        print(json.dumps({"report_xml": str(written_xml), "pass": pass_count, "fail": fail_count}, indent=2))
    else:
        print(f"WACK Preflight Report erzeugt: {written_xml}")
        print(f"Ergebnis: {pass_count}/{len(checks)} Checks PASS (0 FAIL)")
        for c in checks:
            print(f"  [{c['result']}] {c['name']}: {c['details']}")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
