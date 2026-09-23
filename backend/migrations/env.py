from alembic import context

from app import models  # noqa: F401
from app.config import Settings
from app.database import Base, create_db_engine

config = context.config


def include_object(obj, name, type_, reflected, compare_to):
    # Legacy notes are intentionally preserved; they are not owned by the new API.
    return not (type_ == "table" and name == "notes")


def run(connection):
    sqlite = connection.dialect.name == "sqlite"
    if sqlite:
        # SQLite batch migrations recreate referenced tables. Disable enforcement
        # on this migration connection only, then validate before committing.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        include_object=include_object,
        compare_type=True,
        transactional_ddl=True,
    )
    with context.begin_transaction():
        context.run_migrations()
        if sqlite and connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Migration would leave invalid foreign keys")
    if sqlite:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()


if context.is_offline_mode():
    engine = create_db_engine(Settings())
    context.configure(url=engine.url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
    engine.dispose()
elif config.attributes.get("connection") is not None:
    run(config.attributes["connection"])
else:
    engine = create_db_engine(Settings())
    with engine.connect() as connection:
        run(connection)
    engine.dispose()
