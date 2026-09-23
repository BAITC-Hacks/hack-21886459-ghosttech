"""Track daily assistant requests per authenticated business account."""

import sqlalchemy as sa
from alembic import op

revision = "0005_auth_usage"
down_revision = "0004_auth"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_usage",
        sa.Column(
            "participant_id", sa.String(32), sa.ForeignKey("participants.id"), primary_key=True
        ),
        sa.Column("day", sa.String(10), primary_key=True),
        sa.Column("requests", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("requests >= 0", name="ck_ai_usage_requests"),
    )


def downgrade():
    op.drop_table("ai_usage")
