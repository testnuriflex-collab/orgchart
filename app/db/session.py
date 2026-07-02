from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateColumn

from app.config import project_root
from app.db.models import Base

SessionFactory = Callable[[], Session]


def create_session_factory(database_path: Path) -> sessionmaker[Session]:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{database_path}", future=True)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def initialize_database(session_factory: sessionmaker[Session]) -> None:
    engine = session_factory.kw["bind"]
    table_names = set(inspect(engine).get_table_names())
    config = _alembic_config(engine.url.render_as_string(hide_password=False))

    if table_names and "alembic_version" not in table_names:
        Base.metadata.create_all(engine)
        _repair_existing_schema(engine)
        command.stamp(config, "head")
        return

    command.upgrade(config, "head")


def _alembic_config(database_url: str) -> Config:
    root = project_root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "app" / "db" / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _repair_existing_schema(engine: object) -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                column_sql = str(CreateColumn(column).compile(dialect=engine.dialect))
                column_sql = _with_sqlite_add_column_default(column_sql, column.name)
                connection.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN {column_sql}'))


def _with_sqlite_add_column_default(column_sql: str, column_name: str) -> str:
    if " NOT NULL" not in column_sql or " DEFAULT " in column_sql:
        return column_sql
    if column_name in {"status"}:
        return column_sql.replace(" NOT NULL", " DEFAULT '재직' NOT NULL")
    if column_name in {"actor"}:
        return column_sql.replace(" NOT NULL", " DEFAULT 'local-user' NOT NULL")
    if column_name in {"display_order", "row_count"}:
        return column_sql.replace(" NOT NULL", " DEFAULT 0 NOT NULL")
    if column_name.endswith("_at"):
        return column_sql.replace(" NOT NULL", " DEFAULT CURRENT_TIMESTAMP NOT NULL")
    return column_sql
