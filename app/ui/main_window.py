from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.chart.adapters import to_layout_nodes
from app.chart.layout import compute_org_layout
from app.db.repository import HrRepository, OrgUnitNameConflictError
from app.domain.hr import CardDisplayOptions, ImportAction
from app.exporter.excel_exporter import export_database_to_excel
from app.exporter.pdf_exporter import export_scene_to_pdf, export_scene_to_png
from app.importer.excel_importer import INPUT_FILE_FILTER, PeopleFileImporter
from app.importer.sample_files import write_org_template
from app.ui.chart_view import OrgChartViewMixin
from app.ui.dialogs import BulkRenameDialog, ImportPreviewDialog

# 표시 항목 토글 정의: (필드키, 라벨).
DISPLAY_TOGGLES = [
    ("name", "이름"),
    ("title", "직책"),
    ("grade", "직급"),
    ("department", "부서"),
    ("employee_no", "사번"),
    ("email", "이메일"),
    ("status", "재직상태"),
]

# 표(명단) 편집 화면 컬럼. (필드키, 헤더, 편집가능여부).
ROSTER_COLUMNS = [
    ("employee_no", "사번", True),
    ("name", "이름", True),
    ("email", "이메일", True),
    ("company", "소속회사", True),
    ("division", "소속조직", True),
    ("department", "소속부서", True),
    ("grade", "직급", True),
    ("title", "직책", True),
    ("status", "재직상태", True),
    ("hire_date", "입사일", True),
    ("resign_date", "퇴사일", True),
]

_EMPLOYEE_EDIT_FIELDS = {"employee_no", "name", "email", "grade", "title", "status", "hire_date", "resign_date"}


def filter_nodes_for_query(nodes, query: str):
    query = query.strip().lower()
    if not query:
        return nodes

    node_by_id = {node.id: node for node in nodes}
    included_ids: set[str] = set()

    def include_with_ancestors(node) -> None:
        current = node
        while current and current.id not in included_ids:
            included_ids.add(current.id)
            current = node_by_id.get(current.parent_id)

    for node in nodes:
        node_matches = query in node.name.lower() or any(
            query
            in " ".join(
                filter(
                    None,
                    [
                        employee.name,
                        employee.title,
                        employee.grade,
                        employee.status,
                        employee.employee_no,
                        employee.email,
                    ],
                )
            ).lower()
            for employee in node.employees
        )
        if node_matches:
            include_with_ancestors(node)

    return [node for node in nodes if node.id in included_ids]


def _revert_bulk_rename(repository: HrRepository, items: list[tuple[str, str]]) -> None:
    """일괄 변환으로 바뀐 조직들을 각자의 이전 이름으로 되돌린다."""
    for org_unit_id, old_name in items:
        try:
            repository.rename_org_unit(org_unit_id, old_name)
        except OrgUnitNameConflictError:
            # 되돌리는 자리에 이미 같은 이름이 생겼다면 해당 항목만 건너뛴다.
            continue


def org_ancestor_names(org) -> list[str]:
    """말단 조직에서 최상위까지 상위→하위 순서로 이름을 반환한다."""
    names: list[str] = []
    seen: set[str] = set()
    current = org
    while current is not None and current.id not in seen:
        names.append(current.name)
        seen.add(current.id)
        current = current.parent
    return list(reversed(names))


