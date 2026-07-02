from __future__ import annotations

from collections.abc import Callable

from app.chart.layout import LayoutBox

MIN_ZOOM = 0.1
MAX_ZOOM = 3.0
# 첫 화면에서 카드 글자가 읽히도록 강제하는 배율 하한/상한.
# 넓은 조직은 전체를 한눈에 넣으려다 글자가 뭉개지므로, 가독 하한 아래로는
# 축소하지 않고 상단 중앙 정렬 후 스크롤로 탐색하게 한다.
MIN_READABLE_ZOOM = 0.72
INITIAL_MAX_ZOOM = 1.05

# 조직도 캔버스 색 토큰 (styles.TOKENS와 정렬).
CANVAS = "#F1F3F6"
INK = "#1B1F27"
MUTED = "#6B7280"
SUBTLE = "#9AA1AC"
HAIRLINE = "#E4E7EC"
HAIRLINE_STRONG = "#D3D8DF"
SURFACE = "#FFFFFF"
SURFACE_SOFT = "#F6F8FA"
HIGHLIGHT_TINT = "#E7EEFD"  # 검색 매치 카드 연한 블루 틴트
ACCENT = "#1D4ED8"          # 브랜드 블루 (styles.TOKENS['accent']와 정렬)
ACCENT_SOFT = "#E7EEFD"
SUCCESS = "#1D4ED8"         # 재직 등 긍정 상태 인디케이터(블루로 통일)
ROOT = "#12294A"           # 회사(최상위) 카드 배경 — 딥 네이비
DIVISION = "#1D4ED8"       # 본부(depth 1) 레벨 표시색 — 블루
TEAM = "#64748B"           # 팀(depth 2+) 레벨 표시색 — 슬레이트(중성·약한 블루)
CONNECTOR = "#C1CAD8"      # 커넥터 라인 — 뉴트럴 블루그레이
SHADOW = (17, 22, 33, 46)  # 미세 드롭섀도 RGBA


def elide_text(text: str, font: object, max_width: float) -> str:
    """카드 폭을 넘는 긴 이름을 오른쪽 말줄임(…)으로 잘라 클리핑을 막는다."""
    if not text:
        return text
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFontMetrics

    metrics = QFontMetrics(font)
    if metrics.horizontalAdvance(text) <= max_width:
        return text
    return metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(0, int(max_width)))


def clamped_zoom_factor(current_zoom: float, raw_factor: float) -> float:
    if current_zoom <= 0:
        return 1.0
    target_zoom = max(MIN_ZOOM, min(MAX_ZOOM, current_zoom * raw_factor))
    return target_zoom / current_zoom


DEFAULT_DISPLAY_OPTIONS: dict[str, bool] = {
    "name": True,
    "title": True,
    "grade": True,
    "department": False,
    "employee_no": True,
    "email": False,
    "status": True,
}


