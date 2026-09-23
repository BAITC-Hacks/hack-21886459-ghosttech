"""Add account identities and revocable, hashed browser sessions."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "participant_id", sa.String(32), sa.ForeignKey("participants.id"), nullable=False
        ),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_accounts_participant_id", "accounts", ["participant_id"], unique=True)
    op.create_index("ix_accounts_email", "accounts", ["email"], unique=True)
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(32), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_sessions_account_id", "auth_sessions", ["account_id"])


def downgrade():
    op.drop_index("ix_auth_sessions_account_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_accounts_email", table_name="accounts")
    op.drop_index("ix_accounts_participant_id", table_name="accounts")
    op.drop_table("accounts")
