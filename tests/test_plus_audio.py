from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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


if __name__ == '__main__':
    unittest.main()
