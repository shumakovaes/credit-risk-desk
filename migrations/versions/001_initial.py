"""Raw import manifest, clean entities and one shared SQL feature function."""
from pathlib import Path
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    sql = (Path(__file__).parents[1] / "schema.sql").read_text(encoding="utf-8")
    # psycopg supports multi-statements here without bound parameters.
    op.get_bind().exec_driver_sql(sql)


def downgrade():
    for schema in ("analytics", "clean", "raw"):
        op.execute(f"DROP SCHEMA {schema} CASCADE")
