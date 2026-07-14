"""Tests for the windowed tray entrypoint."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from codex_logdatenbank_wartung import tray_app


def test_tray_app_starts_runtime_logging_before_run_tray() -> None:
    config_path = Path("C:/tmp/carecenter-config.json")

    with patch(
        "codex_logdatenbank_wartung.runtime.app_logging.start"
    ) as start_logging, patch(
        "codex_logdatenbank_wartung.config.default_config_path",
        return_value=config_path,
    ), patch(
        "codex_logdatenbank_wartung.tray.run_tray",
        return_value=0,
    ) as run_tray:
        rc = tray_app.main()

    assert rc == 0
    start_logging.assert_called_once_with()
    run_tray.assert_called_once_with(config_path)
