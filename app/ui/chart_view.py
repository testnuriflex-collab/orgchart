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
NEON = "#25E7FF"           # 네온 강조 색 — 다크/블루 테마와 어울리는 시안 네온
NEON_PULSE_MS = 560        # 한 번의 네온 펄스(들숨·날숨) 길이(ms)
NEON_PULSE_COUNT = 2       # 총 펄스 횟수 (~1.1초, 요구 0.6~1.2초 범위)


def pulse_neon_glow(item, duration_ms: int = NEON_PULSE_MS, pulses: int = NEON_PULSE_COUNT):
    """지정한 그래픽 아이템에 시안 네온 글로우 펄스를 입힌다.

    CSS box-shadow 대신 QGraphicsDropShadowEffect(offset 0 · 큰 blur · 채도 높은
    시안)로 카드 둘레에 발광 헤일로를 만들고, blurRadius를 base→peak→base로 반복
    애니메이션해 은은한 네온 펄스를 연출한다. 펄스가 끝나면 이펙트를 제거해 카드를
    원상 복구한다. 반환한 (effect, animation)은 호출부가 참조를 유지해야 GC로
    애니메이션이 조기 중단되지 않는다.
    """
    from PySide6.QtCore import QEasingCurve, QPropertyAnimation
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QGraphicsDropShadowEffect

    glow = QGraphicsDropShadowEffect()
    glow.setOffset(0, 0)
    glow.setColor(QColor(NEON))
    glow.setBlurRadius(4.0)
    item.setGraphicsEffect(glow)

    anim = QPropertyAnimation(glow, b"blurRadius")
    anim.setDuration(duration_ms)
    anim.setLoopCount(pulses)
    anim.setKeyValueAt(0.0, 6.0)
    anim.setKeyValueAt(0.5, 56.0)
    anim.setKeyValueAt(1.0, 6.0)
    anim.setEasingCurve(QEasingCurve.Type.InOutSine)

    def _cleanup() -> None:
        # 펄스 종료 후 글로우 제거(카드 원상 복구). 아이템이 이미 사라졌으면 무시.
        try:
            item.setGraphicsEffect(None)
        except RuntimeError:
            pass

    anim.finished.connect(_cleanup)
    anim.start()
    return glow, anim


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
        refresh_callback: Callable[[], None] | None = None,
    ) -> None:
        self.move_employee_callback = move_employee_callback
        self.rename_org_callback = rename_org_callback
        self.reparent_org_callback = reparent_org_callback
        self.display_options = {**DEFAULT_DISPLAY_OPTIONS, **(display_options or {})}
        # 드롭이 무효(빈 공간 등)일 때 재레이아웃으로 원위치 스냅백하는 콜백.
        self.refresh_callback = refresh_callback

    def build(self, boxes: list[LayoutBox]):
        from PySide6.QtGui import QBrush, QColor, QFont
        from PySide6.QtWidgets import QGraphicsScene, QGraphicsTextItem

        scene = QGraphicsScene()
        card_items: list[SummaryCardItem | OrgCardItem | EmployeeCardItem | OverflowCardItem] = []
        box_by_id = {box.id: box for box in boxes}
        items_by_id: dict[str, object] = {}

        for box in boxes:
            if box.kind == "summary":
                item = SummaryCardItem(box)
                scene.addItem(item.graphics_item)
            elif box.kind == "org":
                item = OrgCardItem(
                    box, self.rename_org_callback, self.reparent_org_callback, self.refresh_callback
                )
                scene.addItem(item.graphics_item)
            elif box.kind == "employee":
                item = EmployeeCardItem(
                    box, self.move_employee_callback, self.display_options, self.refresh_callback
                )
                scene.addItem(item.graphics_item)
            else:
                item = OverflowCardItem(box)
                scene.addItem(item.graphics_item)
            card_items.append(item)
            items_by_id[box.id] = item.graphics_item

        # 연결선을 노드 참조 기반 동적 아이템으로 구성 — 노드가 이동하면
        # (ItemPositionHasChanged) 컨트롤러가 즉시 재계산·재작도한다(직교 라우팅 유지).
        connector_controller = OrgConnectorController(scene, boxes, box_by_id, items_by_id)
        connector_controller.build()
        scene._org_connector_controller = connector_controller

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

