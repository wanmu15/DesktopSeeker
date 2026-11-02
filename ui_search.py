"""悬浮搜索框面板。"""

from __future__ import annotations

import os

from PySide6.QtCore import (QEvent, QFileInfo, QPoint, QPropertyAnimation, QSize, Qt, Signal)
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QIcon
from PySide6.QtWidgets import (QFileIconProvider, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QSizePolicy,
                               QToolButton, QVBoxLayout, QWidget)

from desktop_api import DesktopItem, DesktopScanner
from ui_common import ACCENT, magnifier_pixmap

WINDOW_WIDTH = 600
BASE_HEIGHT = 92
ROW_HEIGHT = 50
MAX_ROWS = 6

_ICON_PROVIDER = QFileIconProvider()


def icon_for(item: DesktopItem) -> QIcon:
    if item.path and os.path.exists(item.path):
        icon = _ICON_PROVIDER.icon(QFileInfo(item.path))
        if not icon.isNull():
            return icon
    return QIcon(magnifier_pixmap(48, ACCENT, 3.2))


class ResultRow(QWidget):
    """单条搜索结果：图标 + 名称 + 来源提示。"""

    def __init__(self, item: DesktopItem) -> None:
        super().__init__()
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(12)

        icon_label = QLabel()
        icon_label.setFixedSize(30, 30)
        icon_label.setPixmap(icon_for(item).pixmap(28, 28))

        name_font = QFont("Microsoft YaHei UI", 10)
        metrics = QFontMetrics(name_font)
        name = QLabel(metrics.elidedText(item.name, Qt.ElideRight, 430))
        name.setFont(name_font)
        name.setStyleSheet("color:#EDF1FA;")
        name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        name.setToolTip(item.name)

        tip = QLabel(item.tip)
        tip.setFont(QFont("Microsoft YaHei UI", 8))
        tip.setStyleSheet("color:#8E97AB;")

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(1)
        column.addWidget(name)
        column.addWidget(tip)

        layout.addWidget(icon_label)
        layout.addLayout(column, 1)


