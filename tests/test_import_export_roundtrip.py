from pathlib import Path

import pandas as pd

from app.db.repository import HrRepository
from app.db.session import create_session_factory, initialize_database
from app.domain.hr import EmployeeInput, EmploymentStatus, ImportAction
from app.exporter.excel_exporter import export_database_to_excel
from app.importer.excel_importer import ExcelImporter
from app.importer.sample_files import SAMPLE_ROWS, write_sample_input_files


def test_import_export_round_trip(tmp_path: Path) -> None:
    database = tmp_path / "hr.sqlite3"
    session_factory = create_session_factory(database)
    initialize_database(session_factory)

    source = tmp_path / "source.xlsx"
    pd.DataFrame(
        [
            {
                "사번": "A001",
                "이름": "홍길동",
                "이메일": "hong@example.com",
                "부서": "인사팀",
                "상위부서": "경영지원본부",
                "직급": "매니저",
                "직책": "팀원",
                "재직상태": "재직",
            }
        ]
    ).to_excel(source, index=False)

    with session_factory() as session:
        preview = ExcelImporter(session).preview(source)
        assert preview.counts["추가"] == 1
        HrRepository(session).apply_import_preview(preview)
        session.commit()

    exported = tmp_path / "exported.xlsx"
    with session_factory() as session:
        export_database_to_excel(session, exported)

    exported_frame = pd.read_excel(exported, sheet_name="인사DB", dtype=str)
    assert exported_frame.loc[0, "이름"] == "홍길동"
    assert exported_frame.loc[0, "부서"] == "인사팀"


def test_import_preview_detects_and_applies_department_only_change(tmp_path: Path) -> None:
    session_factory = create_session_factory(tmp_path / "hr.sqlite3")
    initialize_database(session_factory)

    with session_factory() as session:
        HrRepository(session).create_or_update_employee(
            EmployeeInput(employee_no="A001", name="홍길동", department="인사팀")
        )
        session.commit()

    source = tmp_path / "department_change.xlsx"
    pd.DataFrame([{"사번": "A001", "이름": "홍길동", "부서": "재무팀", "재직상태": "재직"}]).to_excel(
        source, index=False
    )

    with session_factory() as session:
        preview = ExcelImporter(session).preview(source)
        assert preview.rows[0].action == ImportAction.UPDATE
        assert preview.rows[0].changes["department"] == ("인사팀", "재무팀")
        HrRepository(session).apply_import_preview(preview)
        session.commit()

    with session_factory() as session:
        assignment = HrRepository(session).list_active_assignments()[0]
        assert assignment.org_unit.name == "재무팀"


def test_import_blank_email_clears_existing_email(tmp_path: Path) -> None:
    session_factory = create_session_factory(tmp_path / "hr.sqlite3")
    initialize_database(session_factory)

    with session_factory() as session:
        HrRepository(session).create_or_update_employee(
            EmployeeInput(
                employee_no="A001",
                name="홍길동",
                email="hong@example.com",
                department="인사팀",
            )
        )
        session.commit()

    source = tmp_path / "blank_email.xlsx"
    pd.DataFrame([{"사번": "A001", "이름": "홍길동", "이메일": "", "부서": "인사팀"}]).to_excel(
        source, index=False
    )

    with session_factory() as session:
        preview = ExcelImporter(session).preview(source)
        assert preview.rows[0].action == ImportAction.UPDATE
        assert preview.rows[0].changes["email"] == ("hong@example.com", None)
        HrRepository(session).apply_import_preview(preview)
        session.commit()

    with session_factory() as session:
        employee = HrRepository(session).list_employees()[0]
        assert employee.email is None


def test_import_preview_detects_and_applies_status_only_change(tmp_path: Path) -> None:
    session_factory = create_session_factory(tmp_path / "hr.sqlite3")
    initialize_database(session_factory)

    with session_factory() as session:
        HrRepository(session).create_or_update_employee(
            EmployeeInput(employee_no="A001", name="홍길동", department="인사팀", status="재직")
        )
        session.commit()

    source = tmp_path / "status_change.xlsx"
    pd.DataFrame([{"사번": "A001", "이름": "홍길동", "부서": "인사팀", "재직상태": "퇴사"}]).to_excel(
        source, index=False
    )

    with session_factory() as session:
        preview = ExcelImporter(session).preview(source)
        assert preview.rows[0].action == ImportAction.UPDATE
        assert preview.rows[0].changes["status"] == ("재직", "퇴사")
        HrRepository(session).apply_import_preview(preview)
        session.commit()

    with session_factory() as session:
        employee = HrRepository(session).list_employees()[0]
        assert employee.status == "퇴사"


