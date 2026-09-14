import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.logging_config import setup_logging, get_logger


def test_setup_logging_runs():
    # Should not raise
    setup_logging()


def test_get_logger_returns_logger():
    logger = get_logger("test_unit")
    assert isinstance(logger, logging.Logger)


def test_get_logger_name():
    logger = get_logger("my_component")
    assert logger.name == "my_component"


def test_get_logger_different_names():
    a = get_logger("alpha")
    b = get_logger("beta")
    assert a.name != b.name
    assert isinstance(a, logging.Logger)
    assert isinstance(b, logging.Logger)
