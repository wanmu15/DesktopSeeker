"""Win32 支持层。

职责：
1. 读取桌面图标列表及其在屏幕上的物理像素坐标（跨进程读取 Explorer 的 SysListView32）；
2. 枚举开始菜单中的程序（快捷方式 / exe）；
3. 提供显示器物理坐标信息，供界面换算逻辑坐标；
4. 定位前把桌面显示出来。
"""

from __future__ import annotations

import ctypes
import os
import time
import uuid
from ctypes import wintypes
from dataclasses import dataclass

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ole32 = ctypes.WinDLL("ole32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

# ---------- 常量 ----------
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_QUERY_INFORMATION = 0x0400

MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04

LVM_GETITEMCOUNT = 0x1004
LVM_GETITEMRECT = 0x100E
LVM_GETITEMTEXTW = 0x1073
LVIF_TEXT = 0x0001
LVIR_BOUNDS = 0

WM_COMMAND = 0x0111
CMD_TOGGLE_DESKTOP = 0x7402

SMTO_BLOCK = 0x0001
SMTO_ABORTIFHUNG = 0x0002

MONITOR_DEFAULTTONEAREST = 2

TEXT_CAPACITY = 260
MEM_SIZE = 8192
TEXT_OFFSET = 256
RECT_OFFSET = 4096

# 已知文件夹 GUID
FOLDERID_DESKTOP = "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"
FOLDERID_PUBLIC_DESKTOP = "{C4AA340D-F20F-4863-AFEF-F87EF2E6BA25}"
FOLDERID_PROGRAMS = "{A77F5D77-2E2B-44C3-A6A2-ABA601054A51}"
FOLDERID_COMMON_PROGRAMS = "{0139D44E-6AFE-49F2-8690-3DAFCAE6FFB8}"


# ---------- 结构体 ----------
class LVITEMW(ctypes.Structure):
    _fields_ = [
        ("mask", wintypes.UINT),
        ("iItem", ctypes.c_int),
        ("iSubItem", ctypes.c_int),
        ("state", wintypes.UINT),
        ("stateMask", wintypes.UINT),
        ("pszText", ctypes.c_void_p),
        ("cchTextMax", ctypes.c_int),
        ("iImage", ctypes.c_int),
        ("lParam", ctypes.c_ssize_t),
        ("iIndent", ctypes.c_int),
        ("iGroupId", ctypes.c_int),
        ("cColumns", wintypes.UINT),
        ("puColumns", ctypes.c_void_p),
        ("piColFmt", ctypes.c_void_p),
        ("iGroup", ctypes.c_int),
    ]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


# ---------- 函数原型 ----------
user32.SendMessageTimeoutW.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_size_t,
                                       ctypes.c_ssize_t, wintypes.UINT, wintypes.UINT,
                                       ctypes.POINTER(ctypes.c_size_t)]
user32.SendMessageTimeoutW.restype = ctypes.c_ssize_t
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = ctypes.c_void_p
user32.FindWindowExW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowExW.restype = ctypes.c_void_p
user32.ClientToScreen.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.POINT)]
user32.ClientToScreen.restype = wintypes.BOOL
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, ctypes.c_void_p, ctypes.c_ssize_t)
user32.EnumWindows.argtypes = [WNDENUMPROC, ctypes.c_ssize_t]
user32.EnumWindows.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetForegroundWindow.restype = ctypes.c_void_p
user32.GetClassNameW.argtypes = [ctypes.c_void_p, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
user32.MonitorFromPoint.restype = ctypes.c_void_p
user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.GetMonitorInfoW.restype = wintypes.BOOL

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = ctypes.c_void_p
kernel32.VirtualAllocEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]
kernel32.VirtualAllocEx.restype = ctypes.c_void_p
kernel32.VirtualFreeEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD]
kernel32.VirtualFreeEx.restype = wintypes.BOOL
kernel32.WriteProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                        ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
kernel32.WriteProcessMemory.restype = wintypes.BOOL
kernel32.ReadProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                       ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
kernel32.ReadProcessMemory.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
kernel32.CloseHandle.restype = wintypes.BOOL

shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, ctypes.c_void_p,
                                         ctypes.POINTER(ctypes.c_wchar_p)]
shell32.SHGetKnownFolderPath.restype = ctypes.c_long
ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
ole32.CoTaskMemFree.restype = None


# ---------- 数据模型 ----------
@dataclass
class DesktopItem:
    name: str
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0
    path: str = ""
    source: str = "desktop"  # desktop / startmenu

    @property
    def tip(self) -> str:
        if self.source == "desktop":
            return "桌面图标 · 回车定位"
        return "开始菜单 · 回车启动"

    def __repr__(self) -> str:  # 便于命令行调试
        return f"<{self.source} {self.name!r} ({self.x},{self.y},{self.w}x{self.h}) {self.path}>"


# ---------- 已知文件夹 ----------
def known_folder(guid_text: str) -> str:
    raw = uuid.UUID(guid_text).bytes_le
    guid = GUID.from_buffer_copy(raw)
    buf = ctypes.c_wchar_p()
    hr = shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(buf))
    if hr != 0 or not buf.value:
        return ""
    try:
        return buf.value
    finally:
        ole32.CoTaskMemFree(ctypes.cast(buf, ctypes.c_void_p))


# ---------- 桌面 ListView ----------
def _find_desktop_listview() -> int:
    """找到桌面图标的 SysListView32 窗口句柄。"""
    progman = user32.FindWindowW("Progman", None)
    defview = user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None) if progman else None
    if not defview:
        found: list[int] = []

        @WNDENUMPROC
        def _enum(hwnd, _lparam):
            view = user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None)
            if view:
                found.append(view)
                return False
            return True

        user32.EnumWindows(_enum, 0)
        defview = found[0] if found else None
    if not defview:
        return 0
    listview = user32.FindWindowExW(defview, None, "SysListView32", None)
    return int(listview) if listview else 0


class DesktopUnavailable(RuntimeError):
    """无法读取桌面图标（资源管理器异常或权限不足）。"""


def _send_message(hwnd: int, msg: int, wparam: int = 0, lparam: int = 0,
                  timeout_ms: int = 500) -> int | None:
    """带超时的 SendMessage，避免资源管理器无响应时卡住界面。失败返回 None。"""
    result = ctypes.c_size_t()
    ok = user32.SendMessageTimeoutW(hwnd, msg, wparam, lparam,
                                    SMTO_ABORTIFHUNG | SMTO_BLOCK, timeout_ms,
                                    ctypes.byref(result))
    return int(result.value) if ok else None


def _read_items(hwnd: int, proc: int, mem: int) -> list[DesktopItem]:
    count = _send_message(hwnd, LVM_GETITEMCOUNT)
    if count is None:
        raise DesktopUnavailable("桌面图标视图无响应")
    items: list[DesktopItem] = []

    for index in range(max(count, 0)):
        # 1) 读取显示名称
        lv = LVITEMW()
        lv.mask = LVIF_TEXT
        lv.iItem = index
        lv.iSubItem = 0
        lv.pszText = mem + TEXT_OFFSET
        lv.cchTextMax = TEXT_CAPACITY
        if not kernel32.WriteProcessMemory(proc, mem, ctypes.byref(lv), ctypes.sizeof(lv), None):
            continue
        if not _send_message(hwnd, LVM_GETITEMTEXTW, index, mem):
            continue
        text_buf = ctypes.create_unicode_buffer(TEXT_CAPACITY)
        if not kernel32.ReadProcessMemory(proc, mem + TEXT_OFFSET, text_buf,
                                          TEXT_CAPACITY * 2, None):
            continue
        name = text_buf.value
        if not name:
            continue

        # 2) 读取图标整体矩形（left 必须置为 LVIR_BOUNDS）
        rect = wintypes.RECT(LVIR_BOUNDS, 0, 0, 0)
        if not kernel32.WriteProcessMemory(proc, mem + RECT_OFFSET, ctypes.byref(rect),
                                           ctypes.sizeof(rect), None):
            continue
        if not _send_message(hwnd, LVM_GETITEMRECT, index, mem + RECT_OFFSET):
            continue
        if not kernel32.ReadProcessMemory(proc, mem + RECT_OFFSET, ctypes.byref(rect),
                                          ctypes.sizeof(rect), None):
            continue

        top_left = wintypes.POINT(rect.left, rect.top)
        bottom_right = wintypes.POINT(rect.right, rect.bottom)
        user32.ClientToScreen(hwnd, ctypes.byref(top_left))
        user32.ClientToScreen(hwnd, ctypes.byref(bottom_right))
        width = bottom_right.x - top_left.x
        height = bottom_right.y - top_left.y
        if width <= 0 or height <= 0:
            continue

        items.append(DesktopItem(name=name, x=top_left.x, y=top_left.y, w=width, h=height))

    return items


