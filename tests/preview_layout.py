"""Exercise real Tk geometry with simulated monitor sizes and no hardware."""
from pathlib import Path
import os
import sys
import tempfile
from unittest.mock import patch
import tkinter as tk

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'SerialController')]
os.chdir(ROOT / 'SerialController')
from demo_camera import install
install()
import Settings
from Window import PokeControllerApp
from AppLifecycle import Lifecycle

stdout, stderr = sys.stdout, sys.stderr
with tempfile.TemporaryDirectory() as folder:
    Settings.GuiSettings.SETTING_PATH = str(Path(folder) / 'settings.ini')
    root = tk.Tk()
    settings = Settings.GuiSettings()
    settings.show_size.set('1920x1080')
    settings.save()
    app = PokeControllerApp(root, 'layout-test')
    app.lifecycle = Lifecycle(app)
    try:
        for screen in ((1366, 768), (1920, 1080), (2560, 1440)):
            with patch('PreviewLayout.work_area', return_value=(0, 0, *screen)):
                root.withdraw()
                if hasattr(app, 'preview_viewport'):
                    del app.preview_viewport
                app.fitPreviewToScreen()
                for mode in app.select_right_frame_widget_cb['values']:
                    app.right_frame_widget_mode.set(mode)
                    app.replace_right_frame_widget()
                    root.update_idletasks()
                    for tab in app.controller_nb.tabs():
                        app.controller_nb.select(tab)
                        root.update_idletasks()
                        page = root.nametowidget(tab)
                        assert page.winfo_height() >= page.winfo_reqheight(), (screen, tab, page.winfo_height(), page.winfo_reqheight(), 'tab contents clipped')
                    app.controller_nb.select(0)
                    root.update_idletasks()
                    for panel in (app.controller_nb, app.softcon_frame):
                        if panel.winfo_ismapped():
                            assert panel.winfo_rooty() + panel.winfo_height() <= root.winfo_rooty() + root.winfo_height(), (screen, mode, str(panel), 'bottom clipped')
                    if app.softcon_frame.winfo_ismapped():
                        assert app.softcon_frame.winfo_height() >= app.softcon_frame.winfo_reqheight(), (screen, mode, 'controller clipped')
                    widgets = (root, app.camera_lf, app.preview, app.controller_nb, app.output_area_f)
                    def bounds():
                        return [(w.winfo_x(), w.winfo_y(), w.winfo_width(), w.winfo_height()) for w in widgets]
                    before = bounds()
                    for preset in app.show_size_cb['values']:
                        app.show_size.set(preset)
                        with patch.object(root, 'geometry', side_effect=AssertionError('geometry changed')), patch.object(root, 'update_idletasks', side_effect=AssertionError('intermediate redraw')), patch('Window.tkmsg.askokcancel', side_effect=AssertionError('confirmation')):
                            app.applyWindowSize()
                        root.update_idletasks()
                        assert bounds() == before, (screen, mode, preset, before, bounds())
                        assert root.winfo_reqwidth() <= screen[0], (screen, mode, preset, root.winfo_reqwidth())
                        assert root.winfo_reqheight() < screen[1] - 50, (screen, mode, preset, root.winfo_reqheight())
                        w, h = app.preview.show_size
                        assert abs(w / h - 16 / 9) < .02
                        assert app.show_size.get() == preset
                        assert (app.preview.im.width(), app.preview.im.height()) == (w, h)
                        assert app.camera.capture_size == (1280, 720), app.camera.capture_size
        print('PASS: all presets and sidebar modes on 3 monitor sizes; stable widget bounds, no dialogs/intermediate redraws, immediate image resize, capture unchanged', file=stdout)
    finally:
        app.exit(confirm=False)
        root.mainloop()
        sys.stdout, sys.stderr = stdout, stderr
