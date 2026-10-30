from pathlib import Path
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'SerialController')]

import plus_audio  # noqa: E402


class FakeSd:
    def __init__(self, behaviour):
        self.behaviour = behaviour

    def InputStream(self, device, **kwargs):
        action = self.behaviour[device]
        if action == 'hang':
            threading.Event().wait(5)
        if action == 'fail':
            raise RuntimeError('Invalid device')
        return type('Stream', (), {'close': lambda self: None})()


class PlusAudioTest(unittest.TestCase):
    def test_the_same_device_is_found_under_another_host_api(self):
        name = 'デジタル オーディオ インターフェイス (2- Cam Link 4K)'
        self.assertTrue(plus_audio.same_device(name, 'デジタル オーディオ インターフェイス (Cam Link 4K)', 'Windows WDM-KS'))
        self.assertTrue(plus_audio.same_device(name, 'デジタル オーディオ インターフェイス (2- Cam Lin', 'MME'))
        self.assertFalse(plus_audio.same_device(name, 'マイク (Steam Streaming Microphone)', 'Windows WDM-KS'))

    def test_a_hung_or_failing_open_is_not_waited_for(self):
        device = {'name': 'board', 'default_samplerate': 48000, 'max_input_channels': 2}
        sd = FakeSd({0: 'hang', 1: 'fail', 2: 'ok'})
        self.assertFalse(plus_audio.opens(sd, 0, device, 'Windows WASAPI', seconds=.2))
        self.assertIn(('Windows WASAPI', 'board'), plus_audio._hung)
        self.assertFalse(plus_audio.opens(sd, 0, device, 'Windows WASAPI', seconds=.2))  # not tried again
        self.assertFalse(plus_audio.opens(sd, 1, device, 'MME'))
        self.assertTrue(plus_audio.opens(sd, 2, device, 'Windows WDM-KS'))


class DefaultOutputTest(unittest.TestCase):
    def test_playback_on_the_default_follows_windows(self):
        from unittest.mock import Mock, patch
        capture = Mock(output_device_name='', is_playing=True, opened_default='TV')
        with patch.object(plus_audio, 'windows_default_output', return_value='TV'):
            self.assertFalse(plus_audio.follow_default(capture))
        with patch.object(plus_audio, 'windows_default_output', return_value='Steam'):
            self.assertTrue(plus_audio.follow_default(capture))
        capture.set_playback.assert_any_call(False)
        capture.set_playback.assert_called_with(True)
        capture.reset_mock()
        capture.output_device_name = 'TV'  # a chosen device stays
        with patch.object(plus_audio, 'windows_default_output', return_value='Steam'):
            self.assertFalse(plus_audio.follow_default(capture))
        capture.set_playback.assert_not_called()

    def test_windows_notification_reopens_playback(self):
        import platform
        from unittest.mock import Mock, patch
        if platform.system() != 'Windows':
            self.skipTest('Windows only')
        capture, done = Mock(), threading.Event()
        with patch.object(plus_audio, '_watcher', None), \
                patch.object(plus_audio, 'follow_default', side_effect=lambda c: done.set()) as follow:
            plus_audio.watch_default(lambda: capture, threading.RLock())
            on_default_changed = plus_audio._watcher[0][6]
            on_default_changed(None, 1, 1, 'mic')  # a recording device: ignored
            on_default_changed(None, 0, 1, 'speakers')
            self.assertTrue(done.wait(2))
            follow.assert_called_once_with(capture)

    def test_windows_default_output_is_read(self):
        import platform
        if platform.system() != 'Windows':
            self.skipTest('Windows only')
        self.assertIsInstance(plus_audio.windows_default_output(), str)


if __name__ == '__main__':
    unittest.main()
