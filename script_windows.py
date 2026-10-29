"""Windows that a script opens itself (tkinter, cv2.imshow, pygame, ...), shown and operated inside the app.

Any visible top-level window of this worker process (or a process it started) is listed. Its picture is taken with
PrintWindow, so it works whatever library drew it, and clicks, keys and text are posted to it as window messages.
While the app shows a window, the real one is made fully transparent and click-through, so nothing appears on the
desktop; "デスクトップに出す" puts it back as it was."""

import ctypes
import os
import sys
import threading
import time
import weakref
from ctypes import wintypes as wt

if sys.platform == 'win32':
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    dwmapi = ctypes.WinDLL('dwmapi')
else:  # pragma: no cover - the app only runs on Windows
    user32 = gdi32 = kernel32 = dwmapi = None

LONG_PTR = ctypes.c_ssize_t
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_CAPTION, WS_CHILD = 0x00C00000, 0x40000000
WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x80000, 0x20, 0x80, 0x08000000
LWA_ALPHA = 0x2
PW_CLIENTONLY, PW_RENDERFULLCONTENT = 0x1, 0x2
CWP_SKIPINVISIBLE, CWP_SKIPDISABLED = 0x1, 0x2
GW_HWNDNEXT, GW_OWNER, GW_CHILD = 2, 4, 5
DWMWA_CLOAKED = 14
WM_CLOSE, WM_SETFOCUS, WM_ACTIVATE = 0x10, 0x7, 0x6
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_LBUTTONDBLCLK = 0x200, 0x201, 0x202, 0x203
WM_RBUTTONDOWN, WM_RBUTTONUP, WM_MOUSEWHEEL = 0x204, 0x205, 0x20A
WM_KEYDOWN, WM_KEYUP, WM_CHAR = 0x100, 0x101, 0x102
MK_LBUTTON, MK_RBUTTON = 0x1, 0x2
WA_ACTIVE = 1
TH32CS_SNAPPROCESS = 0x2
SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x1, 0x4, 0x10, 0x20
SWP_NOMOVE = 0x2
SW_RESTORE, SW_SHOWNOACTIVATE = 9, 4
RDW_INVALIDATE, RDW_ERASE, RDW_FRAME, RDW_ALLCHILDREN = 0x1, 0x4, 0x400, 0x80

# Keys a page can send by name (as KeyboardEvent.key), with their virtual-key codes.
KEYS = {'Enter': 0x0D, 'Backspace': 0x08, 'Tab': 0x09, 'Escape': 0x1B, 'Delete': 0x2E, 'Home': 0x24, 'End': 0x23,
        'ArrowLeft': 0x25, 'ArrowUp': 0x26, 'ArrowRight': 0x27, 'ArrowDown': 0x28, ' ': 0x20,
        'PageUp': 0x21, 'PageDown': 0x22}
CHAR_KEYS = {'Enter': '\r', 'Backspace': '\b', 'Tab': '\t', 'Escape': '\x1b', ' ': ' '}


class RECT(ctypes.Structure):
    _fields_ = [('left', wt.LONG), ('top', wt.LONG), ('right', wt.LONG), ('bottom', wt.LONG)]


class POINT(ctypes.Structure):
    _fields_ = [('x', wt.LONG), ('y', wt.LONG)]


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [('cbSize', wt.DWORD), ('flags', wt.DWORD), ('hwndActive', wt.HWND), ('hwndFocus', wt.HWND),
                ('hwndCapture', wt.HWND), ('hwndMenuOwner', wt.HWND), ('hwndMoveSize', wt.HWND),
                ('hwndCaret', wt.HWND), ('rcCaret', RECT)]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [('dwSize', wt.DWORD), ('cntUsage', wt.DWORD), ('th32ProcessID', wt.DWORD),
                ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', wt.DWORD), ('cntThreads', wt.DWORD),
                ('th32ParentProcessID', wt.DWORD), ('pcPriClassBase', wt.LONG), ('dwFlags', wt.DWORD),
                ('szExeFile', wt.WCHAR * 260)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', wt.DWORD), ('biWidth', wt.LONG), ('biHeight', wt.LONG), ('biPlanes', wt.WORD),
                ('biBitCount', wt.WORD), ('biCompression', wt.DWORD), ('biSizeImage', wt.DWORD),
                ('biXPelsPerMeter', wt.LONG), ('biYPelsPerMeter', wt.LONG), ('biClrUsed', wt.DWORD),
                ('biClrImportant', wt.DWORD)]


