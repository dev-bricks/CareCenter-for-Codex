"""Build-Provenienz für Source-Runs und gebündelte CareCenter-EXEs."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

BUILD_METADATA_FILENAME = "carecenter_build_provenance.json"


@dataclass(frozen=True)
class BuildInfo:
    version: str
    commit: str
    build_utc: str
    source: str


def _default_candidates() -> list[Path]:
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.append(Path(meipass) / BUILD_METADATA_FILENAME)
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).with_suffix(".provenance.json"))
    return candidates


def _source_version() -> str:
    try:
        return version("carecenter-for-codex")
    except PackageNotFoundError:
        return "source"


def load_build_info(candidates: Iterable[Path] | None = None) -> BuildInfo:
    """Lade datensparsame Buildidentität; kaputte Sidecars bleiben fail-closed."""
    for candidate in candidates if candidates is not None else _default_candidates():
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        build_version = str(data.get("version") or "").strip()
        commit = str(data.get("commit") or "").strip()
        build_utc = str(data.get("build_utc") or "").strip()
        if build_version and commit and build_utc:
            return BuildInfo(
                version=build_version,
                commit=commit,
                build_utc=build_utc,
                source=str(candidate),
            )
    return BuildInfo(
        version=_source_version(),
        commit="source",
        build_utc="not-packaged",
        source="source-run",
    )


def describe_build(info: BuildInfo | None = None) -> str:
    current = info or load_build_info()
    return (
        f"CareCenter build: version={current.version} "
        f"commit={current.commit} build_utc={current.build_utc}"
    )
