"""표준 2 시트 템플릿(명단·위계) 가져오기와 3단계 위계 검증."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.db.repository import HrRepository
from app.db.session import create_session_factory, initialize_database
from app.domain.hr import ImportAction
from app.importer.excel_importer import ExcelImporter, people_sheet_name, read_hierarchy_spec
from app.importer.sample_files import TEMPLATE_COMPANY, write_org_template


def _factory(tmp_path: Path):
    session_factory = create_session_factory(tmp_path / "hr.sqlite3")
    initialize_database(session_factory)
    return session_factory


def test_write_org_template_creates_two_sheets(tmp_path: Path) -> None:
    path = write_org_template(tmp_path / "tpl.xlsx")
    sheets = pd.ExcelFile(path).sheet_names
    assert "명단" in sheets and "위계" in sheets
    people = pd.read_excel(path, sheet_name="명단", dtype=str)
    assert {"소속회사", "소속조직", "소속부서", "이름", "직책"}.issubset(people.columns)


def test_template_import_builds_three_level_hierarchy(tmp_path: Path) -> None:
    path = write_org_template(tmp_path / "tpl.xlsx")
    session_factory = _factory(tmp_path)

    with session_factory() as session:
        importer = ExcelImporter(session)
        assert importer.validate_fixed_template(path) == []
        assert people_sheet_name(path) == "명단"
        preview = importer.preview(path)
        hierarchy = importer.read_hierarchy(path)
        assert not hierarchy.is_empty()
        assert preview.counts[ImportAction.ADD] == 9
        HrRepository(session).apply_import_preview(preview, hierarchy=hierarchy)
        session.commit()

    with session_factory() as session:
        units = {unit.name: unit for unit in HrRepository(session).list_org_units()}
        assert TEMPLATE_COMPANY in units
        people_team = units["People팀"]
        assert people_team.parent.name == "경영지원본부"
        assert people_team.parent.parent.name == TEMPLATE_COMPANY
        # '위계' 시트의 표시순서가 반영됨
        assert units["경영지원본부"].display_order == 1
        assert units["제품본부"].display_order == 2
        assert units["사업본부"].display_order == 3


def test_template_import_is_idempotent(tmp_path: Path) -> None:
    path = write_org_template(tmp_path / "tpl.xlsx")
    session_factory = _factory(tmp_path)

    with session_factory() as session:
        importer = ExcelImporter(session)
        preview = importer.preview(path)
        HrRepository(session).apply_import_preview(preview, hierarchy=importer.read_hierarchy(path))
        session.commit()

    with session_factory() as session:
        importer = ExcelImporter(session)
        second = importer.preview(path)
        assert second.counts[ImportAction.ADD] == 0
        assert second.counts[ImportAction.UPDATE] == 0
        assert second.counts[ImportAction.UNCHANGED] == 9


def test_hierarchy_spec_empty_when_no_sheet(tmp_path: Path) -> None:
    plain = tmp_path / "plain.xlsx"
    pd.DataFrame([{"이름": "홍길동", "부서": "인사팀", "재직상태": "재직"}]).to_excel(plain, index=False)
    assert read_hierarchy_spec(plain).is_empty()
    assert people_sheet_name(plain) == 0


def test_legacy_two_level_format_still_imports(tmp_path: Path) -> None:
    source = tmp_path / "legacy.xlsx"
    pd.DataFrame(
        [{"사번": "A001", "이름": "홍길동", "부서": "인사팀", "상위부서": "경영지원본부", "재직상태": "재직"}]
    ).to_excel(source, index=False)
    session_factory = _factory(tmp_path)

    with session_factory() as session:
        importer = ExcelImporter(session)
        assert importer.validate_fixed_template(source) == []
        preview = importer.preview(source)
        HrRepository(session).apply_import_preview(preview)
        session.commit()

    with session_factory() as session:
        assignment = HrRepository(session).list_active_assignments()[0]
        assert assignment.org_unit.name == "인사팀"
        assert assignment.org_unit.parent.name == "경영지원본부"