if user32:
    user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    user32.GetWindowThreadProcessId.restype = wt.DWORD
    user32.IsWindowVisible.argtypes = [wt.HWND]
    user32.IsWindow.argtypes = [wt.HWND]
    user32.IsIconic.argtypes = [wt.HWND]
    user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(RECT)]
    user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(RECT)]
    user32.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(POINT)]
    user32.ScreenToClient.argtypes = [wt.HWND, ctypes.POINTER(POINT)]
    user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    user32.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = LONG_PTR
    user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, LONG_PTR]
    user32.SetWindowLongPtrW.restype = LONG_PTR
    user32.SetLayeredWindowAttributes.argtypes = [wt.HWND, wt.COLORREF, wt.BYTE, wt.DWORD]
    user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
    user32.GetWindow.argtypes = [wt.HWND, wt.UINT]
    user32.GetWindow.restype = wt.HWND
    user32.ChildWindowFromPointEx.argtypes = [wt.HWND, POINT, wt.UINT]
    user32.ChildWindowFromPointEx.restype = wt.HWND
    user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    user32.GetGUIThreadInfo.argtypes = [wt.DWORD, ctypes.POINTER(GUITHREADINFO)]
    user32.GetDC.argtypes = [wt.HWND]
    user32.GetDC.restype = wt.HDC
    user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
    user32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
    user32.SetForegroundWindow.argtypes = [wt.HWND]
    user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    user32.RedrawWindow.argtypes = [wt.HWND, ctypes.c_void_p, ctypes.c_void_p, wt.UINT]
    user32.MapVirtualKeyW.argtypes = [wt.UINT, wt.UINT]
    user32.MapVirtualKeyW.restype = wt.UINT
    gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
    gdi32.CreateCompatibleDC.restype = wt.HDC
    gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
    gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
    gdi32.SelectObject.restype = wt.HGDIOBJ
    gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wt.HDC]
    gdi32.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT]
    kernel32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    kernel32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.CloseHandle.argtypes = [wt.HANDLE]
    dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]


# ---- tkinter ----
# Tk decides that a mouse button is down from the real button state, so posted mouse messages do nothing there.
# Its windows live in this process, though: the app finds the widget under the point and gives Tk the events itself.
# Weak references only: a Tk object must be freed on its own thread, or Tcl aborts the process.
_tk_roots = []    # (weakref to Tk, native thread id)
_tk_pending = []  # (thread id, call) for Tk threads that are not in mainloop, run at their next update()
TK_KEYS = {'Enter': 'Return', 'Backspace': 'BackSpace', 'Tab': 'Tab', 'Escape': 'Escape', 'Delete': 'Delete',
           'Home': 'Home', 'End': 'End', 'ArrowLeft': 'Left', 'ArrowUp': 'Up', 'ArrowRight': 'Right',
           'ArrowDown': 'Down', ' ': 'space', 'PageUp': 'Prior', 'PageDown': 'Next'}
TK_TEXT_CLASSES = {'Entry', 'TEntry', 'TCombobox', 'Spinbox', 'TSpinbox', 'Text'}


def track_tkinter():
    """Remember every Tk interpreter a script creates (scripts are not changed)."""
    import tkinter
    if getattr(tkinter.Tk, '_pokecon_tracked', False):
        return
    original_init, original_update = tkinter.Tk.__init__, tkinter.Misc.update

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        _tk_roots[:] = [(ref, owner) for ref, owner in _tk_roots if ref() is not None]
        _tk_roots.append((weakref.ref(self), threading.get_native_id()))

    def update(self):
        _run_pending()
        return original_update(self)
    tkinter.Tk.__init__ = init
    tkinter.Misc.update = update
    tkinter.Tk._pokecon_tracked = True


def _run_pending():
    thread = threading.get_native_id()
    for item in [p for p in _tk_pending if p[0] == thread]:
        _tk_pending.remove(item)
        try:
            item[1]()
        except Exception:
            pass


def _tk_run(thread, action):
    """Run action on the Tk thread: directly when it is in mainloop (tkinter passes the call over), else at its next update()."""
    try:
        action()
    except RuntimeError:
        _tk_pending.append((thread, action))


def _tk_paths(interp, path='.'):
    yield path
    try:
        children = interp.splitlist(interp.call('winfo', 'children', path))
    except Exception:
        return
    for child in children:
        yield from _tk_paths(interp, str(child))


def _tk_toplevel(interp, hwnd):
    """The path of the toplevel whose frame is hwnd in this interpreter, or None."""
    for path in _tk_paths(interp):
        if str(interp.call('winfo', 'toplevel', path)) == path and int(str(interp.call('wm', 'frame', path)), 16) == hwnd:
            return path
    return None


