import logging
import sys


def setup_logger(name: str = "snipbot", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
                          datefmt="%H:%M:%S")
    )
    logger.addHandler(handler)
    return logger
