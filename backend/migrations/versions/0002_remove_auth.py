"""Remove accounts and ownership while preserving tasks, teams and proposals."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    naming = {
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
    }
    with op.batch_alter_table("tasks", naming_convention=naming) as batch:
        batch.drop_constraint("fk_tasks_owner_id_users", type_="foreignkey")
        batch.drop_index("ix_tasks_owner_id")
        batch.drop_column("owner_id")
    with op.batch_alter_table("teams", naming_convention=naming) as batch:
        batch.drop_constraint("fk_teams_owner_id_users", type_="foreignkey")
        batch.drop_constraint("uq_teams_owner_id", type_="unique")
        batch.drop_column("owner_id")
    op.drop_table("users")


def downgrade():
    raise RuntimeError("Account ownership cannot be recovered; restore a database backup instead")