def test_csv_and_json_input_files_are_supported(tmp_path: Path) -> None:
    session_factory = create_session_factory(tmp_path / "hr.sqlite3")
    initialize_database(session_factory)
    sample_paths = write_sample_input_files(tmp_path / "samples")

    with session_factory() as session:
        csv_preview = ExcelImporter(session).preview(sample_paths[1])
        json_preview = ExcelImporter(session).preview(sample_paths[2])

    assert csv_preview.counts[ImportAction.ADD] == len(SAMPLE_ROWS)
    assert json_preview.counts[ImportAction.ADD] == len(SAMPLE_ROWS)


def test_auto_import_apply_does_not_mark_missing_employees_as_exit_candidates(
    tmp_path: Path,
) -> None:
    session_factory = create_session_factory(tmp_path / "hr.sqlite3")
    initialize_database(session_factory)

    with session_factory() as session:
        HrRepository(session).create_or_update_employee(
            EmployeeInput(employee_no="A001", name="홍길동", department="인사팀")
        )
        session.commit()

    source = tmp_path / "new_employee.xlsx"
    pd.DataFrame(
        [
            {
                "사번": "A002",
                "이름": "김신규",
                "이메일": "new@example.com",
                "부서": "개발팀",
                "상위부서": "",
                "직급": "사원",
                "직책": "팀원",
                "입사일": "",
                "퇴사일": "",
                "재직상태": "재직",
            }
        ]
    ).to_excel(source, index=False)

    with session_factory() as session:
        preview = ExcelImporter(session).preview(source)
        assert len(preview.missing_existing_employee_ids) == 1
        assert preview.counts[ImportAction.CONFLICT] == 0
        HrRepository(session).apply_import_preview(preview)
        session.commit()

    with session_factory() as session:
        employees = HrRepository(session).list_employees()
        existing = next(employee for employee in employees if employee.employee_no == "A001")
        imported = next(employee for employee in employees if employee.employee_no == "A002")

    assert existing.status == EmploymentStatus.ACTIVE.value
    assert imported.status == EmploymentStatus.ACTIVE.value


def test_sample_input_files_are_created(tmp_path: Path) -> None:
    paths = write_sample_input_files(tmp_path)

    assert {path.suffix for path in paths} == {".xlsx", ".csv", ".json"}
    assert all(path.exists() and path.stat().st_size > 0 for path in paths)


def test_fixed_template_validation_accepts_sample_and_reports_missing_columns(tmp_path: Path) -> None:
    session_factory = create_session_factory(tmp_path / "hr.sqlite3")
    initialize_database(session_factory)
    sample_paths = write_sample_input_files(tmp_path / "samples")
    broken_path = tmp_path / "broken.xlsx"
    pd.DataFrame([{"사번": "A001", "이름": "홍길동"}]).to_excel(broken_path, index=False)

    with session_factory() as session:
        importer = ExcelImporter(session)

        for sample_path in sample_paths:
            assert importer.validate_fixed_template(sample_path) == []
        assert "부서" in importer.validate_fixed_template(broken_path)
        assert "재직상태" in importer.validate_fixed_template(broken_path)


def test_sample_input_is_realistic_multi_level_hr_data() -> None:
    departments = {row["부서"] for row in SAMPLE_ROWS}
    parent_departments = {row["상위부서"] for row in SAMPLE_ROWS if row["상위부서"]}
    statuses = {row["재직상태"] for row in SAMPLE_ROWS}
    names = [row["이름"] for row in SAMPLE_ROWS]

    assert len(SAMPLE_ROWS) >= 15
    assert "대표이사실" in departments
    assert {"제품본부", "사업본부", "경영지원본부"}.issubset(parent_departments)
    assert {"플랫폼개발팀", "AI응용팀", "People팀", "세일즈팀"}.issubset(departments)
    assert {"재직", "퇴사"}.issubset(statuses)
    assert names.count("김민준") == 2
    assert {"근무지", "고용형태", "매니저사번", "스킬", "비고"}.issubset(SAMPLE_ROWS[0])
