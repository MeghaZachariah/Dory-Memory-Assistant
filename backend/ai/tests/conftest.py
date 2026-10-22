import os
import tempfile
from pathlib import Path

import pytest

# Keep the test call log out of the real logs folder.
os.environ.setdefault("DORY_LOG_PATH", str(Path(tempfile.gettempdir()) / "dory_test_calls.jsonl"))

from backend.ai import client  # noqa: E402
from backend.ai.db_interface import set_db  # noqa: E402
from backend.ai.fake_db import FakeDB  # noqa: E402
from backend.ai.tests.fake_model import FakeModel  # noqa: E402


@pytest.fixture
def fake_model():
    fm = FakeModel()
    client.set_backend(fm)
    yield fm
    client.set_backend(None)


@pytest.fixture
def db():
    d = FakeDB()
    set_db(d)
    yield d
    set_db(None)
