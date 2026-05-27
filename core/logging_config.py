"""Configuration des logs applicatifs."""

import logging
from logging.handlers import RotatingFileHandler

from app.core.paths import LOGS_DIR, ensure_project_dirs


def setup_logging(name: str = "psych_ia", level: int = logging.INFO) -> logging.Logger:
    ensure_project_dirs()
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    log_file = LOGS_DIR / f"{name}.log"
    fh = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger
