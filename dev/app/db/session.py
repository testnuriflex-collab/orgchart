from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.util import CommandError
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

    try:
        command.upgrade(config, "head")
    except CommandError:
        # 이 빌드가 모르는 버전 도장이 찍힌 DB(다른 배포본이 생성). 사용자 PC의
        # ~/.org_chart_studio/hr.sqlite3 는 앱 재설치와 무관하게 남으므로 여기서
        # 죽으면 사용자는 영영 실행할 수 없다 — 원본을 백업한 뒤 데이터를 보존한
        # 채 현재 스키마로 재정렬하고 도장을 현재 버전으로 다시 찍는다.
        _backup_database_file(engine)
        Base.metadata.create_all(engine)
        _repair_existing_schema(engine)
        command.stamp(config, "head", purge=True)


def _backup_database_file(engine: object) -> None:
    database = getattr(engine.url, "database", None)
    if not database:
        return
    source = Path(database)
    if not source.exists():
        return
    backup = source.with_name(f"{source.stem}.backup-{datetime.now():%Y%m%d-%H%M%S}{source.suffix}")
    try:
        shutil.copy2(source, backup)
    except OSError:
        # 백업 실패(권한·디스크 부족 등)가 복구 자체를 막아서는 안 된다.
        pass


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