def read_desktop_items() -> list[DesktopItem]:
    """读取桌面全部图标的名称与屏幕矩形（物理像素）。

    无法读取时抛出 DesktopUnavailable，便于界面区分“桌面没有结果”和“读取失败”。
    """
    hwnd = _find_desktop_listview()
    if not hwnd:
        raise DesktopUnavailable("未找到桌面图标视图")

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        raise DesktopUnavailable("无法获取资源管理器进程")

    access = PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_QUERY_INFORMATION
    proc = kernel32.OpenProcess(access, False, pid.value)
    if not proc:
        raise DesktopUnavailable("无法打开资源管理器进程")

    mem = kernel32.VirtualAllocEx(proc, None, MEM_SIZE, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE)
    if not mem:
        kernel32.CloseHandle(proc)
        raise DesktopUnavailable("无法分配读取内存")

    try:
        items = _read_items(hwnd, proc, mem)
    except OSError:
        items = []
    finally:
        kernel32.VirtualFreeEx(proc, mem, 0, MEM_RELEASE)
        kernel32.CloseHandle(proc)

    _attach_paths(items)
    return items


def _attach_paths(items: list[DesktopItem]) -> None:
    """把桌面图标名称映射到真实路径（用于取程序图标、打开文件）。"""
    index: dict[str, str] = {}
    for folder in (known_folder(FOLDERID_DESKTOP), known_folder(FOLDERID_PUBLIC_DESKTOP)):
        if not folder or not os.path.isdir(folder):
            continue
        try:
            entries = os.listdir(folder)
        except OSError:
            continue
        for entry in entries:
            full = os.path.join(folder, entry)
            index.setdefault(entry.casefold(), full)
            index.setdefault(os.path.splitext(entry)[0].casefold(), full)

    for item in items:
        item.path = index.get(item.name.casefold(), "")


# ---------- 开始菜单 ----------
def read_start_menu_apps() -> list[DesktopItem]:
    apps: list[DesktopItem] = []
    seen: set[str] = set()
    for guid in (FOLDERID_COMMON_PROGRAMS, FOLDERID_PROGRAMS):
        root = known_folder(guid)
        if not root or not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for filename in files:
                lower = filename.lower()
                if not lower.endswith((".lnk", ".url", ".exe")):
                    continue
                if lower.startswith(("uninstall", "卸载")):
                    continue
                name = os.path.splitext(filename)[0]
                key = name.casefold()
                if key in seen:
                    continue
                seen.add(key)
                apps.append(DesktopItem(name=name, path=os.path.join(dirpath, filename),
                                        source="startmenu"))
    return apps


# ---------- 显示器与桌面 ----------
def monitor_rect_for_point(x: int, y: int):
    """返回该物理坐标所在显示器：(left, top, right, bottom, 设备名)。"""
    hmon = user32.MonitorFromPoint(wintypes.POINT(x, y), MONITOR_DEFAULTTONEAREST)
    if not hmon:
        return None
    info = MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(MONITORINFOEXW)
    if not user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
        return None
    rect = info.rcMonitor
    return rect.left, rect.top, rect.right, rect.bottom, info.szDevice


