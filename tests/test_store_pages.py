from __future__ import annotations

import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "build_store_pages.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_store_pages", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_store_pages_creates_extensionless_routes(tmp_path: Path) -> None:
    builder = _load_builder()
    output_dir = tmp_path / "_site"

    written = builder.build_pages(PROJECT_ROOT, output_dir)

    expected = {
        output_dir / "privacy" / "index.html",
        output_dir / "support" / "index.html",
        output_dir / "index.html",
    }
    assert set(written) == expected
    assert expected <= {path for path in output_dir.rglob("*.html")}


def test_build_store_pages_rewrites_internal_markdown_links(tmp_path: Path) -> None:
    builder = _load_builder()
    output_dir = tmp_path / "_site"

    builder.build_pages(PROJECT_ROOT, output_dir)

    privacy = (output_dir / "privacy" / "index.html").read_text(encoding="utf-8")
    support = (output_dir / "support" / "index.html").read_text(encoding="utf-8")
    assert "../support/" in privacy
    assert "../privacy/" in support
    assert "./support.md" not in privacy
    assert "./privacy.md" not in support
    assert "https://github.com/dev-bricks/CareCenter-for-Codex/blob/main/PRIVACY_POLICY.md" in privacy
    assert "https://github.com/dev-bricks/CareCenter-for-Codex/blob/main/SUPPORT.md" in support


def test_build_store_pages_preserves_german_text_and_privacy_claim(tmp_path: Path) -> None:
    builder = _load_builder()
    output_dir = tmp_path / "_site"

    builder.build_pages(PROJECT_ROOT, output_dir)

    privacy = (output_dir / "privacy" / "index.html").read_text(encoding="utf-8")
    assert "personenbezogenen Daten" in privacy
    assert "keine Telemetrie" in privacy
    assert "<strong>keine</strong>" in privacy
