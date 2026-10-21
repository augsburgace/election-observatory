"""Scope quality decisions to the producer that supplied an invalid definition."""
from alembic import op
from sqlalchemy import Column, String, inspect

revision = "0003_scoped_quality"
down_revision = "0002_election_atlas"
branch_labels = None
depends_on = None


def upgrade():
    # 0002 creates tables from shared metadata on fresh installations.
    if "source_id" not in {c["name"] for c in inspect(op.get_bind()).get_columns("quality_validations")}:
        op.add_column("quality_validations", Column("source_id", String(), nullable=True))


def downgrade():
    raise RuntimeError("Restore a verified backup into a separate directory; evidence downgrades are destructive.")
