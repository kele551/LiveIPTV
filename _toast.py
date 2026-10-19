# -*- coding: utf-8 -*-
"""右下角自绘提示卡片（不依赖系统通知，Windows 10/11 表现一致）。

做法照搬热点新闻那边已经跑通的一套：
  * 进程声明 DPI 感知，按物理像素画，文字才不糊；
  * 一个 WS_EX_TOPMOST|TOOLWINDOW|NOACTIVATE 的 POPUP 窗口，
    白色圆角卡片 + 左侧红色竖条 + 两行字（标题粗、正文灰），不放任何图标；
  * 显示走 ShowWindow(SW_SHOWNOACTIVATE) + SetWindowPos(SWP_SHOWWINDOW) + InvalidateRect，
    所有绘制都在 WM_PAINT 里完成；
  * 到点自己收起，点一下卡片就回调（打开控制台）。

作者: 海风（kele551）  https://github.com/kele551/LiveIPTV
"""
import ctypes
import sys
import threading
from ctypes import wintypes

CARD_W, CARD_H = 366, 86
PAD = 16
ICON_PX = 44
SHOW_MS = 5500
MAX_QUEUE = 2

_u = ctypes.WinDLL("user32", use_last_error=True)
_g = ctypes.WinDLL("gdi32", use_last_error=True)
_k = ctypes.WinDLL("kernel32", use_last_error=True)

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [("hdc", wintypes.HDC), ("fErase", wintypes.BOOL), ("rcPaint", RECT),
                ("fRestore", wintypes.BOOL), ("fIncUpdate", wintypes.BOOL),
                ("rgbReserved", ctypes.c_byte * 32)]


def _protos():
    _u.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                  wintypes.WPARAM, wintypes.LPARAM]
    _u.DefWindowProcW.restype = ctypes.c_ssize_t
    _u.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    _u.CreateWindowExW.restype = wintypes.HWND
    _u.RegisterClassW.argtypes = [wintypes.LPVOID]
    _u.RegisterClassW.restype = wintypes.ATOM
    _u.BeginPaint.argtypes = [wintypes.HWND, wintypes.LPVOID]
    _u.BeginPaint.restype = wintypes.HDC
    _u.EndPaint.argtypes = [wintypes.HWND, wintypes.LPVOID]
    _u.GetClientRect.argtypes = [wintypes.HWND, wintypes.LPVOID]
    _u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT]
    _u.InvalidateRect.argtypes = [wintypes.HWND, wintypes.LPVOID, wintypes.BOOL]
    _u.SetTimer.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.LPVOID]
    _u.SetTimer.restype = wintypes.UINT
    _u.KillTimer.argtypes = [wintypes.HWND, wintypes.UINT]
    _u.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HANDLE, wintypes.BOOL]
    _u.FillRect.argtypes = [wintypes.HDC, wintypes.LPVOID, wintypes.HBRUSH]
    _u.DrawTextW.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int,
                             wintypes.LPVOID, wintypes.UINT]
    _u.DrawTextW.restype = ctypes.c_int
    _u.GetMessageW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.UINT]
    _u.TranslateMessage.argtypes = [ctypes.c_void_p]
    _u.DispatchMessageW.argtypes = [ctypes.c_void_p]
    _u.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT,
                                        wintypes.LPVOID, wintypes.UINT]
    _u.GetDC.argtypes = [wintypes.HWND]
    _u.GetDC.restype = wintypes.HDC
    _u.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    _g.GetDeviceCaps.argtypes = [wintypes.HDC, ctypes.c_int]
    _g.GetDeviceCaps.restype = ctypes.c_int
    _g.CreateSolidBrush.argtypes = [wintypes.COLORREF]
    _g.CreateSolidBrush.restype = wintypes.HBRUSH
    _g.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.COLORREF]
    _g.CreatePen.restype = wintypes.HANDLE
    _g.CreateFontW.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                               wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                               wintypes.DWORD, wintypes.LPCWSTR]
    _g.CreateFontW.restype = wintypes.HANDLE
    _g.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    _g.SelectObject.restype = wintypes.HANDLE
    _g.DeleteObject.argtypes = [wintypes.HANDLE]
    _g.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
    _g.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
    _g.RoundRect.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int,
                             ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    _g.CreateRoundRectRgn.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_int, ctypes.c_int]
    _g.CreateRoundRectRgn.restype = wintypes.HANDLE
    _g.GetStockObject.argtypes = [ctypes.c_int]
    _g.GetStockObject.restype = wintypes.HANDLE
    _u.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT]
    _u.LoadImageW.restype = wintypes.HANDLE
    _u.DrawIconEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HICON,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT,
                              wintypes.HBRUSH, wintypes.UINT]
    _u.DrawIconEx.restype = wintypes.BOOL
    _k.GetModuleHandleW.restype = wintypes.HMODULE


