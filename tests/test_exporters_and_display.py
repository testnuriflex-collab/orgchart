"""PDF/PNG 원페이지 내보내기와 카드 표시 항목 토글 검증(offscreen)."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QGraphicsTextItem

from app.chart.layout import EmployeeNode, OrgNode, compute_org_layout
from app.exporter.pdf_exporter import export_scene_to_pdf, export_scene_to_png
from app.ui.chart_view import ChartSceneBuilder


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _sample_scene(display_options=None):
    boxes = compute_org_layout(
        [
            OrgNode(id="root", name="대표", parent_id=None),
            OrgNode(
                id="dev",
                name="개발팀",
                parent_id="root",
                employees=(
                    EmployeeNode("e1", "김개발", "책임", "Backend", "재직", employee_no="E001"),
                ),
            ),
        ]
    )
    builder = ChartSceneBuilder(
        lambda *a: None, lambda *a: None, lambda *a: None, display_options
    )
    return builder.build(boxes)


def test_export_png_creates_non_empty_image(tmp_path: Path) -> None:
    _app()
    scene = _sample_scene()
    target = tmp_path / "chart.png"
    export_scene_to_png(scene, target, scale=2.0)
    assert target.exists() and target.stat().st_size > 1000


def test_export_pdf_creates_file(tmp_path: Path) -> None:
    _app()
    scene = _sample_scene()
    target = tmp_path / "chart.pdf"
    export_scene_to_pdf(scene, target)
    assert target.exists() and target.stat().st_size > 500


def test_export_png_handles_empty_scene(tmp_path: Path) -> None:
    _app()
    scene = ChartSceneBuilder(lambda *a: None, lambda *a: None).build([])
    target = tmp_path / "empty.png"
    export_scene_to_png(scene, target)
    assert target.exists() and target.stat().st_size > 0


def _text_values(scene) -> list[str]:
    return [item.toPlainText() for item in scene.items() if isinstance(item, QGraphicsTextItem)]


def test_display_options_hide_fields() -> None:
    _app()
    scene = _sample_scene(
        {
            "name": True,
            "title": False,
            "grade": False,
            "department": False,
            "employee_no": False,
            "email": False,
            "status": False,
        }
    )
    texts = _text_values(scene)
    assert "김개발" in texts
    assert "Backend" not in texts
    assert "책임" not in texts


def test_display_options_show_department_and_employee_no() -> None:
    _app()
    scene = _sample_scene(
        {
            "name": True,
            "title": False,
            "grade": False,
            "department": True,
            "employee_no": True,
            "email": False,
            "status": False,
        }
    )
    joined = " ".join(_text_values(scene))
    assert "개발팀" in joined
    assert "E001" in joined
