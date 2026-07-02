from __future__ import annotations

import os
import sys

from app.config import default_database_path, ensure_app_dirs
from app.db.session import create_session_factory, initialize_database


def main() -> int:
    ensure_app_dirs()
    session_factory = create_session_factory(default_database_path())
    initialize_database(session_factory)
    if os.environ.get("ORG_CHART_STUDIO_SMOKE") == "1":
        print(f"smoke-ok db={default_database_path()}")
        return 0

    try:
        from PySide6.QtWidgets import QApplication

        from app.ui.main_window import MainWindow
        from app.ui.styles import apply_app_style, load_paperlogy
    except ImportError as exc:
        print(
            "PySide6가 설치되어 있지 않습니다. "
            '먼저 `python -m pip install -e ".[dev]"`를 실행해 주세요.'
        )
        print(f"원인: {exc}")
        return 1

    app = QApplication(sys.argv)
    load_paperlogy(app)
    apply_app_style(app)

    window = MainWindow(session_factory=session_factory)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
