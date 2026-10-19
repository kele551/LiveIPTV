# 作者: 海风（kele551）   https://github.com/kele551/LiveIPTV
# 右下角托盘图标 —— 纯 ctypes 调 Windows Shell API，零第三方依赖。
# 左键双击 = 打开控制台；右键 = 菜单（打开控制台 / 立即更新 / 打开 M3U 目录 / 退出程序）。
import ctypes
import os
import sys
import threading
import traceback
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def _dbg():
    """托盘是可选功能：出错不打断主程序；设 LIVE_TRAY_DEBUG=1 时把异常打到 stderr。"""
    if os.environ.get("LIVE_TRAY_DEBUG"):
        traceback.print_exc(file=sys.stderr)


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_LBUTTONDBLCLK = 0x0203
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
WM_APP = 0x8000
WM_TRAY_CB = WM_APP + 20

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x1, 0x2, 0x4, 0x10
NIIF_NONE = 0x0          # 不显示图标（用户说系统缩放的图标糊，那就不要）
NIIF_INFO = 0x1
NIIF_USER = 0x4          # 用自定义图标（程序自己的红方块），不要系统那个蓝底 i
NIIF_LARGE_ICON = 0x20   # 气泡里显示大号图标
MF_STRING = 0x0
MF_GRAYED = 0x1
MF_DISABLED = 0x2
MF_SEPARATOR = 0x800
MF_DEFAULT = 0x1000
TPM_RIGHTBUTTON = 0x2
TPM_RETURNCMD = 0x100
IDI_APPLICATION = 32512
SM_CXSMICON = 49
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040

ID_OPEN, ID_UPDATE, ID_FOLDER, ID_QUIT = 1001, 1002, 1003, 1004


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD),
                ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
                ("uVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64),
                ("dwInfoFlags", wintypes.DWORD), ("guidItem", ctypes.c_byte * 16),
                ("hBalloonIcon", wintypes.HICON)]


