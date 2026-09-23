"""Local setup, migrations, fixtures and OpenAPI export."""

import argparse
import json
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR, Settings
from app.database import create_db_engine


def migrate(engine):
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def setup_env():
    path = BACKEND_DIR / ".env"
    if not path.exists():
        template = (BACKEND_DIR / ".env.example").read_text()
        with path.open("x") as file:
            file.write(template)
        print("Created backend/.env")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["setup", "migrate", "seed", "openapi"])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "setup":
        setup_env()
    settings = Settings()
    engine = create_db_engine(settings)
    try:
        if args.command in {"setup", "migrate"}:
            migrate(engine)
            print("Database migrations applied")
        elif args.command == "seed":
            from app.seed import seed_database

            with Session(engine) as db, db.begin():
                counts = seed_database(db)
            print(f"Demo data ready. Added records: {counts}")
        elif args.command == "openapi":
            from app.api import create_app

            app = create_app(settings)
            path = args.output or BACKEND_DIR / "openapi.json"
            path.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n")
            app.state.engine.dispose()
            print(f"OpenAPI schema written to {path}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
