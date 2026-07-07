"""오프스크린으로 앱을 부팅해 실제 렌더 스크린샷을 저장한다(디자인 리뷰용)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "design_review" / "_shotdata"
DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["ORG_CHART_STUDIO_DATA_DIR"] = str(DATA_DIR)

# 매 실행마다 깨끗한 DB로 시작.
db = DATA_DIR / "hr.sqlite3"
if db.exists():
    db.unlink()

from app.config import default_database_path  # noqa: E402
from app.db.session import create_session_factory, initialize_database  # noqa: E402
from app.importer.excel_importer import PeopleFileImporter  # noqa: E402
from app.db.repository import HrRepository  # noqa: E402


def load_sample(session_factory) -> None:
    sample = ROOT / "sample_inputs" / "sample_hr_info.csv"
    with session_factory() as session:
        importer = PeopleFileImporter(session)
        preview = importer.preview(sample)
        hierarchy = importer.read_hierarchy(sample)
        HrRepository(session).apply_import_preview(preview, hierarchy=hierarchy)
        session.commit()


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "main"
    out = sys.argv[2] if len(sys.argv) > 2 else str(ROOT / "design_review" / f"{mode}.png")

    session_factory = create_session_factory(default_database_path())
    initialize_database(session_factory)
    load_sample(session_factory)

    from PySide6.QtWidgets import QApplication
    from app.ui.main_window import MainWindow
    from app.ui.styles import apply_app_style, load_paperlogy

    app = QApplication(sys.argv)
    load_paperlogy(app)
    apply_app_style(app)

    window = MainWindow(session_factory=session_factory)
    win = window._window
    win.resize(1480, 940)

    if mode == "roster":
        window.toggle_roster()
    elif mode == "empty":
        # 빈 상태 확인용: DB 비우고 새로 그림.
        with session_factory() as session:
            from app.db.models import Assignment, Employee, OrgUnit
            session.query(Assignment).delete()
            session.query(Employee).delete()
            session.query(OrgUnit).delete()
            session.commit()
        window.refresh_chart()

    win.show()
    app.processEvents()
    for _ in range(6):
        app.processEvents()
    if mode in ("main", "empty", "before", "after_final", "zoom", "drag"):
        # 리워크판은 reset_view(가독 배율), 원본은 fit_chart로 폴백.
        if hasattr(window, "reset_view"):
            window.reset_view()
        else:
            window.fit_chart()
    if mode == "zoom":
        # 휠 줌 인 상태 시뮬레이션(뷰 중심 확대)으로 인터랙션 감각 확인.
        view = window.chart_view
        view._user_adjusted = True
        for _ in range(4):
            view.scale(1.15, 1.15)
    if mode == "drag":
        # 화면에 보이는 조직 카드(세일즈팀)를 이동시켜 연결선이 실시간으로
        # 따라오는지(부모→팀, 팀→구성원 정합) 확인.
        controller = getattr(window.current_scene, "_org_connector_controller", None)
        if controller is not None:
            target = None
            for node_id, gfx in controller.items_by_id.items():
                box = controller.box_by_id[node_id]
                movable = bool(gfx.flags() & gfx.GraphicsItemFlag.ItemIsMovable)
                if box.kind == "org" and movable and box.label == "세일즈팀":
                    target = gfx
                    break
            if target is not None:
                target.setPos(90, 150)
    app.processEvents()

    pixmap = win.grab()
    pixmap.save(out, "PNG")
    print(f"saved {out} ({pixmap.width()}x{pixmap.height()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
