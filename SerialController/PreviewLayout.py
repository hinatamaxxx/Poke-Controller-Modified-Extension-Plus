"""Bound preview layout to the current monitor's usable area. MIT."""
import ctypes
from ctypes import wintypes


def work_area(root):
    if hasattr(ctypes, 'windll'):
        class MonitorInfo(ctypes.Structure):
            _fields_ = [('size', wintypes.DWORD), ('monitor', wintypes.RECT),
                        ('work', wintypes.RECT), ('flags', wintypes.DWORD)]
        user = ctypes.windll.user32
        user.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user.MonitorFromWindow.restype = wintypes.HANDLE
        user.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
        info = MonitorInfo()
        info.size = ctypes.sizeof(info)
        if user.GetMonitorInfoW(user.MonitorFromWindow(root.winfo_id(), 2), ctypes.byref(info)):
            return info.work.left, info.work.top, info.work.right, info.work.bottom
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def fit_preview(app):
    if hasattr(app, 'preview_viewport'):
        render_size(app)
        return
    root = app.root
    root.update_idletasks()
    left, top, right, bottom = work_area(root)
    # Reserve space for the native frame, title bar and menu at Tk's DPI scale.
    scale = max(1.0, float(root.tk.call('tk', 'scaling')) / (96 / 72))
    limit_w = max(1, right - left - round(32 * scale))
    limit_h = max(1, bottom - top - round(90 * scale))
    requested_w, requested_h = 1280, 720
    width, height = requested_w, requested_h
    for _ in range(20):
        app.preview.setShowsize(height, width)
        app.changeAreaSize()
        root.update_idletasks()
        overflow_w = max(0, root.winfo_reqwidth() - limit_w)
        overflow_h = max(0, root.winfo_reqheight() - limit_h)
        if not overflow_w and not overflow_h:
            break
        ratio = min((width - overflow_w) / width, (height - overflow_h) / height)
        new_w = max(160, int(width * max(.1, ratio)))
        new_h = max(1, round(new_w * requested_h / requested_w))
        if (new_w, new_h) == (width, height):
            break
        width, height = new_w, new_h
    # Clear a previous manually enlarged geometry when applying a display preset.
    root.update_idletasks()
    app.preview_viewport = app.preview.show_size
    x = max(left + 8, min(root.winfo_x(), right - root.winfo_reqwidth() - round(24 * scale)))
    y = max(top + 8, min(root.winfo_y(), bottom - root.winfo_reqheight() - round(82 * scale)))
    root.geometry(f'{root.winfo_reqwidth()}x{root.winfo_reqheight()}+{x}+{y}')
    render_size(app)
    root.deiconify()


def render_size(app):
    width, height = map(int, app.show_size.get().split('x'))
    viewport_w, viewport_h = app.preview_viewport
    ratio = min(1, viewport_w / width, viewport_h / height)
    app.preview.setShowsize(max(1, round(height * ratio)), max(1, round(width * ratio)), resize_canvas=False)
