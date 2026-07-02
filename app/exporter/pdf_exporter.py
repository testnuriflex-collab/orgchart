from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from pathlib import Path

# 내보내기 여백(scene 단위)과 PNG 기본 확대 배율.
SCENE_MARGIN = 48
DEFAULT_PNG_SCALE = 2.0

# 한 페이지 강제 축소로 글자가 판독 불가해지는 것을 막기 위한 최소 배율.
# scene 1px 당 최소 물리 크기(mm). 이름 폰트(약 13px)가 13*0.18≈2.3mm(≈6.6pt) 이상 되도록 한다.
READABLE_MM_PER_SCENE_PX = 0.18

# PNG 한 장이 과도한 메모리를 쓰지 않도록 하는 총 픽셀 상한(약 1.2억 픽셀).
MAX_PNG_PIXELS = 120_000_000


@dataclass(frozen=True)
class PdfPagePlan:
    """PDF 내보내기 페이지 분할 계획.

    single_page=True면 전체를 한 페이지에 비율 유지로 맞춘다(작은 조직도).
    아니면 columns×rows 타일로 나눠 각 타일을 readable 배율로 렌더한다(대규모 조직도).
    """

    columns: int
    rows: int
    scale: float  # device-px per scene-px
    single_page: bool

    @property
    def total_pages(self) -> int:
        return self.columns * self.rows


def plan_pdf_layout(
    content_w: float,
    content_h: float,
    printable_w: float,
    printable_h: float,
    min_scale: float,
) -> PdfPagePlan:
    """콘텐츠/페이지 크기(device-px)와 최소 판독 배율로 페이지 분할을 계산한다."""
    if content_w <= 0 or content_h <= 0 or printable_w <= 0 or printable_h <= 0:
        return PdfPagePlan(columns=1, rows=1, scale=max(min_scale, 0.0001), single_page=True)
    fit_scale = min(printable_w / content_w, printable_h / content_h)
    if fit_scale >= min_scale:
        # 한 페이지에 넣어도 글자가 충분히 크다(또는 콘텐츠가 작다).
        return PdfPagePlan(columns=1, rows=1, scale=fit_scale, single_page=True)
    columns = max(1, ceil(content_w * min_scale / printable_w))
    rows = max(1, ceil(content_h * min_scale / printable_h))
    return PdfPagePlan(columns=columns, rows=rows, scale=min_scale, single_page=False)


def _content_source(scene: object):
    """조직도 콘텐츠 영역(여백 포함)을 반환한다."""
    from PySide6.QtCore import QRectF

    rect = scene.itemsBoundingRect()
    if rect.isEmpty():
        rect = QRectF(0, 0, 1280, 720)
    return rect.adjusted(-SCENE_MARGIN, -SCENE_MARGIN, SCENE_MARGIN, SCENE_MARGIN)


def _configure_printer(printer: object, target_path: Path, source: object) -> None:
    from PySide6.QtCore import QMarginsF
    from PySide6.QtGui import QPageLayout, QPageSize
    from PySide6.QtPrintSupport import QPrinter

    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(target_path))
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A3))
    printer.setPageOrientation(
        QPageLayout.Orientation.Landscape
        if source.width() >= source.height()
        else QPageLayout.Orientation.Portrait
    )
    printer.setPageMargins(QMarginsF(8, 8, 8, 8), QPageLayout.Unit.Millimeter)


def _render_tiled(
    printer: object,
    painter: object,
    scene: object,
    source: object,
    plan: PdfPagePlan,
    printable_w: float,
    printable_h: float,
) -> None:
    from PySide6.QtCore import QRectF, Qt

    tile_scene_w = printable_w / plan.scale
    tile_scene_h = printable_h / plan.scale
    first = True
    for row in range(plan.rows):
        for col in range(plan.columns):
            src_x = source.left() + col * tile_scene_w
            src_y = source.top() + row * tile_scene_h
            src_w = min(tile_scene_w, source.right() - src_x)
            src_h = min(tile_scene_h, source.bottom() - src_y)
            if src_w <= 0 or src_h <= 0:
                continue
            if not first:
                printer.newPage()
            first = False
            tile_source = QRectF(src_x, src_y, src_w, src_h)
            # 최소 배율(plan.scale)로 정확히 매핑해 모든 페이지의 글자 크기를 일정하게 유지.
            tile_target = QRectF(0, 0, src_w * plan.scale, src_h * plan.scale)
            scene.render(painter, tile_target, tile_source, Qt.AspectRatioMode.KeepAspectRatio)


def export_scene_to_pdf(scene: object, target_path: Path) -> None:
    """조직도를 PDF로 렌더한다.

    작은 조직도는 한 페이지에 비율 유지로 맞추고, 대규모 조직도는 글자가 판독 가능한
    최소 배율을 보장하며 여러 페이지로 자동 타일링한다.
    """
    try:
        from PySide6.QtCore import QRectF, Qt
        from PySide6.QtGui import QPainter
        from PySide6.QtPrintSupport import QPrinter
    except ImportError as exc:
        raise RuntimeError("PDF export에는 PySide6가 필요합니다.") from exc

    target_path.parent.mkdir(parents=True, exist_ok=True)
    source = _content_source(scene)

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    _configure_printer(printer, target_path, source)

    page_rect = QRectF(printer.pageRect(QPrinter.Unit.DevicePixel))
    dpi = float(printer.resolution()) or 300.0
    min_scale = READABLE_MM_PER_SCENE_PX / 25.4 * dpi
    plan = plan_pdf_layout(
        source.width(), source.height(), page_rect.width(), page_rect.height(), min_scale
    )

    painter = QPainter(printer)
    try:
        if plan.single_page:
            target = QRectF(0, 0, page_rect.width(), page_rect.height())
            scene.render(painter, target, source, Qt.AspectRatioMode.KeepAspectRatio)
        else:
            _render_tiled(
                printer, painter, scene, source, plan, page_rect.width(), page_rect.height()
            )
    finally:
        painter.end()


def export_scene_to_png(scene: object, target_path: Path, scale: float = DEFAULT_PNG_SCALE) -> None:
    """조직도 전체를 한 장의 고해상도 PNG로 렌더한다."""
    try:
        from PySide6.QtCore import QRectF, Qt
        from PySide6.QtGui import QColor, QImage, QPainter
    except ImportError as exc:
        raise RuntimeError("PNG export에는 PySide6가 필요합니다.") from exc

    target_path.parent.mkdir(parents=True, exist_ok=True)
    source = _content_source(scene)
    scale = max(1.0, float(scale))
    width = max(1, int(source.width() * scale))
    height = max(1, int(source.height() * scale))
    # 초대형 조직도에서 메모리 폭주를 막기 위해 총 픽셀 상한을 넘으면 배율을 낮춘다(원본 해상도 유지 우선).
    if width * height > MAX_PNG_PIXELS:
        shrink = (MAX_PNG_PIXELS / (width * height)) ** 0.5
        width = max(1, int(width * shrink))
        height = max(1, int(height * shrink))

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor("#FFFFFF"))
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        target = QRectF(0, 0, width, height)
        scene.render(painter, target, source, Qt.AspectRatioMode.KeepAspectRatio)
    finally:
        painter.end()
    if not image.save(str(target_path), "PNG"):
        raise RuntimeError(f"PNG 저장에 실패했습니다: {target_path}")
