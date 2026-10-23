

"""Module for setting up and configuring the logger."""
import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler


def setup_logger() -> logging.Logger:
    """Configures logging level and format from command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Exhibitions CSV Data Validator")

    parser.add_argument(
        "-w", "--warning",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level (default: INFO)"
    )

    parser.add_argument(
        "-d", "--disable",
        action="store_true",
        help="Disable all terminal output, but still log to file."
    )

    args, _ = parser.parse_known_args()
    logger = logging.getLogger(__name__)

    handlers = [RotatingFileHandler(
        "pipeline.log",
        maxBytes=1_000_000
    )]

    if not args.disable:
        handlers.append(logging.StreamHandler(sys.stdout))

    warning_val = args.warning or "INFO"
    log_level = getattr(logging, warning_val.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%d-%m-%Y %H:%M:%S",
        handlers=handlers
    )

    return logger
