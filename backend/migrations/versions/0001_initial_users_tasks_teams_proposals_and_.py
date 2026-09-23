"""initial users tasks teams proposals and progress schema

Revision ID: 0001
Revises: none
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('business', 'team')", name="ck_user_role"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("topic", sa.String(length=100), nullable=False),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("need", sa.Text(), nullable=False),
        sa.Column("users", sa.Text(), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("constraints", sa.Text(), nullable=False),
        sa.Column("expected_result", sa.Text(), nullable=False),
        sa.Column("success_criteria", sa.Text(), nullable=False),
        sa.Column("contact", sa.String(length=500), nullable=False),
        sa.Column("interaction_format", sa.Text(), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "level IN ('draft', 'working', 'ready', 'priority')", name="ck_task_level"
        ),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name="ck_task_score"),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.create_index(
            "ix_tasks_catalog", ["confirmed", "topic", "level", "score"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_tasks_owner_id"), ["owner_id"], unique=False)

    op.create_table(
        "teams",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("interests", sa.JSON(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("tech", sa.JSON(), nullable=False),
        sa.Column("base_points", sa.Integer(), nullable=False),
        sa.CheckConstraint("base_points >= 0", name="ck_team_points"),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", name="uq_teams_owner_id"),
    )
    op.create_table(
        "proposals",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("task_id", sa.String(length=32), nullable=False),
        sa.Column("team_id", sa.String(length=32), nullable=False),
        sa.Column("idea", sa.Text(), nullable=False),
        sa.Column("plan", sa.Text(), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=False),
        sa.Column("prototype_url", sa.String(length=2048), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected')", name="ck_proposal_status"
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "team_id", name="uq_task_team"),
    )
    with op.batch_alter_table("proposals", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_proposals_task_id"), ["task_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_proposals_team_id"), ["team_id"], unique=False)

    op.create_table(
        "progress",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("proposal_id", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=16), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(stage = 'prototype' AND points = 10) OR "
            "(stage = 'testing' AND points = 20) OR "
            "(stage = 'final' AND points = 30)",
            name="ck_stage_points",
        ),
        sa.CheckConstraint("stage IN ('prototype', 'testing', 'final')", name="ck_progress_stage"),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["proposals.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("proposal_id", "stage", name="uq_proposal_stage"),
    )
    with op.batch_alter_table("progress", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_progress_proposal_id"), ["proposal_id"], unique=False)


def downgrade():
    with op.batch_alter_table("progress", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_progress_proposal_id"))

    op.drop_table("progress")
    with op.batch_alter_table("proposals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_proposals_team_id"))
        batch_op.drop_index(batch_op.f("ix_proposals_task_id"))

    op.drop_table("proposals")
    op.drop_table("teams")
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tasks_owner_id"))
        batch_op.drop_index("ix_tasks_catalog")

    op.drop_table("tasks")
    op.drop_table("users")
