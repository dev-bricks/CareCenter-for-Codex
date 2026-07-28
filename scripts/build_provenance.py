"""Erzeuge und prüfe CareCenter-Buildmetadaten ohne Drittanbieter-Abhängigkeiten."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tomllib
from datetime import UTC, datetime
from pathlib import Path

METADATA_FILENAME = "carecenter_build_provenance.json"
VERSION_FILENAME = "carecenter_version_info.txt"


def _git(project_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(project_root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    return result.stdout.strip()


def _project_version(project_root: Path) -> str:
    data = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _version_tuple(project_version: str) -> tuple[int, int, int, int]:
    values: list[int] = []
    for part in project_version.split(".", 3):
        digits = "".join(char for char in part if char.isdigit())
        values.append(int(digits or "0"))
    return tuple((values + [0, 0, 0, 0])[:4])  # type: ignore[return-value]


def version_file_content(project_version: str, commit: str, build_utc: str) -> str:
    numeric = _version_tuple(project_version)
    short_commit = commit[:12]
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numeric},
    prodvers={numeric},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'Lukas Geiger'),
          StringStruct('FileDescription', 'CareCenter for Codex'),
          StringStruct('FileVersion', '{project_version}'),
          StringStruct('InternalName', 'CareCenterForCodex'),
          StringStruct('OriginalFilename', 'CareCenterForCodex.exe'),
          StringStruct('ProductName', 'CareCenter for Codex'),
          StringStruct('ProductVersion', '{project_version}'),
          StringStruct('Comments', 'Commit {short_commit}; built {build_utc}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def prepare(project_root: Path, output_dir: Path) -> Path:
    tracked_status = _git(project_root, "status", "--porcelain", "--untracked-files=no")
    if tracked_status:
        raise RuntimeError(
            "Build verweigert: getrackter Source-Stand ist nicht sauber. Erst committen und erneut bauen."
        )
    commit = _git(project_root, "rev-parse", "HEAD")
    project_version = _project_version(project_root)
    build_utc = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = output_dir / METADATA_FILENAME
    metadata_path.write_text(
        json.dumps(
            {
                "schema": 1,
                "project": "CareCenter for Codex",
                "version": project_version,
                "commit": commit,
                "build_utc": build_utc,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / VERSION_FILENAME).write_text(
        version_file_content(project_version, commit, build_utc),
        encoding="utf-8",
    )
    return metadata_path


def finalize(metadata_path: Path, exe_path: Path) -> Path:
    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not exe_path.is_file():
        raise FileNotFoundError(f"EXE fehlt: {exe_path}")
    digest = hashlib.sha256(exe_path.read_bytes()).hexdigest().upper()
    sidecar = exe_path.with_suffix(".provenance.json")
    sidecar.write_text(
        json.dumps(
            {
                **data,
                "artifact": exe_path.name,
                "artifact_bytes": exe_path.stat().st_size,
                "sha256": digest,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return sidecar


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--project-root", type=Path, required=True)
    prepare_parser.add_argument("--output-dir", type=Path, required=True)
    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--metadata", type=Path, required=True)
    finalize_parser.add_argument("--exe", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "prepare":
        print(prepare(args.project_root.resolve(), args.output_dir.resolve()))
        return 0
    print(finalize(args.metadata.resolve(), args.exe.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
