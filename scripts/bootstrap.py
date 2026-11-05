"""Idempotent Compose initialization; never replace an existing dataset."""
from alembic import command
from alembic.config import Config
import os
from pathlib import Path
from sqlalchemy import text
from credit_risk_desk.db import get_engine
from credit_risk_desk.ingest import demo_frames, load_dataset, download, read_berka

command.upgrade(Config("alembic.ini"), "head")
with get_engine().connect() as conn:
    existing = conn.execute(text("SELECT mode FROM raw.dataset WHERE id=1")).scalar_one_or_none()
mode = os.getenv("DATA_MODE", "demo")
if mode not in ("demo", "berka"):
    raise ValueError("DATA_MODE must be demo or berka")
if existing and existing != mode:
    raise ValueError("Database contains another mode; use a separate database/Compose project.")
if not existing:
    if mode == "demo":
        print(load_dataset(get_engine(), demo_frames(), mode, {"generator": "demo_frames-v1", "seed": 42}))
    else:
        download("data/raw/berka")
        frames, manifest = read_berka("data/raw/berka")
        print(load_dataset(get_engine(), frames, mode, manifest))
if mode == "berka" and not Path("artifacts/model.joblib").exists():
    from credit_risk_desk.ml import train
    report = train(get_engine(), "artifacts")
    print({"model_version": report["model_version"], "test": report["test"]})
