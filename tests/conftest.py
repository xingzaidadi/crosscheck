"""Shared pytest fixtures for the legacy function-style regression modules."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core.workspace import set_workspace


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_WORKSPACE = ROOT / "tests" / "fixtures" / "workspace"


@pytest.fixture(autouse=True)
def isolated_workspace():
    """Make pytest runs independent from a developer's VTA_WORKSPACE."""
    set_workspace(FIXTURE_WORKSPACE)
    yield


@pytest.fixture
def db(request):
    """Build the SQLite fixture expected by reconcile/sentinel pytest tests."""
    setup = getattr(request.module, "setup_db", None) or getattr(request.module, "setup", None)
    if setup is None:
        pytest.fail(f"{request.module.__name__} declares db but no setup helper")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        path = str(Path(directory) / "pytest.db")
        database = setup(path)
        try:
            yield database
        finally:
            close = getattr(database, "close", None)
            if close:
                close()