class ChartSceneBuilder:
    def __init__(
        self,
        move_employee_callback: Callable[[str, str], None],
        rename_org_callback: Callable[[str, str], None],
        reparent_org_callback: Callable[[str, str | None], None] | None = None,
        display_options: dict[str, bool] | None = None,
    ) -> None:
        self.move_employee_callback = move_employee_callback
        self.rename_org_callback = rename_org_callback
        self.reparent_org_callback = reparent_org_callback
        self.display_options = {**DEFAULT_DISPLAY_OPTIONS, **(display_options or {})}

    def build(self, boxes: list[LayoutBox]):
        from PySide6.QtGui import QBrush, QColor, QFont
        from PySide6.QtWidgets import QGraphicsScene, QGraphicsTextItem

        scene = QGraphicsScene()
        card_items: list[SummaryCardItem | OrgCardItem | EmployeeCardItem | OverflowCardItem] = []
        box_by_id = {box.id: box for box in boxes}

        self._draw_connectors(scene, boxes, box_by_id)
        for box in boxes:
            if box.kind == "summary":
                item = SummaryCardItem(box)
                scene.addItem(item.graphics_item)
            elif box.kind == "org":
                item = OrgCardItem(box, self.rename_org_callback, self.reparent_org_callback)
                scene.addItem(item.graphics_item)
            elif box.kind == "employee":
                item = EmployeeCardItem(box, self.move_employee_callback, self.display_options)
                scene.addItem(item.graphics_item)
            else:
                item = OverflowCardItem(box)
                scene.addItem(item.graphics_item)
            card_items.append(item)

        if not boxes:
            empty = QGraphicsTextItem(
                "인사 파일을 가져오면 조직도가 생성됩니다.\n"
                "표준 양식 Excel, CSV, JSON은 자동으로 DB에 반영됩니다."
            )
            empty.setDefaultTextColor(QColor("#4A4A4A"))
            empty.setFont(QFont("Paperlogy", 16, QFont.Weight.Medium))
            empty.setTextWidth(520)
            empty.setPos(48, 48)
            scene.addItem(empty)
        # 캔버스 타이틀은 씬 아이템으로 두면 스크롤·축소에 휩쓸리고 루트 카드와
        # 시각 충돌한다. 뷰에 고정된 오버레이 라벨(#canvasTitle)로 옮겼다.

        # 씬 rect를 콘텐츠보다 넉넉히 확장해 자유로운 줌·패닝(무한 캔버스 감각)을 준다.
        # 첫 화면 정렬은 콘텐츠 실제 경계 기준(reset_view)이므로 이 여백에 영향받지 않는다.
        content = scene.itemsBoundingRect()
        pad_x = max(1400.0, content.width() * 0.75)
        pad_y = max(900.0, content.height() * 0.75)
        scene.setSceneRect(content.adjusted(-pad_x, -pad_y, pad_x, pad_y))
        scene.setBackgroundBrush(QBrush(QColor(CANVAS)))
        scene._org_chart_card_items = card_items
        return scene

    def _draw_connectors(self, scene, boxes: list[LayoutBox], box_by_id: dict[str, LayoutBox]) -> None:
        from collections import defaultdict

        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QPen

        line_pen = QPen(QColor(CONNECTOR), 1.0)
        line_pen.setCosmetic(True)
        line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        line_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        def anchor(box: LayoutBox, key: str, fallback: float) -> float:
            raw_value = box.meta.get(key)
            return float(raw_value) if raw_value is not None else fallback

        def add_line(x1: float, y1: float, x2: float, y2: float) -> None:
            line = scene.addLine(x1, y1, x2, y2, line_pen)
            line.setZValue(-1)

        org_children: dict[str, list[LayoutBox]] = defaultdict(list)
        member_children: dict[str, list[LayoutBox]] = defaultdict(list)
        for box in boxes:
            if not box.parent_id:
                continue
            if box.kind == "org":
                org_children[box.parent_id].append(box)
            elif box.kind in {"employee", "overflow"}:
                member_children[box.parent_id].append(box)

        for parent_id, children in org_children.items():
            parent = box_by_id.get(parent_id)
            if not parent:
                continue
            children.sort(key=lambda item: item.x)
            parent_center_x = anchor(parent, "connector_bottom_x", parent.x + parent.width / 2)
            parent_bottom_y = anchor(parent, "connector_bottom_y", parent.y + parent.height)
            branch_y = min(child.y for child in children) - 36
            add_line(parent_center_x, parent_bottom_y, parent_center_x, branch_y)
            if len(children) > 1:
                first_x = anchor(children[0], "connector_top_x", children[0].x + children[0].width / 2)
                last_x = anchor(children[-1], "connector_top_x", children[-1].x + children[-1].width / 2)
                add_line(first_x, branch_y, last_x, branch_y)
            for child in children:
                child_center_x = anchor(child, "connector_top_x", child.x + child.width / 2)
                child_top_y = anchor(child, "connector_top_y", child.y)
                add_line(child_center_x, branch_y, child_center_x, child_top_y)

        for parent_id, members in member_children.items():
            parent = box_by_id.get(parent_id)
            if not parent:
                continue
            members.sort(key=lambda item: item.y)
            parent_bottom_y = anchor(parent, "connector_bottom_y", parent.y + parent.height)
            spine_x = min(member.x for member in members) - 16
            start_y = parent_bottom_y + 14
            last_y = members[-1].y + members[-1].height / 2
            parent_center_x = anchor(parent, "connector_bottom_x", parent.x + parent.width / 2)
            add_line(parent_center_x, parent_bottom_y, parent_center_x, start_y)
            add_line(parent_center_x, start_y, spine_x, start_y)
            add_line(spine_x, start_y, spine_x, last_y)
            for member in members:
                member_center_y = member.y + member.height / 2
                add_line(spine_x, member_center_y, member.x, member_center_y)


