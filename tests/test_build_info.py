from __future__ import annotations

import json

from codex_logdatenbank_wartung.build_info import BuildInfo, describe_build, load_build_info


def test_load_build_info_reads_complete_metadata(tmp_path) -> None:
    metadata = tmp_path / "carecenter_build_provenance.json"
    metadata.write_text(
        json.dumps(
            {
                "version": "0.8.0",
                "commit": "abc123",
                "build_utc": "2026-07-28T08:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    info = load_build_info([metadata])

    assert info.version == "0.8.0"
    assert info.commit == "abc123"
    assert info.build_utc == "2026-07-28T08:00:00Z"


def test_describe_build_is_compact_and_datapoor() -> None:
    info = BuildInfo(
        version="0.8.0",
        commit="abc123",
        build_utc="2026-07-28T08:00:00Z",
        source="test",
    )

    assert describe_build(info) == (
        "CareCenter build: version=0.8.0 commit=abc123 build_utc=2026-07-28T08:00:00Z"
    )
