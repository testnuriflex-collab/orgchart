from app.db.repository import HrRepository
from app.db.session import create_session_factory, initialize_database
from app.domain.hr import EmploymentStatus, EmployeeInput, ImportAction, ImportPreview, ImportRowResult
from sqlalchemy import create_engine, inspect, text


def test_move_employee_and_rename_org(tmp_path) -> None:
    session_factory = create_session_factory(tmp_path / "hr.sqlite3")
    initialize_database(session_factory)

    with session_factory() as session:
        repository = HrRepository(session)
        employee = repository.create_or_update_employee(
            EmployeeInput(employee_no="A001", name="홍길동", department="인사팀")
        )
        new_org = repository.ensure_org_unit("재무팀")
        repository.move_employee(employee.id, new_org.id)
        repository.rename_org_unit(new_org.id, "Finance")
        session.commit()

    with session_factory() as session:
        repository = HrRepository(session)
        assignments = repository.list_active_assignments()
        assert assignments[0].org_unit.name == "Finance"


def test_conflict_import_rows_are_not_applied(tmp_path) -> None:
    session_factory = create_session_factory(tmp_path / "hr.sqlite3")
    initialize_database(session_factory)

    with session_factory() as session:
        repository = HrRepository(session)
        repository.create_or_update_employee(EmployeeInput(employee_no="A001", name="홍길동", department="인사팀"))
        preview = ImportPreview(
            rows=[
                ImportRowResult(
                    action=ImportAction.CONFLICT,
                    row_number=2,
                    employee=EmployeeInput(employee_no="A002", name="홍길동", department="재무팀"),
                    reason="동명이인이 있어 자동 병합하지 않음",
                )
            ],
            missing_existing_employee_ids=[],
        )
        repository.apply_import_preview(preview)
        session.commit()

    with session_factory() as session:
        employees = HrRepository(session).list_employees()
        assert [(employee.employee_no, employee.name) for employee in employees] == [("A001", "홍길동")]


def test_missing_import_rows_require_explicit_exit_candidate_approval(tmp_path) -> None:
    session_factory = create_session_factory(tmp_path / "hr.sqlite3")
    initialize_database(session_factory)

    with session_factory() as session:
        repository = HrRepository(session)
        employee = repository.create_or_update_employee(
            EmployeeInput(employee_no="A001", name="홍길동", department="인사팀")
        )
        preview = ImportPreview(rows=[], missing_existing_employee_ids=[employee.id])
        repository.apply_import_preview(preview)
        session.commit()

    with session_factory() as session:
        employee = HrRepository(session).list_employees()[0]
        assert employee.status == EmploymentStatus.ACTIVE.value

    with session_factory() as session:
        repository = HrRepository(session)
        employee = repository.list_employees()[0]
        preview = ImportPreview(rows=[], missing_existing_employee_ids=[employee.id])
        repository.apply_import_preview(preview, {employee.id})
        session.commit()

    with session_factory() as session:
        employee = HrRepository(session).list_employees()[0]
        assert employee.status == EmploymentStatus.EXIT_CANDIDATE.value


def test_initialize_database_stamps_existing_unversioned_database(tmp_path) -> None:
    database_path = tmp_path / "legacy.sqlite3"
    engine = create_engine(f"sqlite:///{database_path}", future=True)
    with engine.begin() as connection:
        connection.execute(text("create table employees (id varchar(36) primary key, name varchar(160) not null)"))

    session_factory = create_session_factory(database_path)
    initialize_database(session_factory)

    tables = set(inspect(session_factory.kw["bind"]).get_table_names())
    columns = {column["name"] for column in inspect(session_factory.kw["bind"]).get_columns("employees")}
    assert "alembic_version" in tables
    assert {"employee_no", "email", "status", "created_at", "updated_at"}.issubset(columns)
