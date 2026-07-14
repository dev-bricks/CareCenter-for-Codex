"""Standard-Logger fuer fensterlose Tray-Starts."""

from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
from pathlib import Path

from ..config import DEFAULT_DATA_DIR_NAME, local_root

DEFAULT_MAX_BYTES = 2 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 3
LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def log_dir(app_slug: str = DEFAULT_DATA_DIR_NAME) -> Path:
    """Lege Logs ausserhalb des Projektordners und ausserhalb von OneDrive ab."""
    _ = app_slug
    return local_root() / "logs"


def log_file(app_slug: str = DEFAULT_DATA_DIR_NAME) -> Path:
    return log_dir(app_slug) / "app.log"


def _has_console() -> bool:
    stream = sys.stderr
    return stream is not None and hasattr(stream, "write")


def setup_logging(
    level: int = logging.INFO,
    app_slug: str = DEFAULT_DATA_DIR_NAME,
    console: bool | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> Path:
    """Richte den fensterlosen Start-Logger idempotent ein."""
    target = log_file(app_slug)
    target.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    for handler in root.handlers:
        if getattr(handler, "_app_logging", False):
            return target

    formatter = logging.Formatter(LOG_FORMAT)

    file_handler = logging.handlers.RotatingFileHandler(
        target,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler._app_logging = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)

    use_console = _has_console() if console is None else console
    if use_console and _has_console():
        try:
            sys.stderr.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler._app_logging = True  # type: ignore[attr-defined]
        root.addHandler(stream_handler)

    return target


def install_crash_handler(app_slug: str = DEFAULT_DATA_DIR_NAME) -> None:
    """Leite unbehandelte Ausnahmen in die Logdatei um."""
    logger = logging.getLogger(app_slug)

    def _hook(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical(
            "Unbehandelte Ausnahme - die App bricht ab.",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    sys.excepthook = _hook

    def _thread_hook(args: threading.ExceptHookArgs) -> None:
        if issubclass(args.exc_type, KeyboardInterrupt):
            return
        logger.critical(
            "Unbehandelte Ausnahme in Thread %r.",
            args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = _thread_hook


def start(level: int = logging.INFO, app_slug: str = DEFAULT_DATA_DIR_NAME) -> Path:
    """Aktiviere Startup-Logging und Crash-Hooks fuer fensterlose Starts."""
    target = setup_logging(level=level, app_slug=app_slug)
    install_crash_handler(app_slug=app_slug)
    logging.getLogger(app_slug).info("Start. Log: %s", target)
    return target
