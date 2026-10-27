"""Discord 連携: the settings' webhook for every notification, the Switch's own recording and the attached clip."""
import contextlib
import io
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'SerialController')]

import DiscordNotify  # noqa: E402
from history import FrameHistory  # noqa: E402


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


class WebhookTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = str(Path(folder.name) / 'discord_token.ini')
        patcher = patch.object(DiscordNotify.Discord_Notify, 'DISCORD_SETTING_PATH', self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        hook = patch.object(DiscordNotify.Discord_Notify, 'after_send', None)
        hook.start()
        self.addCleanup(hook.stop)

    def make(self, text):
        Path(self.path).write_text(text, encoding='utf-8')
        return DiscordNotify.Discord_Notify()

    def test_new_file_has_only_the_webhook(self):
        with quiet():
            DiscordNotify.Discord_Notify()
        text = Path(self.path).read_text(encoding='utf-8')
        self.assertIn('[DISCORD_WEBHOOK]', text)
        self.assertNotIn('token', text)

    def test_unknown_or_empty_keys_go_to_the_settings_webhook(self):
        notify = self.make('[DISCORD_WEBHOOK]\nwebhook_url = https://example.invalid/a\n'
                           '[DISCORD_WEBHOOK2]\nwebhook_url =\n[DISCORD_WEBHOOK3]\nwebhook_url = https://example.invalid/c\n')
        self.assertEqual(notify.resolve_keys('DISCORD_WEBHOOK5'), ['DISCORD_WEBHOOK'])
        self.assertEqual(notify.resolve_keys('DISCORD_WEBHOOK2'), ['DISCORD_WEBHOOK'])
        self.assertEqual(notify.resolve_keys(['DISCORD_WEBHOOK3', 'X', 'DISCORD_WEBHOOK']),
                         ['DISCORD_WEBHOOK3', 'DISCORD_WEBHOOK'])
        self.assertEqual(notify.resolve_keys('ALL'), ['DISCORD_WEBHOOK', 'DISCORD_WEBHOOK3'])

    def test_nothing_set_sends_nothing(self):
        notify = self.make('[DISCORD_WEBHOOK]\nwebhook_url =\n')
        with patch('requests.post') as post, quiet():
            self.assertEqual(notify.send_message('x', keys='DISCORD_WEBHOOK2'), [])
        post.assert_not_called()

    def test_after_send_runs_only_for_real_notifications(self):
        notify = self.make('[DISCORD_WEBHOOK]\nwebhook_url = https://example.invalid/a\n')
        hook = Mock()
        with patch.object(DiscordNotify.Discord_Notify, 'after_send', hook), \
                patch('requests.post', return_value=Mock(status_code=204)) as post, quiet():
            self.assertEqual(notify.send_message('found', keys='DISCORD_WEBHOOK9'), ['DISCORD_WEBHOOK'])
            notify.send_message('test', follow_up=False)
        self.assertEqual(post.call_args_list[0].args[0], 'https://example.invalid/a')
        hook.assert_called_once_with(notify, ['DISCORD_WEBHOOK'])

    def test_send_file(self):
        notify = self.make('[DISCORD_WEBHOOK]\nwebhook_url = https://example.invalid/a\n')
        with patch('requests.post', return_value=Mock(status_code=200)) as post, quiet():
            self.assertEqual(notify.send_file(['DISCORD_WEBHOOK'], 'clip.mp4', b'data'), ['DISCORD_WEBHOOK'])
        self.assertEqual(post.call_args.kwargs['files']['file'], ('clip.mp4', b'data'))


class SwitchCaptureTests(unittest.TestCase):
    def make(self):
        from Commands import PythonCommandBase
        from Commands.Keys import Button

        class Script(PythonCommandBase.PythonCommand):
            def do(self):
                pass

        with patch.object(DiscordNotify.Discord_Notify, 'DISCORD_SETTING_PATH',
                          str(Path(tempfile.mkdtemp()) / 'discord_token.ini')), quiet():
            script = Script()
        script.keys = Mock()
        script.Discord = Mock()
        script.Discord.resolve_keys.return_value = ['DISCORD_WEBHOOK']
        PythonCommandBase.PythonCommand._last_switch_capture = None
        self.addCleanup(setattr, PythonCommandBase.PythonCommand, '_last_switch_capture', None)
        return script, Button, PythonCommandBase

    def test_holds_capture_long_enough_for_a_video(self):
        script, Button, base = self.make()
        with patch.object(base, 'sleep') as sleep, quiet():
            self.assertTrue(script.switch_capture())
            self.assertFalse(script.switch_capture())  # the video already covers the last 30 seconds
            self.assertTrue(script.switch_capture(force=True))
        script.keys.hold.assert_called_with(Button.CAPTURE)
        script.keys.holdEnd.assert_called_with(Button.CAPTURE)
        self.assertEqual(script.keys.hold.call_count, 2)
        sleep.assert_called_with(2.0)

    def test_discord_text_records_only_when_turned_on(self):
        script, Button, base = self.make()
        with patch.object(base, 'sleep'), quiet():
            with patch.object(base.PythonCommand, 'isDiscordSwitchCapture', False):
                script.discord_text('found')
            script.keys.hold.assert_not_called()
            with patch.object(base.PythonCommand, 'isDiscordSwitchCapture', True):
                script.discord_text('started', switch_capture=False)
                script.keys.hold.assert_not_called()
                script.discord_text('found')
        script.keys.hold.assert_called_once_with(Button.CAPTURE)
        self.assertEqual(script.Discord.send_message.call_count, 3)

    def test_no_webhook_no_recording(self):
        script, Button, base = self.make()
        script.Discord.resolve_keys.return_value = []
        with patch.object(base, 'sleep'), patch.object(base.PythonCommand, 'isDiscordSwitchCapture', True), quiet():
            script.discord_text('found')
        script.keys.hold.assert_not_called()


class ClipTests(unittest.TestCase):
    def test_encode_mp4(self):
        import cv2
        history = FrameHistory(seconds=5, fps=10)
        for i in range(20):
            frame = np.full((360, 640, 3), i * 10, np.uint8)
            history._next = 0
            ok, data = cv2.imencode('.jpg', frame)
            history.frames.append((time.time() - 2 + i * .1, data.tobytes()))
        data = history.encode_mp4()
        self.assertGreater(len(data), 1000)
        self.assertEqual(data[4:8], b'ftyp')
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'clip.mp4')
            Path(path).write_bytes(data)
            video = cv2.VideoCapture(path)
            self.assertEqual(int(video.get(cv2.CAP_PROP_FRAME_COUNT)), 20)
            video.release()
        self.assertEqual(history.encode_mp4(since=time.time() + 10), b'')

    def test_set_fps_keeps_frames(self):
        history = FrameHistory(seconds=30, fps=4)
        history.frames.extend((i, b'x') for i in range(100))
        history.set_fps(10)
        self.assertEqual(history.frames.maxlen, 300)
        self.assertEqual(len(history.frames), 100)


if __name__ == '__main__':
    unittest.main()
