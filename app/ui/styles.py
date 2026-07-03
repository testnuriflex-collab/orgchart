from __future__ import annotations

from pathlib import Path

from app.config import resources_dir

# ─────────────────────────────────────────────────────────────────────────────
# 디자인 토큰 (단일 라이트 테마)
#   - 브랜드 액센트 1색(딥 레드) + 중성 그레이 스케일 + 상태 2색.
#   - 8px 간격 그리드, 라운드/섀도 토큰을 상수로 정의해 전 위젯에 일관 적용.
# ─────────────────────────────────────────────────────────────────────────────
TOKENS: dict[str, str] = {
    # 표면
    "appBg": "#EDEFF3",        # 최하단 배경(패널이 카드처럼 떠 보이게 하는 캔버스)
    "panel": "#FFFFFF",        # 패널·카드 배경
    "panelSoft": "#F6F8FA",    # 섹션 내부 옅은 면
    "canvas": "#F1F3F6",       # 조직도 캔버스 배경
    "headerBg": "#FFFFFF",
    # 잉크(텍스트)
    "ink": "#1B1F27",          # 제목·강조 텍스트
    "body": "#3D434F",         # 본문
    "muted": "#6B7280",        # 보조 라벨
    "subtle": "#9AA1AC",       # 캡션·비활성
    # 라인
    "hairline": "#E4E7EC",
    "hairlineStrong": "#D3D8DF",
    # 브랜드 액센트 (프로페셔널 블루 스케일)
    "accent": "#1D4ED8",       # blue-700 — 버튼·선택·강조 (흰 텍스트 대비 ~5.5:1, WCAG AA)
    "accentHover": "#2563EB",  # blue-600
    "accentActive": "#1B44B8", # blue-800 계열(pressed)
    "accentSoft": "#E7EEFD",   # 선택/hover 틴트(연한 블루)
    # 상태 (재직 등 긍정 상태도 블루로 통일)
    "success": "#1D4ED8",
    "successSoft": "#E7EEFD",
    "warning": "#B26A00",
    "danger": "#C0392B",
    # 라운드
    "rSm": "8",
    "rMd": "12",
    "rLg": "16",
}

FONT_STACK = '"Paperlogy", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif'

