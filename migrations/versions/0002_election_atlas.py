"""Add nationwide results, geography versions, context, and quality decisions.

Revision ID: 0002_election_atlas
Revises: 0001_evidence_store
"""
from alembic import op
from observatory.atlas.models import ATLAS_TABLES
from observatory.db import Base, QualityValidation

revision = '0002_election_atlas'
down_revision = '0001_evidence_store'
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.create_all(bind=op.get_bind(), tables=[QualityValidation.__table__, *ATLAS_TABLES], checkfirst=True)


def downgrade():
    raise RuntimeError('Restore a verified backup into a separate directory; evidence downgrades are destructive.')