class SearchWindow(QWidget):
    """无边框半透明搜索面板。"""

    locateRequested = Signal(object)
    openRequested = Signal(object)
    dismissed = Signal()

    def __init__(self, scanner: DesktopScanner) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.scanner = scanner
        self._results: list[DesktopItem] = []
        self._fade: QPropertyAnimation | None = None
        # 拖动状态：拖动后记住窗口位置，下次打开沿用
        self._drag_offset: QPoint | None = None
        self._saved_pos: QPoint | None = None
        self._user_positioned = False
        self._edit_press_global: QPoint | None = None
        self._edit_press_pos = QPoint(0, 0)
        self._edit_dragging = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 22)

        card = QFrame(self)
        card.setObjectName("card")
        outer.addWidget(card)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 165))
        card.setGraphicsEffect(shadow)

        body = QVBoxLayout(card)
        body.setContentsMargins(16, 12, 16, 10)
        body.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(10)
        glyph = QLabel()
        glyph.setPixmap(magnifier_pixmap(20, "#8FA4C9", 1.8))
        glyph.setFixedSize(22, 22)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("搜索桌面上的文件、文件夹或程序…")
        self.edit.setFrame(False)
        self.edit.setStyleSheet(
            "QLineEdit{background:transparent;border:none;color:#F2F5FC;font-size:15px;"
            "selection-background-color:rgba(75,141,255,0.45);}")
        self.edit.installEventFilter(self)
        self.edit.textChanged.connect(self._on_text_changed)

        row.addWidget(glyph)
        row.addWidget(self.edit, 1)

        self.close_btn = QToolButton()
        self.close_btn.setText("✕")
        self.close_btn.setToolTip("关闭搜索框（Esc）")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setFocusPolicy(Qt.NoFocus)
        self.close_btn.setFixedSize(26, 26)
        self.close_btn.setStyleSheet(
            "QToolButton{background:transparent;border:none;border-radius:7px;"
            "color:#93A0B8;font-size:13px;}"
            "QToolButton:hover{background:rgba(255,255,255,0.12);color:#FFFFFF;}"
            "QToolButton:pressed{background:rgba(255,255,255,0.20);}")
        self.close_btn.clicked.connect(self.dismiss)
        row.addWidget(self.close_btn)

        body.addLayout(row)

        self.list = QListWidget()
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setSpacing(2)
        # 不接收焦点，避免 Esc / 回车 因焦点落到列表而失效
        self.list.setFocusPolicy(Qt.NoFocus)
        self.list.setStyleSheet(
            "QListWidget{background:transparent;border:none;outline:none;}"
            "QListWidget::item{border-radius:9px;}"
            "QListWidget::item:selected{background:rgba(75,141,255,0.20);}"
            "QListWidget::item:hover{background:rgba(255,255,255,0.05);}")
        self.list.itemClicked.connect(lambda lw: self._activate(self.list.row(lw)))
        self.list.installEventFilter(self)
        self.close_btn.installEventFilter(self)
        self.list.hide()
        body.addWidget(self.list)

        self.status = QLabel("未找到匹配项")
        self.status.setFont(QFont("Microsoft YaHei UI", 9))
        self.status.setStyleSheet("color:#8E97AB;padding:6px 8px;")
        self.status.hide()
        body.addWidget(self.status)

        self.setStyleSheet(
            "QFrame#card{background:rgba(20,22,29,0.95);"
            "border:1px solid rgba(255,255,255,0.10);border-radius:16px;}")
        self.resize(WINDOW_WIDTH, BASE_HEIGHT)

    # ---------- 显示 / 隐藏 ----------
    def open_box(self) -> None:
        self.scanner.ensure_fresh()
        self.edit.blockSignals(True)
        self.edit.clear()
        self.edit.blockSignals(False)
        self._results = []
        self.list.clear()
        self.list.hide()
        self.status.hide()
        self._relayout(0, has_query=False)
        self._place()

        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(130)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

    def hide_box(self) -> None:
        self.hide()
        self.list.clear()
        self._results = []

    def dismiss(self) -> None:
        """关闭面板：右上角 ✕ 或 Esc。"""
        self.hide_box()
        self.dismissed.emit()

    def _place(self) -> None:
        # 用户拖动过：沿用拖动后的位置（按保存位置所在屏幕约束，避免多屏时跳到光标屏）
        if self._user_positioned and self._saved_pos is not None:
            screen = (QGuiApplication.screenAt(self._saved_pos)
                      or QGuiApplication.screenAt(QCursor.pos())
                      or QGuiApplication.primaryScreen())
            if screen is None:
                return
            area = screen.availableGeometry()
            x = min(max(self._saved_pos.x(), area.left()), area.right() - self.width())
            y = min(max(self._saved_pos.y(), area.top()), area.bottom() - self.height())
            self.move(x, y)
            return

        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(area.center().x() - self.width() // 2,
                  area.top() + int(area.height() * 0.16))

    # ---------- 拖动 ----------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            self._user_positioned = True
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            self._saved_pos = self.pos()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ---------- 搜索 ----------
    def _on_text_changed(self, text: str) -> None:
        query = text.strip()
        self._results = self.scanner.search(query) if query else []

        self.list.clear()
        for item in self._results:
            row_item = QListWidgetItem()
            row_item.setSizeHint(QSize(0, ROW_HEIGHT))
            row_item.setData(Qt.UserRole, item)
            self.list.addItem(row_item)
            self.list.setItemWidget(row_item, ResultRow(item))

        if self._results:
            self.list.setCurrentRow(0)
            self.list.show()
            self.status.hide()
            self._relayout(len(self._results), has_query=True)
            self.list.scrollToTop()
        else:
            self.list.hide()
            if query:
                if self.scanner.desktop_ok:
                    self.status.setText("未找到匹配项，试试更短的关键词")
                else:
                    self.status.setText("无法读取桌面图标，请检查资源管理器是否正常")
                self.status.show()
            else:
                self.status.hide()
            self._relayout(0, has_query=bool(query))

        self._place()

    def _relayout(self, rows: int, has_query: bool) -> None:
        if rows > 0:
            area_height = min(rows, MAX_ROWS) * (ROW_HEIGHT + 2)
            self.list.setFixedHeight(area_height)
            self.list.setVerticalScrollBarPolicy(
                Qt.ScrollBarAsNeeded if rows > MAX_ROWS else Qt.ScrollBarAlwaysOff)
        else:
            area_height = 30 if has_query else 0
            self.list.setFixedHeight(0)

        # 状态文字也固定高度，避免隐藏后残留的最小高度把窗口撑大
        self.status.setFixedHeight(area_height if (rows == 0 and has_query) else 0)

        # 先让布局失效并重算最小尺寸，否则窗口会被上一次的高度撑住
        layout = self.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()
        self.setMinimumSize(0, 0)
        self.resize(WINDOW_WIDTH, BASE_HEIGHT + area_height)

    # ---------- 激活 ----------
    def _activate(self, row: int) -> None:
        if not (0 <= row < len(self._results)):
            return
        item = self._results[row]
        self.hide_box()
        if item.source == "desktop":
            self.locateRequested.emit(item)
        else:
            self.openRequested.emit(item)

    def _move_selection(self, step: int) -> None:
        if not self._results:
            return
        row = self.list.currentRow()
        row = min(max(row + step, 0), len(self._results) - 1)
        self.list.setCurrentRow(row)

    def eventFilter(self, obj, event) -> bool:
        # 列表/关闭按钮即使拿到焦点，也保证 Esc 与回车可用
        if event.type() == QEvent.KeyPress and (obj is getattr(self, "close_btn", None)
                                                or obj is getattr(self, "list", None)):
            key = event.key()
            if key == Qt.Key_Escape:
                self.dismiss()
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._activate(self.list.currentRow())
                return True

        if obj is self.edit and event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._activate(self.list.currentRow())
                return True
            if key == Qt.Key_Escape:
                self.dismiss()
                return True
            if key == Qt.Key_Down:
                self._move_selection(1)
                return True
            if key == Qt.Key_Up:
                self._move_selection(-1)
                return True
        # 按住输入框也能拖动整个面板（轻微点击仍是定位光标）
        if obj is self.edit:
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._edit_press_global = event.globalPosition().toPoint()
                self._edit_press_pos = self.pos()
                self._edit_dragging = False
            elif event.type() == QEvent.MouseMove and self._edit_press_global is not None:
                if event.buttons() & Qt.LeftButton:
                    delta = event.globalPosition().toPoint() - self._edit_press_global
                    if self._edit_dragging or delta.manhattanLength() > 5:
                        self._edit_dragging = True
                        self.move(self._edit_press_pos + delta)
                        self._user_positioned = True
                        return True
            elif event.type() == QEvent.MouseButtonRelease:
                self._edit_press_global = None
                if self._edit_dragging:
                    self._edit_dragging = False
                    self._saved_pos = self.pos()
        return super().eventFilter(obj, event)