def _tk_dispatch(hwnd, operation):
    """Run operation(interp, toplevel) for a Tk window. False if no Tk interpreter owns the window's thread."""
    if not _text(user32.GetClassNameW, hwnd).startswith('Tk'):
        return False  # e.g. a cv2 window on the same thread as a Tk window
    thread = user32.GetWindowThreadProcessId(hwnd, None)
    refs = [ref for ref, owner in _tk_roots if owner == thread]
    if not refs:
        return False

    def action():
        import tkinter
        for ref in reversed(refs):
            root = ref()
            if root is None:
                continue
            try:
                toplevel = _tk_toplevel(root.tk, hwnd)
                if toplevel:
                    operation(root.tk, toplevel)
                    return
            except tkinter.TclError:
                continue  # destroyed
            finally:
                del root  # never keep a Tk object alive outside its thread
        raise ValueError('The window is closed')
    _tk_run(thread, action)
    return True


def _tk_widget_at(interp, toplevel, sx, sy):
    """The innermost viewable widget of toplevel at screen point (sx, sy)."""
    path = toplevel
    while True:
        children = [str(c) for c in interp.splitlist(interp.call('winfo', 'children', path))]
        hit = None
        for child in reversed(children):  # later children are drawn on top
            if str(interp.call('winfo', 'toplevel', child)) == child or not int(interp.call('winfo', 'viewable', child)):
                continue
            x, y = int(interp.call('winfo', 'rootx', child)), int(interp.call('winfo', 'rooty', child))
            w, h = int(interp.call('winfo', 'width', child)), int(interp.call('winfo', 'height', child))
            if x <= sx < x + w and y <= sy < y + h:
                hit = child
                break
        if hit is None:
            return path
        path = hit


def _tk_click(interp, toplevel, sx, sy, button):
    widget = _tk_widget_at(interp, toplevel, sx, sy)
    x = sx - int(interp.call('winfo', 'rootx', widget))
    y = sy - int(interp.call('winfo', 'rooty', widget))
    where = ('-x', x, '-y', y, '-rootx', sx, '-rooty', sy)
    number = 3 if button == 'right' else 1
    interp.call('event', 'generate', widget, '<Enter>', *where)
    interp.call('event', 'generate', widget, '<Motion>', *where)
    interp.call('event', 'generate', widget, f'<ButtonPress-{number}>', *where)
    interp.call('event', 'generate', widget, f'<ButtonRelease-{number}>', *where)


def _tk_focus(interp, toplevel):
    return str(interp.call('focus', '-lastfor', toplevel)) or toplevel


def _tk_key(interp, toplevel, key):
    interp.call('event', 'generate', _tk_focus(interp, toplevel), f'<KeyPress-{TK_KEYS[key]}>')


def _tk_type(interp, toplevel, text):
    widget = _tk_focus(interp, toplevel)
    if str(interp.call('winfo', 'class', widget)) not in TK_TEXT_CLASSES:
        raise ValueError('文字を入力できる欄が選ばれていません')
    try:
        if str(interp.call('winfo', 'class', widget)) == 'Text':
            interp.call(widget, 'delete', 'sel.first', 'sel.last')
        elif int(interp.call(widget, 'selection', 'present')):
            interp.call(widget, 'delete', 'sel.first', 'sel.last')
    except Exception:
        pass
    interp.call(widget, 'insert', 'insert', text)


def _text(function, hwnd):
    buffer = ctypes.create_unicode_buffer(256)
    function(hwnd, buffer, 256)
    return buffer.value


def _process_ids():
    """This process and every process it started (a script may run a GUI program of its own)."""
    own = os.getpid()
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    parents = {}
    if snapshot and snapshot != wt.HANDLE(-1).value:
        entry = PROCESSENTRY32W(dwSize=ctypes.sizeof(PROCESSENTRY32W))
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            parents[entry.th32ProcessID] = entry.th32ParentProcessID
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        kernel32.CloseHandle(snapshot)
    found, grew = {own}, True
    while grew:
        grew = False
        for pid, parent in parents.items():
            if parent in found and pid not in found and pid != parent:
                found.add(pid)
                grew = True
    return found


def _client_box(hwnd):
    rect, origin = RECT(), POINT(0, 0)
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    return origin.x, origin.y, rect.right - rect.left, rect.bottom - rect.top


def _cloaked(hwnd):
    value = wt.DWORD(0)
    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(value), ctypes.sizeof(value))
    return bool(value.value)


