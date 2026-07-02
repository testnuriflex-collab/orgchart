import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QGraphicsLineItem, QGraphicsRectItem, QGraphicsTextItem

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
    lines = [item for item in scene.items() if isinstance(item, QGraphicsLineItem)]

    assert lines
    assert all(item.zValue() == -1 for item in lines)
    assert all(
        abs(item.line().x1() - item.line().x2()) < 0.001
        or abs(item.line().y1() - item.line().y2()) < 0.001
        for item in lines
    )
