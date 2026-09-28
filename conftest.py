"""Pytest bootstrap for the HEEH-V1 verification suite.

``pyproject.toml`` configures ``--basetemp=cache_logs/pytest_tmp`` so test
temporaries stay inside the project. pytest creates the basetemp directory
without creating its *parents*, so on a freshly extracted release package
(where ``cache_logs/`` does not exist yet) every ``tmp_path`` test failed at
setup with FileNotFoundError. This hook creates the parent directory
deterministically before any fixture runs, making the first test run from a
fresh extraction pass without a preliminary re-run.
"""

from pathlib import Path


def pytest_configure(config):
    base = getattr(config.option, "basetemp", None)
    if base:
        Path(base).parent.mkdir(parents=True, exist_ok=True)
