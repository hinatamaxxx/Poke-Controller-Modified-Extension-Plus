from pathlib import Path
import sys
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'SerialController'))
import numpy as np

from core import Dialogs, LogArea, Overlay


def answer_when_asked(dialogs, values):
    """Answer the first dialogue that appears, from another thread, like the browser would."""
    def run():
        for _ in range(200):
            pending = dialogs.current()
            if pending:
                dialogs.answer(pending[0]['id'], values)
                return
            time.sleep(.01)
    threading.Thread(target=run, daemon=True).start()


class LogAreaTest(unittest.TestCase):
    def test_text_widget_subset_and_limits(self):
        from UiDispatch import trim_log
        area = LogArea()
        for i in range(3000):
            area.insert('end', f'line {i}\n')
            trim_log(area)
        lines = area.get('1.0', 'end').splitlines()
        self.assertLessEqual(len(lines), 2000)
        self.assertEqual(lines[-1], 'line 2999')
        area.delete('1.0', 'end')
        self.assertEqual(area.get(), '')


class OverlayTest(unittest.TestCase):
    def test_rectangles_and_text_are_drawn_then_expire(self):
        overlay = Overlay()
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        overlay.ImgRect(10, 10, 50, 50, outline='red', tag='r', ms=200)
        overlay.ImgText(60, 60, txt='一致', tag='t', ms=200, ft=('x', 12), color='#00ff00')
        drawn = overlay.draw(frame)
        self.assertTrue(drawn.any())
        self.assertFalse(frame.any(), 'the camera frame itself must stay untouched')
        time.sleep(.25)
        self.assertFalse(overlay.draw(frame).any())


class DialogsTest(unittest.TestCase):
    def test_widget_values_keep_original_types(self):
        dialogs = Dialogs()
        widgets = [['Check', '有効', True], ['Next'], ['Combo', '種類', ['a', 'b'], 'a'],
                   ['Scale', '割合', 0, 1, .5, 2], ['Scale', '回数', 0, 10, 3, 0], ['Entry', '名前', '']]
        answer_when_asked(dialogs, [False, 'b', '0.256', 7.4, 'ピカチュウ'])
        result = dialogs.ask('t', widgets, mode=1, need=dict)
        self.assertEqual(result, {'有効': False, '種類': 'b', '割合': .26, '回数': 7, '名前': 'ピカチュウ'})

    def test_cancel_returns_false(self):
        dialogs = Dialogs()
        answer_when_asked(dialogs, None)
        self.assertFalse(dialogs.ask('t', ['A', 'B']))

    def test_wrong_value_count_is_rejected(self):
        dialogs = Dialogs()
        threading.Thread(target=lambda: dialogs.ask('t', ['A']), daemon=True).start()
        for _ in range(100):
            if dialogs.current():
                break
            time.sleep(.01)
        with self.assertRaises(ValueError):
            dialogs.answer(dialogs.current()[0]['id'], ['x', 'y'])
        dialogs.cancel_all()

    def test_script_dialogue_api_uses_browser_answers(self):
        from Commands.CommandBase import Command
        dialogs = Dialogs()
        Command.dialogue_handler = dialogs.handle
        try:
            command = Command.__new__(Command)
            command.message_dialogue = None
            answer_when_asked(dialogs, [True, '3'])
            result = Command.dialogue6widget(command, 'title', [['Check', 'c', False], ['Spin', 's', ['1', '3'], '1']])
            self.assertEqual(result, [True, '3'])
        finally:
            Command.dialogue_handler = None


if __name__ == '__main__':
    unittest.main()
