"""적대적 감사 결함 중 MainWindow 상호작용 결함 회귀 테스트(offscreen).

커버: H1(부서명 충돌 UI 안내·무크래시), M1(재export 실패 통지),
M2(이동/이름변경/일괄변환 실행취소), M3(표 편집 컬럼 매핑).
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from app.db.repository import HrRepository
from app.db.session import create_session_factory, initialize_database
from app.domain.hr import EmployeeInput
from app.ui.main_window import ROSTER_COLUMNS, MainWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _factory(tmp_path: Path):
    session_factory = create_session_factory(tmp_path / "hr.sqlite3")
    initialize_database(session_factory)
    return session_factory


def _column(field: str) -> int:
    return next(index for index, (name, _, _) in enumerate(ROSTER_COLUMNS) if name == field)


def _seed(session_factory, inputs: list[EmployeeInput]) -> None:
    with session_factory() as session:
        repository = HrRepository(session)
        for employee_input in inputs:
            repository.create_or_update_employee(employee_input)
        session.commit()


# ── H1: 형제 조직명 충돌 시 크래시 대신 경고 ────────────────────────────
def test_rename_conflict_warns_without_crash(tmp_path: Path, monkeypatch) -> None:
    _app()
    session_factory = _factory(tmp_path)
    with session_factory() as session:
        repository = HrRepository(session)
        repository.ensure_org_unit("인사팀")
        repository.ensure_org_unit("피플팀")
        session.commit()
        units = {u.name: u.id for u in repository.list_org_units()}
    window = MainWindow(session_factory)

    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[2]))
    window.rename_org_unit(units["인사팀"], "피플팀")

    assert warnings and "피플팀" in warnings[0]
    with session_factory() as session:
        names = {u.name for u in HrRepository(session).list_org_units()}
        assert "인사팀" in names  # 변경되지 않고 그대로 유지


# ── M2: 조직명 변경 실행취소 ─────────────────────────────────────────────
def test_rename_then_undo_restores_name(tmp_path: Path) -> None:
    _app()
    session_factory = _factory(tmp_path)
    with session_factory() as session:
        org = HrRepository(session).ensure_org_unit("영업팀")
        session.commit()
        org_id = org.id
    window = MainWindow(session_factory)

    window.rename_org_unit(org_id, "세일즈팀")
    with session_factory() as session:
        assert HrRepository(session).list_org_units()[0].name == "세일즈팀"

    window.undo_last()
    with session_factory() as session:
        assert HrRepository(session).list_org_units()[0].name == "영업팀"


# ── M2: 직원 이동 실행취소 ───────────────────────────────────────────────
def test_move_then_undo_restores_department(tmp_path: Path, monkeypatch) -> None:
    _app()
    session_factory = _factory(tmp_path)
    _seed(session_factory, [EmployeeInput(employee_no="A001", name="홍길동", department="인사팀")])
    with session_factory() as session:
        repository = HrRepository(session)
        finance = repository.ensure_org_unit("재무팀")
        session.commit()
        finance_id = finance.id
        employee_id = repository.list_employees()[0].id

    window = MainWindow(session_factory)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.move_employee(employee_id, finance_id)

    with session_factory() as session:
        assert HrRepository(session).list_active_assignments()[0].org_unit.name == "재무팀"

    window.undo_last()
    with session_factory() as session:
        assert HrRepository(session).list_active_assignments()[0].org_unit.name == "인사팀"


# ── M2: 일괄 변환 실행취소 ───────────────────────────────────────────────
def test_bulk_convert_then_undo(tmp_path: Path, monkeypatch) -> None:
    _app()
    session_factory = _factory(tmp_path)
    _seed(session_factory, [EmployeeInput(employee_no="A001", name="홍길동", department="인사팀")])
    window = MainWindow(session_factory)

    class FakeBulkDialog:
        def __init__(self, org_names, parent=None) -> None:
            pass

        def exec(self) -> int:
            return 1

        def mapping(self) -> dict[str, str]:
            return {"인사팀": "피플팀"}

    monkeypatch.setattr("app.ui.main_window.BulkRenameDialog", FakeBulkDialog)
    window.bulk_convert()
    with session_factory() as session:
        names = {u.name for u in HrRepository(session).list_org_units()}
        assert "피플팀" in names and "인사팀" not in names

    window.undo_last()
    with session_factory() as session:
        names = {u.name for u in HrRepository(session).list_org_units()}
        assert "인사팀" in names and "피플팀" not in names


# ── M1: 재export 실패 시 조용히 삼키지 않고 통지 ─────────────────────────
def test_reexport_failure_notifies_and_stops_tracking(tmp_path: Path, monkeypatch) -> None:
    _app()
    session_factory = _factory(tmp_path)
    window = MainWindow(session_factory)
    window._last_excel_path = tmp_path / "tracked.xlsx"

    def _boom(*args, **kwargs):
        raise OSError("파일이 열려 있어 저장할 수 없습니다.")

    monkeypatch.setattr("app.ui.main_window.export_database_to_excel", _boom)
    window._reexport_excel_if_tracked()

    assert window._last_excel_path is None  # 추적 해제
    assert "자동 갱신 실패" in window.status.currentMessage()


# ── M3: 2단계 조직에서 회사명이 소속조직 칸으로 밀리지 않음 ──────────────────
def test_roster_two_level_mapping_keeps_company(tmp_path: Path) -> None:
    _app()
    session_factory = _factory(tmp_path)
    _seed(
        session_factory,
        [EmployeeInput(employee_no="CEO001", name="정민서", company="(주)오르그스튜디오", department="대표이사실")],
    )
    window = MainWindow(session_factory)
    window.toggle_roster()

    company = window.roster_table.item(0, _column("company")).text()
    division = window.roster_table.item(0, _column("division")).text()
    department = window.roster_table.item(0, _column("department")).text()
    assert company == "(주)오르그스튜디오"
    assert division == ""
    assert department == "대표이사실"
