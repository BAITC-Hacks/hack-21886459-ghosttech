"""Optional public contact for team profiles; preserve existing teams."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("teams", sa.Column("contact", sa.String(500), nullable=False, server_default=""))


def downgrade():
    op.drop_column("teams", "contact")