# 显式声明原型：64 位下指针/长整型不声明会被截断（会抛 OverflowError 或让消息环坏掉）
_void_p = ctypes.c_void_p
user32.DefWindowProcW.argtypes = [_void_p, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.CreateWindowExW.restype = _void_p
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                   wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, _void_p, _void_p, _void_p, _void_p]
user32.RegisterClassExW.restype = ctypes.c_ushort
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterWindowMessageW.restype = wintypes.UINT
user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
user32.LoadImageW.restype = _void_p
user32.LoadImageW.argtypes = [_void_p, wintypes.LPCWSTR, wintypes.UINT,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.CreatePopupMenu.restype = _void_p
user32.AppendMenuW.restype = wintypes.BOOL
user32.AppendMenuW.argtypes = [_void_p, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.DestroyMenu.argtypes = [_void_p]
user32.SetMenuDefaultItem.argtypes = [_void_p, wintypes.UINT, wintypes.UINT]
user32.SetMenuDefaultItem.restype = wintypes.BOOL
user32.TrackPopupMenu.restype = ctypes.c_int
user32.TrackPopupMenu.argtypes = [_void_p, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, _void_p, _void_p]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.SetForegroundWindow.argtypes = [_void_p]
user32.PostMessageW.argtypes = [_void_p, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), _void_p, wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.LoadImageW.restype = _void_p
user32.LoadImageW.argtypes = [_void_p, wintypes.LPCWSTR, wintypes.UINT,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.LoadIconW.restype = _void_p
user32.LoadIconW.argtypes = [_void_p, _void_p]
shell32.ExtractIconExW.restype = wintypes.UINT
shell32.ExtractIconExW.argtypes = [wintypes.LPCWSTR, ctypes.c_int,
                                   ctypes.POINTER(_void_p), ctypes.POINTER(_void_p),
                                   wintypes.UINT]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
kernel32.GetModuleHandleW.restype = _void_p
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]



class Tray:
    """托盘图标。start() 返回是否成功；失败时调用方继续以"只有网页"的方式运行。"""

    def __init__(self, title, icon_path, on_open=None, on_update=None,
                 on_folder=None, on_quit=None, status_provider=None, icon_file="",
                 icon_busy="", app_icon=""):
        self.title = title
        self.status_provider = status_provider
        self.icon_path = icon_path
        self.icon_file = icon_file
        self.icon_busy = icon_busy
        self.app_icon = app_icon          # 气泡里用的"程序图标"，不是托盘小三角
        self._busy = False
        self.on_open = on_open
        self.on_update = on_update
        self.on_folder = on_folder
        self.on_quit = on_quit
        self.hwnd = None
        self._thread = None
        self._ready = threading.Event()
        self._ok = False
        self._nid = None
        self._proc = None
        self._class_name = "LIVEIPTV_TRAY_%d" % id(self)

    # ---------------------------------------------------------------- 对外
    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="tray")
        self._thread.start()
        self._ready.wait(3)
        return self._ok

    def stop(self):
        if self.hwnd:
            try:
                user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(1.5)

    def notify(self, title, text, icon=None):
        """气泡提示（更新完成之类）。图标用程序自己的红方块，不用系统的蓝底 i。"""
        try:
            if not self._nid:
                return
            nid = self._nid
            nid.szInfo = text[:255]
            nid.szInfoTitle = title[:63]
            # 提示里不放图标：Windows 会把它缩放到固定大小，无论给多大都会糊
            # （用户明确说"小图标都糊了，也就别要了"）。只留两行干净文字。
            nid.hBalloonIcon = 0
            nid.dwInfoFlags = NIIF_NONE
            nid.uFlags = NIF_INFO
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
        except Exception:
            pass

    def refresh_tip(self):
        """把"悬停提示"更新成当前状态（频道数 / 上次更新）。"""
        try:
            st = self._status()
            if not self._nid:
                return
            nid = self._nid
            tip = st.get("tip") or self.title
            nid.szTip = tip[:127]
            nid.uFlags = NIF_TIP
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
        except Exception:
            _dbg()

    def _balloon_icon(self):
        """气泡图标：程序大图标(红徽标)的 128/96 像素档，Windows 缩下来才不糊。"""
        for path, sizes in ((self.app_icon, (128, 96, 256, 64)),
                            (self.icon_file, (48, 32))):
            if not path:
                continue
            try:
                for size in sizes:
                    h = user32.LoadImageW(None, ctypes.c_wchar_p(path),
                                          IMAGE_ICON, size, size, LR_LOADFROMFILE)
                    if h:
                        return h
            except Exception:
                _dbg()
        return None

    # ---------------------------------------------------------------- 内部
    def _load_icon(self, path=""):
        # 1) 随包的 ico：按系统"小图标"实际尺寸取，托盘里最清楚
        path = path or self.icon_file
        if path:
            try:
                cx = user32.GetSystemMetrics(SM_CXSMICON) or 16
                for size in (cx, 32, 24, 20, 16):
                    h = user32.LoadImageW(None, ctypes.c_wchar_p(path),
                                          IMAGE_ICON, size, size, LR_LOADFROMFILE)
                    if h:
                        return h
            except Exception:
                _dbg()
        large = wintypes.HICON()
        small = wintypes.HICON()
        try:
            n = shell32.ExtractIconExW(ctypes.c_wchar_p(self.icon_path), 0,
                                       ctypes.byref(large), ctypes.byref(small), 1)
            if n and small.value:
                return small.value
            if n and large.value:
                return large.value
        except Exception:
            pass
        try:
            return user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))
        except Exception:
            return None

    def set_busy(self, busy):
        """更新中换成"方块"图标，更新完换回"三角"。"""
        busy = bool(busy)
        if busy == self._busy:
            return
        self._busy = busy
        h = None
        if busy and self.icon_busy:
            h = self._load_icon(self.icon_busy)
        if not h:
            h = self._load_icon(self.icon_file)
            if busy and self.icon_busy:
                self._busy = False        # 忙碌图标没加载出来，别把状态卡住
        if not h:
            return
        self._icon = h
        try:
            if self._nid is not None:
                nid = self._nid
                nid.uFlags = NIF_ICON
                nid.hIcon = h
                shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
        except Exception:
            _dbg()

    def _status(self):
        """取当前状态（版本/可用数/上次更新/是否正在更新），拿不到就返回空字典。"""
        try:
            if self.status_provider:
                return self.status_provider() or {}
        except Exception:
            _dbg()
        return {}

    def _menu(self):
        st = self._status()
        hmenu = user32.CreatePopupMenu()
        # 顶部两行是"说明"，不是按钮：灰显，只为让菜单一眼看清现在什么状态
        user32.AppendMenuW(hmenu, MF_STRING | MF_GRAYED | MF_DISABLED, 0,
                           st.get("header") or self.title)
        user32.AppendMenuW(hmenu, MF_STRING | MF_GRAYED | MF_DISABLED, 0,
                           st.get("info") or "正在准备…")
        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(hmenu, MF_STRING | MF_DEFAULT, ID_OPEN, "打开控制台")
        if st.get("updating"):
            user32.AppendMenuW(hmenu, MF_STRING | MF_GRAYED | MF_DISABLED, ID_UPDATE,
                               "正在更新… %s" % st.get("progress", ""))
        else:
            user32.AppendMenuW(hmenu, MF_STRING, ID_UPDATE, "立即更新频道")
        user32.AppendMenuW(hmenu, MF_STRING, ID_FOLDER, "打开保存目录")
        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(hmenu, MF_STRING, ID_QUIT, "退出")
        user32.SetMenuDefaultItem(hmenu, ID_OPEN, 0)
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(hmenu, TPM_RIGHTBUTTON | TPM_RETURNCMD,
                                    pt.x, pt.y, 0, self.hwnd, None)
        user32.PostMessageW(self.hwnd, 0, 0, 0)   # WM_NULL：让菜单正常收起
        user32.DestroyMenu(hmenu)
        return cmd

    def _on_menu(self, cmd):
        try:
            if cmd == ID_OPEN and self.on_open:
                self.on_open()
            elif cmd == ID_UPDATE and self.on_update:
                self.on_update()
            elif cmd == ID_FOLDER and self.on_folder:
                self.on_folder()
            elif cmd == ID_QUIT and self.on_quit:
                self.on_quit()
        except Exception:
            pass

    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TRAY_CB:
                ev = lparam & 0xFFFF
                if ev in (WM_LBUTTONDBLCLK, WM_LBUTTONUP):
                    self._on_menu(ID_OPEN)
                elif ev in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    self._on_menu(self._menu())
                return 0
            if msg == self._taskbar_created:
                self._add_icon()
                return 0
            if msg == WM_COMMAND:
                self._on_menu(wparam & 0xFFFF)
                return 0
            if msg in (WM_CLOSE, WM_DESTROY):
                self._del_icon()
                user32.PostQuitMessage(0)
                return 0
        except Exception:
            _dbg()
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _add_icon(self):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY_CB
        nid.hIcon = self._icon or 0
        nid.szTip = self.title[:127]
        shell32.Shell_NotifyIconW(NIM_ADD if self._nid is None else NIM_MODIFY,
                                  ctypes.byref(nid))
        self._nid = nid

    def _del_icon(self):
        try:
            if self._nid is not None:
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
                self._nid = None
        except Exception:
            pass

    def _run(self):
        try:
            hinst = kernel32.GetModuleHandleW(None)
            self._proc = WNDPROC(self._wndproc)          # 必须留引用，否则被回收后崩
            self._taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
            wc = WNDCLASSEXW()
            wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
            wc.lpfnWndProc = self._proc
            wc.hInstance = hinst
            wc.lpszClassName = self._class_name
            if not user32.RegisterClassExW(ctypes.byref(wc)):
                self._ready.set()
                return
            self.hwnd = user32.CreateWindowExW(0, self._class_name, self.title, 0,
                                               0, 0, 0, 0, None, None, hinst, None)
            if not self.hwnd:
                self._ready.set()
                return
            self._icon = self._load_icon()
            self._add_icon()
            self._ok = True
            self._ready.set()
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            self._ok = False
        except Exception:
            self._ready.set()
