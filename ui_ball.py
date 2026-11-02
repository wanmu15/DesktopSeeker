"""悬浮球、桌面图标高亮环与名称气泡。"""

from __future__ import annotations

import math

from PySide6.QtCore import (QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRect, QRectF,
                            Qt, QTimer, Signal)
from PySide6.QtGui import QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QLabel, QMenu, QVBoxLayout, QWidget

from ui_common import ACCENT, ACCENT_DEEP


class NameTag(QWidget):
    """跟随悬浮球的名称气泡。"""

    def __init__(self) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus
                         | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._label = QLabel(self)
        self._label.setStyleSheet(
            "QLabel{color:#EAF0FF;background:rgba(16,18,24,238);"
            "border:1px solid rgba(255,255,255,0.16);border-radius:9px;padding:7px 11px;}")
        self._label.setFont(QFont("Microsoft YaHei UI", 9))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)

    def show_text(self, text: str, ball_pos: QPoint, ball_width: int) -> None:
        self._label.setText(text)
        self._label.adjustSize()
        self.adjustSize()

        screen = QGuiApplication.screenAt(ball_pos + QPoint(ball_width // 2, 0)) \
            or QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRect(0, 0, 1280, 800)

        x = ball_pos.x() + ball_width // 2 - self.width() // 2
        y = ball_pos.y() + ball_width + 8
        if y + self.height() > area.bottom() - 4:
            y = ball_pos.y() - self.height() - 8
        x = min(max(x, area.left() + 4), area.right() - self.width() - 4)
        y = min(max(y, area.top() + 4), area.bottom() - self.height() - 4)

        self.move(x, y)
        self.show()
        self.raise_()


class FloatingBall(QWidget):
    """常驻桌面的悬浮球：单击开搜索框，可拖动，定位时飞到目标图标旁。"""

    clicked = Signal()
    request_search = Signal()
    request_quit = Signal()
    show_desktop_toggled = Signal(bool)
    collapse_after_launch_toggled = Signal(bool)

    SIZE = 58

    def __init__(self) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(self.SIZE, self.SIZE)

        self.tag = NameTag()
        self._home = QPoint(0, 0)
        self._press_global: QPoint | None = None
        self._press_window = QPoint(0, 0)
        self._dragged = False
        self._active = False
        self._pending_tag = ""
        self._show_desktop = True
        self._collapse_after_launch = True

        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(460)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._on_move_finished)

        self._return_timer = QTimer(self)
        self._return_timer.setSingleShot(True)
        self._return_timer.timeout.connect(self.return_home)

        # 临时提示气泡的自动隐藏（新提示/定位时会重置，避免误隐藏新气泡）
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self.tag.hide)

        self.setToolTip("桌面搜索器 · 单击打开（Ctrl+Alt+F）")
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

    # ---------- 交互 ----------
    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        self._press_global = event.globalPosition().toPoint()
        self._press_window = self.pos()
        self._dragged = False

    def mouseMoveEvent(self, event) -> None:
        if self._press_global is None:
            return
        delta = event.globalPosition().toPoint() - self._press_global
        if delta.manhattanLength() > 3:
            self._dragged = True
            self._anim.stop()
            self._return_timer.stop()
            self.tag.hide()
            self.move(self._press_window + delta)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or self._press_global is None:
            return
        self._press_global = None
        if self._dragged:
            self._home = self.pos()
            self.return_home()
        else:
            self.clicked.emit()

    def _show_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu{background:#1B1E26;color:#E8EDF8;border:1px solid rgba(255,255,255,0.12);"
            "border-radius:8px;padding:6px;}"
            "QMenu::item{padding:6px 18px;border-radius:5px;}"
            "QMenu::item:selected{background:rgba(75,141,255,0.24);}")
        menu.addAction("打开搜索框 (Ctrl+Alt+F)", self.request_search.emit)
        action_desktop = menu.addAction("定位前先显示桌面")
        action_desktop.setCheckable(True)
        action_desktop.setChecked(self._show_desktop)
        action_desktop.toggled.connect(self._on_show_desktop_toggled)
        action_collapse = menu.addAction("启动程序后收起定位提示")
        action_collapse.setCheckable(True)
        action_collapse.setChecked(self._collapse_after_launch)
        action_collapse.toggled.connect(self._on_collapse_after_launch_toggled)
        menu.addSeparator()
        menu.addAction("退出", self.request_quit.emit)
        menu.exec(self.mapToGlobal(pos))

    def _on_show_desktop_toggled(self, checked: bool) -> None:
        self._show_desktop = checked
        self.show_desktop_toggled.emit(checked)

    def _on_collapse_after_launch_toggled(self, checked: bool) -> None:
        self._collapse_after_launch = checked
        self.collapse_after_launch_toggled.emit(checked)

    def set_collapse_after_launch_checked(self, checked: bool) -> None:
        """同步右键菜单中的勾选状态（菜单每次打开时重建）。"""
        self._collapse_after_launch = checked

    def set_show_desktop_checked(self, checked: bool) -> None:
        self._show_desktop = checked

    def set_active(self, active: bool) -> None:
        self._active = active
        self.update()

    # ---------- 定位 ----------
    def move_home(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        area = screen.availableGeometry()
        self._home = QPoint(area.right() - self.width() - 8,
                            area.center().y() - self.height() // 2)
        self.move(self._home)

    def point_to(self, target: QRect, name: str) -> None:
        """把悬浮球移到目标图标旁并显示名称。"""
        self._return_timer.stop()
        self._flash_timer.stop()
        self._pending_tag = name

        screen = QGuiApplication.screenAt(target.center()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen else target
        point = QPoint(target.right() + 14, target.center().y() - self.height() // 2)
        point.setX(min(max(point.x(), area.left() + 4), area.right() - self.width() - 4))
        point.setY(min(max(point.y(), area.top() + 4), area.bottom() - self.height() - 4))

        self._anim.stop()
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(point)
        self._anim.start()
        self.raise_()

    def _on_move_finished(self) -> None:
        if not self._pending_tag:
            return
        self.tag.show_text(self._pending_tag, self.pos(), self.width())
        self._pending_tag = ""
        self._return_timer.start(5000)

    def return_home(self) -> None:
        self._pending_tag = ""
        self._return_timer.stop()
        self._flash_timer.stop()
        self.tag.hide()
        if self.pos() == self._home:
            return
        self._anim.stop()
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(self._home)
        self._anim.start()

    def flash_text(self, text: str, msec: int = 2400) -> None:
        """原地提示一句话（不移动悬浮球）。"""
        self.tag.show_text(text, self.pos(), self.width())
        self._flash_timer.start(msec)

    # ---------- 绘制 ----------
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        size = float(self.width())
        body = QRectF(4, 4, size - 8, size - 8)

        glow = QRadialGradient(body.center(), body.width() / 2 + 6)
        glow.setColorAt(0.70, QColor(75, 141, 255, 95 if self._active else 45))
        glow.setColorAt(1.0, QColor(75, 141, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(body.adjusted(-3, -3, 3, 3))

        gradient = QLinearGradient(body.topLeft(), body.bottomRight())
        gradient.setColorAt(0.0, QColor(ACCENT))
        gradient.setColorAt(1.0, QColor(ACCENT_DEEP))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor(255, 255, 255, 75), 1.2))
        painter.drawEllipse(body)

        pen = QPen(QColor(255, 255, 255, 238), 2.6)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        center = body.center()
        painter.drawEllipse(QPointF(center.x() - 1.5, center.y() - 1.5), 8.2, 8.2)
        painter.drawLine(QPointF(center.x() + 5.4, center.y() + 5.4),
                         QPointF(center.x() + 11.0, center.y() + 11.0))


class HighlightOverlay(QWidget):
    """覆盖整个屏幕的透明高亮层（鼠标穿透）。"""

    def __init__(self) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus
                         | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._rect = QRect()
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def show_at(self, rect: QRect) -> None:
        screen = QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.geometry()
        self.setGeometry(geometry)
        self._rect = rect.translated(-geometry.topLeft())
        self._phase = 0.0
        self.show()
        self.raise_()
        self._timer.start()

    def hide_overlay(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.035) % 1.0
        self.update()

    def paintEvent(self, _event) -> None:
        if self._rect.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        pulse = 0.5 + 0.5 * math.sin(self._phase * 2 * math.pi)
        rect = QRectF(self._rect).adjusted(-8, -8, 8, 8)

        for index in range(3):
            grow = index * (7 + 9 * pulse)
            alpha = max(6, int((72 - index * 22) * (1.0 - 0.55 * pulse)))
            pen = QPen(QColor(75, 141, 255, alpha))
            pen.setWidthF(2.0)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(-grow, -grow, grow, grow),
                                    14 + grow, 14 + grow)

        pen = QPen(QColor(126, 178, 255, 235))
        pen.setWidthF(2.6)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, 14, 14)

        # 四角加粗折角，便于在杂乱桌面上辨认
        corner = QPen(QColor(255, 255, 255, 235))
        corner.setWidthF(3.2)
        corner.setCapStyle(Qt.RoundCap)
        painter.setPen(corner)
        length = 16.0
        left, top = rect.left(), rect.top()
        right, bottom = rect.right(), rect.bottom()
        for sx, sy, dx, dy in ((left, top, 1, 1), (right, top, -1, 1),
                               (left, bottom, 1, -1), (right, bottom, -1, -1)):
            painter.drawLine(QPointF(sx + 4 * dx, sy + 4 * dy),
                             QPointF(sx + (4 + length) * dx, sy + 4 * dy))
            painter.drawLine(QPointF(sx + 4 * dx, sy + 4 * dy),
                             QPointF(sx + 4 * dx, sy + (4 + length) * dy))
