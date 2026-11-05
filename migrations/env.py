from alembic import context
from credit_risk_desk.db import get_engine

with get_engine().connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
