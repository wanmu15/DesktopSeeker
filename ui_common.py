"""界面公共工具：矢量图标绘制、物理像素 → Qt 逻辑坐标换算。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap

ACCENT = "#4B8DFF"
ACCENT_DEEP = "#7A5BFF"


def magnifier_pixmap(size: int, color: str = "#FFFFFF", stroke: float = 2.0,
                     dpr: float = 2.0) -> QPixmap:
    """绘制一枚放大镜图标（不依赖字体/图片资源）。"""
    pixmap = QPixmap(int(size * dpr), int(size * dpr))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(stroke)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    s = float(size)
    painter.drawEllipse(QRectF(s * 0.16, s * 0.16, s * 0.50, s * 0.50))
    painter.drawLine(QPointF(s * 0.62, s * 0.62), QPointF(s * 0.88, s * 0.88))
    painter.end()
    return pixmap


def physical_rect_to_logical(x: int, y: int, w: int, h: int) -> QRect | None:
    """把 Win32 物理像素矩形换算为 Qt 逻辑坐标矩形（支持多显示器不同缩放）。"""
    from desktop_api import monitor_rect_for_point

    monitor = monitor_rect_for_point(int(x), int(y))
    if not monitor:
        return None
    left, top, _right, _bottom, device = monitor

    screens = QGuiApplication.screens()
    if not screens:
        return None

    screen = None
    device_key = device.replace("\\", "").casefold()
    for candidate in screens:
        if candidate.name().replace("\\", "").casefold() == device_key:
            screen = candidate
            break
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    if screen is None:
        return None

    ratio = screen.devicePixelRatio() or 1.0
    geo = screen.geometry()
    return QRect(
        round(geo.x() + (x - left) / ratio),
        round(geo.y() + (y - top) / ratio),
        max(1, round(w / ratio)),
        max(1, round(h / ratio)),
    )
