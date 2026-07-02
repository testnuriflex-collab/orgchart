import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.domain.hr import EmployeeInput, ImportAction, ImportPreview, ImportRowResult
from app.ui.dialogs import ImportPreviewDialog, change_summary, import_preview_text, row_change_summary


def test_import_preview_text_lists_conflict_rows() -> None:
    preview = ImportPreview(
        rows=[
            ImportRowResult(
                action=ImportAction.CONFLICT,
                row_number=3,
                employee=EmployeeInput(employee_no=None, name="홍길동", department="영업팀"),
                reason="동명이인이 있어 자동 병합하지 않음",
            )
        ],
        missing_existing_employee_ids=[],
    )

    text = import_preview_text(preview)

    assert "- 충돌: 1건" in text
    assert "3행 홍길동" in text
    assert "충돌은 자동 적용되지 않습니다" in text


def test_change_summary_uses_human_labels() -> None:
    text = change_summary({"department": ("인사팀", "재무팀"), "status": ("재직", "퇴사")})

    assert "부서: 인사팀 → 재무팀" in text
    assert "재직상태: 재직 → 퇴사" in text


def test_import_preview_dialog_returns_checked_exit_candidates() -> None:
    app = QApplication.instance() or QApplication([])
    assert app is not None
    preview = ImportPreview(
        rows=[
            ImportRowResult(
                action=ImportAction.UPDATE,
                row_number=2,
                employee=EmployeeInput(employee_no="A001", name="홍길동", department="재무팀"),
                reason="기존 직원과 매칭됨",
                changes={"department": ("인사팀", "재무팀")},
            )
        ],
        missing_existing_employee_ids=["emp-1"],
    )
    dialog = ImportPreviewDialog(preview, [("emp-1", "홍길동 · A001 · 재직")])

    dialog.exit_list.item(0).setCheckState(Qt.CheckState.Checked)

    assert dialog.selected_exit_candidate_ids() == {"emp-1"}
    assert dialog.table.item(0, 5).text() == "부서: 인사팀 → 재무팀"


def test_import_preview_dialog_blocks_apply_when_conflicts_exist() -> None:
    app = QApplication.instance() or QApplication([])
    assert app is not None
    preview = ImportPreview(
        rows=[
            ImportRowResult(
                action=ImportAction.CONFLICT,
                row_number=2,
                employee=EmployeeInput(employee_no=None, name="홍길동", department="영업팀"),
                reason="동명이인이 있어 자동 병합하지 않음",
            )
        ],
        missing_existing_employee_ids=[],
    )

    dialog = ImportPreviewDialog(preview, [])

    assert not dialog.apply_button.isEnabled()


def test_import_preview_dialog_lists_new_employee_fields_and_defaults_exit_unchecked() -> None:
    app = QApplication.instance() or QApplication([])
    assert app is not None
    add_row = ImportRowResult(
        action=ImportAction.ADD,
        row_number=2,
        employee=EmployeeInput(
            employee_no="A002",
            name="김신규",
            email="new@example.com",
            department="개발팀",
            grade="사원",
            title="Frontend",
            status="재직",
        ),
        reason="신규 직원",
    )
    preview = ImportPreview(rows=[add_row], missing_existing_employee_ids=["emp-1"])

    dialog = ImportPreviewDialog(preview, [("emp-1", "홍길동 · A001 · 재직")])

    assert "사번: A002" in row_change_summary(add_row)
    assert "부서: 개발팀" in dialog.table.item(0, 5).text()
    assert dialog.selected_exit_candidate_ids() == set()
