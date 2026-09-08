"""Contract tests for repository hygiene, PEP 621 metadata, CI guardrails, and security policies."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_pep621_metadata_and_urls() -> None:
    """Verify PEP 621 compliance, version, and required project URLs in pyproject.toml."""
    pyproject_path = ROOT / "pyproject.toml"
    assert pyproject_path.is_file()

    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project", {})

    assert project.get("name") == "carecenter-for-codex"
    assert project.get("version") == "0.8.0"

    urls = project.get("urls", {})
    required_urls = [
        "Homepage",
        "Documentation",
        "Repository",
        "Issues",
        "Changelog",
        "Security",
        "Umbrella",
        "Parent Organization",
        "Umbrella Ecosystem",
    ]
    for key in required_urls:
        assert key in urls, f"Missing project URL: {key}"
        assert urls[key].startswith("https://"), f"Invalid URL for {key}: {urls[key]}"

    classifiers = project.get("classifiers", [])
    assert "Operating System :: Microsoft :: Windows" in classifiers
    assert "Programming Language :: Python :: 3.12" in classifiers
    assert "Programming Language :: Python :: 3.13" in classifiers
    assert "License :: OSI Approved :: MIT License" in classifiers


def test_ci_workflow_guardrails() -> None:
    """Verify GitHub Actions CI workflow includes concurrency, ruff linting, and Python matrix."""
    ci_path = ROOT / ".github" / "workflows" / "tests.yml"
    assert ci_path.is_file()

    content = ci_path.read_text(encoding="utf-8")
    assert "cancel-in-progress: true" in content
    assert "3.12" in content
    assert "3.13" in content
    assert "ruff check" in content
    assert "compileall" in content
    assert "pytest" in content


def test_security_policy_structure() -> None:
    """Verify SECURITY.md bilingual structure, supported versions, and maintainer contacts."""
    security_path = ROOT / "SECURITY.md"
    assert security_path.is_file()

    content = security_path.read_text(encoding="utf-8")
    assert "## Deutsch" in content
    assert "## English" in content
    assert "0.8.x" in content
    assert "security@open-bricks.org" in content
    assert "support@lukasgeiger.com" in content
    assert "github.com/dev-bricks/CareCenter-for-Codex/security/advisories" in content


def test_llms_txt_and_docs_sync() -> None:
    """Verify llms.txt contains the canonical repository, package name, and current timestamp."""
    llms_path = ROOT / "llms.txt"
    assert llms_path.is_file()

    content = llms_path.read_text(encoding="utf-8")
    assert "Last-checked: 2026-09-08" in content
    assert "https://github.com/dev-bricks/CareCenter-for-Codex" in content
    assert "carecenter-for-codex" in content


def test_readme_badges_consistency() -> None:
    """Verify essential shields.io badges are present across English and German READMEs."""
    readme_en = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_de = (ROOT / "README.de.md").read_text(encoding="utf-8")

    for readme in (readme_en, readme_de):
        assert "actions/workflows/tests.yml/badge.svg" in readme
        assert "badge/Python-3.12" in readme
        assert ("badge/Platform-Windows" in readme or "badge/Plattform-Windows" in readme)
        assert "dev--bricks" in readme
        assert "open--bricks" in readme
        assert "llms.txt" in readme
        assert "PySide6" in readme


def test_quick_navigation_anchors_parity() -> None:
    """Verify that both READMEs contain identical 14-item Quick Navigation anchors matching headings."""
    readme_en = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_de = (ROOT / "README.de.md").read_text(encoding="utf-8")

    en_expected_headings = [
        "Why & Problem Statement",
        "Architecture & System Flow",
        "Complete Lifecycle Sequence",
        "Key Capabilities & Safety Invariants",
        "Sibling Ecosystem & Partner Tools",
        "Features",
        "Screenshot",
        "Requirements",
        "Install and Run",
        "CLI Usage",
        "Configuration",
        "Safety Model & Invariants",
        "Windows Store Materials",
        "Development & License",
    ]

    de_expected_headings = [
        "Warum & Problemstellung",
        "Architektur & Systemfluss",
        "Vollständiger Lebenszyklus-Ablauf",
        "Kernfähigkeiten & Sicherheitsinvarianten",
        "Geschwisterwerkzeuge & Partner-Ökosystem",
        "Funktionen",
        "Screenshot",
        "Voraussetzungen",
        "Installation und Start",
        "CLI-Befehle",
        "Konfiguration",
        "Sicherheitsmodell & Invarianten",
        "Windows-Store-Materialien",
        "Entwicklung & Lizenz",
    ]

    for heading in en_expected_headings:
        assert f"## {heading}" in readme_en, f"Missing English heading: ## {heading}"

    for heading in de_expected_headings:
        assert f"## {heading}" in readme_de, f"Missing German heading: ## {heading}"

    assert "🧭 Quick Navigation" in readme_en
    assert "🧭 Schnellnavigation" in readme_de


def test_mermaid_dual_diagrams_syntax_and_parity() -> None:
    """Verify both READMEs include valid Flowchart and Sequence diagrams with core components."""
    readme_en = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_de = (ROOT / "README.de.md").read_text(encoding="utf-8")

    for readme in (readme_en, readme_de):
        assert "```mermaid\nflowchart TD" in readme
        assert "```mermaid\nsequenceDiagram" in readme
        assert "autonumber" in readme
        assert "state_5.sqlite" in readme
        assert "PRAGMA integrity_check" in readme
        assert "VACUUM" in readme


def test_governance_invariants_table_parity() -> None:
    """Verify both READMEs define all 10 runtime safety invariants."""
    readme_en = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_de = (ROOT / "README.de.md").read_text(encoding="utf-8")

    for i in range(1, 11):
        assert f"**{i}." in readme_en, f"Missing invariant {i} in English README"
        assert f"**{i}." in readme_de, f"Missing invariant {i} in German README"


def test_sibling_ecosystem_matrix_parity() -> None:
    """Verify both READMEs link to the 12 partner repositories across the sibling ecosystem."""
    readme_en = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_de = (ROOT / "README.de.md").read_text(encoding="utf-8")

    partners = [
        "safe-start-for-codex",
        "MethodenAnalyser",
        "companion-for-agy",
        "lock-master",
        "bach",
        "usmc",
        "clutch",
        "open-compute",
        "system-auditor",
        "CloudLockFixer",
        "SoftwareCenter",
        "DokuZen",
    ]

    for partner in partners:
        assert f"[{partner}]" in readme_en, f"Missing partner {partner} in English README"
        assert f"[{partner}]" in readme_de, f"Missing partner {partner} in German README"


def test_changelog_release_entry_present() -> None:
    """Verify CHANGELOG.md contains the 2026-09-08 Pfad B entry under Unreleased."""
    changelog_path = ROOT / "CHANGELOG.md"
    assert changelog_path.is_file()

    content = changelog_path.read_text(encoding="utf-8")
    assert "## Unreleased" in content
    assert "Discoverability & Ecosystem (2026-09-08)" in content
    assert "Pfad B" in content


def test_german_umlauts_utf8_integrity() -> None:
    """Verify README.de.md uses native German umlauts and valid UTF-8 without replacement corruptions."""
    readme_de = (ROOT / "README.de.md").read_text(encoding="utf-8")

    # Native umlauts and eszett must be present
    assert "ä" in readme_de
    assert "ö" in readme_de
    assert "ü" in readme_de
    assert "ß" in readme_de

    # No unescaped Unicode replacement characters
    assert "\ufffd" not in readme_de
