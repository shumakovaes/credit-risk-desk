import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from credit_risk_desk.api import app
from credit_risk_desk.ingest import demo_frames, load_dataset


@pytest.fixture(scope="session")
def pg():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    if not (make_url(url).database or "").endswith("_test"):
        pytest.fail("Use a dedicated database whose name ends with _test")
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
    engine = create_engine(url)
    with engine.connect() as conn:
        empty = conn.execute(text("SELECT count(*) FROM raw.dataset")).scalar_one() == 0
    if empty:
        load_dataset(engine, demo_frames(), "demo", {"seed": 42, "purpose": "tests"})
    yield engine
    engine.dispose()


@pytest.fixture
def client(pg, monkeypatch, tmp_path):
    monkeypatch.setattr("credit_risk_desk.api.get_engine", lambda: pg)
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    monkeypatch.setenv("RULES_PATH", str(Path("config/rules.json").resolve()))
    with TestClient(app) as c:
        yield c
