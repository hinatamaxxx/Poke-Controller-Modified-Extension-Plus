from pathlib import Path
import sys
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'SerialController')]
import script_windows


def wait_for(check, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(.05)
    raise AssertionError('timed out')


@unittest.skipUnless(sys.platform == 'win32', 'Windows only')
class ScriptWindowsTest(unittest.TestCase):
    def test_tk_settings_window_is_shown_and_operated(self):
        script_windows.track_tkinter()
        result, ready = {}, threading.Event()

        def gui():
            import tkinter as tk
            from tkinter import ttk
            root = tk.Tk()
            root.withdraw()
            dialog = tk.Toplevel(root)
            dialog.title('窓テスト')
            name = tk.StringVar(dialog, value='デオキシス')
            ttk.Label(dialog, text='厳選ポケモンを選択').pack(pady=4)
            ttk.Combobox(dialog, textvariable=name, values=['ファイヤー', 'ミュウツー', 'デオキシス'], state='readonly').pack(pady=4)
            entry = ttk.Entry(dialog, width=12)
            entry.insert(0, '0.95')
            entry.pack(pady=4)
            flag = tk.BooleanVar(dialog, value=False)
            ttk.Checkbutton(dialog, text='通知する', variable=flag).pack(pady=4)

            def start():
                result.update(name=name.get(), entry=entry.get(), flag=flag.get())
                root.quit()
            ttk.Button(dialog, text='開始', command=start).pack(pady=8)
            self.positions = {}
            dialog.update()
            for widget in dialog.winfo_children():
                self.positions[widget.winfo_class()] = (widget.winfo_rootx() - dialog.winfo_rootx() + widget.winfo_width() // 2,
                                                        widget.winfo_rooty() - dialog.winfo_rooty() + widget.winfo_height() // 2)
            ready.set()
            root.mainloop()
            root.destroy()
        threading.Thread(target=gui, daemon=True).start()
        ready.wait(5)
        windows = script_windows.ScriptWindows()
        main = wait_for(lambda: next((w for w in windows.list() if w['title'] == '窓テスト'), None))
        self.assertGreater(windows.capture(main['id']).mean(), 0)
        self.assertTrue(windows.png(main['id']).startswith(b'\x89PNG'))

        windows.click(main['id'], *self.positions['TCombobox'])
        popup = wait_for(lambda: next((w for w in windows.list() if w['popup']), None))
        self.assertEqual(popup['parent'], main['id'])
        windows.click(popup['id'], popup['width'] // 2, popup['height'] // 2)  # the middle item
        windows.click(main['id'], *self.positions['TEntry'])
        windows.key(main['id'], 'End')
        for _ in range(4):
            windows.key(main['id'], 'Backspace')
        windows.type(main['id'], '0.88')
        windows.click(main['id'], *self.positions['TCheckbutton'])
        windows.click(main['id'], *self.positions['TButton'])
        wait_for(lambda: result)
        self.assertEqual(result, {'name': 'ミュウツー', 'entry': '0.88', 'flag': True})

    def test_a_busy_window_never_holds_up_the_app(self):
        # A status window that its script updates only now and then: its thread does not answer window messages.
        script_windows.track_tkinter()
        shown, finish = threading.Event(), threading.Event()

        def gui():
            import tkinter as tk
            root = tk.Tk()
            root.title('いそがしい窓')
            tk.Label(root, text='回数: 0').pack(padx=40, pady=20)
            root.update()
            shown.set()
            finish.wait(10)  # busy: no update() for a while
            root.destroy()
        thread = threading.Thread(target=gui, daemon=True)
        thread.start()
        shown.wait(5)
        windows = script_windows.ScriptWindows()
        try:
            started = time.monotonic()
            window = next(w for w in windows.list() if w['title'] == 'いそがしい窓')
            windows.list()
            try:
                windows.capture(window['id'])
            except ValueError:
                pass  # not drawn yet is fine; waiting is not
            self.assertLess(time.monotonic() - started, 2)
        finally:
            finish.set()
            thread.join(5)

    def test_cv2_window_gets_clicks(self):
        import cv2
        import numpy as np
        clicks = []
        cv2.namedWindow('cv2 test')
        cv2.setMouseCallback('cv2 test', lambda event, x, y, *_: clicks.append((event, x, y)))
        picture = np.zeros((120, 240, 3), np.uint8)
        windows = script_windows.ScriptWindows()
        try:
            for step in range(60):
                cv2.imshow('cv2 test', picture)
                cv2.waitKey(10)
                if step == 5:
                    window = next(w for w in windows.list() if w['title'] == 'cv2 test')
                    windows.click(window['id'], 50, 60)
                if (cv2.EVENT_LBUTTONDOWN, 50, 60) in clicks:
                    break
        finally:
            cv2.destroyAllWindows()
        self.assertIn((cv2.EVENT_LBUTTONDOWN, 50, 60), clicks)


if __name__ == '__main__':
    unittest.main()
