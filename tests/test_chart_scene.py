import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QGraphicsPathItem, QGraphicsRectItem, QGraphicsTextItem

from app.chart.layout import EmployeeNode, OrgNode, compute_org_layout
from app.ui.chart_view import ACCENT, MAX_ZOOM, MIN_ZOOM, ChartSceneBuilder, clamped_zoom_factor


def test_chart_scene_keeps_text_items_alive() -> None:
    app = QApplication.instance() or QApplication([])
    assert app is not None
    boxes = compute_org_layout(
        [
            OrgNode(id="root", name="대표", parent_id=None),
            OrgNode(
                id="dev",
                name="개발",
                parent_id="root",
                employees=(EmployeeNode("e1", "김개발", "책임", "Backend", "재직"),),
            ),
        ]
    )

    scene = ChartSceneBuilder(lambda employee_id, org_id: None, lambda org_id, name: None).build(boxes)

    text_values = [item.toPlainText() for item in scene.items() if isinstance(item, QGraphicsTextItem)]
    assert {"대표", "개발", "김개발"}.issubset(text_values)


def test_zoom_factor_is_clamped() -> None:
    assert 0.999 < clamped_zoom_factor(MIN_ZOOM, 0.87) < 1.001
    assert 0.999 < clamped_zoom_factor(MAX_ZOOM, 1.15) < 1.001
    assert clamped_zoom_factor(1.0, 1.15) == 1.15
    assert clamped_zoom_factor(1.0, 0.87) == 0.87


def test_connectors_track_node_movement() -> None:
    app = QApplication.instance() or QApplication([])
    assert app is not None
    boxes = compute_org_layout(
        [
            OrgNode(id="root", name="대표", parent_id=None),
            OrgNode(id="dev", name="개발", parent_id="root"),
            OrgNode(id="ops", name="운영", parent_id="root"),
        ]
    )
    scene = ChartSceneBuilder(
        lambda employee_id, org_id: None,
        lambda org_id, name: None,
        lambda org_id, parent_id: None,
    ).build(boxes)

    controller = scene._org_connector_controller
    dev_item = controller.items_by_id["dev"]
    before = controller.connectors_bounding_rect()

    # 자식 카드 이동(setPos) → ItemPositionHasChanged가 controller.update()를 자동 호출.
    dev_item.setPos(420, 80)
    after = controller.connectors_bounding_rect()

    assert after != before  # 연결선이 좌표 고정이 아니라 노드 이동을 추적한다.
    dev_box = next(box for box in boxes if box.id == "dev")
    new_center_x = dev_box.x + dev_box.width / 2 + 420
    # 이동한 자식의 새 중심 x까지 연결선 경로가 도달(옛 위치에 박혀있지 않음).
    assert after.right() >= new_center_x - 1.0


def test_wheel_zoom_without_modifier() -> None:
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

    from app.ui.chart_view import OrgChartViewMixin

    class _View(OrgChartViewMixin, QGraphicsView):
        pass

    app = QApplication.instance() or QApplication([])
    assert app is not None
    view = _View()
    view.setScene(QGraphicsScene())
    before = view.transform().m11()

    def wheel(delta: int) -> None:
        event = QWheelEvent(
            QPointF(10, 10),
            QPointF(10, 10),
            QPoint(0, 0),
            QPoint(0, delta),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,  # 보조키 없음 — 그래도 줌돼야 한다.
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        view.wheelEvent(event)

    wheel(120)
    assert view.transform().m11() > before  # 휠 업 = 줌 인
    assert view._user_adjusted is True
    zoomed_in = view.transform().m11()
    wheel(-120)
    assert view.transform().m11() < zoomed_in  # 휠 다운 = 줌 아웃


def test_chart_scene_renders_overflow_and_search_highlight() -> None:
    app = QApplication.instance() or QApplication([])
    assert app is not None
    employees = tuple(
        EmployeeNode(f"e{index}", f"직원{index}", "사원", "Staff", "재직")
        for index in range(10)
    )
    boxes = compute_org_layout(
        [OrgNode(id="large", name="큰팀", parent_id=None, employees=employees)],
        highlight_query="직원9",
    )

    scene = ChartSceneBuilder(lambda employee_id, org_id: None, lambda org_id, name: None).build(boxes)
    rects = [item for item in scene.items() if isinstance(item, QGraphicsRectItem)]
    overflow = next(item for item in rects if item.data(1) == "overflow")
    highlighted = [item for item in rects if item.pen().color().name().lower() == ACCENT.lower()]

    assert overflow.data(0) == "large"
    assert "직원" in overflow.toolTip()
    assert highlighted


def test_chart_scene_connectors_are_orthogonal_and_behind_cards() -> None:
    app = QApplication.instance() or QApplication([])
    assert app is not None
    boxes = compute_org_layout(
        [
            OrgNode(
                id="root",
                name="대표",
                parent_id=None,
                employees=(EmployeeNode("e1", "김대표", "대표", "CEO", "재직"),),
            ),
            OrgNode(id="dev", name="개발", parent_id="root", display_order=1),
            OrgNode(id="sales", name="영업", parent_id="root", display_order=2),
        ]
    )

    scene = ChartSceneBuilder(lambda employee_id, org_id: None, lambda org_id, name: None).build(boxes)
    # 연결선은 노드 참조 기반 동적 경로 아이템(부모 그룹당 1개)이며 카드 뒤(z=-1)에 놓인다.
    connectors = [
        item
        for item in scene.items()
        if isinstance(item, QGraphicsPathItem) and item.parentItem() is None and item.zValue() == -1
    ]

    assert connectors
    for connector in connectors:
        path = connector.path()
        previous = None
        for index in range(path.elementCount()):
            element = path.elementAt(index)
            if element.isLineTo() and previous is not None:
                # 각 세그먼트는 수평 또는 수직(직교 라우팅).
                assert abs(element.x - previous[0]) < 0.001 or abs(element.y - previous[1]) < 0.001
            previous = (element.x, element.y)
