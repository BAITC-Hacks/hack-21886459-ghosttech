"""Public participants and optional task authors; preserve existing platform records."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "teams", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.create_table(
        "participants",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("organization", sa.String(150), nullable=False),
        sa.Column("bio", sa.Text(), nullable=False),
        sa.Column("interests", sa.JSON(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("team_id", sa.String(32), sa.ForeignKey("teams.id")),
        sa.CheckConstraint("role IN ('business', 'student')", name="ck_participant_role"),
    )
    op.create_index("ix_participants_team_id", "participants", ["team_id"])
    # Existing tasks keep their content and have no author until one is explicitly assigned.
    op.add_column("tasks", sa.Column("owner_id", sa.String(32)))
    op.add_column(
        "tasks", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("tasks", sa.Column("work_tags", sa.JSON(), nullable=False, server_default="[]"))
    with op.batch_alter_table("tasks") as batch:
        batch.create_foreign_key(
            "fk_tasks_owner_id_participants", "participants", ["owner_id"], ["id"]
        )
        batch.create_index("ix_tasks_owner_id", ["owner_id"])


def downgrade():
    with op.batch_alter_table("tasks") as batch:
        batch.drop_index("ix_tasks_owner_id")
        batch.drop_constraint("fk_tasks_owner_id_participants", type_="foreignkey")
        batch.drop_column("owner_id")
        batch.drop_column("is_demo")
        batch.drop_column("work_tags")
    op.drop_index("ix_participants_team_id", table_name="participants")
    op.drop_table("participants")
    op.drop_column("teams", "is_demo")
