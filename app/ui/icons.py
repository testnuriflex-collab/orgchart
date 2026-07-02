from __future__ import annotations

from app.ui.styles import TOKENS

# 헤더 툴바 등에서 쓰는 라인 아이콘 매핑 (Font Awesome 5 solid).
ICON_NAMES: dict[str, str] = {
    "import": "fa5s.file-import",
    "template": "fa5s.file-download",
    "roster": "fa5s.table",
    "bulk": "fa5s.exchange-alt",
    "undo": "fa5s.undo",
    "pdf": "fa5s.file-pdf",
    "png": "fa5s.file-image",
    "excel": "fa5s.file-excel",
    "fit": "fa5s.expand",
    "search": "fa5s.search",
}

# qtawesome 미설치·로드 실패 시 사용할 Qt 표준 아이콘 폴백.
_STD_FALLBACK: dict[str, str] = {
    "import": "SP_DialogOpenButton",
    "template": "SP_FileIcon",
    "roster": "SP_FileDialogDetailedView",
    "bulk": "SP_BrowserReload",
    "undo": "SP_ArrowBack",
    "pdf": "SP_DialogSaveButton",
    "png": "SP_DialogSaveButton",
    "excel": "SP_DriveHDIcon",
    "fit": "SP_FileDialogContentsView",
    "search": "SP_FileDialogContentsView",
}


def make_icon(key: str, primary: bool = False):
    """디자인 토큰 색을 입힌 QIcon을 반환한다.

    qtawesome가 있으면 일관된 라인 아이콘을, 없으면 Qt 표준 아이콘으로 폴백한다.
    두 경로 모두 널이 아닌 아이콘을 보장한다(테스트 계약).
    """
    from PySide6.QtGui import QIcon

    name = ICON_NAMES.get(key)
    if name:
        try:
            import qtawesome as qta

            base = "#FFFFFF" if primary else TOKENS["muted"]
            active = "#FFFFFF" if primary else TOKENS["accent"]
            return qta.icon(name, color=base, color_active=active, color_disabled=TOKENS["subtle"])
        except Exception:
            pass
    return _standard_icon(key) or QIcon()


def _standard_icon(key: str):
    from PySide6.QtWidgets import QApplication, QStyle

    app = QApplication.instance()
    if app is None:
        return None
    pixmap_name = _STD_FALLBACK.get(key, "SP_FileIcon")
    pixmap = getattr(QStyle.StandardPixmap, pixmap_name, QStyle.StandardPixmap.SP_FileIcon)
    return app.style().standardIcon(pixmap)
