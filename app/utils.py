from __future__ import annotations
import logging
import os
import shutil
from datetime import datetime
from typing import Optional


def setup_logger(name: str, log_dir: str = "logs", level: int = logging.DEBUG) -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fh = logging.FileHandler(os.path.join(log_dir, f"{name}_{timestamp}.log"))
        fh.setLevel(logging.DEBUG)
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)

        formatter = logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        logger.addHandler(fh)
        logger.addHandler(ch)

    return logger


def move_to_failed(src_path: str, failed_dir: str, reason: str, logger: logging.Logger) -> None:
    os.makedirs(failed_dir, exist_ok=True)
    basename = os.path.basename(src_path)
    dest = os.path.join(failed_dir, basename)

    counter = 1
    while os.path.exists(dest):
        name, ext = os.path.splitext(basename)
        dest = os.path.join(failed_dir, f"{name}_{counter}{ext}")
        counter += 1

    try:
        shutil.move(src_path, dest)
        logger.error(f"Moved failed file to {dest}: {reason}")
    except Exception as e:
        logger.error(f"Failed to move file {src_path}: {e}")


def sanitize_filename(filename: str) -> str:
    return "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in filename).strip()


def move_to_parsed(src_path: str, parsed_dir: str, logger: logging.Logger) -> None:
    """Move a successfully parsed PDF into the parsed directory, avoiding name collisions.

    Preserves the original filename; if a file with the same name exists in parsed_dir,
    appends an incrementing suffix.
    """
    os.makedirs(parsed_dir, exist_ok=True)
    basename = os.path.basename(src_path)
    dest = os.path.join(parsed_dir, basename)

    counter = 1
    name, ext = os.path.splitext(basename)
    while os.path.exists(dest):
        dest = os.path.join(parsed_dir, f"{name}_{counter}{ext}")
        counter += 1

    try:
        shutil.move(src_path, dest)
        logger.info(f"Moved parsed file to {dest}")
    except Exception as e:
        logger.error(f"Failed to move parsed file {src_path} to {dest}: {e}")
