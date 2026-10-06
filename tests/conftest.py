import os
import sys

# Make the project root importable when running `pytest` from anywhere
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture(autouse=True)
def _reset_alert_limiter():
    """The hourly alert cap is shared state; start every test with a clean slate"""
    from monitoring.limiter import DEFAULT_LIMITER
    DEFAULT_LIMITER.reset()
    yield
    DEFAULT_LIMITER.reset()
