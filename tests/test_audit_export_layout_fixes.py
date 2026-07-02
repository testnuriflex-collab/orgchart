"""적대적 감사 결함 중 내보내기/레이아웃 시각 결함 회귀 테스트.

커버: H2(대규모 원페이지 판독 불가 → 다중 페이지 타일링), L1(초장문 카드 말줄임).
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from app.exporter.pdf_exporter import plan_pdf_layout
from app.ui.chart_view import elide_text


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


# ── H2: 500명 규모는 한 페이지로 뭉개지 않고 여러 페이지로 분할 ──────────────
def test_small_chart_stays_single_page() -> None:
    plan = plan_pdf_layout(
        content_w=1200, content_h=700, printable_w=4000, printable_h=2800, min_scale=1.0
    )
    assert plan.single_page is True
    assert plan.total_pages == 1


def test_large_wide_chart_tiles_across_pages() -> None:
    # 500명 조직도 실측 비율(16233 x 979) + A3 가로 인쇄영역(device-px 근사).
    plan = plan_pdf_layout(
        content_w=16233,
        content_h=979,
        printable_w=4000,
        printable_h=2600,
        min_scale=0.85,  # scene-px 당 최소 판독 배율(device-px)
    )
    assert plan.single_page is False
    assert plan.columns > 1  # 가로로 여러 페이지에 나뉜다
    assert plan.total_pages > 1
    # 타일링 배율은 최소 판독 배율 이상으로 유지되어 글자가 판독 가능하다.
    assert plan.scale >= 0.85


def test_zero_content_is_safe_single_page() -> None:
    plan = plan_pdf_layout(0, 0, 4000, 2800, 1.0)
    assert plan.single_page is True
    assert plan.total_pages == 1


# ── L1: 초장문 부서명/이름은 말줄임(…)으로 폭 안에 들어간다 ──────────────────
def test_long_label_is_elided_within_width() -> None:
    _app()
    font = QFont("Paperlogy", 14)
    long_name = "정말로매우긴부서이름연구개발전략기획운영지원본부팀"
    elided = elide_text(long_name, font, 200)
    from PySide6.QtGui import QFontMetrics

    metrics = QFontMetrics(font)
    assert metrics.horizontalAdvance(elided) <= 200
    assert len(elided) < len(long_name)


def test_short_label_is_unchanged() -> None:
    _app()
    font = QFont("Paperlogy", 14)
    assert elide_text("영업팀", font, 200) == "영업팀"