class ScriptWindows:
    """The windows of one worker process, as the page and MCP see them."""

    def __init__(self, ignore=()):
        self.lock = threading.Lock()
        self.concealed = {}   # hwnd -> extended style before it was hidden from the desktop
        self.on_desktop = set()  # windows the user chose to see on the desktop
        self.ignore = set(ignore)

    def available(self):
        return user32 is not None

    def _all(self):
        pids = _process_ids()
        found = []

        def visit(hwnd, _):
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in pids and hwnd not in self.ignore and user32.IsWindowVisible(hwnd) and not _cloaked(hwnd):
                found.append(hwnd)
            return True
        user32.EnumWindows(WNDENUMPROC(visit), 0)
        return found  # top of the z-order first

    def list(self):
        """Visible windows, top first. A popup (no title bar, e.g. a drop-down list) names the window it belongs to."""
        if user32 is None:
            return []
        windows = []
        for hwnd in self._all():
            if user32.IsIconic(hwnd):
                if hwnd in self.on_desktop:
                    continue
                user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)  # a minimized window draws nothing for the app to show
            x, y, w, h = _client_box(hwnd)
            if w < 8 or h < 8:
                continue
            style = user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
            windows.append({'id': str(hwnd), 'title': _text(user32.GetWindowTextW, hwnd),
                            'class': _text(user32.GetClassNameW, hwnd), 'x': x, 'y': y, 'width': w, 'height': h,
                            'popup': not (style & WS_CAPTION), 'desktop': hwnd in self.on_desktop})
        mains = [w for w in windows if not w['popup']]
        for window in windows:
            if window['popup']:
                owner = user32.GetWindow(int(window['id']), GW_OWNER)
                parent = next((m for m in mains if m['id'] == str(owner)), None) or next(
                    (m for m in mains if m['x'] <= window['x'] < m['x'] + m['width'] and m['y'] <= window['y'] < m['y'] + m['height']),
                    mains[0] if mains else None)
                window['parent'] = parent['id'] if parent else None
        self.hide_new(windows)
        return windows

    def hide_new(self, windows):
        """Windows the app shows are hidden from the desktop: fully transparent and click-through."""
        with self.lock:
            alive = {int(w['id']) for w in windows}
            for hwnd in list(self.concealed):
                if not user32.IsWindow(hwnd):
                    self.concealed.pop(hwnd, None)
            self.on_desktop &= alive | {h for h in self.on_desktop if user32.IsWindow(h)}
            for window in windows:
                hwnd = int(window['id'])
                if hwnd in self.concealed or hwnd in self.on_desktop:
                    continue
                ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
                self.concealed[hwnd] = ex
                user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED | WS_EX_TRANSPARENT)
                user32.SetLayeredWindowAttributes(hwnd, 0, 0, LWA_ALPHA)

    def show_on_desktop(self, window_id):
        """Put a window back on the desktop as it was, in front."""
        hwnd = self._known(window_id)
        with self.lock:
            ex = self.concealed.pop(hwnd, None)
            self.on_desktop.add(hwnd)
        if ex is not None:
            user32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
            user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)
            user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        user32.RedrawWindow(hwnd, None, None, RDW_INVALIDATE | RDW_ERASE | RDW_FRAME | RDW_ALLCHILDREN)
        user32.SetForegroundWindow(hwnd)

    def _known(self, window_id):
        try:
            hwnd = int(window_id)
        except (TypeError, ValueError):
            raise ValueError('Unknown window')
        if hwnd not in self._all():
            raise ValueError('The window is closed')
        return hwnd

    def capture(self, window_id):
        """The window's client area as a BGR image (numpy)."""
        import numpy as np
        hwnd = self._known(window_id)
        _, _, w, h = _client_box(hwnd)
        if w <= 0 or h <= 0:
            raise ValueError('The window has no size')
        screen = user32.GetDC(None)
        memory = gdi32.CreateCompatibleDC(screen)
        bitmap = gdi32.CreateCompatibleBitmap(screen, w, h)
        old = gdi32.SelectObject(memory, bitmap)
        try:
            user32.PrintWindow(hwnd, memory, PW_CLIENTONLY | PW_RENDERFULLCONTENT)
            header = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=w, biHeight=-h, biPlanes=1,
                                      biBitCount=32, biCompression=0)
            pixels = np.empty((h, w, 4), dtype=np.uint8)
            gdi32.GetDIBits(memory, bitmap, 0, h, pixels.ctypes.data, ctypes.byref(header), 0)
        finally:
            gdi32.SelectObject(memory, old)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(memory)
            user32.ReleaseDC(None, screen)
        return np.ascontiguousarray(pixels[:, :, :3])

    def png(self, window_id):
        import cv2
        ok, encoded = cv2.imencode('.png', self.capture(window_id))
        if not ok:
            raise ValueError('Could not encode the window')
        return encoded.tobytes()

    def _target(self, hwnd, x, y):
        """The innermost child window at client point (x, y) of hwnd, and the point in its own coordinates."""
        point = POINT(int(x), int(y))
        user32.ClientToScreen(hwnd, ctypes.byref(point))
        target = hwnd
        while True:
            child = user32.GetWindow(target, GW_CHILD)  # top of the children's z-order first
            hit = None
            while child:
                rect = RECT()
                user32.GetWindowRect(child, ctypes.byref(rect))
                if user32.IsWindowVisible(child) and rect.left <= point.x < rect.right and rect.top <= point.y < rect.bottom:
                    hit = child
                    break
                child = user32.GetWindow(child, GW_HWNDNEXT)
            if hit is None:
                local = POINT(point.x, point.y)
                user32.ScreenToClient(target, ctypes.byref(local))
                return target, local.x, local.y
            target = hit

    def _focus_owner(self, hwnd):
        """Tell the window's toolkit that it is active, as when the user clicks it, without taking real focus."""
        user32.PostMessageW(hwnd, WM_ACTIVATE, WA_ACTIVE, 0)
        user32.PostMessageW(hwnd, WM_SETFOCUS, 0, 0)

    def click(self, window_id, x, y, button='left', double=False):
        hwnd = self._known(window_id)
        origin = POINT(int(x), int(y))
        user32.ClientToScreen(hwnd, ctypes.byref(origin))
        if _tk_dispatch(hwnd, lambda interp, top: _tk_click(interp, top, origin.x, origin.y, button)):
            return
        target, cx, cy = self._target(hwnd, x, y)
        lparam = (cy & 0xFFFF) << 16 | (cx & 0xFFFF)
        down, up, flag = (WM_RBUTTONDOWN, WM_RBUTTONUP, MK_RBUTTON) if button == 'right' else (WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON)
        self._focus_owner(hwnd)
        user32.PostMessageW(target, WM_MOUSEMOVE, 0, lparam)
        user32.PostMessageW(target, down, flag, lparam)
        user32.PostMessageW(target, up, 0, lparam)
        if double and button != 'right':
            user32.PostMessageW(target, WM_LBUTTONDBLCLK, flag, lparam)
            user32.PostMessageW(target, up, 0, lparam)

    def scroll(self, window_id, x, y, delta):
        hwnd = self._known(window_id)
        target, _, _ = self._target(hwnd, x, y)
        point = POINT(int(x), int(y))
        user32.ClientToScreen(hwnd, ctypes.byref(point))
        lparam = (point.y & 0xFFFF) << 16 | (point.x & 0xFFFF)
        wheel = max(-32768, min(32767, int(delta))) & 0xFFFF
        user32.PostMessageW(target, WM_MOUSEWHEEL, wheel << 16, lparam)

    def _keyboard_target(self, hwnd):
        thread = user32.GetWindowThreadProcessId(hwnd, None)
        info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
        if user32.GetGUIThreadInfo(thread, ctypes.byref(info)) and info.hwndFocus:
            return info.hwndFocus
        return hwnd

    def key(self, window_id, key):
        """A named key (Enter, Backspace, Tab, Escape, arrows, ...)."""
        hwnd = self._known(window_id)
        vk = KEYS.get(key)
        if vk is None:
            raise ValueError(f'Unsupported key: {key}')
        if _tk_dispatch(hwnd, lambda interp, top: _tk_key(interp, top, key)):
            return
        target = self._keyboard_target(hwnd)
        scan = user32.MapVirtualKeyW(vk, 0)
        user32.PostMessageW(target, WM_KEYDOWN, vk, 1 | scan << 16)
        if key in CHAR_KEYS:
            user32.PostMessageW(target, WM_CHAR, ord(CHAR_KEYS[key]), 1 | scan << 16)
        user32.PostMessageW(target, WM_KEYUP, vk, 1 | scan << 16 | 0xC0000000)

    def type(self, window_id, text):
        hwnd = self._known(window_id)
        text = str(text)
        if _tk_dispatch(hwnd, lambda interp, top: _tk_type(interp, top, text)):
            return
        target = self._keyboard_target(hwnd)
        for char in str(text):
            if char == '\n':
                self.key(window_id, 'Enter')
                continue
            for unit in char.encode('utf-16-le').hex(' ', 2).split():
                user32.PostMessageW(target, WM_CHAR, int.from_bytes(bytes.fromhex(unit), 'little'), 1)

    def close(self, window_id):
        user32.PostMessageW(self._known(window_id), WM_CLOSE, 0, 0)

    def close_all(self):
        for hwnd in self._all():
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
