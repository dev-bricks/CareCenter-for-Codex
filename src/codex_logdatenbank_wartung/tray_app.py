"""Direkter EXE-Einstieg für die Systemtray-App."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import traceback


def main() -> int:
    try:
        from codex_logdatenbank_wartung.config import DEFAULT_CONFIG_PATH
        from codex_logdatenbank_wartung.tray import run_tray

        return run_tray(DEFAULT_CONFIG_PATH)
    except Exception:
        log_dir = Path(r"C:\_Local_DEV\codex-maintenance\logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        (log_dir / f"startup-error-{stamp}.txt").write_text(
            traceback.format_exc(),
            encoding="utf-8",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
