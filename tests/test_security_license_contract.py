"""Hermetic contract test suite for CareCenter for Codex security, licensing, SBOM, and privacy compliance."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def test_dependency_versions_no_vulnerable_floors() -> None:
    """Verify that pyproject.toml and requirements.txt specify hardened dependency floors without known CVEs."""
    pyproject_path = ROOT / "pyproject.toml"
    assert pyproject_path.is_file(), "pyproject.toml missing"

    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project", {})

    # Direct dependencies
    deps = project.get("dependencies", [])
    deps_dict = {}
    for d in deps:
        match = re.match(r"^([A-Za-z0-9_\-]+)>=(.*)$", d)
        if match:
            deps_dict[match.group(1)] = match.group(2)

    assert "PySide6" in deps_dict, "PySide6 floor required"
    assert "tomlkit" in deps_dict, "tomlkit floor required"

    # Dev and build dependencies
    optional_deps = project.get("optional-dependencies", {})
    dev_deps = optional_deps.get("dev", [])
    build_deps = optional_deps.get("build", [])

    dev_dict = {}
    for d in dev_deps:
        match = re.match(r"^([A-Za-z0-9_\-\[\]]+)>=(.*)$", d)
        if match:
            dev_dict[match.group(1)] = match.group(2)

    # Protect against CVE-2025-7117 / GHSA-6w46-j5rx-g56g
    assert "pytest" in dev_dict, "pytest dependency must be declared in dev"
    pytest_floor = dev_dict["pytest"]
    assert tuple(map(int, pytest_floor.split("."))) >= (9, 1, 1), f"pytest floor {pytest_floor} must be >= 9.1.1"

    # Linter and type checker floors
    assert "ruff" in dev_dict, "ruff dependency must be declared in dev"
    assert tuple(map(int, dev_dict["ruff"].split("."))) >= (0, 9, 0), "ruff floor must be >= 0.9.0"

    # Build tools floors
    build_dict = {}
    for b in build_deps:
        match = re.match(r"^([A-Za-z0-9_\-]+)>=(.*)$", b)
        if match:
            build_dict[match.group(1)] = match.group(2)

    assert "pyinstaller" in build_dict, "pyinstaller dependency must be declared in build"
    assert tuple(map(int, build_dict["pyinstaller"].split("."))) >= (6, 10, 0), "pyinstaller floor must be >= 6.10.0"

    # Author contact with email
    authors = project.get("authors", [])
    assert authors, "Authors list must not be empty"
    author_emails = [a.get("email") for a in authors if isinstance(a, dict) and a.get("email")]
    assert "support@lukasgeiger.com" in author_emails, "support@lukasgeiger.com must be registered as author email"

    # requirements.txt parity
    req_path = ROOT / "requirements.txt"
    assert req_path.is_file(), "requirements.txt missing"
    req_text = req_path.read_text(encoding="utf-8")
    assert "PySide6>=6.7" in req_text
    assert "tomlkit>=0.13" in req_text


def test_third_party_license_inventory_metadata() -> None:
    """Verify THIRD_PARTY_LICENSES.txt contains 5-field schema entries, valid SPDX, and MIT compatibility."""
    license_file = ROOT / "THIRD_PARTY_LICENSES.txt"
    assert license_file.is_file(), "THIRD_PARTY_LICENSES.txt missing"

    content = license_file.read_text(encoding="utf-8")

    # Required 5-fields schema markers
    assert "License:" in content, "Missing 'License:' 5-fields marker"
    assert "SPDX:" in content, "Missing 'SPDX:' 5-fields marker"
    assert "URL:" in content, "Missing 'URL:' 5-fields marker"
    assert "Notice:" in content, "Missing 'Notice:' 5-fields marker"

    # Direct, build, test, and transitive Qt dependencies inventoried
    required_components = [
        "PySide6",
        "PySide6_Addons",
        "PySide6_Essentials",
        "shiboken6",
        "tomlkit",
        "safe-start-for-codex",
        "PyInstaller",
        "altgraph",
        "packaging",
        "hatchling",
        "pytest",
        "ruff",
        "mypy",
        "jsonschema",
        "rfc3339-validator",
        "isoduration",
    ]
    for comp in required_components:
        assert comp in content, f"Component '{comp}' missing from THIRD_PARTY_LICENSES.txt"

    # Legal compatibility assertions:
    # 1. PySide6 / shiboken6 LGPL-3.0 dynamic linking without modification
    assert "Dynamically linked" in content or "dynamically linked" in content
    # 2. PyInstaller special bootloader exception allowing MIT distribution
    assert "special exception" in content or "Bootloader-exception" in content


def test_security_policy_bilingual_and_contacts() -> None:
    """Verify SECURITY.md is bilingual, declares 48h SLA, 5-day triage, and proper vulnerability channels."""
    security_file = ROOT / "SECURITY.md"
    assert security_file.is_file(), "SECURITY.md missing"

    content = security_file.read_text(encoding="utf-8")

    # Bilingual structure
    assert "## Deutsch" in content, "German section missing"
    assert "## English" in content, "English section missing"

    # SLA guarantees
    assert "48 Stunden" in content and "48 hours" in content, "48h response SLA missing in both languages"
    assert "5 Werktagen" in content or "5 Werktage" in content
    assert "5 business days" in content

    # Maintainer and reporting channels
    assert "security@open-bricks.org" in content
    assert "security@dev-bricks.org" in content
    assert "support@lukasgeiger.com" in content
    assert "https://github.com/dev-bricks/CareCenter-for-Codex/security/advisories" in content


def test_repo_hygiene_and_gitignore_rules() -> None:
    """Verify .gitignore includes sensitive file, certificate, token, lock, and conflict exclusion patterns."""
    gitignore_file = ROOT / ".gitignore"
    assert gitignore_file.is_file(), ".gitignore missing"

    content = gitignore_file.read_text(encoding="utf-8")

    # Certificates & keys
    assert "*.pfx" in content
    assert "*.p12" in content
    assert "*.pem" in content
    assert "*.key" in content
    assert "*.cer" in content
    assert "*.crt" in content

    # Secrets & credentials
    assert "credentials.json" in content
    assert "token.json" in content
    assert "client_secret*.json" in content
    assert "secrets.*" in content
    assert "keyring/" in content

    # Test run artifacts
    assert "pytest_out.txt" in content

    # Multi-host sync conflicts
    assert "*-conflict-*" in content
    assert "*.sync-conflict-*" in content

    # Canonical locks
    assert "LOCK" in content
    assert "LOCK.*" in content
    assert "LOCK*.txt" in content


def test_no_hardcoded_user_paths_or_plaintext_secrets_in_src() -> None:
    """Verify that source code under src/ contains zero hardcoded developer paths or plaintext credentials."""
    assert SRC.is_dir(), "src/ directory missing"

    user_path_pattern = re.compile(r"C:[\\/]Users[\\/](?:lukas|User)[^\"'\s]*", re.IGNORECASE)
    secret_patterns = [
        re.compile(r"(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\s*=\s*['\"][A-Za-z0-9_\-]{16,}['\"]", re.IGNORECASE),
        re.compile(r"ghp_[A-Za-z0-9]{36}"),
        re.compile(r"sk-[A-Za-z0-9]{32,}"),
    ]

    for py_file in SRC.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), 1):
            assert not user_path_pattern.search(line), (
                f"Hardcoded user path in {py_file.relative_to(ROOT)}:{line_no}: {line.strip()}"
            )
            for pat in secret_patterns:
                assert not pat.search(line), (
                    f"Possible plaintext secret in {py_file.relative_to(ROOT)}:{line_no}: {line.strip()}"
                )


def test_license_parity_across_manifests() -> None:
    """Verify license parity and consistency across pyproject.toml, LICENSE, NOTICE, and store_package.json."""
    # pyproject.toml
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject.get("project", {}).get("license") == {"text": "MIT"}

    # LICENSE file
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in license_text
    assert "Copyright (c) 2026 Lukas Geiger" in license_text

    # NOTICE file
    notice_text = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "CareCenter for Codex" in notice_text
    assert "MIT License" in notice_text

    # store_package.json
    store_package_file = ROOT / "store_package.json"
    if store_package_file.is_file():
        import json
        sp_data = json.loads(store_package_file.read_text(encoding="utf-8"))
        assert sp_data.get("app_name") == "CareCenter for Codex"
        assert sp_data.get("publisher_display") == "Lukas Geiger"


def test_zero_unauthorized_telemetry_or_network_egress() -> None:
    """Verify that tray, watchdog, and maintenance modules perform local-only operations without network egress."""
    forbidden_network_modules = {"requests", "httpx", "urllib.request", "aiohttp", "socket"}

    # Inspect source files in core modules
    core_modules = [
        SRC / "codex_logdatenbank_wartung" / "cli.py",
        SRC / "codex_logdatenbank_wartung" / "config.py",
        SRC / "codex_logdatenbank_wartung" / "config_audit.py",
        SRC / "codex_logdatenbank_wartung" / "orchestrator.py",
        SRC / "codex_logdatenbank_wartung" / "thread_hygiene.py",
        SRC / "codex_logdatenbank_wartung" / "tray_app.py",
        SRC / "codex_logdatenbank_wartung" / "watchdog.py",
    ]

    for mod in core_modules:
        if not mod.is_file():
            continue
        text = mod.read_text(encoding="utf-8")
        for net_mod in forbidden_network_modules:
            pattern = rf"^\s*(?:import\s+{net_mod}|from\s+{net_mod}\s+import)"
            assert not re.search(pattern, text, re.MULTILINE), (
                f"Unauthorized network import '{net_mod}' detected in local runtime module {mod.name}"
            )
