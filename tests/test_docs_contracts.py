"""Static contracts for the offline runtime and release-gate documentation."""

from __future__ import annotations

import re
from pathlib import Path

from codex_logdatenbank_wartung.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_DOCS = (
    ROOT / "README.md",
    ROOT / "README.de.md",
    ROOT / "SECURITY.md",
    ROOT / "PRIVACY_POLICY.md",
    ROOT / "SUPPORT.md",
    ROOT / "docs" / "privacy.md",
    ROOT / "docs" / "support.md",
    ROOT / "llms.txt",
    ROOT / "CHANGELOG.md",
)
LOCAL_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)\s]+)(?:\s+['\"][^)]*)?\)")


def test_active_docs_describe_runtime_boundary_and_manual_release_gate() -> None:
    for path in ACTIVE_DOCS:
        content = path.read_text(encoding="utf-8")
        assert "store-materials --live-pages" in content, path
        assert any(
            marker in content
            for marker in (
                "local-only",
                "normal runtime",
                "normale CareCenter-Laufzeit",
                "normalen CareCenter-Laufzeit",
                "normalen Betrieb",
                "normale Laufzeit",
            )
        ), path


def test_live_pages_is_explicitly_labelled_as_a_non_runtime_gate() -> None:
    parser = build_parser()
    subparsers = next(action for action in parser._actions if action.dest == "help")
    assert subparsers is not None

    command_action = next(action for action in parser._actions if action.dest == "command")
    store_parser = command_action.choices["store-materials"]
    live_pages = next(action for action in store_parser._actions if action.dest == "live_pages")

    assert live_pages.default is False
    assert "Release-Gate" in live_pages.help
    assert "nicht Teil der Laufzeit" in live_pages.help


def test_active_relative_markdown_links_resolve_to_tracked_or_present_files() -> None:
    for path in ACTIVE_DOCS:
        for match in LOCAL_LINK.finditer(path.read_text(encoding="utf-8")):
            target = match.group(1)
            if "://" in target or target.startswith(("mailto:", "#")):
                continue
            target = target.split("#", 1)[0]
            if not target:
                continue
            assert (path.parent / target).exists(), f"{path}: missing link target {target}"


def test_removed_control_references_are_not_active_support_references() -> None:
    support = (ROOT / "SUPPORT.md").read_text(encoding="utf-8")
    health = (ROOT / "src" / "codex_logdatenbank_wartung" / "health.py").read_text(
        encoding="utf-8"
    )

    for stale_name in ("PORTIERUNGSPLAN.md", "TODO.md", "STATE.md", "DECISIONS.md"):
        assert stale_name not in support
    assert "DECISIONS.md" not in health
    assert (ROOT / "THIRD_PARTY_LICENSES.txt").is_file()
