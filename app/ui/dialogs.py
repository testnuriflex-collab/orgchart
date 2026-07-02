from __future__ import annotations

from app.domain.hr import ImportAction, ImportPreview

CHANGE_FIELD_LABELS = {
    "employee_no": "사번",
    "name": "이름",
    "email": "이메일",
    "company": "소속회사",
    "department": "부서",
    "parent_department": "상위부서",
    "grade": "직급",
    "title": "직책",
    "hire_date": "입사일",
    "resign_date": "퇴사일",
    "status": "재직상태",
}


def import_preview_text(preview: ImportPreview) -> str:
    counts = preview.counts
    conflict_rows = [row for row in preview.rows if row.action == ImportAction.CONFLICT]
    heading = (
        "충돌이 있어 자동 가져오기를 중단했습니다. 아래 행을 수정한 뒤 다시 가져와 주세요."
        if conflict_rows
        else "가져오기 전에 아래 변경을 검토하세요."
    )
    summary = (
        f"{heading}\n"
        f"- 추가: {counts.get(ImportAction.ADD, 0)}명\n"
        f"- 수정: {counts.get(ImportAction.UPDATE, 0)}명\n"
        f"- 변경 없음: {counts.get(ImportAction.UNCHANGED, 0)}명\n"
        f"- 충돌: {counts.get(ImportAction.CONFLICT, 0)}건\n"
        f"- 이번 파일에서 빠진 기존 직원: {len(preview.missing_existing_employee_ids)}명"
    )
    if not conflict_rows:
        return summary
    details = "\n".join(
        f"- {row.row_number}행 {row.employee.name}: {row.reason}" for row in conflict_rows[:8]
    )
    overflow = "" if len(conflict_rows) <= 8 else f"\n- 외 {len(conflict_rows) - 8}건"
    guidance = (
        "충돌은 자동 적용되지 않습니다. 사번, 이메일, _org_chart_uuid로 기존 직원을 "
        "식별하거나 중복 이름을 정리한 뒤 다시 가져오세요."
    )
    return f"{summary}\n\n충돌 행:\n{details}{overflow}\n\n{guidance}"


def change_summary(changes: dict[str, tuple[str | None, str | None]]) -> str:
    if not changes:
        return ""
    return ", ".join(
        f"{CHANGE_FIELD_LABELS.get(field, field)}: {before or '-'} → {after or '-'}"
        for field, (before, after) in changes.items()
    )


def row_change_summary(row) -> str:
    if row.changes:
        return change_summary(row.changes)
    if row.action != ImportAction.ADD:
        return "-"
    fields = {
        "employee_no": row.employee.employee_no,
        "email": row.employee.email,
        "department": row.employee.department,
        "parent_department": row.employee.parent_department,
        "grade": row.employee.grade,
        "title": row.employee.title,
        "hire_date": row.employee.hire_date,
        "resign_date": row.employee.resign_date,
        "status": row.employee.status,
    }
    return ", ".join(
        f"{CHANGE_FIELD_LABELS.get(field, field)}: {value}"
        for field, value in fields.items()
        if value
    ) or "신규 직원"


class ImportPreviewDialog:
    def __init__(
        self,
        preview: ImportPreview,
        exit_candidate_options: list[tuple[str, str]],
        parent=None,
    ) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QAbstractItemView,
            QDialog,
            QDialogButtonBox,
            QLabel,
            QListWidget,
            QListWidgetItem,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
        )

        self.preview = preview
        self._dialog = QDialog(parent)
        self._dialog.setWindowTitle("가져오기 변경 검토")
        self._dialog.resize(980, 640)
        layout = QVBoxLayout(self._dialog)

        summary = QLabel(import_preview_text(preview))
        summary.setWordWrap(True)
        layout.addWidget(summary)

        self.table = QTableWidget(len(preview.rows), 7)
        self.table.setHorizontalHeaderLabels(["행", "사번", "이름", "액션", "조직", "변경 내용", "사유"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        for row_index, result in enumerate(preview.rows):
            employee = result.employee
            values = [
                str(result.row_number),
                employee.employee_no or "",
                employee.name,
                result.action.value,
                employee.department or "",
                row_change_summary(result),
                result.reason,
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                if result.action == ImportAction.CONFLICT:
                    item.setForeground(Qt.GlobalColor.red)
                self.table.setItem(row_index, column_index, item)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        self.exit_list = QListWidget()
        self.exit_list.setAccessibleName("퇴사후보 수동 승인 목록")
        for employee_id, label in exit_candidate_options:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, employee_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.exit_list.addItem(item)
        if exit_candidate_options:
            layout.addWidget(QLabel("이번 파일에서 빠진 기존 직원입니다. 체크한 사람만 퇴사후보로 표시됩니다."))
            layout.addWidget(self.exit_list)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        self.apply_button = buttons.button(QDialogButtonBox.StandardButton.Apply)
        self.apply_button.setText("적용")
        self.apply_button.setEnabled(preview.counts[ImportAction.CONFLICT] == 0)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        self.apply_button.clicked.connect(self._dialog.accept)
        buttons.accepted.connect(self._dialog.accept)
        buttons.rejected.connect(self._dialog.reject)
        layout.addWidget(buttons)

    def __getattr__(self, name: str):
        return getattr(self._dialog, name)

    def selected_exit_candidate_ids(self) -> set[str]:
        from PySide6.QtCore import Qt

        selected: set[str] = set()
        for index in range(self.exit_list.count()):
            item = self.exit_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                selected.add(item.data(Qt.ItemDataRole.UserRole))
        return selected


class BulkRenameDialog:
    """부서/조직명 일괄 치환 다이얼로그.

    각 행의 '새 이름'을 채우면 해당 조직명을 일괄 변경한다(예: 인사팀 → 피플팀).
    비워 두면 변경하지 않는다.
    """

    def __init__(self, org_names: list[str], parent=None) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QAbstractItemView,
            QDialog,
            QDialogButtonBox,
            QLabel,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
        )

        self._names = list(org_names)
        self._dialog = QDialog(parent)
        self._dialog.setWindowTitle("부서명 일괄 변환")
        self._dialog.resize(560, 560)
        layout = QVBoxLayout(self._dialog)
        guide = QLabel("바꿀 조직의 '새 이름'만 입력하세요. 비워 두면 그대로 유지됩니다.")
        guide.setWordWrap(True)
        layout.addWidget(guide)

        self.table = QTableWidget(len(self._names), 2)
        self.table.setHorizontalHeaderLabels(["현재 이름", "새 이름"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAccessibleName("부서명 일괄 변환 표")
        for row_index, name in enumerate(self._names):
            current_item = QTableWidgetItem(name)
            current_item.setFlags(current_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_index, 0, current_item)
            self.table.setItem(row_index, 1, QTableWidgetItem(""))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("변환")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        buttons.accepted.connect(self._dialog.accept)
        buttons.rejected.connect(self._dialog.reject)
        layout.addWidget(buttons)

    def __getattr__(self, name: str):
        return getattr(self._dialog, name)

    def mapping(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for row_index, old_name in enumerate(self._names):
            cell = self.table.item(row_index, 1)
            new_name = cell.text().strip() if cell else ""
            if new_name and new_name != old_name:
                result[old_name] = new_name
        return result
