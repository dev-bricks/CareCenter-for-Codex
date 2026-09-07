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
    assert "Last-checked: 2026-09-07" in content
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
        assert "open--bricks" in readme
        assert "llms.txt" in readme
