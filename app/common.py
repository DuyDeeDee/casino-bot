import logging
import sys
from logging.handlers import RotatingFileHandler

from app.config import config


def _configure_console_encoding() -> None:
    """Use UTF-8 on Windows consoles so Vietnamese bot names log correctly."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def setup_logging():
    """
    Configure console and file logging once per process.
    """
    root_logger = logging.getLogger()
    if getattr(root_logger, "_casino_logging_configured", False):
        return root_logger

    _configure_console_encoding()
    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    file_handler = RotatingFileHandler(
        config.storage.log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    discord_logger = logging.getLogger("discord")
    discord_logger.setLevel(logging.INFO)
    root_logger._casino_logging_configured = True  # type: ignore[attr-defined]
    return root_logger
