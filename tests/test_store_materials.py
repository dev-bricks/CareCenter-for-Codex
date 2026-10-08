"""
test_store_materials.py - Vertragstests für Microsoft Windows Store Materialien & Readiness für CareCenter for Codex.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_PUBLISHER = "CN=52596601-BAB4-4F3F-B182-E8F3F273B202"
EXPECTED_IDENTITY = "LukasGeiger.CareCenterForCodex"
EXPECTED_EXECUTABLE = "CareCenterForCodex.exe"


def _read_version_from_pyproject() -> str:
    content = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    assert match is not None
    return match.group(1)


def test_store_package_matches_project_metadata() -> None:
    pkg_file = PROJECT_ROOT / "store_package.json"
    assert pkg_file.exists()
    package = json.loads(pkg_file.read_text(encoding="utf-8"))

    assert package["app_name"] == "CareCenter for Codex"
    assert package["identity_name"] == EXPECTED_IDENTITY
    assert package["publisher"] == EXPECTED_PUBLISHER
    assert package["executable"] == EXPECTED_EXECUTABLE
    assert package["capabilities"] == "runFullTrust"
    assert package["category"] == "Developer Tools"
    assert package["license"] == "MIT"
    assert package["version"] == f"{_read_version_from_pyproject()}.0"
    assert package["privacy_url"].endswith("/privacy")
    assert package["support_url"].endswith("/support")
    assert package["logo"] == "store_assets/StoreLogo.png"
    assert "de-DE" in package["languages"]
    assert "en-US" in package["languages"]
    assert len(package["languages"]) >= 6


def test_appx_manifest_structure_and_identity() -> None:
    manifest_paths = [
        PROJECT_ROOT / "AppxManifest.xml",
        PROJECT_ROOT / "store_package" / "CareCenter for Codex" / "AppxManifest.xml",
    ]

    for manifest_file in manifest_paths:
        assert manifest_file.exists(), f"Fehlt: {manifest_file}"

        tree = ET.parse(manifest_file)
        root = tree.getroot()

        ns = {"def": "http://schemas.microsoft.com/appx/manifest/foundation/windows10"}
        identity = root.find("def:Identity", ns)
        if identity is None:
            identity = root.find("{http://schemas.microsoft.com/appx/manifest/foundation/windows10}Identity")

        assert identity is not None
        assert identity.get("Name") == EXPECTED_IDENTITY
        assert identity.get("Publisher") == EXPECTED_PUBLISHER
        assert identity.get("Version") == f"{_read_version_from_pyproject()}.0"
        assert identity.get("ProcessorArchitecture") == "x64"

        props = root.find("def:Properties", ns)
        if props is None:
            props = root.find("{http://schemas.microsoft.com/appx/manifest/foundation/windows10}Properties")
        assert props is not None
        logo = props.find("def:Logo", ns)
        if logo is None:
            logo = props.find("{http://schemas.microsoft.com/appx/manifest/foundation/windows10}Logo")
        assert logo is not None
        assert logo.text == r"icons\StoreLogo.png"


def test_store_tile_icons_dimensions_and_validity() -> None:
    required_icons = {
        "icon_44x44.png": (44, 44),
        "icon_50x50.png": (50, 50),
        "icon_150x150.png": (150, 150),
        "icon_310x150.png": (310, 150),
        "icon_310x310.png": (310, 310),
        "StoreLogo.png": (50, 50),
    }

    dirs = [
        PROJECT_ROOT / "store_package" / "CareCenter for Codex" / "icons",
        PROJECT_ROOT / "store_assets",
        PROJECT_ROOT / "assets" / "icons",
        PROJECT_ROOT / "releases" / "windowsstore",
    ]

    png_sig = b"\x89PNG\r\n\x1a\n"
    for d in dirs:
        assert d.exists(), f"Verzeichnis fehlt: {d}"
        for icon_name, expected_dim in required_icons.items():
            icon_path = d / icon_name
            assert icon_path.exists(), f"Fehlendes Icon: {icon_path}"
            data = icon_path.read_bytes()
            assert data.startswith(png_sig), f"Kein PNG: {icon_path}"
            with Image.open(icon_path) as img:
                assert img.format == "PNG"
                assert img.size == expected_dim


def test_store_screenshots_resolution_and_format() -> None:
    required_shots = [
        "01_dashboard_status.png",
        "02_database_maintenance.png",
        "03_process_cleanup.png",
        "04_audit_settings.png",
    ]

    dirs = [
        PROJECT_ROOT / "releases" / "windowsstore" / "screenshots",
        PROJECT_ROOT / "screenshots" / "store",
    ]

    png_sig = b"\x89PNG\r\n\x1a\n"
    for d in dirs:
        assert d.exists(), f"Verzeichnis fehlt: {d}"
        for shot_name in required_shots:
            shot_path = d / shot_name
            assert shot_path.exists(), f"Screenshot fehlt: {shot_path}"
            data = shot_path.read_bytes()
            assert data.startswith(png_sig), f"Kein PNG: {shot_path}"
            with Image.open(shot_path) as img:
                assert img.format == "PNG"
                assert img.size == (1920, 1080)


def test_store_listings_policy_10_1_3() -> None:
    listing = PROJECT_ROOT / "STORE_LISTING.md"
    assert listing.exists()
    content = listing.read_text(encoding="utf-8")

    kw_de_match = re.search(r"### Schlüsselwörter\s*\n([^\n#]+)", content)
    assert kw_de_match is not None
    kws_de = [k.strip() for k in kw_de_match.group(1).split(",") if k.strip()]
    assert 0 < len(kws_de) <= 7, f"DE Keywords count: {len(kws_de)}"

    kw_en_match = re.search(r"### Keywords\s*\n([^\n#]+)", content)
    assert kw_en_match is not None
    kws_en = [k.strip() for k in kw_en_match.group(1).split(",") if k.strip()]
    assert 0 < len(kws_en) <= 7, f"EN Keywords count: {len(kws_en)}"

    disallowed = ["gmail", "google", "netflix", "spotify", "adobe", "apple", "amazon"]
    for kw in kws_de + kws_en:
        assert not any(d in kw.lower() for d in disallowed)
        assert len(kw) <= 30


def test_authentic_german_umlauts_in_store_listings() -> None:
    listing_de = PROJECT_ROOT / "releases" / "windowsstore" / "store_listing_de.md"
    assert listing_de.exists()
    content = listing_de.read_text(encoding="utf-8")
    assert any(c in content for c in ["ä", "ö", "ü", "Ä", "Ö", "Ü", "ß"]), "Echte deutsche Umlaute fehlen in store_listing_de.md"


def test_store_staging_complete() -> None:
    staging_dir = PROJECT_ROOT / "releases" / "windowsstore"
    assert staging_dir.exists()

    required_files = [
        "BUILD.md",
        "WACK_PROTOCOL.md",
        "store_settings.json",
        "store_listing_de.md",
        "store_listing_en.md",
        "StoreLogo.png",
    ]
    for name in required_files:
        p = staging_dir / name
        assert p.exists(), f"Staging-Datei fehlt: {p}"
        assert p.stat().st_size > 0


def test_wack_preflight_runner_and_reports() -> None:
    runner_script = PROJECT_ROOT / "scripts" / "run_windows_wack.py"
    assert runner_script.exists()

    reports_dir = PROJECT_ROOT / "releases" / "windowsstore" / "test_reports"
    assert reports_dir.exists()

    xml_reports = list(reports_dir.glob("wack_preflight_*.xml"))
    json_reports = list(reports_dir.glob("wack_preflight_*.json"))
    assert len(xml_reports) >= 1
    assert len(json_reports) >= 1

    tree = ET.parse(xml_reports[0])
    root = tree.getroot()
    assert root.attrib.get("OverallResult") == "PASS"
    assert root.attrib.get("FailCount") == "0"


def test_check_store_readiness_audit_passes() -> None:
    auditor = PROJECT_ROOT / "scripts" / "check_store_readiness.py"
    assert auditor.exists()

    res = subprocess.run([sys.executable, str(auditor)], capture_output=True, text=True)
    assert res.returncode == 0, f"Auditor failed:\n{res.stdout}\n{res.stderr}"
    assert "AUDIT PASSED (6/6 Checks OK" in res.stdout


def test_execution_alias_declaration() -> None:
    settings = json.loads((PROJECT_ROOT / "releases" / "windowsstore" / "store_settings.json").read_text(encoding="utf-8"))
    assert settings.get("execution_alias") == "carecenter.exe"

    manifest_file = PROJECT_ROOT / "store_package" / "CareCenter for Codex" / "AppxManifest.xml"
    content = manifest_file.read_text(encoding="utf-8")
    assert 'Alias="carecenter.exe"' in content


def test_tier2_language_parity_in_manifest() -> None:
    manifest_file = PROJECT_ROOT / "AppxManifest.xml"
    content = manifest_file.read_text(encoding="utf-8")
    expected_langs = ["de-DE", "en-US", "es-ES", "zh-CN", "ja-JP", "ru-RU"]
    for lang in expected_langs:
        assert f'Language="{lang}"' in content
