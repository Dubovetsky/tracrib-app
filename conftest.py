from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest


_PYTEST_TEMP_ROOT = Path(__file__).resolve().parent / ".codex-pytest-runtime"
_PYTEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("TMP", str(_PYTEST_TEMP_ROOT))
os.environ.setdefault("TEMP", str(_PYTEST_TEMP_ROOT))


@pytest.fixture
def tmp_path() -> Path:
    path = _PYTEST_TEMP_ROOT / f"test-{os.getpid()}-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path