class Toast(object):
    """一条提示：Toast().show("更新完成", "353 个频道可用 · 用时 39 秒")。"""

    def __init__(self, on_click=None, app_icon="", name="LIVEToastWnd"):
        self.on_click = on_click
        self.app_icon = app_icon or ""
        self.name = name
        self.ok = False
        self.hwnd = None
        self.q = []
        self.lock = threading.Lock()
        self.cur = ("", "")
        self.showing = False
        self._ref = None
        self.scale = 1.0
        if sys.platform != "win32":
            return
        try:
            _protos()
            try:
                _u.SetProcessDPIAware()
            except Exception:
                pass
            hdc = _u.GetDC(None)
            dpi = _g.GetDeviceCaps(hdc, 88) or 96
            _u.ReleaseDC(None, hdc)
            self.scale = max(1.0, min(3.0, dpi / 96.0))
            self.W = int(CARD_W * self.scale)
            self.H = int(CARD_H * self.scale)
            self.pad = int(PAD * self.scale)
            self.ok = True
        except Exception as ex:
            print("[warn] 提示卡片初始化失败: %s: %s" % (type(ex).__name__, ex), flush=True)

    # ---------- 对外 ----------
    def start(self):
        if not self.ok:
            return False
        threading.Thread(target=self._thread, daemon=True).start()
        return True

    def show(self, title, text, ms=SHOW_MS):
        if not self.ok:
            return False
        with self.lock:
            self.q.append((title or "", text or "", int(ms)))
            if len(self.q) > MAX_QUEUE:
                del self.q[:-MAX_QUEUE]
        return True

    # ---------- 内部 ----------
    def _place(self):
        wa = RECT()
        try:
            _u.SystemParametersInfoW(0x0030, 0, ctypes.byref(wa), 0)   # SPI_GETWORKAREA
        except Exception:
            pass
        if not wa.right or not wa.bottom:
            wa.right, wa.bottom = 1920, 1080
        self.x = max(0, wa.right - self.W - self.pad)
        self.y = max(0, wa.bottom - self.H - self.pad)

    def _paint(self, hwnd, hdc):
        rc = RECT()
        _u.GetClientRect(hwnd, ctypes.byref(rc))
        s = self.scale
        title, text = self.cur
        _u.FillRect(hdc, ctypes.byref(rc), self.br_bg)
        op = _g.SelectObject(hdc, self.pen_border)
        ob = _g.SelectObject(hdc, self.null_brush)
        _g.RoundRect(hdc, 0, 0, rc.right, rc.bottom, int(14 * s), int(14 * s))
        _g.SelectObject(hdc, op)
        _g.SelectObject(hdc, ob)
        bar = RECT(0, 0, int(5 * s), rc.bottom)
        _u.FillRect(hdc, ctypes.byref(bar), self.br_bar)
        _g.SetBkMode(hdc, 1)                      # TRANSPARENT
        left = int(18 * s)
        # 左边放程序大图标（自己按像素画，不会被系统缩放糊掉）
        if self.hicon:
            ic = self.icon_px
            top = int((rc.bottom - ic) / 2)
            _u.DrawIconEx(hdc, left, top, self.hicon, ic, ic, 0, None, 3)   # DI_NORMAL
            left += ic + int(14 * s)
        right = rc.right - int(14 * s)
        _g.SelectObject(hdc, self.font_title)
        _g.SetTextColor(hdc, 0x2C201A)            # #1A202C
        t = RECT(left, int(12 * s), right, int(40 * s))
        _u.DrawTextW(hdc, title, -1, ctypes.byref(t),
                     0x20 | 0x4 | 0x8000 | 0x800)   # SINGLELINE|VCENTER|ELLIPSIS|NOPREFIX
        _g.SelectObject(hdc, self.font_msg)
        _g.SetTextColor(hdc, 0x68554A)             # #4A5568
        m = RECT(left, int(44 * s), right, rc.bottom - int(8 * s))
        _u.DrawTextW(hdc, text, -1, ctypes.byref(m), 0x10 | 0x800)   # WORDBREAK|NOPREFIX

    def _wndproc(self, hwnd, msg, wp, lp):
        try:
            if msg == 0x000F:                                   # WM_PAINT
                ps = PAINTSTRUCT()
                hdc = _u.BeginPaint(hwnd, ctypes.byref(ps))
                try:
                    self._paint(hwnd, hdc)
                finally:
                    _u.EndPaint(hwnd, ctypes.byref(ps))
                return 0
            if msg == 0x0113:                                   # WM_TIMER
                if wp == 1:
                    _u.KillTimer(hwnd, 1)
                    _u.ShowWindow(hwnd, 0)
                    self.showing = False
                    return 0
                if wp == 2:
                    payload = None
                    with self.lock:
                        if self.q and not self.showing:
                            payload = self.q.pop(0)
                    if payload:
                        self.cur = (payload[0], payload[1])
                        self._place()
                        _u.ShowWindow(hwnd, 4)                  # SW_SHOWNOACTIVATE
                        _u.SetWindowPos(hwnd, wintypes.HWND(-1), self.x, self.y,
                                        self.W, self.H, 0x0010 | 0x0040)
                        _u.InvalidateRect(hwnd, None, True)
                        self.showing = True
                        _u.SetTimer(hwnd, 1, payload[2], None)
                return 0
            if msg == 0x0201:                                   # WM_LBUTTONDOWN
                _u.KillTimer(hwnd, 1)
                _u.ShowWindow(hwnd, 0)
                self.showing = False
                if self.on_click:
                    try:
                        threading.Thread(target=self.on_click, daemon=True).start()
                    except Exception:
                        pass
                return 0
        except Exception as ex:
            print("[warn] 提示卡片绘制异常: %s: %s" % (type(ex).__name__, ex), flush=True)
        return _u.DefWindowProcW(hwnd, msg, wp, lp)

    def _thread(self):
        try:
            s = self.scale
            self._ref = WNDPROC(self._wndproc)
            wc = WNDCLASSW()
            wc.hInstance = _k.GetModuleHandleW(None)
            wc.lpszClassName = self.name
            wc.lpfnWndProc = self._ref
            if not _u.RegisterClassW(ctypes.byref(wc)):
                if ctypes.get_last_error() not in (0, 1410):    # 1410 = 类已注册
                    print("[warn] 注册窗口类失败 err=%s" % ctypes.get_last_error(), flush=True)
            self._place()
            self.hwnd = _u.CreateWindowExW(
                0x00000008 | 0x00000080 | 0x08000000,           # TOPMOST|TOOLWINDOW|NOACTIVATE
                self.name, "LIVE直播源提示", 0x80000000,         # WS_POPUP
                self.x, self.y, self.W, self.H,
                None, None, wc.hInstance, None)
            if not self.hwnd:
                print("[warn] 创建提示窗口失败 err=%s" % ctypes.get_last_error(), flush=True)
                self.ok = False
                return
            self.hicon = None
            want = int(ICON_PX * s)
            # ICO 里没有的尺寸 LoadImageW 会直接失败（err=6），
            # 所以先挑最接近的现成尺寸，画的时候再交给 DrawIconEx 缩放。
            sizes = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
            pick = min(sizes, key=lambda v: abs(v - want))
            self.icon_px = pick
            if self.app_icon:
                try:
                    h = _u.LoadImageW(None, self.app_icon, 1, pick, pick,
                                      0x10)                    # LR_LOADFROMFILE
                    if h:
                        self.hicon = h
                except Exception:
                    self.hicon = None
            self.br_bg = _g.CreateSolidBrush(0xFFFFFF)          # 白卡片
            self.br_bar = _g.CreateSolidBrush(0x2E11E1)         # 红竖条 #E11D2E
            self.pen_border = _g.CreatePen(0, max(1, int(s)), 0xE8E2E2)
            self.null_brush = _g.GetStockObject(5)              # NULL_BRUSH
            self.font_title = _g.CreateFontW(-int(18 * s), 0, 0, 0, 700, 0, 0, 0,
                                             134, 5, 0, 5, 0, "Microsoft YaHei UI")
            self.font_msg = _g.CreateFontW(-int(15 * s), 0, 0, 0, 400, 0, 0, 0,
                                           134, 5, 0, 5, 0, "Microsoft YaHei UI")
            try:
                hrgn = _g.CreateRoundRectRgn(0, 0, self.W + 1, self.H + 1,
                                             int(14 * s), int(14 * s))
                if hrgn:
                    _u.SetWindowRgn(self.hwnd, hrgn, True)
            except Exception:
                pass
            _u.SetTimer(self.hwnd, 2, 200, None)                # 200ms 看一次队列
            msg = wintypes.MSG()
            while _u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                _u.TranslateMessage(ctypes.byref(msg))
                _u.DispatchMessageW(ctypes.byref(msg))
        except Exception as ex:
            import traceback
            print("[warn] 提示卡片线程异常: %s: %s" % (type(ex).__name__, ex), flush=True)
            traceback.print_exc()
            self.ok = False


_TOAST = None


def init(on_click=None, app_icon=""):
    """进程里只建一个提示卡片实例（GDI 资源复用）。"""
    global _TOAST
    if _TOAST is None:
        _TOAST = Toast(on_click=on_click, app_icon=app_icon)
        _TOAST.start()
    return _TOAST


def show(title, text, ms=SHOW_MS):
    t = _TOAST
    if t is None or not t.ok:
        return False
    return t.show(title, text, ms)
