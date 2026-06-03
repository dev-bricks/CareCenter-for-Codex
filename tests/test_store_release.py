from __future__ import annotations

import json
from pathlib import Path

from codex_logdatenbank_wartung.store_release import validate_store_materials


def _write_store_files(project_root: Path, payload: dict[str, object]) -> None:
    (project_root / "store_package.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for name in ("STORE_LISTING.md", "PRIVACY_POLICY.md", "SUPPORT.md"):
        (project_root / name).write_text(f"# {name}\n", encoding="utf-8")
    screenshot = project_root / "README" / "screenshots"
    screenshot.mkdir(parents=True, exist_ok=True)
    (screenshot / "main.png").write_bytes(b"png")


def test_validate_store_materials_reports_ok_for_complete_materials(tmp_path: Path) -> None:
    exe_path = tmp_path / "CareCenterForCodex.exe"
    exe_path.write_bytes(b"exe")
    _write_store_files(
        tmp_path,
        {
            "app_name": "CareCenter for Codex",
            "publisher": "CN=01234567-89AB-CDEF-0123-456789ABCDEF",
            "publisher_display": "Lukas Geiger",
            "identity_name": "LukasGeiger.CareCenterForCodex",
            "version": "0.6.2.0",
            "description": "Offline Wartung und Reparatur fuer die Codex-Desktop-App.",
            "executable": "CareCenterForCodex.exe",
            "capabilities": "runFullTrust",
            "category": "Developer Tools",
            "age_rating": "3+",
            "privacy_url": "https://lukas.example.org/privacy",
            "support_url": "https://lukas.example.org/support",
        },
    )

    report = validate_store_materials(project_root=tmp_path, exe_path=exe_path)

    assert report.status == "ok"


def test_validate_store_materials_fails_without_runfulltrust(tmp_path: Path) -> None:
    _write_store_files(
        tmp_path,
        {
            "app_name": "CareCenter for Codex",
            "publisher": "CN=01234567-89AB-CDEF-0123-456789ABCDEF",
            "publisher_display": "Lukas Geiger",
            "identity_name": "LukasGeiger.CareCenterForCodex",
            "version": "0.6.2.0",
            "description": "Offline Wartung und Reparatur fuer die Codex-Desktop-App.",
            "executable": "CareCenterForCodex.exe",
            "capabilities": "internetClient",
            "category": "Developer Tools",
            "age_rating": "3+",
            "privacy_url": "https://lukas.example.org/privacy",
            "support_url": "https://lukas.example.org/support",
        },
    )

    report = validate_store_materials(project_root=tmp_path)

    assert report.status == "failed"
    assert any(check.name == "Capabilities" and check.status == "failed" for check in report.checks)


def test_validate_store_materials_warns_for_placeholder_urls(tmp_path: Path) -> None:
    _write_store_files(
        tmp_path,
        {
            "app_name": "CareCenter for Codex",
            "publisher": "CN=01234567-89AB-CDEF-0123-456789ABCDEF",
            "publisher_display": "Lukas Geiger",
            "identity_name": "LukasGeiger.CareCenterForCodex",
            "version": "0.6.2.0",
            "description": "Offline Wartung und Reparatur fuer die Codex-Desktop-App.",
            "executable": "CareCenterForCodex.exe",
            "capabilities": "runFullTrust",
            "category": "Developer Tools",
            "age_rating": "3+",
            "privacy_url": "https://example.invalid/privacy",
            "support_url": "https://example.com/support",
        },
    )

    report = validate_store_materials(project_root=tmp_path)

    assert report.status == "warning"
    assert any(check.name == "Store-URLs" and check.status == "warning" for check in report.checks)
