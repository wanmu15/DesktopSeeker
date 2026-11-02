"""Windows 桌面搜索器：悬浮搜索框 + 悬浮球定位桌面图标。

启动后：
- 屏幕右侧出现悬浮球，单击（或按 Ctrl+Alt+F）打开搜索框；
- 输入文件名 / 程序名，回车后悬浮球飞到该桌面图标旁并高亮；
- 托盘图标提供退出与“定位前先显示桌面”开关。
"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes

from PySide6.QtCore import QLockFile, QAbstractNativeEventFilter, QObject, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

import desktop_api
from desktop_api import DesktopItem, DesktopScanner
from ui_ball import FloatingBall, HighlightOverlay
from ui_common import magnifier_pixmap, physical_rect_to_logical
from ui_search import SearchWindow

HOTKEY_ID = 0xA1
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
VK_F = 0x46
WM_HOTKEY = 0x0312
SINGLE_INSTANCE_KEY = "DesktopSeeker.SingleInstance"

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.RegisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL


def _set_dpi_aware() -> None:
    """让系统返回真实物理像素，坐标换算由我们自己处理。"""
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4 & 0xFFFFFFFFFFFFFFFF))
    except Exception:
        pass


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback) -> None:
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and int(msg.wParam) == HOTKEY_ID:
                self._callback()
                return True, 0
        return False, 0


class DesktopSeeker(QObject):
    """把搜索框、悬浮球、高亮层串起来。"""

    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.scanner = DesktopScanner()
        self.scanner.ensure_fresh(desktop_max_age=0, apps_max_age=0)
        self.show_desktop_first = True
        self.collapse_after_launch = True
        self._tray_collapse_action = None
        self._tray_show_desktop_action = None

        self.ball = FloatingBall()
        self.search = SearchWindow(self.scanner)
        self.overlay = HighlightOverlay()

        self.ball.clicked.connect(self.toggle_search)
        self.ball.request_search.connect(self.open_search)
        self.ball.request_quit.connect(self.app.quit)
        self.ball.show_desktop_toggled.connect(self.set_show_desktop)
        self.ball.collapse_after_launch_toggled.connect(self.set_collapse_after_launch)
        self.search.locateRequested.connect(self.locate)
        self.search.openRequested.connect(self.launch)
        self.search.dismissed.connect(self.on_search_dismissed)

        self.ball.move_home()
        self.ball.show()

        # 高亮环在悬浮球返回后自动淡出
        self._overlay_timer = QTimer(self)
        self._overlay_timer.setSingleShot(True)
        self._overlay_timer.timeout.connect(self._on_overlay_timeout)

        # 定位后监测被定位的程序是否被打开（双击图标等）
        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(700)
        self._watch_timer.timeout.connect(self._tick_watch)
        self._watch_names: set[str] = set()
        self._watch_pids: set[int] = set()
        self._watch_foreground: tuple[int, str] = (0, "")

    # ---------- 开关 ----------
    @staticmethod
    def _sync_action(action, value: bool) -> None:
        """把托盘菜单的勾选状态同步为 value（不触发它自己的信号）。"""
        if action is not None and action.isChecked() != value:
            action.blockSignals(True)
            action.setChecked(value)
            action.blockSignals(False)

    def set_show_desktop(self, value: bool) -> None:
        self.show_desktop_first = value
        self.ball.set_show_desktop_checked(value)
        self._sync_action(self._tray_show_desktop_action, value)

    def attach_tray_toggle(self, collapse_action, show_desktop_action=None) -> None:
        """记录托盘中的同名开关，用于与悬浮球菜单双向同步。"""
        self._tray_collapse_action = collapse_action
        self._tray_show_desktop_action = show_desktop_action

    def set_collapse_after_launch(self, value: bool) -> None:
        """程序被打开后是否收起定位提示（高亮环 + 名称气泡）。"""
        self.collapse_after_launch = value
        self.ball.set_collapse_after_launch_checked(value)
        self._sync_action(self._tray_collapse_action, value)

    def open_search(self) -> None:
        self._watch_timer.stop()
        self._overlay_timer.stop()
        self.overlay.hide_overlay()
        self.ball.return_home()
        self.ball.set_active(True)
        self.search.open_box()

    def toggle_search(self) -> None:
        if self.search.isVisible():
            self.search.dismiss()
        else:
            self.open_search()

    def on_search_dismissed(self) -> None:
        """搜索框被 ✕ / Esc 关闭后，收起高亮与悬浮球。"""
        self._watch_timer.stop()
        self._overlay_timer.stop()
        self.overlay.hide_overlay()
        self.ball.return_home()
        self.ball.set_active(False)

    # ---------- 定位 / 启动 ----------
    def locate(self, item: DesktopItem) -> None:
        self.ball.set_active(False)

        if item.source != "desktop":
            self.launch(item)
            return
        if item.w <= 0 or item.h <= 0:
            self.ball.flash_text("该图标当前无法定位")
            return

        if self.show_desktop_first:
            desktop_api.show_desktop()

        rect = physical_rect_to_logical(item.x, item.y, item.w, item.h)
        if rect is None:
            self.ball.flash_text("无法获取图标位置")
            return

        self.overlay.show_at(rect)
        self.ball.point_to(rect, item.name)
        self.ball.show()
        self.ball.raise_()
        self._overlay_timer.start(5600)
        self._start_watch(item)

    # ---------- 打开被定位的程序后收起提示 ----------
    def _start_watch(self, item: DesktopItem) -> None:
        self._watch_timer.stop()
        if not self.collapse_after_launch:
            return

        names = {item.name.casefold(), os.path.splitext(item.name)[0].casefold()}
        if item.path:
            names.add(os.path.splitext(os.path.basename(item.path))[0].casefold())
            target = desktop_api.resolve_shortcut_target(item.path)
            if target:
                names.add(os.path.splitext(os.path.basename(target))[0].casefold())
        names.discard("")

        self._watch_names = names
        self._watch_pids = desktop_api.list_process_ids()
        self._watch_foreground = desktop_api.foreground_window()
        self._watch_timer.start()

    def _tick_watch(self) -> None:
        pids = desktop_api.list_process_ids()
        for pid in pids - self._watch_pids:
            stem = self._exe_stem(pid)
            if stem and stem in self._watch_names:
                self.collapse_hint()
                return
        self._watch_pids = pids

        foreground = desktop_api.foreground_window()
        if foreground != self._watch_foreground:
            self._watch_foreground = foreground
            pid, title = foreground
            stem = self._exe_stem(pid)
            if (stem and stem in self._watch_names) or self._title_matches(title):
                self.collapse_hint()

    @staticmethod
    def _exe_stem(pid: int) -> str:
        path = desktop_api.process_image_path(pid)
        return os.path.splitext(os.path.basename(path))[0].casefold() if path else ""

    def _title_matches(self, title: str) -> bool:
        clean = title.strip().casefold()
        if not clean:
            return False
        for name in self._watch_names:
            if clean == name or clean.startswith(name + " "):
                return True
        return False

    def collapse_hint(self) -> None:
        """收起高亮环与名称气泡，悬浮球回到原位。"""
        self._watch_timer.stop()
        self._overlay_timer.stop()
        self.overlay.hide_overlay()
        self.ball.return_home()

    def _on_overlay_timeout(self) -> None:
        self.overlay.hide_overlay()
        self._watch_timer.stop()

    def launch(self, item: DesktopItem) -> None:
        self._overlay_timer.stop()
        self.overlay.hide_overlay()
        if not item.path:
            self.ball.flash_text("找不到该程序的文件位置")
            return
        try:
            os.startfile(item.path)
        except OSError:
            self.ball.flash_text("启动失败：" + item.name)
            return
        if self.collapse_after_launch:
            self.collapse_hint()
            return
        self.ball.flash_text("已启动：" + item.name, 2200)


def _notify_existing_instance() -> None:
    """已有实例时，请求它打开搜索框。"""
    socket = QLocalSocket()
    socket.connectToServer(SINGLE_INSTANCE_KEY)
    if not socket.waitForConnected(300):
        return
    socket.write(b"show")
    socket.flush()
    socket.waitForBytesWritten(300)
    socket.disconnectFromServer()


def _acquire_instance_lock() -> QLockFile | None:
    """获取单实例文件锁；已有实例在运行时返回 None。

    注意：PyInstaller 单文件模式会改写 TEMP 目录，所以不能用临时目录，
    否则每个实例的锁文件路径都不同，单实例会失效。
    """
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    lock = QLockFile(os.path.join(base, "DesktopSeeker.lock"))
    if not lock.tryLock(100):
        return None
    return lock


def main() -> None:
    _set_dpi_aware()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("桌面搜索器")

    # 单实例：第二个进程只唤醒已运行实例并退出
    instance_lock = _acquire_instance_lock()
    if instance_lock is None:
        _notify_existing_instance()
        return

    server = QLocalServer()
    if not server.listen(SINGLE_INSTANCE_KEY):
        QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
        server.listen(SINGLE_INSTANCE_KEY)

    icon = QIcon(magnifier_pixmap(64, "#4B8DFF", 5.0))
    app.setWindowIcon(icon)

    seeker = DesktopSeeker(app)

    def on_instance_request() -> None:
        connection = server.nextPendingConnection()
        if connection is not None:
            connection.readyRead.connect(lambda: connection.readAll())
            connection.disconnected.connect(connection.deleteLater)
        seeker.open_search()

    server.newConnection.connect(on_instance_request)

    tray_menu = QMenu()
    tray_menu.setStyleSheet(
        "QMenu{background:#1B1E26;color:#E8EDF8;border:1px solid rgba(255,255,255,0.12);"
        "border-radius:8px;padding:6px;}"
        "QMenu::item{padding:6px 18px;border-radius:5px;}"
        "QMenu::item:selected{background:rgba(75,141,255,0.24);}")

    action_search = tray_menu.addAction("打开搜索框  Ctrl+Alt+F")
    action_desktop = tray_menu.addAction("定位前先显示桌面")
    action_desktop.setCheckable(True)
    action_desktop.setChecked(True)
    action_collapse = tray_menu.addAction("启动程序后收起定位提示")
    action_collapse.setCheckable(True)
    action_collapse.setChecked(True)
    seeker.attach_tray_toggle(action_collapse, action_desktop)
    tray_menu.addSeparator()
    action_quit = tray_menu.addAction("退出")

    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("桌面搜索器  Ctrl+Alt+F")
    tray.setContextMenu(tray_menu)
    tray.show()

    action_search.triggered.connect(seeker.open_search)
    action_desktop.toggled.connect(seeker.set_show_desktop)
    action_collapse.toggled.connect(seeker.set_collapse_after_launch)
    action_quit.triggered.connect(app.quit)
    tray.activated.connect(
        lambda reason: seeker.open_search() if reason == QSystemTrayIcon.Trigger else None)

    # 全局热键
    hotkey_filter = HotkeyFilter(seeker.toggle_search)
    app.installNativeEventFilter(hotkey_filter)
    registered = user32.RegisterHotKey(None, HOTKEY_ID,
                                       MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_F)
    if not registered:
        tray.showMessage("桌面搜索器", "全局热键 Ctrl+Alt+F 被占用，请用悬浮球打开搜索框",
                         QSystemTrayIcon.Information, 4000)

    try:
        code = app.exec()
    finally:
        if registered:
            user32.UnregisterHotKey(None, HOTKEY_ID)
    sys.exit(code)


if __name__ == "__main__":
    main()
