from __future__ import annotations

from pathlib import Path

from app.config import resources_dir

QSS = """
QWidget {
    background: #FFFFFF;
    color: #222222;
    font-family: "Paperlogy", "Apple SD Gothic Neo", "Malgun Gothic", "Inter", sans-serif;
    font-size: 14px;
}
QMainWindow, QSplitter {
    background: #FFFFFF;
}
QToolBar {
    background: #FFFFFF;
    border-bottom: 1px solid #DDDDDD;
    spacing: 8px;
    padding: 8px 12px;
}
QPushButton {
    min-height: 44px;
    padding: 8px 14px;
    border-radius: 8px;
    border: 1px solid #DDDDDD;
    background: #FFFFFF;
    color: #222222;
}
QPushButton:hover {
    background: #F7F7F7;
}
QPushButton[primary="true"] {
    background: #A0002A;
    color: #FFFFFF;
    border: 1px solid #A0002A;
}
QPushButton[primary="true"]:pressed {
    background: #8F0024;
}
QLineEdit, QComboBox, QSpinBox {
    min-height: 34px;
    padding: 6px 10px;
    border-radius: 8px;
    border: 1px solid #DDDDDD;
    background: #FFFFFF;
}
QLineEdit:focus, QComboBox:focus {
    border: 2px solid #222222;
}
QListWidget, QTableWidget {
    border: 1px solid #DDDDDD;
    border-radius: 14px;
    background: #FFFFFF;
    alternate-background-color: #F7F7F7;
}
QHeaderView::section {
    background: #F7F7F7;
    border: 0;
    border-bottom: 1px solid #DDDDDD;
    padding: 8px;
}
QDockWidget::title {
    background: #FFFFFF;
    padding: 10px;
    border-bottom: 1px solid #DDDDDD;
}
QGraphicsView {
    background: #FAFAFA;
    border: 0;
}
"""


def load_paperlogy(app: object) -> None:
    from PySide6.QtGui import QFontDatabase

    font_dir = resources_dir() / "fonts"
    for path in font_dir.glob("Paperlogy*.ttf"):
        QFontDatabase.addApplicationFont(str(path))
    for path in font_dir.glob("Paperlogy*.otf"):
        QFontDatabase.addApplicationFont(str(path))


def apply_app_style(app: object) -> None:
    app.setStyleSheet(QSS)


def font_resource_hint() -> Path:
    return resources_dir() / "fonts"
