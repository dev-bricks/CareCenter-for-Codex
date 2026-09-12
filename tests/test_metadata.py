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
        "LLM Ready",
        "Marketing Log",
        "Third-Party Licenses",
        "Bug Tracker",
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
    assert "Last-checked: 2026-09-12" in content
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
        assert ("Security%20SLA" in readme or "Sicherheits--SLA" in readme)
        assert ("code%20style-ruff" in readme or "Code--Stil-ruff" in readme)
        assert ("Third--Party%20Licenses-Audited" in readme or "Drittanbieter--Lizenzen-Gepr" in readme)
        assert "Tests-397" in readme


def test_quick_navigation_anchors_parity() -> None:
    """Verify that both READMEs contain identical 17-item Quick Navigation anchors matching headings."""
    readme_en = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_de = (ROOT / "README.de.md").read_text(encoding="utf-8")

    en_expected_headings = [
        "Why & Problem Statement",
        "Architecture & System Flow",
        "Complete Lifecycle Sequence",
        "Key Capabilities & Safety Invariants",
        "Target Personas & Discoverability",
        "Comparative Matrix & Alternatives",
        "Sibling Ecosystem & Partner Tools",
        "Features",
        "Screenshot",
        "Requirements",
        "Install and Run",
        "CLI Usage",
        "Configuration",
        "Safety Model & Invariants",
        "Windows Store Materials",
        "Third-Party Licenses & Transparency",
        "Development & License",
    ]

    de_expected_headings = [
        "Warum & Problemstellung",
        "Architektur & Systemfluss",
        "Vollständiger Lebenszyklus-Ablauf",
        "Kernfähigkeiten & Sicherheitsinvarianten",
        "Zielgruppen & Auffindbarkeit",
        "Vergleichsmatrix & Alternativen",
        "Geschwisterwerkzeuge & Partner-Ökosystem",
        "Funktionen",
        "Screenshot",
        "Voraussetzungen",
        "Installation und Start",
        "CLI-Befehle",
        "Konfiguration",
        "Sicherheitsmodell & Invarianten",
        "Windows-Store-Materialien",
        "Drittanbieter-Lizenzen & Transparenz",
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


def test_gitignore_hygiene() -> None:
    """Verify .gitignore includes multi-host sync conflict, lock, coverage, and temporary editor patterns."""
    gitignore_path = ROOT / ".gitignore"
    assert gitignore_path.is_file()

    content = gitignore_path.read_text(encoding="utf-8")
    required_patterns = [
        "*-conflict-*",
        "*.sync-conflict-*",
        "*.conflict",
        "*-CONFLIT-*",
        "*.sync-temp-*",
        "LOCK.*",
        "*.lock",
        "LOCK",
        "LOCK*.txt",
        ".coverage",
        "coverage/",
        "htmlcov/",
        "wheelhouse/",
        ".wheel-smoke/",
        "*.tmp",
        "*.bak",
        "*.swp",
        "*~",
    ]
    for pattern in required_patterns:
        assert pattern in content, f"Missing required .gitignore pattern: {pattern}"


def test_security_policy_triage_commitment() -> None:
    """Verify SECURITY.md declares 48h response SLA, 5-business-day triage commitment, and official contacts."""
    security_path = ROOT / "SECURITY.md"
    assert security_path.is_file()

    content = security_path.read_text(encoding="utf-8")
    assert "48 Stunden" in content
    assert "48 hours" in content
    assert "5 Werktagen" in content or "5 Werktage" in content
    assert "5 business days" in content
    assert "security@open-bricks.org" in content
    assert "security@dev-bricks.org" in content
    assert "support@lukasgeiger.com" in content
    assert "lukas@open-bricks.org" in content


def test_ci_pip_cache_and_bytecode_gate() -> None:
    """Verify CI workflow tests.yml includes pip caching, compileall bytecode gate, and timeout guardrail."""
    ci_path = ROOT / ".github" / "workflows" / "tests.yml"
    assert ci_path.is_file()

    content = ci_path.read_text(encoding="utf-8")
    assert "cache: 'pip'" in content
    assert "python -m compileall -q src tests" in content
    assert "timeout-minutes: 15" in content


def test_changelog_pfad_a_hygiene_entry() -> None:
    """Verify CHANGELOG.md contains the 2026-09-11 Pfad A technical hygiene entry under Unreleased."""
    changelog_path = ROOT / "CHANGELOG.md"
    assert changelog_path.is_file()

    content = changelog_path.read_text(encoding="utf-8")
    assert "## Unreleased" in content
    assert "Technical Hygiene & Quality Hardening (2026-09-11)" in content
    assert "Pfad A" in content


def test_changelog_pfad_b_refresh_entry() -> None:
    """Verify CHANGELOG.md contains the 2026-09-12 Pfad B refresh entry under Unreleased."""
    changelog_path = ROOT / "CHANGELOG.md"
    assert changelog_path.is_file()

    content = changelog_path.read_text(encoding="utf-8")
    assert "## Unreleased" in content
    assert "Discoverability, Governance & License Audit Refresh (2026-09-12)" in content
    assert "Pfad B" in content


def test_target_personas_bilingual_sections() -> None:
    """Verify that both READMEs contain all 4 target personas and search keyword sections."""
    readme_en = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_de = (ROOT / "README.de.md").read_text(encoding="utf-8")

    assert "## Target Personas & Discoverability" in readme_en
    assert "Solo Developers & AI Engineers" in readme_en
    assert "DevOps & Workstation Tooling Integrators" in readme_en
    assert "Local-First & Data Privacy Advocates" in readme_en
    assert "IT Support & System Administrators" in readme_en
    assert "High-Intent Search & Discovery Keywords" in readme_en

    assert "## Zielgruppen & Auffindbarkeit" in readme_de
    assert "Solo-Entwickler & KI-Ingenieure" in readme_de
    assert "DevOps & Tooling-Integratoren" in readme_de
    assert "Lokal-Erstmals- & Datenschutz-Verfechter" in readme_de
    assert "IT-Support & Systemadministratoren" in readme_de
    assert "Suchbegriffe & Auffindbarkeit" in readme_de


def test_comparative_matrix_sections() -> None:
    """Verify that both READMEs contain the 10-dimension 5-way comparative matrix."""
    readme_en = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_de = (ROOT / "README.de.md").read_text(encoding="utf-8")

    assert "## Comparative Matrix & Alternatives" in readme_en
    assert "Windows Task Manager" in readme_en
    assert "Ad-Hoc Scripts (Batch/PS)" in readme_en
    assert "Generic Cleaners (CCleaner)" in readme_en
    assert "Codex Reinstallation" in readme_en

    assert "## Vergleichsmatrix & Alternativen" in readme_de
    assert "Windows Task-Manager" in readme_de
    assert "Ad-Hoc Skripte (Batch/PS)" in readme_de
    assert "Generische Cleaner (CCleaner)" in readme_de
    assert "Codex-Neuinstallation" in readme_de


def test_third_party_licenses_audit_and_transparency() -> None:
    """Verify THIRD_PARTY_LICENSES.md exists and comprehensively details dependencies and invariants."""
    audit_path = ROOT / "THIRD_PARTY_LICENSES.md"
    assert audit_path.is_file()

    content = audit_path.read_text(encoding="utf-8")
    assert "MIT License" in content
    assert "PySide6" in content
    assert "LGPL-3.0-only" in content
    assert "tomlkit" in content
    assert "safe-start-for-codex" in content
    assert "PyInstaller" in content
    assert "pytest" in content
    assert "Ruff" in content
    assert "mypy" in content
    assert "Python Software Foundation (PSF) License Agreement 2.0" in content


def test_governance_invariants_canonical_codes() -> None:
    """Verify all 10 canonical invariant codes (INV-LOCAL-01 through INV-SLA-10) are present across core files."""
    audit_content = (ROOT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
    readme_en = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_de = (ROOT / "README.de.md").read_text(encoding="utf-8")
    llms_txt = (ROOT / "llms.txt").read_text(encoding="utf-8")

    codes = [
        "INV-LOCAL-01",
        "INV-NOELEV-02",
        "INV-ISOLAT-03",
        "INV-SESSIM-04",
        "INV-ATOMIC-05",
        "INV-CRYPTO-06",
        "INV-GRACE-07",
        "INV-STAGGER-08",
        "INV-NONDEST-09",
        "INV-SLA-10",
    ]

    for code in codes:
        assert code in audit_content, f"Missing {code} in THIRD_PARTY_LICENSES.md"
        assert code in readme_en, f"Missing {code} in README.md"
        assert code in readme_de, f"Missing {code} in README.de.md"
        assert code in llms_txt, f"Missing {code} in llms.txt"


def test_readme_de_files_parity() -> None:
    """Verify that README.de.md and README_de.md both exist and are identical."""
    de_dot = ROOT / "README.de.md"
    de_underscore = ROOT / "README_de.md"

    assert de_dot.is_file()
    assert de_underscore.is_file()

    content_dot = de_dot.read_text(encoding="utf-8")
    content_underscore = de_underscore.read_text(encoding="utf-8")

    assert content_dot == content_underscore, "README.de.md and README_de.md diverged"
