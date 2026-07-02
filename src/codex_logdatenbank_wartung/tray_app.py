"""Direkter EXE-Einstieg für die Systemtray-App."""

from __future__ import annotations

import traceback
from datetime import datetime
from pathlib import Path


def main() -> int:
    try:
        from codex_logdatenbank_wartung.config import default_config_path
        from codex_logdatenbank_wartung.tray import run_tray

        return run_tray(default_config_path())
    except Exception:
        try:
            from codex_logdatenbank_wartung.config import local_root

            log_dir = local_root() / "logs"
        except Exception:
            log_dir = Path.home() / "AppData" / "Local" / "CareCenterForCodex" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        (log_dir / f"startup-error-{stamp}.txt").write_text(
            traceback.format_exc(),
            encoding="utf-8",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
