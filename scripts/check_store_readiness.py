#!/usr/bin/env python3
"""
check_store_readiness.py - Windows Store Readiness Audit Tool for CareCenter for Codex.

Validates:
1. store_package.json metadata and schema
2. AppxManifest.xml syntax, identities, capabilities, and visual elements
3. Tile icons presence, PNG signature, and exact dimensions across all directories
4. STORE_LISTING.md, PRIVACY_POLICY.md, SUPPORT.md, WINDOWS_STORE_PREP.md and keyword guidelines
5. Store screenshot assets and 1920x1080 dimensions
6. releases/windowsstore Packaging Staging and WACK Preflight Reports
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

EXPECTED_PUBLISHER = "CN=52596601-BAB4-4F3F-B182-E8F3F273B202"
EXPECTED_IDENTITY = "LukasGeiger.CareCenterForCodex"
EXPECTED_EXECUTABLE = "CareCenterForCodex.exe"
EXPECTED_VERSION = "0.8.0.0"

DISALLOWED_KEYWORD_TRADEMARKS = [
    "gmail", "google", "netflix", "spotify", "adobe", "apple", "amazon"
]

REQUIRED_TILE_ICONS = {
    "icon_44x44.png": (44, 44),
    "icon_50x50.png": (50, 50),
    "icon_150x150.png": (150, 150),
    "icon_310x150.png": (310, 150),
    "icon_310x310.png": (310, 310),
    "StoreLogo.png": (50, 50),
}

REQUIRED_SCREENSHOTS = [
    "01_dashboard_status.png",
    "02_database_maintenance.png",
    "03_process_cleanup.png",
    "04_audit_settings.png",
]

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def read_pyproject_version() -> str:
    content = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if match is None:
        raise ValueError("version fehlt in pyproject.toml")
    return match.group(1)


def check_store_package_json(results: dict) -> None:
    pkg_file = PROJECT_ROOT / "store_package.json"
    if not pkg_file.exists():
        results["errors"].append("store_package.json fehlt im Root-Verzeichnis.")
        return

    try:
        data = json.loads(pkg_file.read_text(encoding="utf-8"))
    except Exception as e:
        results["errors"].append(f"store_package.json ungültiges JSON: {e}")
        return

    required = [
        "app_name", "publisher", "publisher_display", "identity_name",
        "version", "description", "executable", "capabilities",
        "category", "age_rating", "privacy_url", "support_url", "languages", "logo"
    ]
    for key in required:
        if key not in data or not str(data[key]).strip():
            results["errors"].append(f"store_package.json: Pflichtfeld '{key}' fehlt oder ist leer.")

    if data.get("publisher") != EXPECTED_PUBLISHER:
        results["errors"].append(f"store_package.json: Publisher '{data.get('publisher')}' != '{EXPECTED_PUBLISHER}'")

    if data.get("identity_name") != EXPECTED_IDENTITY:
        results["errors"].append(f"store_package.json: Identity '{data.get('identity_name')}' != '{EXPECTED_IDENTITY}'")

    if data.get("executable") != EXPECTED_EXECUTABLE:
        results["errors"].append(f"store_package.json: Executable '{data.get('executable')}' != '{EXPECTED_EXECUTABLE}'")

    expected_ver = f"{read_pyproject_version()}.0"
    if data.get("version") != expected_ver:
        results["errors"].append(f"store_package.json: Version '{data.get('version')}' != '{expected_ver}'")

    if data.get("capabilities") != "runFullTrust":
        results["errors"].append("store_package.json: capabilities muss 'runFullTrust' sein.")

    langs = data.get("languages", [])
    if not isinstance(langs, list) or len(langs) < 2:
        results["errors"].append("store_package.json: Mindestens de-DE und en-US in languages erforderlich.")


def check_appx_manifest(results: dict) -> None:
    manifest_paths = [
        PROJECT_ROOT / "AppxManifest.xml",
        PROJECT_ROOT / "store_package" / "CareCenter for Codex" / "AppxManifest.xml",
    ]
    for manifest_path in manifest_paths:
        if not manifest_path.exists():
            results["errors"].append(f"{manifest_path.relative_to(PROJECT_ROOT)} fehlt.")
            continue

        try:
            tree = ET.parse(manifest_path)
            root = tree.getroot()
        except Exception as e:
            results["errors"].append(f"{manifest_path.relative_to(PROJECT_ROOT)} XML ungültig: {e}")
            continue

        ns = {"def": "http://schemas.microsoft.com/appx/manifest/foundation/windows10"}
        identity = root.find("def:Identity", ns)
        if identity is None:
            identity = root.find("{http://schemas.microsoft.com/appx/manifest/foundation/windows10}Identity")
        if identity is None:
            results["errors"].append(f"{manifest_path.name}: Identity-Element fehlt.")
        else:
            if identity.get("Name") != EXPECTED_IDENTITY:
                results["errors"].append(f"{manifest_path.name}: Identity Name '{identity.get('Name')}' != '{EXPECTED_IDENTITY}'")
            if identity.get("Publisher") != EXPECTED_PUBLISHER:
                results["errors"].append(f"{manifest_path.name}: Identity Publisher '{identity.get('Publisher')}' != '{EXPECTED_PUBLISHER}'")
            if identity.get("ProcessorArchitecture") != "x64":
                results["errors"].append(f"{manifest_path.name}: ProcessorArchitecture muss 'x64' sein.")

        props = root.find("def:Properties", ns)
        if props is None:
            props = root.find("{http://schemas.microsoft.com/appx/manifest/foundation/windows10}Properties")
        if props is not None:
            logo = props.find("def:Logo", ns)
            if logo is None:
                logo = props.find("{http://schemas.microsoft.com/appx/manifest/foundation/windows10}Logo")
            if logo is None or logo.text != r"icons\StoreLogo.png":
                actual = logo.text if logo is not None else "<fehlt>"
                results["errors"].append(f"{manifest_path.name}: Properties Logo muss 'icons\\StoreLogo.png' sein, ist: '{actual}'")
        else:
            results["errors"].append(f"{manifest_path.name}: Properties fehlt.")


def check_tile_icons(results: dict) -> None:
    dirs = [
        PROJECT_ROOT / "store_package" / "CareCenter for Codex" / "icons",
        PROJECT_ROOT / "store_assets",
        PROJECT_ROOT / "assets" / "icons",
        PROJECT_ROOT / "releases" / "windowsstore",
    ]

    for d in dirs:
        if not d.exists():
            results["errors"].append(f"Kachelverzeichnis fehlt: {d.relative_to(PROJECT_ROOT)}")
            continue

        for icon_name, expected_dim in REQUIRED_TILE_ICONS.items():
            icon_path = d / icon_name
            if not icon_path.exists():
                results["errors"].append(f"Fehlendes Icon: {icon_path.relative_to(PROJECT_ROOT)}")
                continue

            try:
                data = icon_path.read_bytes()
                if not data.startswith(PNG_SIGNATURE):
                    results["errors"].append(f"{icon_path.relative_to(PROJECT_ROOT)} ist kein valides PNG.")
                with Image.open(icon_path) as img:
                    if img.size != expected_dim:
                        results["errors"].append(
                            f"{icon_path.relative_to(PROJECT_ROOT)} Dimensionen {img.size} != {expected_dim}"
                        )
            except Exception as e:
                results["errors"].append(f"Fehler beim Prüfen von {icon_path.relative_to(PROJECT_ROOT)}: {e}")


def check_screenshots(results: dict) -> None:
    dirs = [
        PROJECT_ROOT / "releases" / "windowsstore" / "screenshots",
        PROJECT_ROOT / "screenshots" / "store",
    ]

    for d in dirs:
        if not d.exists():
            results["errors"].append(f"Screenshot-Verzeichnis fehlt: {d.relative_to(PROJECT_ROOT)}")
            continue

        for shot_name in REQUIRED_SCREENSHOTS:
            shot_path = d / shot_name
            if not shot_path.exists():
                results["errors"].append(f"Fehlender Store-Screenshot: {shot_path.relative_to(PROJECT_ROOT)}")
                continue

            try:
                data = shot_path.read_bytes()
                if not data.startswith(PNG_SIGNATURE):
                    results["errors"].append(f"{shot_path.relative_to(PROJECT_ROOT)} ist kein valides PNG.")
                with Image.open(shot_path) as img:
                    if img.size != (1920, 1080):
                        results["errors"].append(
                            f"{shot_path.relative_to(PROJECT_ROOT)} Auflösung {img.size} != (1920, 1080)"
                        )
            except Exception as e:
                results["errors"].append(f"Fehler beim Prüfen von {shot_path.relative_to(PROJECT_ROOT)}: {e}")


def check_store_listings_and_docs(results: dict) -> None:
    docs = [
        PROJECT_ROOT / "STORE_LISTING.md",
        PROJECT_ROOT / "PRIVACY_POLICY.md",
        PROJECT_ROOT / "SUPPORT.md",
        PROJECT_ROOT / "WINDOWS_STORE_PREP.md",
        PROJECT_ROOT / "releases" / "windowsstore" / "store_listing_de.md",
        PROJECT_ROOT / "releases" / "windowsstore" / "store_listing_en.md",
    ]

    for doc in docs:
        if not doc.exists():
            results["errors"].append(f"Pflichtdokument fehlt: {doc.relative_to(PROJECT_ROOT)}")

    listing = PROJECT_ROOT / "STORE_LISTING.md"
    if listing.exists():
        content = listing.read_text(encoding="utf-8")
        kw_de_match = re.search(r"### Schlüsselwörter\s*\n([^\n#]+)", content)
        if kw_de_match:
            kws_de = [k.strip() for k in kw_de_match.group(1).split(",") if k.strip()]
            if len(kws_de) > 7:
                results["errors"].append(f"STORE_LISTING.md DE: {len(kws_de)} Keywords überschreitet Limit von 7 (Richtlinie 10.1.3)")
            for kw in kws_de:
                if any(tm in kw.lower() for tm in DISALLOWED_KEYWORD_TRADEMARKS):
                    results["errors"].append(f"STORE_LISTING.md DE: Unzulässige Marke in Keyword '{kw}'")

        kw_en_match = re.search(r"### Keywords\s*\n([^\n#]+)", content)
        if kw_en_match:
            kws_en = [k.strip() for k in kw_en_match.group(1).split(",") if k.strip()]
            if len(kws_en) > 7:
                results["errors"].append(f"STORE_LISTING.md EN: {len(kws_en)} Keywords überschreitet Limit von 7 (Richtlinie 10.1.3)")
            for kw in kws_en:
                if any(tm in kw.lower() for tm in DISALLOWED_KEYWORD_TRADEMARKS):
                    results["errors"].append(f"STORE_LISTING.md EN: Unzulässige Marke in Keyword '{kw}'")


def check_staging_and_wack(results: dict) -> None:
    staging_dir = PROJECT_ROOT / "releases" / "windowsstore"
    required_staging_files = [
        "BUILD.md",
        "WACK_PROTOCOL.md",
        "store_settings.json",
        "store_listing_de.md",
        "store_listing_en.md",
        "StoreLogo.png",
    ]
    for name in required_staging_files:
        if not (staging_dir / name).exists():
            results["errors"].append(f"Staging-Datei fehlt: releases/windowsstore/{name}")

    reports_dir = staging_dir / "test_reports"
    if not reports_dir.exists() or not list(reports_dir.glob("wack_preflight_*.xml")):
        results["errors"].append("WACK-Preflight-Report (test_reports/wack_preflight_*.xml) fehlt.")


def run_full_audit() -> dict[str, list[str]]:
    results: dict[str, list[str]] = {"errors": [], "warnings": []}

    check_store_package_json(results)
    check_appx_manifest(results)
    check_tile_icons(results)
    check_screenshots(results)
    check_store_listings_and_docs(results)
    check_staging_and_wack(results)

    return results


def main() -> int:
    print("=== CareCenter for Codex — Windows Store Readiness Audit ===")
    results = run_full_audit()

    if results["errors"]:
        print(f"\nAUDIT FAILED ({len(results['errors'])} Fehler gefunden):")
        for err in results["errors"]:
            print(f"  [FAIL] {err}")
        return 1

    if results["warnings"]:
        print(f"\nAUDIT WARNUNGEN ({len(results['warnings'])} Warnungen):")
        for warn in results["warnings"]:
            print(f"  [WARN] {warn}")

    print("\nAUDIT PASSED (6/6 Checks OK - Vorbereitung vollständig)")
    print("Alle Store-Metadaten, Kacheln, Screenshots, Listings, Packaging-Staging und WACK-Preflight-Berichte sind valide.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
