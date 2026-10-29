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


class SleepTest(unittest.TestCase):
    def test_a_running_script_is_stopped_after_the_pc_slept(self):
        import threading
        from unittest.mock import Mock
        import core
        owner = Mock(lock=threading.RLock(), running=True)
        core.Core._resumed(owner, 600)
        owner.watch.expect_stop.assert_called_once_with()
        owner.watch.report.assert_called_once_with('sleep', '約600秒')
        owner.cur_command.end.assert_called_once_with(owner.ser)
        owner.reset_mock()
        owner.running = False
        core.Core._resumed(owner, 600)
        owner.cur_command.end.assert_not_called()

    def test_the_fork_origins_sleep_watch_sees_a_gap(self):
        from services.sleep_watch import SleepWatch
        now = [1000.0]
        seen = []
        watch = SleepWatch(seen.append, clock=lambda: now[0])
        watch._last = now[0]
        now[0] += 1.5
        self.assertEqual(watch.check(), 0)
        now[0] += 300
        watch.check()
        self.assertEqual(len(seen), 1)


class ScriptsTest(unittest.TestCase):
    def test_an_edited_script_is_read_again_once_also_inside_a_run_list(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        import core
        entry = SimpleNamespace(name='A (x/a)', module_name='x.a')
        loader = Mock()
        loader.findEntry.return_value = entry
        loader.reload.return_value = [entry]
        scripts = core._command_service()(lambda: None, lambda: None)
        scripts.loaders, scripts.commands = {'Python': loader, 'Mcu': Mock(reload=Mock(return_value=[]))}, {}
        scripts.reload()
        self.assertEqual(scripts.reload_next, {'x.a'})
        scripts.find_class('Python', 'A (x/a)')  # a run list's step
        loader.getCommandClass.assert_called_with(entry, reload=True)
        scripts.command_class('Python', entry)
        loader.getCommandClass.assert_called_with(entry, reload=False)


class MaskTest(unittest.TestCase):
    def owner(self):
        import threading
        from types import SimpleNamespace
        from unittest.mock import Mock
        import core
        owner = Mock(lock=threading.RLock(), camera=SimpleNamespace(capture_filter=None),
                     settings=Mock(masks=[], is_show_mask=True, is_mask_apply_to_capture=False))
        for name in ('masks', 'mask_image', '_apply_mask_filter'):
            setattr(owner, name, getattr(core.Core, name).__get__(owner))
        owner.MAX_MASKS = core.Core.MAX_MASKS
        return owner

    def test_masks_cover_the_shown_picture_but_not_the_camera_image(self):
        import core
        owner = self.owner()
        core.Core.set_masks(owner, {'items': [{'shape': 'Rectangle', 'x1': 30, 'y1': 30, 'x2': 10, 'y2': 10,
                                               'color': '#ff0000', 'enabled': True},
                                              {'shape': 'Ellipse', 'x1': 0, 'y1': 0, 'x2': 1, 'y2': 1}]})
        self.assertEqual(owner.settings.masks, ['Rectangle,10,10,30,30,#ff0000,1'])  # too small one dropped
        owner.settings.save.assert_called_once_with()
        image = np.zeros((40, 40, 3), np.uint8)
        shown = owner.mask_image(image)
        self.assertEqual(tuple(shown[20, 20]), (0, 0, 255))
        self.assertEqual(image[20, 20].sum(), 0)
        self.assertIsNone(owner.camera.capture_filter)
        core.Core.set_masks(owner, {'apply': True})
        self.assertIsNotNone(owner.camera.capture_filter)
        core.Core.set_masks(owner, {'show': False})
        self.assertIsNone(owner.camera.capture_filter)
        self.assertIs(owner.mask_image(image), image)

    def test_a_wrong_shape_is_refused(self):
        import core
        with self.assertRaises(ValueError):
            core.Core.set_masks(self.owner(), {'items': [{'shape': 'Star', 'x2': 9, 'y2': 9}]})


class AudioTest(unittest.TestCase):
    def test_the_fork_origins_audio_service_reads_and_writes_the_profiles_values(self):
        from types import SimpleNamespace
        import core
        from plus_settings import Var
        settings = SimpleNamespace(is_use_audio=Var(False), audio_volume=Var(100), masks=[])
        view = core.AudioSettings(settings)
        self.assertIs(view.is_use_audio, False)
        view.is_use_audio = True
        view.audio_volume = 40
        view.masks = ['x']
        self.assertEqual((settings.is_use_audio.get(), settings.audio_volume.get(), settings.masks), (True, 40, ['x']))

    def test_changing_the_input_restarts_the_capture(self):
        import threading
        from types import SimpleNamespace
        from unittest.mock import Mock
        import core
        from plus_settings import Var
        settings = SimpleNamespace(is_use_audio=Var(True), audio_device=Var('a'), audio_output_device=Var(''),
                                   is_audio_playback=Var(True), audio_volume=Var(100), camera_path='cam', save=Mock())
        audio = Mock(available=True)
        owner = Mock(lock=threading.RLock(), settings=settings)
        owner._audio.return_value = audio
        owner._audio_cameras.return_value = {0: 'cam'}
        core.Core.set_audio(owner, {'input': 'b', 'volume': 150})
        audio.apply.assert_called_once_with({0: 'cam'}, 0)
        self.assertEqual((settings.audio_device.get(), settings.audio_volume.get()), ('b', 100))
        audio.reset_mock()
        core.Core.set_audio(owner, {'playback': False})
        audio.apply.assert_not_called()
        audio.apply_playback.assert_called_once_with()
        settings.save.assert_called()


class SwitchKeyboardTest(unittest.TestCase):
    def test_why_text_cannot_be_typed(self):
        from unittest.mock import Mock
        import core
        owner = Mock(running=True, demo=False)
        self.assertIn('実行中', core.Core.keyboard_unavailable(owner))
        owner.running = False
        owner.ser.isOpened.return_value = False
        self.assertIn('シリアルポート', core.Core.keyboard_unavailable(owner))
        owner.demo = True
        self.assertEqual(core.Core.keyboard_unavailable(owner), '')

    def test_a_refused_text_is_an_error(self):
        import threading
        from unittest.mock import Mock
        import core
        owner = Mock(lock=threading.RLock(), keyboard_session=Mock())
        owner.keyboard_unavailable.return_value = ''
        owner.keyboard_session.send_text.return_value = False
        with self.assertRaises(ValueError):
            core.Core.switch_keyboard(owner, {'text': 'あいう'})
        core.Core.switch_keyboard(owner, {'key': 'ok'})
        owner.keyboard_session.ok.assert_called_once_with()
        owner.keyboard_unavailable.return_value = 'だめ'
        with self.assertRaisesRegex(ValueError, 'だめ'):
            core.Core.switch_keyboard(owner, {'text': 'a'})


if __name__ == '__main__':
    unittest.main()
