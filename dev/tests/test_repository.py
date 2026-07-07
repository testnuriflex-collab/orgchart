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


def test_initialize_database_recovers_database_stamped_by_unknown_release(tmp_path) -> None:
    # 시나리오: 다른(구/신) 배포본이 만든 hr.sqlite3에 이 빌드가 모르는 버전 도장
    # (예: 20260706_0004)이 찍혀 있음 — 실제 고객 PC에서 기동 크래시로 재현된 사례.
    database_path = tmp_path / "hr.sqlite3"
    session_factory = create_session_factory(database_path)
    initialize_database(session_factory)

    with session_factory() as session:
        HrRepository(session).create_or_update_employee(
            EmployeeInput(employee_no="A001", name="홍길동", department="인사팀")
        )
        session.commit()

    engine = session_factory.kw["bind"]
    with engine.begin() as connection:
        connection.execute(text("update alembic_version set version_num = '20260706_0004'"))

    initialize_database(session_factory)

    with engine.connect() as connection:
        version = connection.execute(text("select version_num from alembic_version")).scalar_one()
    assert version == "20260605_0001"

    with session_factory() as session:
        employees = HrRepository(session).list_employees()
        assert [(employee.employee_no, employee.name) for employee in employees] == [("A001", "홍길동")]

    assert list(tmp_path.glob("hr.backup-*.sqlite3")), "복구 전 원본 DB 백업 파일이 있어야 함"


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