def show_desktop() -> None:
    """如果当前前台不是桌面，则把桌面显示出来（Win+D 的等价操作）。"""
    foreground = user32.GetForegroundWindow()
    class_name = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(foreground, class_name, 256)
    if class_name.value in ("Progman", "WorkerW"):
        return
    progman = user32.FindWindowW("Progman", None)
    if progman:
        _send_message(progman, WM_COMMAND, CMD_TOGGLE_DESKTOP, 0, 1000)


# ---------- 进程 / 前台窗口（用于判断被定位的程序是否已启动） ----------
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

psapi.EnumProcesses.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD,
                                ctypes.POINTER(wintypes.DWORD)]
psapi.EnumProcesses.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, wintypes.DWORD,
                                                wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
user32.GetWindowTextW.argtypes = [ctypes.c_void_p, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int


def list_process_ids() -> set[int]:
    capacity = 4096
    buffer = (wintypes.DWORD * capacity)()
    needed = wintypes.DWORD()
    if not psapi.EnumProcesses(buffer, ctypes.sizeof(buffer), ctypes.byref(needed)):
        return set()
    count = needed.value // ctypes.sizeof(wintypes.DWORD)
    return {int(buffer[index]) for index in range(count)}


def process_image_path(pid: int) -> str:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return ""
        return buffer.value
    finally:
        kernel32.CloseHandle(handle)


def foreground_window() -> tuple[int, str]:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return 0, ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    title = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, title, 512)
    return pid.value, title.value


def resolve_shortcut_target(path: str) -> str:
    """解析 .lnk 指向的目标路径；依赖 pywin32，失败时返回空串。"""
    if not path or not path.lower().endswith(".lnk"):
        return ""
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return ""
    try:
        pythoncom.CoInitialize()
        shell = win32com.client.Dispatch("WScript.Shell")
        return shell.CreateShortcut(path).TargetPath or ""
    except Exception:
        return ""


# ---------- 检索 ----------
def _match_score(name: str, query: str) -> int:
    full = name.casefold()
    stem = os.path.splitext(full)[0]
    if full == query or stem == query:
        return 0
    if full.startswith(query) or stem.startswith(query):
        return 1
    if query in full:
        return 2
    return 99


class DesktopScanner:
    """带缓存的检索器：桌面图标 + 开始菜单程序。"""

    def __init__(self) -> None:
        self._desktop: list[DesktopItem] = []
        self._apps: list[DesktopItem] = []
        self._desktop_time = 0.0
        self._apps_time = 0.0
        self.desktop_ok = False

    def ensure_fresh(self, desktop_max_age: float = 2.0, apps_max_age: float = 600.0) -> None:
        now = time.time()
        if now - self._desktop_time > desktop_max_age:
            try:
                self._desktop = read_desktop_items()
                self.desktop_ok = True
                self._desktop_time = now
            except Exception:
                self._desktop = []
                self.desktop_ok = False
                self._desktop_time = 0.0  # 读取失败时下次调用立即重试
        if now - self._apps_time > apps_max_age:
            try:
                self._apps = read_start_menu_apps()
            except Exception:
                self._apps = []
            self._apps_time = now

    def search(self, query: str, limit: int = 8) -> list[DesktopItem]:
        q = query.strip().casefold()
        if not q:
            return []

        scored: list[tuple[int, int, DesktopItem]] = []
        seen: set[str] = set()

        for item in self._desktop:
            score = _match_score(item.name, q)
            if score < 99:
                scored.append((score, len(item.name), item))
                seen.add(item.name.casefold())

        for item in self._apps:
            key = item.name.casefold()
            if key in seen:
                continue
            score = _match_score(item.name, q)
            if score < 99:
                scored.append((score + 3, len(item.name), item))  # 开始菜单结果排在桌面之后

        scored.sort(key=lambda row: (row[0], row[1]))
        return [row[2] for row in scored[:limit]]