class OrgConnectorController:
    """부모-자식 연결선을 노드 참조 기반 동적 아이템으로 관리한다.

    연결선을 레이아웃 시점 좌표로 한 번만 그리면 카드를 드래그해도 선이 옛 자리에
    남는다(원인). 이 컨트롤러는 각 부모 그룹당 하나의 QGraphicsPathItem을 두고,
    노드의 '현재' 위치(레이아웃 좌표 + 아이템 이동량 pos)에서 경로를 다시 계산한다.
    카드가 이동하면(ItemPositionHasChanged) update()가 호출돼 실시간으로 재작도한다.
    직교 라우팅(수직 드롭 + 수평 버스/스파인)은 그대로 유지한다.
    """

    BRANCH_GAP = 36.0        # 부모 아래 수평 버스까지 간격(조직 자식)
    MEMBER_START_GAP = 14.0  # 부모 아래 멤버 스파인 시작 간격
    MEMBER_SPINE_INSET = 16.0

    def __init__(self, scene, boxes, box_by_id, items_by_id) -> None:
        from collections import defaultdict

        self.scene = scene
        self.box_by_id = box_by_id
        self.items_by_id = items_by_id
        self._org_children: dict[str, list[str]] = defaultdict(list)
        self._member_children: dict[str, list[str]] = defaultdict(list)
        for box in boxes:
            if not box.parent_id:
                continue
            if box.kind == "org":
                self._org_children[box.parent_id].append(box.id)
            elif box.kind in {"employee", "overflow"}:
                self._member_children[box.parent_id].append(box.id)
        self._org_paths: dict[str, object] = {}
        self._member_paths: dict[str, object] = {}
        self._pen = None

    def _make_pen(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QPen

        pen = QPen(QColor(CONNECTOR), 1.0)
        pen.setCosmetic(True)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    # ── 노드의 '현재' 기하 (레이아웃 좌표 + 드래그 이동량) ──────────────
    def _offset(self, node_id: str) -> tuple[float, float]:
        item = self.items_by_id.get(node_id)
        if item is None:
            return (0.0, 0.0)
        pos = item.pos()
        return (pos.x(), pos.y())

    def _center_x(self, node_id: str) -> float:
        box = self.box_by_id[node_id]
        return box.x + box.width / 2 + self._offset(node_id)[0]

    def _left_x(self, node_id: str) -> float:
        return self.box_by_id[node_id].x + self._offset(node_id)[0]

    def _top_y(self, node_id: str) -> float:
        return self.box_by_id[node_id].y + self._offset(node_id)[1]

    def _bottom_y(self, node_id: str) -> float:
        box = self.box_by_id[node_id]
        return box.y + box.height + self._offset(node_id)[1]

    def _center_y(self, node_id: str) -> float:
        box = self.box_by_id[node_id]
        return box.y + box.height / 2 + self._offset(node_id)[1]

    def build(self) -> None:
        from PySide6.QtWidgets import QGraphicsPathItem

        self._pen = self._make_pen()
        for parent_id in self._org_children:
            if parent_id not in self.box_by_id:
                continue
            item = QGraphicsPathItem()
            item.setPen(self._pen)
            item.setZValue(-1)
            self.scene.addItem(item)
            self._org_paths[parent_id] = item
        for parent_id in self._member_children:
            if parent_id not in self.box_by_id:
                continue
            item = QGraphicsPathItem()
            item.setPen(self._pen)
            item.setZValue(-1)
            self.scene.addItem(item)
            self._member_paths[parent_id] = item
        self.update()

    def update(self) -> None:
        """모든 부모 그룹의 연결선 경로를 현재 노드 위치에서 다시 계산한다."""
        from PySide6.QtGui import QPainterPath

        for parent_id, path_item in self._org_paths.items():
            children = sorted(self._org_children[parent_id], key=self._center_x)
            if not children:
                path_item.setPath(QPainterPath())
                continue
            path = QPainterPath()
            p_cx = self._center_x(parent_id)
            p_by = self._bottom_y(parent_id)
            branch_y = min(self._top_y(cid) for cid in children) - self.BRANCH_GAP
            path.moveTo(p_cx, p_by)
            path.lineTo(p_cx, branch_y)
            if len(children) > 1:
                path.moveTo(self._center_x(children[0]), branch_y)
                path.lineTo(self._center_x(children[-1]), branch_y)
            for cid in children:
                cx = self._center_x(cid)
                path.moveTo(cx, branch_y)
                path.lineTo(cx, self._top_y(cid))
            path_item.setPath(path)

        for parent_id, path_item in self._member_paths.items():
            members = sorted(self._member_children[parent_id], key=self._top_y)
            if not members:
                path_item.setPath(QPainterPath())
                continue
            path = QPainterPath()
            p_cx = self._center_x(parent_id)
            p_by = self._bottom_y(parent_id)
            spine_x = min(self._left_x(mid) for mid in members) - self.MEMBER_SPINE_INSET
            start_y = p_by + self.MEMBER_START_GAP
            last_y = self._center_y(members[-1])
            path.moveTo(p_cx, p_by)
            path.lineTo(p_cx, start_y)
            path.moveTo(p_cx, start_y)
            path.lineTo(spine_x, start_y)
            path.moveTo(spine_x, start_y)
            path.lineTo(spine_x, last_y)
            for mid in members:
                my = self._center_y(mid)
                path.moveTo(spine_x, my)
                path.lineTo(self._left_x(mid), my)
            path_item.setPath(path)

    def connectors_bounding_rect(self):
        """모든 연결선 경로의 합집합 경계(검증용)."""
        from PySide6.QtCore import QRectF

        union = QRectF()
        for path_item in (*self._org_paths.values(), *self._member_paths.values()):
            union = union.united(path_item.path().boundingRect())
        return union


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


_DRAG_THRESHOLD = 6.0  # 클릭과 드래그를 가르는 이동 임계(scene px, manhattan).


def _notify_connectors_moved(item) -> None:
    """이동한 카드가 속한 씬의 연결선 컨트롤러에 재계산을 요청한다."""
    scene = item.scene()
    controller = getattr(scene, "_org_connector_controller", None) if scene else None
    if controller is not None:
        controller.update()


def _was_dragged(item, event) -> bool:
    """release 시점이 press 대비 임계 이상 이동했는지(=드래그) 판정."""
    press = getattr(item, "_press_scene_pos", None)
    if press is None:
        return False
    return (event.scenePos() - press).manhattanLength() > _DRAG_THRESHOLD


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
        refresh_callback: Callable[[], None] | None = None,
    ) -> None:
        from PySide6.QtGui import QBrush, QColor, QFont, QPen
        from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem

        is_root = box.meta.get("is_root") == "true" and not box.parent_id
        can_reparent = reparent_callback is not None and not is_root

        class ReparentableOrgRect(QGraphicsRectItem):
            def itemChange(inner_self, change, value):  # noqa: N802
                # 카드가 이동하면 연결된 엣지를 즉시 재계산(드래그 중 실시간 추적).
                if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
                    _notify_connectors_moved(inner_self)
                return QGraphicsRectItem.itemChange(inner_self, change, value)

            def mousePressEvent(inner_self, event):  # noqa: N802
                inner_self._press_scene_pos = event.scenePos()
                super().mousePressEvent(event)

            def mouseReleaseEvent(inner_self, event):  # noqa: N802
                super().mouseReleaseEvent(event)
                if not can_reparent:
                    return
                if not _was_dragged(inner_self, event):
                    return  # 단순 클릭(선택)엔 관여하지 않음.
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
                # 유효 타겟 없음(빈 공간 등) → 재레이아웃으로 원위치 스냅백.
                if refresh_callback is not None:
                    refresh_callback()

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
            self.group.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

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
        refresh_callback: Callable[[], None] | None = None,
    ) -> None:
        from PySide6.QtGui import QBrush, QColor, QFont, QPen
        from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem

        self.box = box
        self.move_callback = move_callback
        options = {**DEFAULT_DISPLAY_OPTIONS, **(display_options or {})}

        class MovableEmployeeRect(QGraphicsRectItem):
            def itemChange(inner_self, change, value):  # noqa: N802
                # 카드 이동 시 소속 연결선을 실시간 재계산.
                if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
                    _notify_connectors_moved(inner_self)
                return QGraphicsRectItem.itemChange(inner_self, change, value)

            def mousePressEvent(inner_self, event):  # noqa: N802
                inner_self._press_scene_pos = event.scenePos()
                super().mousePressEvent(event)

            def mouseReleaseEvent(inner_self, event):  # noqa: N802
                super().mouseReleaseEvent(event)
                if not _was_dragged(inner_self, event):
                    return  # 단순 클릭(선택)엔 관여하지 않음.
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
                # 유효 타겟 없음(빈 공간 등) → 재레이아웃으로 원위치 스냅백.
                if refresh_callback is not None:
                    refresh_callback()

        self.item = MovableEmployeeRect(box.x, box.y, box.width, box.height)
        self.item.setData(0, box.id)
        self.item.setData(1, "employee")
        is_highlighted = bool(box.meta.get("highlight"))
        _prepare_hit_rect(self.item)
        self.item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        self.item.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
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
