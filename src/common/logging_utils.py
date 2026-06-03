# -*- coding: utf-8 -*-
"""
src/common/logging_utils.py
Central logging setup for the reconciliation pipeline.
"""
import logging
import os
import sys
from typing import Optional

def setup_logging(name: str = "pipeline", log_file: Optional[str] = None) -> logging.Logger:
    """
    Initializes a standard logging configuration with streams to stdout and an optional file.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Avoid adding duplicate handlers if setup_logging is called multiple times
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Optional File handler
    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
