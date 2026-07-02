from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.chart.adapters import to_layout_nodes  # noqa: E402
from app.chart.layout import compute_org_layout  # noqa: E402
from app.db.repository import HrRepository  # noqa: E402
from app.db.session import create_session_factory, initialize_database  # noqa: E402
from app.importer.excel_importer import PeopleFileImporter  # noqa: E402
from app.ui.chart_view import ChartSceneBuilder  # noqa: E402
from app.ui.styles import load_paperlogy  # noqa: E402


def main() -> int:
    app = QApplication.instance() or QApplication([])
    load_paperlogy(app)
    sample_path = Path("sample_inputs/인사정보_샘플.json")
    output_path = Path("artifacts/org_chart_sample.png")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        session_factory = create_session_factory(Path(tmpdir) / "hr.sqlite3")
        initialize_database(session_factory)
        with session_factory() as session:
            importer = PeopleFileImporter(session)
            repository = HrRepository(session)
            for row in importer.read_rows(sample_path):
                repository.create_or_update_employee(row)
            session.commit()
            org_units, assignments = repository.org_tree_payload()
            boxes = compute_org_layout(to_layout_nodes(org_units, assignments))

    scene = ChartSceneBuilder(lambda employee_id, org_id: None, lambda org_id, name: None).build(boxes)
    rect = scene.sceneRect()
    width = max(1, int(rect.width()))
    height = max(1, int(rect.height()))
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor("#F7F7F7"))

    painter = QPainter(image)
    scene.render(painter, QRectF(0, 0, width, height), rect)
    painter.end()

    if not image.save(str(output_path)):
        raise RuntimeError(f"PNG 저장 실패: {output_path}")
    print(f"rendered {output_path} {width}x{height} boxes={len(boxes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
