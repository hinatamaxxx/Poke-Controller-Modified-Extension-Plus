"""Application logging using only the Python standard library. MIT."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import os
import Paths


def root_logger():
    logger = logging.getLogger()
    if getattr(logger, '_poke_configured', False):
        return logger
    Path(Paths.LOGS).mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(os.path.join(Paths.LOGS, f'controller-{os.getpid()}.log'),
                                  maxBytes=4 * 1024 * 1024, backupCount=2, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger._poke_configured = True
    return logger
