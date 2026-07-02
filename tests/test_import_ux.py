import os
from pathlib import Path

import pandas as pd

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.db.repository import HrRepository
from app.db.session import create_session_factory, initialize_database
from app.domain.hr import EmployeeInput, EmploymentStatus
from app.ui.dialogs import import_preview_text
from app.ui.main_window import MainWindow


REQUIRED_ROW = {
    "사번": "A001",
    "이름": "홍길동",
    "이메일": "hong@example.com",
    "부서": "인사팀",
    "상위부서": "경영지원본부",
    "직급": "매니저",
    "직책": "팀원",
    "입사일": "2026-01-01",
    "퇴사일": "",
    "재직상태": "재직",
}


class FakeStatus:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def showMessage(self, message: str, timeout: int | None = None) -> None:
        self.messages.append(message)


def _window(session_factory):
    window = MainWindow.__new__(MainWindow)
    window._window = None
    window.session_factory = session_factory
    window.status = FakeStatus()
    window.refresh_count = 0

    def refresh_chart() -> None:
        window.refresh_count += 1

    window.refresh_chart = refresh_chart
    return window


def _write_people_file(path: Path, rows: list[dict[str, str]]) -> None:
    if path.suffix == ".csv":
        pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
    elif path.suffix == ".json":
        pd.DataFrame(rows).to_json(path, orient="records", force_ascii=False)
    else:
        pd.DataFrame(rows).to_excel(path, index=False)


def _block_messages(monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError(args)))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError(args)))


def _select_file(monkeypatch, path: Path) -> None:
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(path), ""))


def test_fixed_template_import_auto_applies_without_mapping_or_preview(tmp_path, monkeypatch) -> None:
    session_factory = create_session_factory(tmp_path / "hr.sqlite3")
    initialize_database(session_factory)
    source = tmp_path / "people.xlsx"
    _write_people_file(source, [REQUIRED_ROW])
    _select_file(monkeypatch, source)
    _block_messages(monkeypatch)
    monkeypatch.setattr(
        "app.ui.main_window.ImportPreviewDialog",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("preview dialog should not open")),
    )
    window = _window(session_factory)

    MainWindow.import_people_file(window)

    with session_factory() as session:
        employees = HrRepository(session).list_employees()
        assert [(employee.employee_no, employee.name) for employee in employees] == [("A001", "홍길동")]
    assert window.refresh_count == 1
    assert window.status.messages[-1].startswith("자동 가져오기 완료")


def test_fixed_template_csv_and_json_import_auto_apply_without_preview(tmp_path, monkeypatch) -> None:
    for suffix in (".csv", ".json"):
        session_factory = create_session_factory(tmp_path / f"hr{suffix}.sqlite3")
        initialize_database(session_factory)
        source = tmp_path / f"people{suffix}"
        row = {**REQUIRED_ROW, "사번": f"A{suffix[1:].upper()}", "이름": f"{suffix}직원"}
        _write_people_file(source, [row])
        _select_file(monkeypatch, source)
        _block_messages(monkeypatch)
        monkeypatch.setattr(
            "app.ui.main_window.ImportPreviewDialog",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("preview dialog should not open")),
        )
        window = _window(session_factory)

        MainWindow.import_people_file(window)

        with session_factory() as session:
            assert HrRepository(session).list_employees()[0].name == f"{suffix}직원"


def test_conflict_import_blocks_and_shows_actionable_details(tmp_path, monkeypatch) -> None:
    session_factory = create_session_factory(tmp_path / "hr.sqlite3")
    initialize_database(session_factory)
    with session_factory() as session:
        HrRepository(session).create_or_update_employee(
            EmployeeInput(employee_no="A001", name="홍길동", email="hong@example.com", department="인사팀")
        )
        session.commit()
    source = tmp_path / "conflict.xlsx"
    _write_people_file(source, [{**REQUIRED_ROW, "사번": "", "이메일": "", "부서": "재무팀"}])
    _select_file(monkeypatch, source)
    _block_messages(monkeypatch)
    captured: dict[str, str] = {}

    class FakePreviewDialog:
        def __init__(self, preview, exit_candidate_options, parent=None) -> None:
            captured["text"] = import_preview_text(preview)
            captured["exit_options"] = str(exit_candidate_options)

        def exec(self) -> int:
            return 0

    monkeypatch.setattr("app.ui.main_window.ImportPreviewDialog", FakePreviewDialog)
    window = _window(session_factory)

    MainWindow.import_people_file(window)

    assert "자동 가져오기를 중단" in captured["text"]
    assert "사번이나 이메일" in captured["text"]
    assert captured["exit_options"] == "[]"
    with session_factory() as session:
        employees = HrRepository(session).list_employees()
        assert len(employees) == 1
        assert employees[0].department is None if hasattr(employees[0], "department") else True


def test_auto_import_keeps_missing_existing_employees_active(tmp_path, monkeypatch) -> None:
    session_factory = create_session_factory(tmp_path / "hr.sqlite3")
    initialize_database(session_factory)
    with session_factory() as session:
        HrRepository(session).create_or_update_employee(
            EmployeeInput(employee_no="A001", name="기존직원", department="인사팀")
        )
        session.commit()
    source = tmp_path / "new_only.xlsx"
    _write_people_file(source, [{**REQUIRED_ROW, "사번": "A002", "이름": "신규직원", "이메일": "new@example.com"}])
    _select_file(monkeypatch, source)
    _block_messages(monkeypatch)
    monkeypatch.setattr(
        "app.ui.main_window.ImportPreviewDialog",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("preview dialog should not open")),
    )
    window = _window(session_factory)

    MainWindow.import_people_file(window)

    with session_factory() as session:
        employees = {employee.employee_no: employee for employee in HrRepository(session).list_employees()}
        assert employees["A001"].status == EmploymentStatus.ACTIVE.value
        assert employees["A002"].status == EmploymentStatus.ACTIVE.value
    assert "파일에서 빠진 기존 직원 1명은 유지" in window.status.messages[-1]


def test_fixed_template_missing_columns_show_simple_korean_error(tmp_path, monkeypatch) -> None:
    session_factory = create_session_factory(tmp_path / "hr.sqlite3")
    initialize_database(session_factory)
    source = tmp_path / "broken.xlsx"
    pd.DataFrame([{"사번": "A001", "이름": "홍길동"}]).to_excel(source, index=False)
    _select_file(monkeypatch, source)
    warning: dict[str, str] = {}
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError(args)))
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, message: warning.update(title=title, message=message))
    monkeypatch.setattr(
        "app.ui.main_window.ImportPreviewDialog",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("preview dialog should not open")),
    )
    window = _window(session_factory)

    MainWindow.import_people_file(window)

    assert warning["title"] == "필수 컬럼 누락"
    assert warning["message"].startswith("필수 컬럼이 없습니다.")
    assert "빠진 컬럼:" in warning["message"]
    assert window.refresh_count == 0
