"""Initial immutable evidence and personal research schema.

Revision ID: 0001_evidence_store
"""
from alembic import op
from observatory.db import Base

revision = '0001_evidence_store'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # checkfirst supports databases created by the first local research release.
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('Evidence-store downgrade is destructive. Restore a verified backup into a new directory instead.')
