"""Append-only validation for changed source contest configurations."""
from alembic import op
from observatory.atlas.models import AtlasResultValidation

revision = "0004_result_validation"
down_revision = "0003_scoped_quality"
branch_labels = None
depends_on = None


def upgrade():
    AtlasResultValidation.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError("Restore a verified backup into a separate directory; evidence downgrades are destructive.")
