import os
from functools import lru_cache

from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()


@lru_cache
def engine_for(url: str):
    return create_engine(url, pool_pre_ping=True)


def get_engine():
    return engine_for(os.getenv("DATABASE_URL", "postgresql+psycopg://creditdesk:creditdesk@localhost:5433/creditdesk"))