class MainWindow:
    def __init__(self, session_factory: sessionmaker) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QGraphicsView,
            QLabel,
            QLineEdit,
            QListWidget,
            QMainWindow,
            QPushButton,
            QSplitter,
            QStackedWidget,
            QVBoxLayout,
            QWidget,
        )

        class OrgChartView(OrgChartViewMixin, QGraphicsView):
            pass

        self._window = QMainWindow()
        self._window.setWindowTitle("조직도 Studio")
        self._window.resize(1480, 940)
        self.session_factory = session_factory
        self.current_scene = None
        self._selected_org_id: str | None = None
        self._last_excel_path: Path | None = None
        # 커밋된 구조 변경(이동·이름변경·일괄변환)의 1단계 실행취소 스택.
        self._undo_stack: list[tuple[str, Callable[[HrRepository], None]]] = []
        self.display_options = CardDisplayOptions().as_dict()

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── 좌측: 아이콘 중심 커맨드 레일 + 조직 목록 ──────────────────
        self.command_rail = self._build_command_rail()
        if "실행취소" in self._rail_buttons:
            self._rail_buttons["실행취소"].setEnabled(False)

        self.org_list = QListWidget()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("이름·조직·직책 검색")
        self.search_input.setAccessibleName("조직도 검색")
        self.search_input.textChanged.connect(self.refresh_chart)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.command_rail)
        left_layout.addWidget(QLabel("조직 목록"))
        self.summary_label = QLabel("조직 0 · 구성원 0")
        left_layout.addWidget(self.search_input)
        left_layout.addWidget(self.summary_label)
        left_layout.addWidget(self.org_list, 1)

        # ── 중앙: 조직도 캔버스 ⇄ 명단 표 편집 (스택 전환) ───────────
        self.chart_view = OrgChartView()
        self.chart_view.setAccessibleName("조직도 캔버스")
        self.chart_view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.chart_view.setRenderHints(self.chart_view.renderHints())

        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(self.chart_view)
        self.center_stack.addWidget(self._build_roster_editor())

        # ── 우측: 표시 항목 토글 + 속성 패널 ───────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self._build_display_panel())
        right_layout.addWidget(QLabel("속성"))
        self.detail_label = QLabel("조직이나 직원을 선택하면 상세 정보가 표시됩니다.")
        self.detail_label.setWordWrap(True)
        self.detail_label.setAccessibleName("선택 상세 정보")
        right_layout.addWidget(self.detail_label)
        self.name_editor = QLineEdit()
        self.name_editor.setPlaceholderText("선택 항목 이름")
        self.name_editor.setAccessibleName("조직명 편집")
        save_name_button = QPushButton("조직명 저장")
        save_name_button.setToolTip("선택한 조직의 이름을 저장합니다.")
        save_name_button.setAccessibleName("조직명 저장")
        save_name_button.clicked.connect(self.save_selected_org_name)
        right_layout.addWidget(self.name_editor)
        right_layout.addWidget(save_name_button)
        right_layout.addStretch()

        splitter.addWidget(left)
        splitter.addWidget(self.center_stack)
        splitter.addWidget(right)
        splitter.setSizes([300, 900, 300])
        self._window.setCentralWidget(splitter)

        self.status = self._window.statusBar()
        self.status.showMessage("표준 템플릿(명단·위계) 또는 인사 파일을 가져오면 조직도가 자동 생성됩니다.")
        self.org_list.currentItemChanged.connect(self._org_selected_from_list)
        self.refresh_chart()

    def __getattr__(self, name: str):
        return getattr(self._window, name)

    # ── UI 빌더 ────────────────────────────────────────────────────
    def _rail_button(self, pixmap, text: str, tooltip: str, slot, primary: bool = False):
        from PySide6.QtCore import QSize, Qt
        from PySide6.QtWidgets import QToolButton

        button = QToolButton()
        style = self._window.style()
        button.setIcon(style.standardIcon(pixmap))
        button.setIconSize(QSize(20, 20))
        button.setText(text)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setAutoRaise(True)
        button.setMinimumHeight(40)
        button.setProperty("primary", primary)
        button.clicked.connect(slot)
        return button

    def _build_command_rail(self):
        from PySide6.QtWidgets import QGridLayout, QStyle, QWidget

        sp = QStyle.StandardPixmap
        specs = [
            (sp.SP_DialogOpenButton, "가져오기", "명단·위계 템플릿 또는 인사 파일을 불러옵니다.", self.import_people_file, True),
            (sp.SP_FileIcon, "템플릿", "표준 조직도 템플릿(명단·위계) Excel을 생성합니다.", self.save_template, False),
            (sp.SP_FileDialogDetailedView, "표 편집", "명단을 표로 편집하고 저장하면 조직도에 반영됩니다.", self.toggle_roster, False),
            (sp.SP_BrowserReload, "일괄 변환", "부서명을 한 번에 치환합니다(예: 인사팀→피플팀).", self.bulk_convert, False),
            (sp.SP_ArrowBack, "실행취소", "직전의 이동·이름변경·일괄변환을 되돌립니다.", self.undo_last, False),
            (sp.SP_DialogSaveButton, "PDF", "조직도 전체를 한 페이지 PDF로 저장합니다.", self.export_pdf, False),
            (sp.SP_DialogSaveButton, "PNG", "조직도 전체를 고해상도 PNG로 저장합니다.", self.export_png, False),
            (sp.SP_DriveHDIcon, "Excel", "현재 인사 DB를 Excel로 내보냅니다.", self.export_excel, False),
            (sp.SP_FileDialogContentsView, "전체 보기", "조직도를 화면에 맞춥니다.", self.fit_chart, False),
        ]
        rail = QWidget()
        rail.setAccessibleName("주요 작업 레일")
        grid = QGridLayout(rail)
        grid.setContentsMargins(0, 0, 0, 6)
        grid.setSpacing(6)
        self._rail_buttons = {}
        for index, (pixmap, text, tooltip, slot, primary) in enumerate(specs):
            button = self._rail_button(pixmap, text, tooltip, slot, primary)
            self._rail_buttons[text] = button
            grid.addWidget(button, index // 2, index % 2)
        return rail

    def _build_display_panel(self):
        from PySide6.QtWidgets import QCheckBox, QGridLayout, QGroupBox

        group = QGroupBox("표시 항목")
        group.setAccessibleName("카드 표시 항목 토글")
        grid = QGridLayout(group)
        self.display_checks = {}
        for index, (field, label) in enumerate(DISPLAY_TOGGLES):
            check = QCheckBox(label)
            check.setChecked(bool(self.display_options.get(field, True)))
            check.setAccessibleName(f"{label} 표시")
            check.stateChanged.connect(self._on_display_toggled)
            self.display_checks[field] = check
            grid.addWidget(check, index // 2, index % 2)
        return group

    def _build_roster_editor(self):
        from PySide6.QtWidgets import (
            QAbstractItemView,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QTableWidget,
            QVBoxLayout,
            QWidget,
        )

        container = QWidget()
        layout = QVBoxLayout(container)
        header = QHBoxLayout()
        header.addWidget(QLabel("명단 표 편집 — 셀을 수정한 뒤 저장하면 DB와 조직도에 반영됩니다."))
        header.addStretch()
        reload_button = QPushButton("되돌리기")
        reload_button.setToolTip("편집 내용을 버리고 DB에서 다시 불러옵니다.")
        reload_button.clicked.connect(self.load_roster)
        save_button = QPushButton("저장")
        save_button.setProperty("primary", True)
        save_button.setToolTip("표 편집 내용을 DB에 저장합니다.")
        save_button.clicked.connect(self.save_roster)
        header.addWidget(reload_button)
        header.addWidget(save_button)
        layout.addLayout(header)

        self.roster_table = QTableWidget(0, len(ROSTER_COLUMNS))
        self.roster_table.setHorizontalHeaderLabels([label for _, label, _ in ROSTER_COLUMNS])
        self.roster_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.roster_table.setAlternatingRowColors(True)
        self.roster_table.setAccessibleName("명단 편집 표")
        layout.addWidget(self.roster_table, 1)
        return container

    # ── 조직도 렌더 ────────────────────────────────────────────────
    def refresh_chart(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QListWidgetItem

        from app.ui.chart_view import ChartSceneBuilder

        with self.session_factory() as session:
            repository = HrRepository(session)
            org_units, assignments = repository.org_tree_payload()
            nodes = to_layout_nodes(org_units, assignments)
            query = self.search_input.text().strip() if hasattr(self, "search_input") else ""
            nodes = filter_nodes_for_query(nodes, query)
            boxes = compute_org_layout(nodes, query)
            self._mark_search_matches(boxes, query)
            visible_org_ids = {node.id for node in nodes}
            employee_count_by_org = {
                org.id: sum(1 for assignment in assignments if assignment.org_unit_id == org.id)
                for org in org_units
            }
            self.org_list.clear()
            for org in org_units:
                if query and org.id not in visible_org_ids:
                    continue
                count = employee_count_by_org.get(org.id, 0)
                item = QListWidgetItem(f"{org.name} · {count}명")
                item.setData(Qt.ItemDataRole.UserRole, org.id)
                self.org_list.addItem(item)
            if hasattr(self, "summary_label"):
                total_people = sum(len(node.employees) for node in nodes)
                self.summary_label.setText(f"조직 {len(nodes)} · 구성원 {total_people}")

        builder = ChartSceneBuilder(
            self.move_employee,
            self.rename_org_unit,
            self.reparent_org_unit,
            self.display_options,
        )
        self.current_scene = builder.build(boxes)
        self.current_scene.selectionChanged.connect(self.update_selection_details)
        self.chart_view.setScene(self.current_scene)
        self.fit_chart()
        if hasattr(self, "status"):
            total_people = sum(len(node.employees) for node in nodes)
            if query:
                self.status.showMessage(f"검색 결과: 조직 {len(nodes)}개, 구성원 {total_people}명")
            else:
                self.status.showMessage(f"현재 조직 {len(org_units)}개, 구성원 {total_people}명")

    def fit_chart(self) -> None:
        if not self.current_scene:
            return
        from PySide6.QtCore import Qt

        self.chart_view.fitInView(self.current_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _on_display_toggled(self) -> None:
        self.display_options = {field: check.isChecked() for field, check in self.display_checks.items()}
        self.refresh_chart()

    # ── 가져오기 / 템플릿 ─────────────────────────────────────────
    def import_people_file(self) -> None:
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        path, _ = QFileDialog.getOpenFileName(
            self._window,
            "인사정보 파일 선택",
            str(Path.home()),
            INPUT_FILE_FILTER,
        )
        if not path:
            return
        try:
            importer_path = Path(path)
            with self.session_factory() as session:
                importer = PeopleFileImporter(session)
                missing_columns = importer.validate_fixed_template(importer_path)
        except Exception as exc:
            QMessageBox.critical(self._window, "파일 읽기 실패", f"파일을 읽을 수 없습니다.\n{exc}")
            return
        if missing_columns:
            QMessageBox.warning(
                self._window,
                "필수 컬럼 누락",
                "필수 컬럼이 없습니다. 표준 양식으로 다시 가져와 주세요.\n"
                f"빠진 컬럼: {', '.join(missing_columns)}",
            )
            return
        applied_summary: str | None = None
        try:
            with self.session_factory() as session:
                importer = PeopleFileImporter(session)
                preview = importer.preview(importer_path)
                if preview.counts[ImportAction.CONFLICT] > 0:
                    preview_dialog = ImportPreviewDialog(preview, [], self._window)
                    preview_dialog.exec()
                    return
                hierarchy = importer.read_hierarchy(importer_path)
                HrRepository(session).apply_import_preview(preview, hierarchy=hierarchy)
                session.commit()
                skipped_exit_candidates = len(preview.missing_existing_employee_ids)
                applied_summary = (
                    "자동 가져오기 완료: "
                    f"추가 {preview.counts[ImportAction.ADD]}명, "
                    f"수정 {preview.counts[ImportAction.UPDATE]}명"
                )
                if skipped_exit_candidates:
                    applied_summary += f", 파일에서 빠진 기존 직원 {skipped_exit_candidates}명은 유지"
                if preview.skipped_no_name_count:
                    applied_summary += (
                        f", 이름이 비어 제외된 행 {preview.skipped_no_name_count}건"
                    )
        except Exception as exc:
            QMessageBox.critical(self._window, "가져오기 실패", f"변경 내용을 적용하지 못했습니다.\n{exc}")
            return
        self.refresh_chart()
        if applied_summary:
            self.status.showMessage(applied_summary, 7000)

    import_excel = import_people_file

    def save_template(self) -> None:
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        path, _ = QFileDialog.getSaveFileName(
            self._window,
            "표준 조직도 템플릿 저장",
            str(Path.home() / "조직도_표준템플릿.xlsx"),
            "Excel Files (*.xlsx)",
        )
        if not path:
            return
        try:
            write_org_template(Path(path))
        except Exception as exc:
            QMessageBox.critical(self._window, "템플릿 저장 실패", f"템플릿을 저장하지 못했습니다.\n{exc}")
            return
        self.status.showMessage(f"표준 템플릿 저장 완료: {path}", 6000)

    # ── 내보내기 ──────────────────────────────────────────────────
    def export_excel(self) -> None:
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        path, _ = QFileDialog.getSaveFileName(
            self._window,
            "인사 DB Excel 저장",
            str(Path.home() / "인사DB.xlsx"),
            "Excel Files (*.xlsx)",
        )
        if not path:
            return
        try:
            with self.session_factory() as session:
                export_database_to_excel(session, Path(path))
        except Exception as exc:
            QMessageBox.critical(self._window, "Excel 저장 실패", f"파일을 저장하지 못했습니다.\n{exc}")
            return
        self._last_excel_path = Path(path)
        self.status.showMessage(f"Excel 저장 완료: {path}", 5000)

    def export_pdf(self) -> None:
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        if not self.current_scene:
            return
        path, _ = QFileDialog.getSaveFileName(
            self._window,
            "조직도 PDF 저장",
            str(Path.home() / "조직도.pdf"),
            "PDF Files (*.pdf)",
        )
        if not path:
            return
        try:
            export_scene_to_pdf(self.current_scene, Path(path))
        except Exception as exc:
            QMessageBox.critical(self._window, "PDF 저장 실패", f"PDF를 저장하지 못했습니다.\n{exc}")
            return
        self.status.showMessage(f"PDF 저장 완료: {path}", 5000)

    def export_png(self) -> None:
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        if not self.current_scene:
            return
        path, _ = QFileDialog.getSaveFileName(
            self._window,
            "조직도 PNG 저장",
            str(Path.home() / "조직도.png"),
            "PNG Files (*.png)",
        )
        if not path:
            return
        try:
            export_scene_to_png(self.current_scene, Path(path))
        except Exception as exc:
            QMessageBox.critical(self._window, "PNG 저장 실패", f"PNG를 저장하지 못했습니다.\n{exc}")
            return
        self.status.showMessage(f"PNG 저장 완료: {path}", 5000)

    # ── 표(명단) 편집 화면 ────────────────────────────────────────
    def toggle_roster(self) -> None:
        if self.center_stack.currentIndex() == 1:
            self.center_stack.setCurrentIndex(0)
            self.status.showMessage("조직도 화면으로 전환했습니다.", 3000)
            self.refresh_chart()
            return
        self.load_roster()
        self.center_stack.setCurrentIndex(1)
        self.status.showMessage("명단 표 편집 화면입니다. 저장하면 조직도에 반영됩니다.", 5000)

    def load_roster(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QTableWidgetItem

        with self.session_factory() as session:
            repository = HrRepository(session)
            employees = repository.list_employees()
            org_by_employee = {
                assignment.employee_id: org_ancestor_names(assignment.org_unit)
                for assignment in repository.list_active_assignments()
            }
            rows = []
            for employee in employees:
                path = org_by_employee.get(employee.id, [])
                # 경로는 상위→하위 순서. 위계 깊이 기준으로 매핑한다.
                # 1단계: 부서만 / 2단계: 회사·부서 / 3단계 이상: 회사·조직(중간)·부서.
                company = path[0] if len(path) >= 2 else ""
                division = " / ".join(path[1:-1]) if len(path) >= 3 else ""
                department = path[-1] if path else ""
                rows.append(
                    {
                        "_id": employee.id,
                        "employee_no": employee.employee_no or "",
                        "name": employee.name,
                        "email": employee.email or "",
                        "company": company,
                        "division": division,
                        "department": department,
                        "grade": employee.grade or "",
                        "title": employee.title or "",
                        "status": employee.status or "",
                        "hire_date": employee.hire_date or "",
                        "resign_date": employee.resign_date or "",
                    }
                )

        self.roster_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, (field, _, editable) in enumerate(ROSTER_COLUMNS):
                item = QTableWidgetItem(row[field])
                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row["_id"])
                if not editable:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.roster_table.setItem(row_index, column_index, item)
        self.roster_table.resizeColumnsToContents()

    def _roster_row_values(self, row_index: int) -> tuple[str, dict[str, str]]:
        from PySide6.QtCore import Qt

        id_item = self.roster_table.item(row_index, 0)
        employee_id = id_item.data(Qt.ItemDataRole.UserRole) if id_item else None
        values: dict[str, str] = {}
        for column_index, (field, _, _) in enumerate(ROSTER_COLUMNS):
            cell = self.roster_table.item(row_index, column_index)
            values[field] = cell.text().strip() if cell else ""
        return employee_id, values

    def save_roster(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        updated = 0
        moved = 0
        try:
            with self.session_factory() as session:
                repository = HrRepository(session)
                for row_index in range(self.roster_table.rowCount()):
                    employee_id, values = self._roster_row_values(row_index)
                    if not employee_id:
                        continue
                    fields = {field: values.get(field) for field in _EMPLOYEE_EDIT_FIELDS}
                    if repository.update_employee_fields(employee_id, fields):
                        updated += 1
                    path_names = [values.get("company"), values.get("division"), values.get("department")]
                    path_names = [name for name in path_names if name]
                    if path_names:
                        target = repository.ensure_org_path(path_names)
                        current = next(
                            (
                                assignment
                                for assignment in repository.list_active_assignments()
                                if assignment.employee_id == employee_id
                            ),
                            None,
                        )
                        if not current or current.org_unit_id != target.id:
                            repository.move_employee(employee_id, target.id)
                            moved += 1
                session.commit()
        except Exception as exc:
            QMessageBox.critical(self._window, "표 저장 실패", f"명단을 저장하지 못했습니다.\n{exc}")
            return
        self._reexport_excel_if_tracked()
        self.status.showMessage(f"명단 저장 완료: 수정 {updated}건, 소속 이동 {moved}건", 6000)
        self.center_stack.setCurrentIndex(0)
        self.refresh_chart()

    def _reexport_excel_if_tracked(self) -> None:
        if not self._last_excel_path:
            return
        try:
            with self.session_factory() as session:
                export_database_to_excel(session, self._last_excel_path)
        except Exception:
            failed = self._last_excel_path
            # 재export 실패를 조용히 삼키면 사용자가 낡은 Excel을 최신으로 오해한다.
            # 추적을 해제하고 상태바로 명확히 통지한다.
            self._last_excel_path = None
            if hasattr(self, "status"):
                self.status.showMessage(
                    f"내보낸 Excel 자동 갱신 실패: '{failed.name}'이(가) 열려 있는지 확인하세요. "
                    "자동 갱신을 중단하니 편집 후 Excel로 다시 내보내 주세요.",
                    12000,
                )

    # ── 부서 일괄 변환 ────────────────────────────────────────────
    def bulk_convert(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        with self.session_factory() as session:
            org_names = sorted({org.name for org in HrRepository(session).list_org_units()})
        if not org_names:
            QMessageBox.information(self._window, "일괄 변환", "변환할 조직이 없습니다. 먼저 인사 파일을 가져오세요.")
            return
        dialog = BulkRenameDialog(org_names, self._window)
        if not dialog.exec():
            return
        mapping = dialog.mapping()
        if not mapping:
            self.status.showMessage("변경할 부서명이 없습니다.", 4000)
            return
        try:
            with self.session_factory() as session:
                changed, conflicts, reverts = HrRepository(session).bulk_rename_org_units(mapping)
                session.commit()
        except Exception as exc:
            QMessageBox.critical(
                self._window, "일괄 변환 실패", f"부서명을 변환하지 못했습니다.\n{exc}"
            )
            return
        if reverts:
            self._push_undo(
                "부서명 일괄 변환",
                lambda repo, items=list(reverts): _revert_bulk_rename(repo, items),
            )
        self._reexport_excel_if_tracked()
        self.refresh_chart()
        message = f"부서명 일괄 변환 완료: {changed}개 조직 변경"
        if conflicts:
            unique_conflicts = ", ".join(sorted(set(conflicts)))
            message += f" · 같은 상위에 이미 있어 건너뜀: {unique_conflicts}"
        self.status.showMessage(message, 8000)

    # ── 드래그/편집 반영 ──────────────────────────────────────────
    def move_employee(self, employee_id: str, org_unit_id: str) -> None:
        from PySide6.QtWidgets import QMessageBox

        moved_summary: str | None = None
        with self.session_factory() as session:
            from app.db.models import Employee, OrgUnit

            repository = HrRepository(session)
            employee = session.get(Employee, employee_id)
            target_org = session.get(OrgUnit, org_unit_id)
            current_assignment = next(
                (assignment for assignment in repository.list_active_assignments() if assignment.employee_id == employee_id),
                None,
            )
            if not employee or not target_org:
                QMessageBox.warning(self._window, "이동 실패", "직원 또는 조직을 찾을 수 없습니다.")
                self.refresh_chart()
                return
            if current_assignment and current_assignment.org_unit_id == org_unit_id:
                self.refresh_chart()
                return
            current_name = current_assignment.org_unit.name if current_assignment else "미지정"
            answer = QMessageBox.question(
                self._window,
                "인사 발령 확인",
                f"{employee.name}님을\n{current_name} → {target_org.name}\n으로 이동할까요?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.refresh_chart()
                return
            previous_org_id = current_assignment.org_unit_id if current_assignment else None
            employee_name = employee.name
            HrRepository(session).move_employee(employee_id, org_unit_id)
            session.commit()
            moved_summary = f"이동 완료: {employee.name} · {current_name} → {target_org.name}"
        if previous_org_id:
            self._push_undo(
                f"{employee_name} 소속 이동",
                lambda repo, eid=employee_id, oid=previous_org_id: repo.move_employee(eid, oid),
            )
        self._reexport_excel_if_tracked()
        self.refresh_chart()
        if moved_summary:
            self.status.showMessage(moved_summary, 7000)

    def reparent_org_unit(self, org_unit_id: str, new_parent_id: str | None) -> None:
        from PySide6.QtWidgets import QMessageBox

        summary: str | None = None
        with self.session_factory() as session:
            from app.db.models import OrgUnit

            org_unit = session.get(OrgUnit, org_unit_id)
            target = session.get(OrgUnit, new_parent_id) if new_parent_id else None
            if not org_unit:
                self.refresh_chart()
                return
            if org_unit.parent_id == new_parent_id:
                self.refresh_chart()
                return
            target_name = target.name if target else "최상위"
            answer = QMessageBox.question(
                self._window,
                "조직 이동 확인",
                f"'{org_unit.name}' 조직을\n'{target_name}' 아래로 옮길까요?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.refresh_chart()
                return
            repository = HrRepository(session)
            previous_parent_id = org_unit.parent_id
            org_name = org_unit.name
            try:
                moved = repository.reparent_org_unit(org_unit_id, new_parent_id)
            except OrgUnitNameConflictError as exc:
                QMessageBox.warning(self._window, "조직 이동 불가", str(exc))
                self.refresh_chart()
                return
            if not moved:
                QMessageBox.warning(
                    self._window,
                    "이동 불가",
                    "자기 자신이나 하위 조직 아래로는 옮길 수 없습니다.",
                )
                self.refresh_chart()
                return
            session.commit()
            summary = f"조직 이동 완료: {org_unit.name} → {target_name} 하위"
        self._push_undo(
            f"'{org_name}' 조직 이동",
            lambda repo, oid=org_unit_id, pid=previous_parent_id: repo.reparent_org_unit(oid, pid),
        )
        self._reexport_excel_if_tracked()
        self.refresh_chart()
        if summary:
            self.status.showMessage(summary, 7000)

    def rename_org_unit(self, org_unit_id: str, new_name: str) -> None:
        from PySide6.QtWidgets import QMessageBox

        from app.db.models import OrgUnit

        old_name: str | None = None
        try:
            with self.session_factory() as session:
                org_unit = session.get(OrgUnit, org_unit_id)
                old_name = org_unit.name if org_unit else None
                HrRepository(session).rename_org_unit(org_unit_id, new_name)
                session.commit()
        except OrgUnitNameConflictError as exc:
            QMessageBox.warning(self._window, "이름 변경 불가", str(exc))
            self.refresh_chart()
            return
        if old_name and old_name != new_name.strip():
            self._push_undo(
                f"'{old_name}' 이름 변경",
                lambda repo, oid=org_unit_id, nm=old_name: repo.rename_org_unit(oid, nm),
            )
        self._reexport_excel_if_tracked()
        self.refresh_chart()

    def save_selected_org_name(self) -> None:
        if not self._selected_org_id:
            return
        new_name = self.name_editor.text().strip()
        if new_name:
            self.rename_org_unit(self._selected_org_id, new_name)

    # ── 실행취소(undo) ────────────────────────────────────────────
    def _push_undo(self, label: str, revert: Callable[[HrRepository], None]) -> None:
        self._undo_stack.append((label, revert))
        # 메모리 무한 증가 방지: 최근 30건만 유지.
        if len(self._undo_stack) > 30:
            self._undo_stack.pop(0)
        button = getattr(self, "_rail_buttons", {}).get("실행취소")
        if button is not None:
            button.setEnabled(True)

    def undo_last(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        if not self._undo_stack:
            if hasattr(self, "status"):
                self.status.showMessage("되돌릴 작업이 없습니다.", 4000)
            return
        label, revert = self._undo_stack.pop()
        try:
            with self.session_factory() as session:
                revert(HrRepository(session))
                session.commit()
        except Exception as exc:
            QMessageBox.warning(
                self._window, "실행취소 실패", f"'{label}'을(를) 되돌리지 못했습니다.\n{exc}"
            )
            return
        button = getattr(self, "_rail_buttons", {}).get("실행취소")
        if button is not None:
            button.setEnabled(bool(self._undo_stack))
        self._reexport_excel_if_tracked()
        self.refresh_chart()
        if hasattr(self, "status"):
            self.status.showMessage(f"실행취소 완료: {label}", 6000)

    def _org_selected_from_list(self, current, previous) -> None:
        if not current:
            return
        from PySide6.QtCore import Qt

        self._selected_org_id = current.data(Qt.ItemDataRole.UserRole)
        self.name_editor.setText(current.text().rsplit(" · ", 1)[0])
        self.show_org_details(self._selected_org_id)

    def update_selection_details(self) -> None:
        if not self.current_scene:
            return
        selected = self.current_scene.selectedItems()
        if not selected:
            return
        item = selected[0]
        item_id = item.data(0)
        item_kind = item.data(1)
        if item_kind == "org":
            self._selected_org_id = item_id
            self.show_org_details(item_id)
        elif item_kind == "employee":
            self.show_employee_details(item_id)
        elif item_kind == "overflow":
            self._selected_org_id = item_id
            self.show_org_details(item_id)

    def show_org_details(self, org_unit_id: str) -> None:
        with self.session_factory() as session:
            from app.db.models import OrgUnit

            org = session.get(OrgUnit, org_unit_id)
            if not org:
                return
            assignments = [
                assignment
                for assignment in HrRepository(session).list_active_assignments()
                if assignment.org_unit_id == org_unit_id
            ]
            leader = next(
                (
                    assignment.employee.name
                    for assignment in assignments
                    if "팀장" in (assignment.employee.title or "")
                    or "본부장" in (assignment.employee.title or "")
                    or "대표" in (assignment.employee.title or "")
                ),
                "미지정",
            )
            parent_name = org.parent.name if org.parent else "최상위 조직"
            member_names = [assignment.employee.name for assignment in assignments]
            member_summary = ", ".join(member_names[:12])
            if len(member_names) > 12:
                member_summary = f"{member_summary}, 외 {len(member_names) - 12}명"
            self.name_editor.setText(org.name)
            self.detail_label.setText(
                "\n".join(
                    [
                        f"조직: {org.name}",
                        f"상위 조직: {parent_name}",
                        f"직속 구성원: {len(assignments)}명",
                        f"리더: {leader}",
                        "구성원: " + member_summary,
                    ]
                )
            )

    def show_employee_details(self, employee_id: str) -> None:
        with self.session_factory() as session:
            from app.db.models import Employee

            employee = session.get(Employee, employee_id)
            if not employee:
                return
            assignment = next(
                (item for item in HrRepository(session).list_active_assignments() if item.employee_id == employee_id),
                None,
            )
            org_name = assignment.org_unit.name if assignment else "미지정"
            self.detail_label.setText(
                "\n".join(
                    filter(
                        None,
                        [
                            f"직원: {employee.name}",
                            f"조직: {org_name}",
                            f"사번: {employee.employee_no}" if employee.employee_no else None,
                            f"이메일: {employee.email}" if employee.email else None,
                            f"직급/직책: {' · '.join(filter(None, [employee.grade, employee.title]))}",
                            f"상태: {employee.status}",
                            f"입사일: {employee.hire_date}" if employee.hire_date else None,
                            f"퇴사일: {employee.resign_date}" if employee.resign_date else None,
                        ],
                    )
                )
            )

    def _exit_candidate_options(self, session, employee_ids: list[str]) -> list[tuple[str, str]]:
        from app.db.models import Employee

        options: list[tuple[str, str]] = []
        for employee_id in employee_ids:
            employee = session.get(Employee, employee_id)
            if employee:
                label_parts = [
                    employee.name,
                    employee.employee_no or "",
                    employee.email or "",
                    employee.status,
                ]
                options.append((employee.id, " · ".join(part for part in label_parts if part)))
        return options

    def _mark_search_matches(self, boxes, query: str) -> None:
        query = query.strip().lower()
        if not query:
            return
        for box in boxes:
            searchable = " ".join(
                filter(
                    None,
                    [
                        box.label,
                        box.meta.get("grade"),
                        box.meta.get("title"),
                        box.meta.get("status"),
                        box.meta.get("employee_no"),
                        box.meta.get("email"),
                    ],
                )
            ).lower()
            if query in searchable:
                box.meta["highlight"] = "true"
