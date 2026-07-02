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
from app.ui.icons import make_icon

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

        # ── 상단 헤더바(앱 아이덴티티 + 그룹화된 아이콘 툴바) ──────────
        self.header_bar = self._build_header_bar()
        if "실행취소" in self._rail_buttons:
            self._rail_buttons["실행취소"].setEnabled(False)

        # ── 좌측: 검색 + 조직 목록 패널 ───────────────────────────────
        self.org_list = QListWidget()
        self.org_list.setAccessibleName("조직 목록")
        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("이름·조직·직책 검색")
        self.search_input.setAccessibleName("조직도 검색")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.addAction(
            make_icon("search"), QLineEdit.ActionPosition.LeadingPosition
        )
        self.search_input.textChanged.connect(self.refresh_chart)
        self.summary_label = QLabel("조직 0 · 구성원 0")
        self.summary_label.setObjectName("summaryPill")
        left = self._build_left_panel()

        # ── 중앙: 조직도 캔버스 ⇄ 명단 표 편집 (스택 전환) ───────────
        self.chart_view = OrgChartView()
        self.chart_view.setAccessibleName("조직도 캔버스")
        self.chart_view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.chart_view.setRenderHints(self.chart_view.renderHints())
        # 리사이즈·표시 시 가독 배율로 자동 정렬(사용자가 직접 줌하기 전까지).
        self.chart_view.reset_view_callback = self.reset_view
        # 캔버스 좌상단 고정 오버레이 타이틀(스크롤·축소와 무관, 뷰포트에 고정).
        self.canvas_title = QLabel("조직도 · 현재 보고 체계", self.chart_view.viewport())
        self.canvas_title.setObjectName("canvasTitle")
        self.canvas_title.adjustSize()
        self.canvas_title.move(16, 12)
        self.canvas_title.raise_()
        self.canvas_title.show()

        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(self.chart_view)              # index 0: 조직도
        self.center_stack.addWidget(self._build_roster_editor())  # index 1: 표 편집
        self.center_stack.addWidget(self._build_empty_state())    # index 2: 빈 상태

        # ── 우측: 표시 항목 토글 + 속성 폼 + 조직명 편집 ───────────
        self.right_panel = self._build_right_panel()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.center_stack)
        splitter.addWidget(self.right_panel)
        splitter.setSizes([308, 872, 300])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setChildrenCollapsible(False)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16, 16, 16, 14)
        body_layout.setSpacing(0)
        body_layout.addWidget(splitter)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.header_bar)
        central_layout.addWidget(body, 1)
        self._window.setCentralWidget(central)

        self.status = self._window.statusBar()
        self.status.showMessage("표준 템플릿(명단·위계) 또는 인사 파일을 가져오면 조직도가 자동 생성됩니다.")
        self.org_list.currentItemChanged.connect(self._org_selected_from_list)
        self.refresh_chart()

    def __getattr__(self, name: str):
        return getattr(self._window, name)

    # ── UI 빌더 ────────────────────────────────────────────────────
    def _rail_button(self, icon_key: str, text: str, tooltip: str, slot, primary: bool = False):
        from PySide6.QtCore import QSize, Qt
        from PySide6.QtWidgets import QToolButton

        button = QToolButton()
        button.setIcon(make_icon(icon_key, primary=primary))
        button.setIconSize(QSize(18, 18))
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if primary:
            button.setText(text)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        else:
            # 아이콘 단독 + 툴팁으로 라벨을 대체(정돈된 헤더 툴바).
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setMinimumHeight(36)
        button.setProperty("primary", primary)
        button.clicked.connect(slot)
        return button

    def _tool_separator(self):
        from PySide6.QtWidgets import QFrame

        sep = QFrame()
        sep.setObjectName("toolSep")
        sep.setFrameShape(QFrame.Shape.VLine)
        return sep

    def _build_header_bar(self):
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

        bar = QWidget()
        bar.setObjectName("headerBar")
        bar.setFixedHeight(60)
        bar.setAccessibleName("주요 작업 헤더")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 16, 0)
        layout.setSpacing(6)

        mark = QLabel()
        mark.setObjectName("appMark")
        title = QLabel("조직도 Studio")
        title.setObjectName("appTitle")
        layout.addWidget(mark)
        layout.addSpacing(8)
        layout.addWidget(title)
        layout.addStretch(1)

        # (아이콘키, 라벨, 툴팁, 슬롯, primary), None = 그룹 구분선.
        specs = [
            ("import", "가져오기", "명단·위계 템플릿 또는 인사 파일을 불러옵니다.", self.import_people_file, True),
            ("template", "템플릿", "표준 조직도 템플릿(명단·위계) Excel을 생성합니다.", self.save_template, False),
            None,
            ("roster", "표 편집", "명단을 표로 편집하고 저장하면 조직도에 반영됩니다.", self.toggle_roster, False),
            ("bulk", "일괄 변환", "부서명을 한 번에 치환합니다(예: 인사팀→피플팀).", self.bulk_convert, False),
            ("undo", "실행취소", "직전의 이동·이름변경·일괄변환을 되돌립니다.", self.undo_last, False),
            None,
            ("pdf", "PDF", "조직도 전체를 한 페이지 PDF로 저장합니다.", self.export_pdf, False),
            ("png", "PNG", "조직도 전체를 고해상도 PNG로 저장합니다.", self.export_png, False),
            ("excel", "Excel", "현재 인사 DB를 Excel로 내보냅니다.", self.export_excel, False),
            None,
            ("fit", "전체 보기", "조직도를 화면에 맞춥니다.", self.fit_chart, False),
        ]
        self._rail_buttons = {}
        for spec in specs:
            if spec is None:
                layout.addWidget(self._tool_separator())
                continue
            icon_key, text, tooltip, slot, primary = spec
            button = self._rail_button(icon_key, text, tooltip, slot, primary)
            self._rail_buttons[text] = button
            layout.addWidget(button)
        return bar

    def _build_left_panel(self):
        from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

        panel = QFrame()
        panel.setObjectName("sidePanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("조직 목록")
        title.setObjectName("panelTitle")
        layout.addWidget(title)
        layout.addWidget(self.search_input)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.org_list, 1)
        return panel

    def _build_display_panel(self):
        from PySide6.QtWidgets import QCheckBox, QGridLayout, QGroupBox

        group = QGroupBox("표시 항목")
        group.setAccessibleName("카드 표시 항목 토글")
        grid = QGridLayout(group)
        grid.setContentsMargins(12, 8, 12, 10)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        self.display_checks = {}
        for index, (field, label) in enumerate(DISPLAY_TOGGLES):
            check = QCheckBox(label)
            check.setChecked(bool(self.display_options.get(field, True)))
            check.setAccessibleName(f"{label} 표시")
            check.stateChanged.connect(self._on_display_toggled)
            self.display_checks[field] = check
            grid.addWidget(check, index // 2, index % 2)
        return group

    def _build_right_panel(self):
        from PySide6.QtWidgets import (
            QFrame,
            QLabel,
            QLineEdit,
            QPushButton,
            QVBoxLayout,
        )

        panel = QFrame()
        panel.setObjectName("sidePanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        layout.addWidget(self._build_display_panel())

        prop_caption = QLabel("속성")
        prop_caption.setObjectName("panelCaption")
        layout.addWidget(prop_caption)

        # 라벨-값 정렬 폼(선택 시 동적으로 행을 채운다).
        self.prop_container = QFrame()
        self.prop_layout = QVBoxLayout(self.prop_container)
        self.prop_layout.setContentsMargins(0, 0, 0, 0)
        self.prop_layout.setSpacing(8)
        self.prop_empty = QLabel("조직이나 직원을 선택하면\n상세 정보가 표시됩니다.")
        self.prop_empty.setObjectName("propEmpty")
        self.prop_empty.setWordWrap(True)
        self.prop_empty.setAccessibleName("선택 상세 정보")
        self.prop_layout.addWidget(self.prop_empty)
        layout.addWidget(self.prop_container)

        layout.addStretch(1)

        name_caption = QLabel("조직명")
        name_caption.setObjectName("panelCaption")
        layout.addWidget(name_caption)
        self.name_editor = QLineEdit()
        self.name_editor.setPlaceholderText("선택 항목 이름")
        self.name_editor.setAccessibleName("조직명 편집")
        self.name_editor.returnPressed.connect(self.save_selected_org_name)
        layout.addWidget(self.name_editor)
        save_name_button = QPushButton("조직명 저장")
        save_name_button.setProperty("primary", True)
        save_name_button.setToolTip("선택한 조직의 이름을 저장합니다.")
        save_name_button.setAccessibleName("조직명 저장")
        save_name_button.clicked.connect(self.save_selected_org_name)
        layout.addWidget(save_name_button)
        return panel

    # ── 속성 폼 갱신 ──────────────────────────────────────────────
    def _clear_property_rows(self) -> None:
        while self.prop_layout.count():
            item = self.prop_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # 레이아웃에서 빼는 것만으로는 부모 자식 관계·기존 위치가 남아
                # 새 행 위에 유령처럼 겹쳐 보인다. 부모를 끊어 즉시 제거한다.
                widget.setParent(None)
                widget.deleteLater()

    def _set_property_rows(self, heading: str, rows: list[tuple[str, str]]) -> None:
        from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

        self._clear_property_rows()
        head = QLabel(heading)
        head.setObjectName("propVal")
        head.setWordWrap(True)
        self.prop_layout.addWidget(head)
        for key, value in rows:
            if not value:
                continue
            row = QWidget()
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(1)
            key_label = QLabel(key)
            key_label.setObjectName("propKey")
            value_label = QLabel(value)
            value_label.setObjectName("propVal")
            value_label.setWordWrap(True)
            row_layout.addWidget(key_label)
            row_layout.addWidget(value_label)
            self.prop_layout.addWidget(row)

    def _build_roster_editor(self):
        from PySide6.QtWidgets import (
            QAbstractItemView,
            QFrame,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QTableWidget,
            QVBoxLayout,
        )

        container = QFrame()
        container.setObjectName("sidePanel")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        header = QHBoxLayout()
        header.setSpacing(8)
        editor_title = QLabel("명단 표 편집 — 셀을 수정한 뒤 저장하면 DB와 조직도에 반영됩니다.")
        editor_title.setObjectName("panelTitle")
        header.addWidget(editor_title)
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
        self.roster_table.verticalHeader().setDefaultSectionSize(38)
        self.roster_table.setWordWrap(False)
        # 컬럼 폭: 내용에 맞추되 남는 폭은 이메일이 흡수 → 뒤 컬럼이 잘려 가로
        # 스크롤을 강요하던 문제 해소.
        from PySide6.QtWidgets import QHeaderView

        header = self.roster_table.horizontalHeader()
        for column_index in range(len(ROSTER_COLUMNS)):
            header.setSectionResizeMode(column_index, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # 이메일
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(72)
        layout.addWidget(self.roster_table, 1)
        return container

    def _build_empty_state(self):
        """데이터가 없을 때 캔버스 자리에 뜨는 온보딩 카드(실제 CTA 버튼 포함)."""
        from PySide6.QtCore import QSize, Qt
        from PySide6.QtWidgets import (
            QFrame,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QVBoxLayout,
            QWidget,
        )

        page = QFrame()
        page.setObjectName("emptyStage")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addStretch(1)

        card = QFrame()
        card.setObjectName("emptyCard")
        card.setMaximumWidth(560)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 40, 40, 40)
        card_layout.setSpacing(14)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        icon_badge = QLabel()
        icon_badge.setObjectName("emptyBadge")
        icon_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_badge.setPixmap(make_icon("import", primary=True).pixmap(QSize(30, 30)))
        icon_badge.setFixedSize(64, 64)
        badge_row = QHBoxLayout()
        badge_row.addStretch(1)
        badge_row.addWidget(icon_badge)
        badge_row.addStretch(1)
        card_layout.addLayout(badge_row)

        title = QLabel("조직도를 시작해 볼까요?")
        title.setObjectName("emptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)

        desc = QLabel(
            "인사 명단 파일(Excel · CSV · JSON)을 가져오면\n조직도가 자동으로 그려집니다."
        )
        desc.setObjectName("emptyDesc")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        card_layout.addWidget(desc)

        steps = QWidget()
        steps_layout = QVBoxLayout(steps)
        steps_layout.setContentsMargins(0, 6, 0, 6)
        steps_layout.setSpacing(8)
        for index, text in enumerate(
            [
                "표준 템플릿을 내려받아 명단을 채웁니다.",
                "‘가져오기’로 채운 파일을 불러옵니다.",
                "조직도가 생성되면 드래그로 인사발령·편집이 가능합니다.",
            ],
            start=1,
        ):
            row = QHBoxLayout()
            row.setSpacing(10)
            num = QLabel(str(index))
            num.setObjectName("emptyStepNum")
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            num.setFixedSize(22, 22)
            step_text = QLabel(text)
            step_text.setObjectName("emptyStepText")
            step_text.setWordWrap(True)
            row.addWidget(num, 0, Qt.AlignmentFlag.AlignTop)
            row.addWidget(step_text, 1)
            steps_layout.addLayout(row)
        card_layout.addWidget(steps)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)
        template_btn = QPushButton("표준 템플릿 받기")
        template_btn.setIcon(make_icon("template"))
        template_btn.setToolTip("표준 조직도 템플릿(명단·위계) Excel을 생성합니다.")
        template_btn.clicked.connect(self.save_template)
        import_btn = QPushButton("인사 파일 가져오기")
        import_btn.setProperty("primary", True)
        import_btn.setIcon(make_icon("import", primary=True))
        import_btn.setToolTip("명단·위계 템플릿 또는 인사 파일을 불러옵니다.")
        import_btn.clicked.connect(self.import_people_file)
        buttons.addWidget(template_btn)
        buttons.addWidget(import_btn)
        buttons.addStretch(1)
        card_layout.addLayout(buttons)

        card_row = QHBoxLayout()
        card_row.addStretch(1)
        card_row.addWidget(card)
        card_row.addStretch(1)
        outer.addLayout(card_row)
        outer.addStretch(1)
        return page

    def _sync_center_and_panels(self, has_data: bool) -> None:
        """데이터 유무·현재 화면에 맞춰 빈 상태 페이지와 우측 패널 노출을 정리한다.

        - 데이터 없음 & 표 편집 아님 → 빈 상태 온보딩(우측 패널 숨김).
        - 데이터 있음 & 빈 상태 표시 중 → 조직도로 복귀.
        - 우측 패널(표시 항목·속성·조직명)은 조직도 화면에서만 의미 있으므로
          표 편집·빈 상태에서는 숨겨 맥락 혼선을 없앤다.
        """
        if not hasattr(self, "center_stack"):
            return
        current = self.center_stack.currentIndex()
        if current == 1:  # 표 편집 화면은 건드리지 않음.
            if hasattr(self, "right_panel"):
                self.right_panel.setVisible(False)
            return
        if not has_data:
            self.center_stack.setCurrentIndex(2)
        elif current == 2:
            self.center_stack.setCurrentIndex(0)
        if hasattr(self, "right_panel"):
            self.right_panel.setVisible(self.center_stack.currentIndex() == 0)

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
            self._layout_boxes = boxes  # reset_view의 카드 경계 스냅에 사용.
            self._mark_search_matches(boxes, query)
            visible_org_ids = {node.id for node in nodes}
            employee_count_by_org = {
                org.id: sum(1 for assignment in assignments if assignment.org_unit_id == org.id)
                for org in org_units
            }
            # 조직 목록을 위계(DFS) 순서로, 하위 포함 인원수와 함께 그린다.
            # (직속만 세면 본부가 '0명'으로 보여 빈 조직처럼 오해되던 문제 해소.)
            from collections import defaultdict

            children_map: dict[str | None, list] = defaultdict(list)
            for org in org_units:
                children_map[org.parent_id].append(org)
            for siblings in children_map.values():
                siblings.sort(key=lambda item: (getattr(item, "display_order", 0), item.name))

            total_count_cache: dict[str, int] = {}

            def total_members(org_id: str) -> int:
                if org_id in total_count_cache:
                    return total_count_cache[org_id]
                subtotal = employee_count_by_org.get(org_id, 0)
                for child in children_map.get(org_id, []):
                    subtotal += total_members(child.id)
                total_count_cache[org_id] = subtotal
                return subtotal

            self.org_list.clear()

            def emit_org(org, depth: int) -> None:
                if query and org.id not in visible_org_ids:
                    return  # 필터에서 숨겨진 조직(및 하위)은 건너뜀.
                direct = employee_count_by_org.get(org.id, 0)
                has_children = bool(children_map.get(org.id))
                total = total_members(org.id)
                # 하위가 있고 총원이 직속과 다르면 총원을 보여 위계 규모를 드러낸다.
                count = total if (has_children and total != direct) else direct
                indent = "    " * depth
                item = QListWidgetItem(f"{indent}{org.name} · {count}명")
                item.setData(Qt.ItemDataRole.UserRole, org.id)
                self.org_list.addItem(item)
                for child in children_map.get(org.id, []):
                    emit_org(child, depth + 1)

            for root in children_map.get(None, []):
                emit_org(root, 0)
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
        # 새 데이터가 그려질 때마다 사용자 줌 상태를 초기화하고 가독 배율로 재정렬한다.
        self.chart_view._user_adjusted = False
        self.reset_view()
        self._sync_center_and_panels(has_data=bool(org_units))
        if hasattr(self, "status"):
            total_people = sum(len(node.employees) for node in nodes)
            if query:
                self.status.showMessage(f"검색 결과: 조직 {len(nodes)}개, 구성원 {total_people}명")
            else:
                self.status.showMessage(f"현재 조직 {len(org_units)}개, 구성원 {total_people}명")

    def _root_center_x(self, boxes, fallback: float) -> float:
        """루트(회사) 카드의 중심 x. 첫 화면 수평 정렬 기준."""
        for box in boxes:
            if box.kind == "summary" or (box.kind == "org" and box.meta.get("is_root") == "true"):
                return box.x + box.width / 2
        return fallback

    def _clean_cut_positions(self, boxes) -> list[float]:
        """카드 내부를 가르지 않는(=카드 사이 '틈'이나 경계에 있는) x 좌표 목록.

        뷰포트 좌우 경계를 이 지점에 맞추면 반쯤 잘린 카드가 생기지 않는다.
        """
        eps = 1.0
        points = {box.x for box in boxes} | {box.x + box.width for box in boxes}
        return sorted(
            pos
            for pos in points
            if not any(box.x + eps < pos < box.x + box.width - eps for box in boxes)
        )

    def _best_clean_span(
        self, cuts: list[float], root_cx: float, vw: float, min_scale: float, max_scale: float
    ) -> tuple[float, float] | None:
        """루트를 포함하면서 좌우 끝이 모두 카드 틈에 떨어지는 최적 수평 구간.

        구간 폭에서 배율(vw/폭)이 가독 범위[min_scale, max_scale]에 들도록 하고,
        그 안에서 가장 넓은(=문맥을 가장 많이 보여주는) 구간을 고른다. 이렇게 고른
        구간을 뷰포트 폭에 정확히 맞추면 좌우 엣지가 카드 경계와 일치해 잘린 카드가 0개다.
        """
        min_span = vw / max_scale
        max_span = vw / min_scale
        best: tuple[float, float] | None = None
        best_score = float("inf")
        for i in range(len(cuts)):
            left = cuts[i]
            if left > root_cx:
                break
            for j in range(i + 1, len(cuts)):
                right = cuts[j]
                if right < root_cx:
                    continue
                span = right - left
                if span < min_span:
                    continue
                if span > max_span:
                    break  # cuts 정렬됨 → 더 오른쪽은 더 넓어 무효.
                # 루트를 최대한 화면 중앙에 두되(주), 넓은 구간에 약간의 가점(부).
                score = abs((left + right) / 2 - root_cx) - 0.05 * span
                if score < best_score:
                    best_score = score
                    best = (left, right)
        return best

    def reset_view(self) -> None:
        """첫 화면·데이터 갱신 시 카드 글자가 읽히는 배율로 조직도를 정렬한다.

        - 전체 트리가 가독 배율(≥0.72) 안에 들어오면: 그대로 맞추고 상단 정렬.
        - 트리가 너무 넓으면: 루트를 포함하는 '카드 틈~카드 틈' 구간을 뷰포트에 정확히
          맞춘다. 좌우 엣지가 카드 경계와 일치해 **반쯤 잘린 카드가 0개**가 되고,
          배율은 가독 범위 안에서 유지된다.
        - 수직: 트리 최상단을 뷰포트 상단에서 ~32px 아래에 정렬(상단 대량 공백 제거).
          트리가 뷰포트보다 짧으면 씬 하단을 넓혀 상단 정렬이 실제로 적용되게 한다.
        """
        if not self.current_scene:
            return
        from PySide6.QtCore import QRectF

        from app.ui.chart_view import INITIAL_MAX_ZOOM, MIN_READABLE_ZOOM

        view = self.chart_view
        scene = self.current_scene
        rect = scene.sceneRect()
        if rect.width() <= 0 or rect.height() <= 0:
            return
        viewport = view.viewport().size()
        vw, vh = float(viewport.width()), float(viewport.height())
        if vw <= 1 or vh <= 1:
            return
        boxes = list(getattr(self, "_layout_boxes", []) or [])
        if boxes:
            content_top = min(box.y for box in boxes)
            content_bottom = max(box.y + box.height for box in boxes)
            content_left = min(box.x for box in boxes)
            content_right = max(box.x + box.width for box in boxes)
        else:
            content_top, content_bottom = rect.top(), rect.bottom()
            content_left, content_right = rect.left(), rect.right()

        # 씬 rect는 패닝 여백까지 포함해 넓으므로, 첫 화면 배율은 콘텐츠 실제 크기 기준.
        content_w = max(1.0, content_right - content_left)
        content_h = max(1.0, content_bottom - content_top)
        fit_scale = min(vw / content_w, vh / content_h)
        root_cx = self._root_center_x(boxes, (content_left + content_right) / 2)

        if fit_scale >= MIN_READABLE_ZOOM or not boxes:
            # 전체가 가독 배율 안에 들어옴.
            scale = min(INITIAL_MAX_ZOOM, fit_scale)
            center_sx = (content_left + content_right) / 2
        else:
            # 트리가 넓음 → 카드 틈에 정확히 맞는 구간을 골라 잘린 카드 0개로.
            cuts = self._clean_cut_positions(boxes)
            span = self._best_clean_span(cuts, root_cx, vw, MIN_READABLE_ZOOM, INITIAL_MAX_ZOOM)
            if span is not None:
                left, right = span
                scale = vw / (right - left)
                center_sx = (left + right) / 2
            else:
                scale = MIN_READABLE_ZOOM
                center_sx = root_cx

        view.resetTransform()
        view.scale(scale, scale)

        # 수직 상단 정렬: 씬이 뷰포트보다 짧으면 centerOn이 강제로 세로 중앙 배치를
        # 하므로, 씬 하단을 넓혀 상단 정렬이 먹히게 한다.
        top_margin = 32.0
        window_h = vh / scale
        needed_bottom = content_top - top_margin / scale + window_h + 24
        if rect.bottom() < needed_bottom:
            rect = QRectF(rect.left(), rect.top(), rect.width(), needed_bottom - rect.top())
            scene.setSceneRect(rect)
        center_sy = content_top + window_h / 2 - top_margin / scale

        view.centerOn(center_sx, center_sy)

    def fit_chart(self) -> None:
        """'전체 보기' 버튼: 조직도 전체를 한 화면에 담는다(사용자 명시적 조작)."""
        if not self.current_scene:
            return
        from PySide6.QtCore import Qt

        self.chart_view._user_adjusted = True
        # 패닝 여백이 포함된 sceneRect가 아니라 실제 콘텐츠 경계에 맞춘다.
        content = self.current_scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self.chart_view.fitInView(content, Qt.AspectRatioMode.KeepAspectRatio)

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
            self.refresh_chart()  # 내부에서 우측 패널·빈 상태를 다시 정리한다.
            return
        self.load_roster()
        self.center_stack.setCurrentIndex(1)
        if hasattr(self, "right_panel"):
            self.right_panel.setVisible(False)
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
        self.name_editor.setText(current.text().rsplit(" · ", 1)[0].strip())
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
            self._set_property_rows(
                org.name,
                [
                    ("상위 조직", parent_name),
                    ("직속 구성원", f"{len(assignments)}명"),
                    ("리더", leader),
                    ("구성원", member_summary),
                ],
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
            self._set_property_rows(
                employee.name,
                [
                    ("소속", org_name),
                    ("사번", employee.employee_no or ""),
                    ("이메일", employee.email or ""),
                    ("직급/직책", " · ".join(filter(None, [employee.grade, employee.title]))),
                    ("상태", employee.status or ""),
                    ("입사일", employee.hire_date or ""),
                    ("퇴사일", employee.resign_date or ""),
                ],
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
