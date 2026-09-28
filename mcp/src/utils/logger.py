import logging
import sys

_fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s — %(message)s", "%H:%M:%S")
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(_fmt)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.addHandler(_handler)
    logger.setLevel(logging.DEBUG)
    return logger
