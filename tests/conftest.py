import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ULTRON_DATA_DIR"] = tempfile.mkdtemp(prefix="ultron-test-")

import pytest


@pytest.fixture
def sandbox(tmp_path):
    docs = tmp_path / "Documents"
    downloads = tmp_path / "Downloads"
    outside = tmp_path / "Outside"
    for d in (docs, downloads, outside):
        d.mkdir()
    return tmp_path


@pytest.fixture
def db(sandbox):
    from memory.database import Database
    database = Database(sandbox / "test.db")
    database.set("allowed_roots", [str(sandbox / "Documents"), str(sandbox / "Downloads")])
    return database
