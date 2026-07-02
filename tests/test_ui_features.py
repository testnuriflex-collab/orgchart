"""MainWindow의 커맨드 레일·표 편집·일괄 변환·조직 재배치 UI 통합 검증(offscreen)."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from app.db.repository import HrRepository
from app.db.session import create_session_factory, initialize_database
from app.domain.hr import EmployeeInput
from app.ui.main_window import ROSTER_COLUMNS, MainWindow


def _column(field: str) -> int:
    return next(index for index, (name, _, _) in enumerate(ROSTER_COLUMNS) if name == field)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _factory(tmp_path: Path):
    session_factory = create_session_factory(tmp_path / "hr.sqlite3")
    initialize_database(session_factory)
    return session_factory


def _seed(session_factory, inputs: list[EmployeeInput]) -> None:
    with session_factory() as session:
        repository = HrRepository(session)
        for employee_input in inputs:
            repository.create_or_update_employee(employee_input)
        session.commit()


def test_command_rail_exposes_icon_actions(tmp_path: Path) -> None:
    _app()
    session_factory = _factory(tmp_path)
    window = MainWindow(session_factory)
    assert set(window._rail_buttons) >= {"가져오기", "템플릿", "표 편집", "일괄 변환", "PDF", "PNG", "Excel", "전체 보기"}
    for button in window._rail_buttons.values():
        assert not button.icon().isNull()
    assert len(window.display_checks) == 7


def test_roster_edit_moves_employee_department(tmp_path: Path) -> None:
    _app()
    session_factory = _factory(tmp_path)
    _seed(session_factory, [EmployeeInput(employee_no="A001", name="홍길동", department="인사팀", title="팀원")])
    window = MainWindow(session_factory)

    window.toggle_roster()
    assert window.center_stack.currentIndex() == 1
    assert window.roster_table.rowCount() == 1

    window.roster_table.item(0, _column("department")).setText("재무팀")
    window.roster_table.item(0, _column("title")).setText("팀장")
    window.save_roster()

    with session_factory() as session:
        repository = HrRepository(session)
        assignment = repository.list_active_assignments()[0]
        assert assignment.org_unit.name == "재무팀"
        assert repository.list_employees()[0].title == "팀장"


def test_bulk_convert_renames_departments(tmp_path: Path, monkeypatch) -> None:
    _app()
    session_factory = _factory(tmp_path)
    _seed(session_factory, [EmployeeInput(employee_no="A001", name="홍길동", department="인사팀")])
    window = MainWindow(session_factory)

    class FakeBulkDialog:
        def __init__(self, org_names, parent=None) -> None:
            assert "인사팀" in org_names

        def exec(self) -> int:
            return 1

        def mapping(self) -> dict[str, str]:
            return {"인사팀": "피플팀"}

    monkeypatch.setattr("app.ui.main_window.BulkRenameDialog", FakeBulkDialog)
    window.bulk_convert()

    with session_factory() as session:
        names = {unit.name for unit in HrRepository(session).list_org_units()}
        assert "피플팀" in names and "인사팀" not in names


def test_reparent_handler_moves_org(tmp_path: Path, monkeypatch) -> None:
    _app()
    session_factory = _factory(tmp_path)
    with session_factory() as session:
        repository = HrRepository(session)
        repository.ensure_org_unit("영업팀")
        repository.ensure_org_unit("본부")
        session.commit()
        units = {unit.name: unit.id for unit in repository.list_org_units()}
    window = MainWindow(session_factory)

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.reparent_org_unit(units["영업팀"], units["본부"])

    with session_factory() as session:
        moved = {unit.name: unit for unit in HrRepository(session).list_org_units()}
        assert moved["영업팀"].parent.name == "본부"


def test_save_template_writes_two_sheet_workbook(tmp_path: Path, monkeypatch) -> None:
    import pandas as pd

    _app()
    session_factory = _factory(tmp_path)
    window = MainWindow(session_factory)
    target = tmp_path / "std_template.xlsx"

    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    window.save_template()

    assert target.exists()
    assert {"명단", "위계"}.issubset(set(pd.ExcelFile(target).sheet_names))