QSS = f"""
/* ── 전역 ─────────────────────────────────────────────────────────── */
QWidget {{
    background: transparent;
    color: {TOKENS['body']};
    font-family: {FONT_STACK};
    font-size: 13px;
}}
QMainWindow, QSplitter {{
    background: {TOKENS['appBg']};
}}
QSplitter::handle {{
    background: transparent;
    width: 12px;
}}
QToolTip {{
    background: {TOKENS['ink']};
    color: #FFFFFF;
    border: 0;
    padding: 6px 9px;
    border-radius: 6px;
    font-size: 12px;
}}

/* ── 상단 헤더바 ───────────────────────────────────────────────────── */
#headerBar {{
    background: {TOKENS['headerBg']};
    border-bottom: 1px solid {TOKENS['hairline']};
}}
#appMark {{
    background: {TOKENS['accent']};
    border-radius: 5px;
    min-width: 10px;
    max-width: 10px;
    min-height: 10px;
    max-height: 10px;
}}
#appTitle {{
    color: {TOKENS['ink']};
    font-size: 15px;
    font-weight: 700;
}}
#appKicker {{
    color: {TOKENS['subtle']};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
}}
#toolSep {{
    background: {TOKENS['hairline']};
    min-width: 1px;
    max-width: 1px;
    margin: 6px 4px;
}}

/* 헤더 아이콘 툴버튼 */
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {TOKENS['rSm']}px;
    padding: 7px;
    color: {TOKENS['body']};
    font-weight: 600;
}}
QToolButton:hover {{
    background: {TOKENS['panelSoft']};
    border: 1px solid {TOKENS['hairline']};
}}
QToolButton:pressed {{
    background: {TOKENS['hairline']};
}}
QToolButton:disabled {{
    color: {TOKENS['subtle']};
}}
QToolButton[primary="true"] {{
    background: {TOKENS['accent']};
    color: #FFFFFF;
    padding: 7px 14px;
    font-weight: 700;
}}
QToolButton[primary="true"]:hover {{
    background: {TOKENS['accentHover']};
    border: 1px solid {TOKENS['accentHover']};
}}
QToolButton[primary="true"]:pressed {{
    background: {TOKENS['accentActive']};
}}

/* ── 패널 카드(좌/우) ──────────────────────────────────────────────── */
#sidePanel {{
    background: {TOKENS['panel']};
    border: 1px solid {TOKENS['hairline']};
    border-radius: {TOKENS['rLg']}px;
}}
#panelTitle {{
    color: {TOKENS['ink']};
    font-size: 13px;
    font-weight: 700;
}}
#panelCaption {{
    color: {TOKENS['subtle']};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}

/* 요약 pill */
#summaryPill {{
    background: {TOKENS['panelSoft']};
    color: {TOKENS['muted']};
    border: 1px solid {TOKENS['hairline']};
    border-radius: {TOKENS['rSm']}px;
    padding: 6px 10px;
    font-weight: 600;
    font-size: 12px;
}}

/* ── 입력 ─────────────────────────────────────────────────────────── */
QLineEdit, QComboBox, QSpinBox {{
    min-height: 22px;
    padding: 8px 12px;
    border-radius: {TOKENS['rSm']}px;
    border: 1px solid {TOKENS['hairlineStrong']};
    background: {TOKENS['panel']};
    color: {TOKENS['ink']};
    selection-background-color: {TOKENS['accentSoft']};
    selection-color: {TOKENS['accent']};
}}
QLineEdit#searchInput {{
    background: {TOKENS['panelSoft']};
    padding-left: 34px;  /* 돋보기 아이콘 자리 */
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border: 1.5px solid {TOKENS['accent']};
    background: {TOKENS['panel']};
}}
QLineEdit::placeholder {{
    color: {TOKENS['subtle']};
}}

/* ── 버튼(다이얼로그·표 편집) ─────────────────────────────────────── */
QPushButton {{
    min-height: 20px;
    padding: 9px 16px;
    border-radius: {TOKENS['rSm']}px;
    border: 1px solid {TOKENS['hairlineStrong']};
    background: {TOKENS['panel']};
    color: {TOKENS['ink']};
    font-weight: 600;
}}
QPushButton:hover {{
    background: {TOKENS['panelSoft']};
    border-color: {TOKENS['hairlineStrong']};
}}
QPushButton:pressed {{
    background: {TOKENS['hairline']};
}}
QPushButton[primary="true"] {{
    background: {TOKENS['accent']};
    color: #FFFFFF;
    border: 1px solid {TOKENS['accent']};
}}
QPushButton[primary="true"]:hover {{
    background: {TOKENS['accentHover']};
    border-color: {TOKENS['accentHover']};
}}
QPushButton[primary="true"]:pressed {{
    background: {TOKENS['accentActive']};
}}

/* ── 리스트 ───────────────────────────────────────────────────────── */
QListWidget {{
    border: 1px solid {TOKENS['hairline']};
    border-radius: {TOKENS['rMd']}px;
    background: {TOKENS['panel']};
    padding: 4px;
    outline: 0;
}}
QListWidget::item {{
    padding: 9px 10px;
    border-radius: {TOKENS['rSm']}px;
    color: {TOKENS['body']};
    margin: 1px 2px;
}}
QListWidget::item:hover {{
    background: {TOKENS['panelSoft']};
}}
QListWidget::item:selected {{
    background: {TOKENS['accentSoft']};
    color: {TOKENS['accent']};
    font-weight: 700;
}}

/* ── 조직 트리(아코디언) ───────────────────────────────────────────── */
QTreeWidget {{
    border: 1px solid {TOKENS['hairline']};
    border-radius: {TOKENS['rMd']}px;
    background: {TOKENS['panel']};
    padding: 4px;
    outline: 0;
}}
QTreeWidget::item {{
    padding: 7px 6px;
    border-radius: {TOKENS['rSm']}px;
    color: {TOKENS['body']};
    margin: 1px 2px;
}}
QTreeWidget::item:hover {{
    background: {TOKENS['panelSoft']};
}}
QTreeWidget::item:selected {{
    background: {TOKENS['accentSoft']};
    color: {TOKENS['accent']};
    font-weight: 700;
}}

/* ── 표 ───────────────────────────────────────────────────────────── */
QTableWidget {{
    border: 1px solid {TOKENS['hairline']};
    border-radius: {TOKENS['rMd']}px;
    background: {TOKENS['panel']};
    gridline-color: {TOKENS['hairline']};
    alternate-background-color: {TOKENS['panelSoft']};
    selection-background-color: {TOKENS['accentSoft']};
    selection-color: {TOKENS['accent']};
}}
QTableWidget::item {{
    padding: 6px 8px;
}}
QHeaderView::section {{
    background: {TOKENS['panelSoft']};
    color: {TOKENS['muted']};
    border: 0;
    border-bottom: 1px solid {TOKENS['hairlineStrong']};
    padding: 9px 8px;
    font-weight: 700;
}}
QTableCornerButton::section {{
    background: {TOKENS['panelSoft']};
    border: 0;
}}

/* ── 그룹박스(표시 항목) ──────────────────────────────────────────── */
QGroupBox {{
    background: {TOKENS['panelSoft']};
    border: 1px solid {TOKENS['hairline']};
    border-radius: {TOKENS['rMd']}px;
    margin-top: 14px;
    padding: 14px 12px 12px 12px;
    font-weight: 700;
    color: {TOKENS['ink']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 4px;
    color: {TOKENS['muted']};
    font-size: 11px;
    font-weight: 700;
}}
QCheckBox {{
    color: {TOKENS['body']};
    spacing: 8px;
    padding: 4px 2px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1.5px solid {TOKENS['hairlineStrong']};
    background: {TOKENS['panel']};
}}
QCheckBox::indicator:hover {{
    border-color: {TOKENS['accent']};
}}
QCheckBox::indicator:checked {{
    background: {TOKENS['accent']};
    border-color: {TOKENS['accent']};
    image: url("{(resources_dir() / 'icons' / 'check.svg').as_posix()}");
}}

/* 속성 폼 라벨/값 */
#propKey {{
    color: {TOKENS['muted']};
    font-size: 12px;
    font-weight: 600;
}}
#propVal {{
    color: {TOKENS['ink']};
    font-size: 13px;
    font-weight: 600;
}}
#propEmpty {{
    color: {TOKENS['subtle']};
    font-size: 12px;
}}

/* ── 조직도 캔버스 ────────────────────────────────────────────────── */
QGraphicsView {{
    background: {TOKENS['canvas']};
    border: 1px solid {TOKENS['hairlineStrong']};
    border-radius: {TOKENS['rLg']}px;
}}

/* 캔버스 좌상단 고정 타이틀(뷰포트 오버레이) */
#canvasTitle {{
    background: rgba(255, 255, 255, 0.96);
    color: {TOKENS['muted']};
    border: 1px solid {TOKENS['hairlineStrong']};
    border-radius: {TOKENS['rSm']}px;
    padding: 5px 11px;
    font-size: 12px;
    font-weight: 700;
}}

/* ── 빈 상태 온보딩 ───────────────────────────────────────────────── */
#emptyStage {{
    background: {TOKENS['canvas']};
    border: 1px solid {TOKENS['hairlineStrong']};
    border-radius: {TOKENS['rLg']}px;
}}
#emptyCard {{
    background: {TOKENS['panel']};
    border: 1px solid {TOKENS['hairline']};
    border-radius: {TOKENS['rLg']}px;
}}
#emptyBadge {{
    background: {TOKENS['accentSoft']};
    border-radius: 32px;
}}
#emptyTitle {{
    color: {TOKENS['ink']};
    font-size: 20px;
    font-weight: 700;
}}
#emptyDesc {{
    color: {TOKENS['muted']};
    font-size: 13px;
}}
#emptyStepNum {{
    background: {TOKENS['accent']};
    color: #FFFFFF;
    border-radius: 11px;
    font-size: 12px;
    font-weight: 700;
}}
#emptyStepText {{
    color: {TOKENS['body']};
    font-size: 13px;
}}

/* ── 상태바 ───────────────────────────────────────────────────────── */
QStatusBar {{
    background: {TOKENS['panel']};
    border-top: 1px solid {TOKENS['hairline']};
    color: {TOKENS['muted']};
    font-size: 12px;
    padding: 2px 8px;
}}
QStatusBar::item {{ border: 0; }}

/* ── 스크롤바 ─────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {TOKENS['hairlineStrong']};
    border-radius: 5px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{
    background: {TOKENS['subtle']};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 12px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {TOKENS['hairlineStrong']};
    border-radius: 5px;
    min-width: 32px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {TOKENS['subtle']};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0; height: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ── 다이얼로그 ───────────────────────────────────────────────────── */
QDialog {{
    background: {TOKENS['appBg']};
}}
QDialog QLabel {{
    color: {TOKENS['body']};
}}
"""


