"""Alembic environment — reuses the app's engine + metadata.

The app engine (app.database) already resolves the Cloud SQL unix-socket for
pg8000 and the sqlite dev path, so migrations connect exactly like the app does.
Importing app.models registers every table on Base.metadata for autogenerate.
"""
from logging.config import fileConfig

from alembic import context

from app.database import Base, engine
import app.models  # noqa: F401  — registers all ORM tables on Base.metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
