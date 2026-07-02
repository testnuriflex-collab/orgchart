from __future__ import annotations

from collections.abc import Callable

from app.chart.layout import LayoutBox

MIN_ZOOM = 0.25
MAX_ZOOM = 3.0

CANVAS = "#F7F7F7"
INK = "#222222"
MUTED = "#4A4A4A"
SUBTLE = "#8A918D"
HAIRLINE = "#DDDDDD"
SURFACE = "#FFFFFF"
SURFACE_SOFT = "#FBFBFA"
HIGHLIGHT_TINT = "#FFF7F8"
ACCENT = "#A0002A"
SUCCESS = "#0F7B45"
ROOT = "#3F3F3F"
CONNECTOR = "#C8C8C8"


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
        else:
            content_rect = scene.itemsBoundingRect()
            title = QGraphicsTextItem("조직도")
            title.setDefaultTextColor(QColor(INK))
            title.setFont(QFont("Paperlogy", 24, QFont.Weight.Bold))
            title.setTextWidth(760)
            title.setPos(content_rect.center().x() - 380, content_rect.top() - 82)
            scene.addItem(title)
            subtitle = QGraphicsTextItem("현재 보고 체계")
            subtitle.setDefaultTextColor(QColor(SUBTLE))
            subtitle.setFont(QFont("Paperlogy", 10, QFont.Weight.Medium))
            subtitle.setTextWidth(760)
            subtitle.setPos(content_rect.center().x() - 380, content_rect.top() - 48)
            scene.addItem(subtitle)

        scene.setSceneRect(scene.itemsBoundingRect().adjusted(-96, -88, 96, 96))
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
        _prepare_hit_rect(self.group)
        self.group.setAcceptDrops(True)
        self.group.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        if can_reparent:
            self.group.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        _rounded_rect_item(
            self.group,
            box.x,
            box.y,
            box.width,
            box.height,
            14,
            ROOT if is_root else (HIGHLIGHT_TINT if is_highlighted else SURFACE),
            ACCENT if is_highlighted else HAIRLINE,
            2 if is_highlighted else 1,
        )

        if not is_root:
            indicator = QGraphicsRectItem(box.x + 16, box.y + 16, 34, 4, self.group)
            indicator_color = ACCENT if is_highlighted else SUCCESS
            indicator.setBrush(QBrush(QColor(indicator_color)))
            indicator.setPen(QPen(QColor(indicator_color), 1))

        title_font = QFont("Paperlogy", 14, QFont.Weight.DemiBold)
        title = QGraphicsTextItem(elide_text(box.label, title_font, box.width - 32), self.group)
        title.setToolTip(box.label)
        title.setDefaultTextColor(QColor("#FFFFFF" if is_root else INK))
        title.setFont(title_font)
        title.setTextWidth(box.width - 32)
        title.setPos(box.x + 16, box.y + (22 if is_root else 28))

        count = box.meta.get("employee_count") or "0"
        hint = QGraphicsTextItem(("최상위 조직" if is_root else f"구성원 {count}명"), self.group)
        hint.setDefaultTextColor(QColor("#EDEDED" if is_root else MUTED))
        hint.setFont(QFont("Paperlogy", 10, QFont.Weight.Normal))
        hint.setTextWidth(box.width - 32)
        hint.setPos(box.x + 16, box.y + (55 if is_root else 60))
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
        _rounded_rect_item(self.group, box.x, box.y, box.width, box.height, 14, SURFACE, HAIRLINE)
        indicator = QGraphicsRectItem(box.x + 16, box.y + 16, 34, 4, self.group)
        indicator.setBrush(QBrush(QColor(ROOT)))
        indicator.setPen(QPen(QColor(ROOT), 1))

        title = QGraphicsTextItem(box.label, self.group)
        title.setDefaultTextColor(QColor(INK))
        title.setFont(QFont("Paperlogy", 14, QFont.Weight.DemiBold))
        title.setTextWidth(box.width - 32)
        title.setPos(box.x + 16, box.y + 28)

        hint = QGraphicsTextItem("전체 조직", self.group)
        hint.setDefaultTextColor(QColor(MUTED))
        hint.setFont(QFont("Paperlogy", 10))
        hint.setTextWidth(box.width - 32)
        hint.setPos(box.x + 16, box.y + 60)
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
        _rounded_rect_item(
            self.item,
            box.x,
            box.y,
            box.width,
            box.height,
            12,
            HIGHLIGHT_TINT if is_highlighted else SURFACE,
            ACCENT if is_highlighted else HAIRLINE,
            2 if is_highlighted else 1,
        )
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

        bar = QGraphicsRectItem(box.x + 1, box.y + 12, 4, box.height - 24, self.item)
        bar_color = ACCENT if is_highlighted else SUCCESS
        bar.setBrush(QBrush(QColor(bar_color)))
        bar.setPen(QPen(QColor(bar_color), 1))

        self.text_items = []

        name_font = QFont("Paperlogy", 13, QFont.Weight.DemiBold)
        name_text = elide_text(box.label, name_font, box.width - 38) if options.get("name", True) else ""
        name = QGraphicsTextItem(name_text, self.item)
        if options.get("name", True):
            name.setToolTip(box.label)
        name.setDefaultTextColor(QColor(INK))
        name.setFont(name_font)
        name.setTextWidth(box.width - 38)
        name.setPos(box.x + 28, box.y + 28)
        self.text_items.append(name)

        meta_parts: list[str] = []
        if options.get("grade", True):
            meta_parts.append(box.meta.get("grade") or "")
        if options.get("title", True):
            meta_parts.append(box.meta.get("title") or "")
        if options.get("department", False):
            meta_parts.append(box.meta.get("department") or "")
        meta_text = " · ".join(part for part in meta_parts if part) or "직원"
        meta = QGraphicsTextItem(meta_text, self.item)
        meta.setDefaultTextColor(QColor(MUTED))
        meta.setFont(QFont("Paperlogy", 10, QFont.Weight.Normal))
        meta.setTextWidth(box.width - 38)
        meta.setPos(box.x + 28, box.y + 8)
        self.text_items.append(meta)

        identity_value = ""
        if options.get("email", False) and box.meta.get("email"):
            identity_value = box.meta.get("email") or ""
        elif options.get("employee_no", True) and box.meta.get("employee_no"):
            identity_value = box.meta.get("employee_no") or ""
        identity = QGraphicsTextItem(identity_value, self.item)
        identity.setDefaultTextColor(QColor(SUBTLE))
        identity.setFont(QFont("Paperlogy", 9))
        identity.setTextWidth(box.width - 38)
        identity.setPos(box.x + 28, box.y + 50)
        self.text_items.append(identity)

        if options.get("status", True):
            status = QGraphicsTextItem(box.meta.get("status") or "재직", self.item)
            status_color = SUCCESS if (box.meta.get("status") or "재직") == "재직" else ACCENT
            status.setDefaultTextColor(QColor(status_color))
            status.setFont(QFont("Paperlogy", 9, QFont.Weight.Medium))
            status.setPos(box.x + box.width - 46, box.y + 8)
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
        _rounded_rect_item(
            self.item,
            box.x,
            box.y,
            box.width,
            box.height,
            12,
            HIGHLIGHT_TINT if is_highlighted else SURFACE_SOFT,
            ACCENT if is_highlighted else HAIRLINE,
            2 if is_highlighted else 1,
        )
        tooltip = "접힌 구성원은 오른쪽 조직 상세에서 확인합니다."
        if box.meta.get("employee_names"):
            tooltip = f"{tooltip}\n{box.meta['employee_names']}"
        self.item.setToolTip(tooltip)

        bar = QGraphicsRectItem(box.x + 1, box.y + 12, 4, box.height - 24, self.item)
        overflow_bar = ACCENT if is_highlighted else SUBTLE
        bar.setBrush(QBrush(QColor(overflow_bar)))
        bar.setPen(QPen(QColor(overflow_bar), 1))

        label = QGraphicsTextItem(box.label, self.item)
        label.setDefaultTextColor(QColor(INK))
        label.setFont(QFont("Paperlogy", 13, QFont.Weight.DemiBold))
        label.setTextWidth(box.width - 38)
        label.setPos(box.x + 28, box.y + 18)

        hint = QGraphicsTextItem("조직 상세 보기", self.item)
        hint.setDefaultTextColor(QColor(MUTED))
        hint.setFont(QFont("Paperlogy", 10))
        hint.setTextWidth(box.width - 38)
        hint.setPos(box.x + 28, box.y + 44)
        self.text_items = [label, hint]
        self.graphics_item = self.item

    def __getattr__(self, name: str):
        return getattr(self.item, name)


class OrgChartViewMixin:
    def wheelEvent(self, event):  # noqa: N802
        from PySide6.QtCore import Qt

        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            raw_factor = 1.15 if event.angleDelta().y() > 0 else 0.87
            factor = clamped_zoom_factor(self.transform().m11(), raw_factor)
            self.scale(factor, factor)
            event.accept()
            return
        super().wheelEvent(event)