def _rounded_rect_item(
    parent,
    x: float,
    y: float,
    width: float,
    height: float,
    radius: float,
    fill_color: str,
    border_color: str,
    border_width: float = 1.0,
):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen
    from PySide6.QtWidgets import QGraphicsPathItem

    path = QPainterPath()
    path.addRoundedRect(QRectF(x, y, width, height), radius, radius)
    item = QGraphicsPathItem(path, parent)
    item.setBrush(QBrush(QColor(fill_color)))
    item.setPen(QPen(QColor(border_color), border_width))
    item.setZValue(-0.2)
    return item


def _prepare_hit_rect(rect) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QBrush, QPen

    rect.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    rect.setPen(QPen(Qt.PenStyle.NoPen))


def _apply_soft_shadow(item, blur: float = 18.0, dy: float = 4.0) -> None:
    """카드에 미세한 드롭섀도를 입혀 캔버스에서 떠 보이게 한다."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QGraphicsDropShadowEffect

    effect = QGraphicsDropShadowEffect()
    effect.setBlurRadius(blur)
    effect.setColor(QColor(*SHADOW))
    effect.setOffset(0, dy)
    item.setGraphicsEffect(effect)


class OrgCardItem:
    def __init__(
        self,
        box: LayoutBox,
        rename_callback: Callable[[str, str], None],
        reparent_callback: Callable[[str, str | None], None] | None = None,
    ) -> None:
        from PySide6.QtGui import QBrush, QColor, QFont, QPen
        from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsTextItem

        is_root = box.meta.get("is_root") == "true" and not box.parent_id
        can_reparent = reparent_callback is not None and not is_root

        class ReparentableOrgRect(QGraphicsRectItem):
            def mouseReleaseEvent(inner_self, event):  # noqa: N802
                super().mouseReleaseEvent(event)
                if not can_reparent:
                    return
                scene = inner_self.scene()
                if scene is None:
                    return
                center = inner_self.sceneBoundingRect().center()
                for candidate in scene.items(center):
                    if candidate.data(1) != "org":
                        continue
                    target_id = candidate.data(0)
                    if target_id and target_id != box.id:
                        reparent_callback(box.id, target_id)
                        return

        self.group = ReparentableOrgRect(box.x, box.y, box.width, box.height)
        self.group.setData(0, box.id)
        self.group.setData(1, "org")
        is_highlighted = bool(box.meta.get("highlight"))
        level = box.meta.get("level") or ("company" if is_root else "team")
        _prepare_hit_rect(self.group)
        self.group.setAcceptDrops(True)
        self.group.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        if can_reparent:
            self.group.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)

        # 레벨별 색 구분: 회사=다크, 본부=액센트, 팀=중성.
        if is_root:
            fill_color = ROOT
            border_color = ROOT
            level_color = "#FFFFFF"
        else:
            fill_color = HIGHLIGHT_TINT if is_highlighted else SURFACE
            border_color = ACCENT if is_highlighted else HAIRLINE_STRONG
            level_color = DIVISION if level == "division" else TEAM
            if is_highlighted:
                level_color = ACCENT
        card = _rounded_rect_item(
            self.group,
            box.x,
            box.y,
            box.width,
            box.height,
            14,
            fill_color,
            border_color,
            2 if is_highlighted else 1,
        )
        _apply_soft_shadow(card, blur=22 if is_root else 16, dy=5 if is_root else 3)

        # 레벨 표시 바(좌상단). 회사는 흰 점, 본부·팀은 색으로 위계 구분.
        indicator = QGraphicsRectItem(box.x + 18, box.y + 18, 30, 4, self.group)
        indicator.setBrush(QBrush(QColor(level_color)))
        indicator.setPen(QPen(QColor(level_color), 0))

        level_label = {"company": "회사", "division": "본부", "team": "팀"}.get(level, "")
        if level_label:
            tag = QGraphicsTextItem(level_label, self.group)
            tag.setDefaultTextColor(QColor("#C7CBD3" if is_root else SUBTLE))
            tag.setFont(QFont("Paperlogy", 8, QFont.Weight.Bold))
            tag.setPos(box.x + box.width - 44, box.y + 14)

        title_font = QFont("Paperlogy", 15, QFont.Weight.Bold)
        title = QGraphicsTextItem(elide_text(box.label, title_font, box.width - 36), self.group)
        title.setToolTip(box.label)
        title.setDefaultTextColor(QColor("#FFFFFF" if is_root else INK))
        title.setFont(title_font)
        title.setTextWidth(box.width - 36)
        title.setPos(box.x + 18, box.y + 34)

        count = box.meta.get("employee_count") or "0"
        hint = QGraphicsTextItem(("최상위 조직" if is_root else f"구성원 {count}명"), self.group)
        hint.setDefaultTextColor(QColor("#B9BEC7" if is_root else MUTED))
        hint.setFont(QFont("Paperlogy", 11, QFont.Weight.Medium))
        hint.setTextWidth(box.width - 36)
        hint.setPos(box.x + 18, box.y + 64)
        self.text_items = [title, hint]
        self.graphics_item = self.group

    def __getattr__(self, name: str):
        return getattr(self.group, name)


class SummaryCardItem:
    def __init__(self, box: LayoutBox) -> None:
        from PySide6.QtGui import QBrush, QColor, QFont, QPen
        from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsTextItem

        self.group = QGraphicsRectItem(box.x, box.y, box.width, box.height)
        self.group.setData(0, box.id)
        self.group.setData(1, "summary")
        _prepare_hit_rect(self.group)
        self.group.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        card = _rounded_rect_item(self.group, box.x, box.y, box.width, box.height, 14, ROOT, ROOT)
        _apply_soft_shadow(card, blur=22, dy=5)
        indicator = QGraphicsRectItem(box.x + 18, box.y + 18, 30, 4, self.group)
        indicator.setBrush(QBrush(QColor("#FFFFFF")))
        indicator.setPen(QPen(QColor("#FFFFFF"), 0))

        title = QGraphicsTextItem(box.label, self.group)
        title.setDefaultTextColor(QColor("#FFFFFF"))
        title.setFont(QFont("Paperlogy", 15, QFont.Weight.Bold))
        title.setTextWidth(box.width - 36)
        title.setPos(box.x + 18, box.y + 34)

        hint = QGraphicsTextItem("전체 조직", self.group)
        hint.setDefaultTextColor(QColor("#B9BEC7"))
        hint.setFont(QFont("Paperlogy", 11, QFont.Weight.Medium))
        hint.setTextWidth(box.width - 36)
        hint.setPos(box.x + 18, box.y + 64)
        self.text_items = [title, hint]
        self.graphics_item = self.group

    def __getattr__(self, name: str):
        return getattr(self.group, name)


class EmployeeCardItem:
    def __init__(
        self,
        box: LayoutBox,
        move_callback: Callable[[str, str], None],
        display_options: dict[str, bool] | None = None,
    ) -> None:
        from PySide6.QtGui import QBrush, QColor, QFont, QPen
        from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsTextItem

        self.box = box
        self.move_callback = move_callback
        options = {**DEFAULT_DISPLAY_OPTIONS, **(display_options or {})}

        class MovableEmployeeRect(QGraphicsRectItem):
            def mouseReleaseEvent(inner_self, event):  # noqa: N802
                super().mouseReleaseEvent(event)
                scene = inner_self.scene()
                if scene is None:
                    return
                center = inner_self.sceneBoundingRect().center()
                for candidate in scene.items(center):
                    if candidate is inner_self:
                        continue
                    if candidate.data(1) == "org":
                        move_callback(box.id, candidate.data(0))
                        return

        self.item = MovableEmployeeRect(box.x, box.y, box.width, box.height)
        self.item.setData(0, box.id)
        self.item.setData(1, "employee")
        is_highlighted = bool(box.meta.get("highlight"))
        _prepare_hit_rect(self.item)
        self.item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        card = _rounded_rect_item(
            self.item,
            box.x,
            box.y,
            box.width,
            box.height,
            12,
            HIGHLIGHT_TINT if is_highlighted else SURFACE,
            ACCENT if is_highlighted else HAIRLINE_STRONG,
            2 if is_highlighted else 1,
        )
        _apply_soft_shadow(card, blur=11, dy=2)
        self.item.setToolTip(
            "\n".join(
                filter(
                    None,
                    [
                        box.label,
                        " · ".join(filter(None, [box.meta.get("grade"), box.meta.get("title")])),
                        box.meta.get("email") or box.meta.get("employee_no"),
                        box.meta.get("status"),
                    ],
                )
            )
        )

        status_value = box.meta.get("status") or "재직"
        is_active = status_value == "재직"
        bar = QGraphicsRectItem(box.x, box.y + 12, 4, box.height - 24, self.item)
        bar_color = ACCENT if is_highlighted else (SUCCESS if is_active else TEAM)
        bar.setBrush(QBrush(QColor(bar_color)))
        bar.setPen(QPen(QColor(bar_color), 0))

        self.text_items = []
        text_x = box.x + 22
        text_w = box.width - 34

        name_font = QFont("Paperlogy", 13, QFont.Weight.Bold)
        name_text = elide_text(box.label, name_font, text_w - 40) if options.get("name", True) else ""
        name = QGraphicsTextItem(name_text, self.item)
        if options.get("name", True):
            name.setToolTip(box.label)
        name.setDefaultTextColor(QColor(INK))
        name.setFont(name_font)
        name.setTextWidth(text_w)
        name.setPos(text_x, box.y + 13)
        self.text_items.append(name)

        meta_parts: list[str] = []
        if options.get("grade", True):
            meta_parts.append(box.meta.get("grade") or "")
        if options.get("title", True):
            meta_parts.append(box.meta.get("title") or "")
        if options.get("department", False):
            meta_parts.append(box.meta.get("department") or "")
        meta_text = " · ".join(part for part in meta_parts if part) or "직원"
        meta = QGraphicsTextItem(elide_text(meta_text, QFont("Paperlogy", 11), text_w), self.item)
        meta.setDefaultTextColor(QColor(MUTED))
        meta.setFont(QFont("Paperlogy", 11, QFont.Weight.Normal))
        meta.setTextWidth(text_w)
        meta.setPos(text_x, box.y + 35)
        self.text_items.append(meta)

        identity_value = ""
        if options.get("email", False) and box.meta.get("email"):
            identity_value = box.meta.get("email") or ""
        elif options.get("employee_no", True) and box.meta.get("employee_no"):
            identity_value = box.meta.get("employee_no") or ""
        identity = QGraphicsTextItem(elide_text(identity_value, QFont("Paperlogy", 10), text_w), self.item)
        identity.setDefaultTextColor(QColor(SUBTLE))
        identity.setFont(QFont("Paperlogy", 10))
        identity.setTextWidth(text_w)
        identity.setPos(text_x, box.y + 53)
        self.text_items.append(identity)

        if options.get("status", True):
            status = QGraphicsTextItem(status_value, self.item)
            status.setDefaultTextColor(QColor(SUCCESS if is_active else MUTED))
            status.setFont(QFont("Paperlogy", 10, QFont.Weight.Bold))
            status.setPos(box.x + box.width - 48, box.y + 13)
            self.text_items.append(status)
        self.graphics_item = self.item

    def __getattr__(self, name: str):
        return getattr(self.item, name)


class OverflowCardItem:
    def __init__(self, box: LayoutBox) -> None:
        from PySide6.QtGui import QBrush, QColor, QFont, QPen
        from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsTextItem

        self.item = QGraphicsRectItem(box.x, box.y, box.width, box.height)
        self.item.setData(0, box.meta.get("org_id"))
        self.item.setData(1, "overflow")
        is_highlighted = bool(box.meta.get("highlight"))
        _prepare_hit_rect(self.item)
        self.item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        card = _rounded_rect_item(
            self.item,
            box.x,
            box.y,
            box.width,
            box.height,
            12,
            HIGHLIGHT_TINT if is_highlighted else SURFACE_SOFT,
            ACCENT if is_highlighted else HAIRLINE_STRONG,
            2 if is_highlighted else 1,
        )
        _apply_soft_shadow(card, blur=11, dy=2)
        tooltip = "접힌 구성원은 오른쪽 조직 상세에서 확인합니다."
        if box.meta.get("employee_names"):
            tooltip = f"{tooltip}\n{box.meta['employee_names']}"
        self.item.setToolTip(tooltip)

        bar = QGraphicsRectItem(box.x, box.y + 12, 4, box.height - 24, self.item)
        overflow_bar = ACCENT if is_highlighted else SUBTLE
        bar.setBrush(QBrush(QColor(overflow_bar)))
        bar.setPen(QPen(QColor(overflow_bar), 0))

        label = QGraphicsTextItem(box.label, self.item)
        label.setDefaultTextColor(QColor(ACCENT if is_highlighted else INK))
        label.setFont(QFont("Paperlogy", 13, QFont.Weight.Bold))
        label.setTextWidth(box.width - 34)
        label.setPos(box.x + 22, box.y + 18)

        hint = QGraphicsTextItem("조직 상세에서 전체 보기", self.item)
        hint.setDefaultTextColor(QColor(MUTED))
        hint.setFont(QFont("Paperlogy", 10, QFont.Weight.Medium))
        hint.setTextWidth(box.width - 34)
        hint.setPos(box.x + 22, box.y + 42)
        self.text_items = [label, hint]
        self.graphics_item = self.item

    def __getattr__(self, name: str):
        return getattr(self.item, name)


class OrgChartViewMixin:
    # 자동 초기 정렬 콜백(MainWindow.reset_view). 사용자가 직접 줌/전체보기를
    # 하기 전까지는 리사이즈·표시 시점에 재정렬해 첫 화면 배율을 보장한다.
    reset_view_callback: Callable[[], None] | None = None
    _user_adjusted = False

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if self.reset_view_callback and not self._user_adjusted and self.scene():
            self.reset_view_callback()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if self.reset_view_callback and not self._user_adjusted and self.scene():
            self.reset_view_callback()

    def wheelEvent(self, event):  # noqa: N802
        # 보조키 없이 휠만으로 커서 기준 줌(AnchorUnderMouse). Ctrl+휠도 동일 동작.
        # 스크롤이 필요하면 빈 공간 드래그(손바닥 패닝, ScrollHandDrag)로 이동한다.
        from PySide6.QtWidgets import QGraphicsView

        previous_anchor = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        raw_factor = 1.15 if event.angleDelta().y() > 0 else 0.87
        factor = clamped_zoom_factor(self.transform().m11(), raw_factor)
        self.scale(factor, factor)
        self.setTransformationAnchor(previous_anchor)
        self._user_adjusted = True
        event.accept()