def _write_check_icon() -> None:
    """체크박스 체크 표시용 SVG를 리소스에 보장한다(외부 에셋 의존 제거).

    패키징된 읽기 전용 리소스 경로에서도 앱이 죽지 않도록 실패를 조용히 흡수한다
    (체크 아이콘이 없으면 체크박스 배경만 액센트로 채워질 뿐 기능은 정상).
    """
    try:
        icon_dir = resources_dir() / "icons"
        icon_dir.mkdir(parents=True, exist_ok=True)
        check = icon_dir / "check.svg"
        if not check.exists():
            check.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" '
                'viewBox="0 0 18 18"><path d="M4 9.2l3.2 3.3L14 5.4" fill="none" '
                'stroke="#FFFFFF" stroke-width="2.2" stroke-linecap="round" '
                'stroke-linejoin="round"/></svg>',
                encoding="utf-8",
            )
    except OSError:
        pass


def load_paperlogy(app: object) -> None:
    from PySide6.QtGui import QFontDatabase

    font_dir = resources_dir() / "fonts"
    for pattern in ("Paperlogy*.ttf", "Paperlogy*.otf"):
        for path in font_dir.glob(pattern):
            QFontDatabase.addApplicationFont(str(path))


def apply_app_style(app: object) -> None:
    _write_check_icon()
    app.setStyleSheet(QSS)


def font_resource_hint() -> Path:
    return resources_dir() / "fonts"
