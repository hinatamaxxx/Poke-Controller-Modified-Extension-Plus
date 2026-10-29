import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'SerialController')]
import plus_runtime  # noqa: E402

plus_runtime.install()


class PortableTests(unittest.TestCase):
    def test_keyboard_hook_lifecycle(self):
        from pynput.keyboard import Listener, Key
        self.assertEqual(Key.ctrl_l.value.vk, 162)
        listener = Listener()
        listener.start()
        listener.wait()
        self.assertTrue(listener.is_alive())
        listener.stop()
        listener.join(3)
        self.assertFalse(listener.is_alive())

    def test_sdl_virtual_controller(self):
        import pygame
        from virtual_gamepad import VirtualPads
        with VirtualPads() as pads:
            stick = pads.sticks[0]
            pads.sdl.SDL_JoystickSetVirtualAxis(pads.handles[0], 0, 16000)
            pads.sdl.SDL_JoystickSetVirtualButton(pads.handles[0], 0, 1)
            events = pygame.event.get()
            self.assertAlmostEqual(stick.get_axis(0), 16000 / 32768, places=3)
            self.assertTrue(any(e.type == pygame.JOYBUTTONDOWN and e.button == 0 for e in events))

    def test_serial_controller_is_the_fork_origin_as_shipped(self):
        # Only these files differ from futo030/Poke-Controller-Modified-Extension (so its updates merge cleanly).
        import subprocess
        try:
            subprocess.check_output(['git', 'rev-parse', '--verify', 'upstream/master'], cwd=ROOT, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.CalledProcessError):
            self.skipTest('no upstream remote')
        changed = subprocess.check_output(['git', 'diff', '--name-only', 'upstream/master', '--', 'SerialController'],
                                          cwd=ROOT, text=True).split()
        allowed = {'SerialController/Paths.py', 'SerialController/WindowsDevices.py', 'SerialController/UiDispatch.py',
                   'SerialController/Commands/PythonCommands/Samples/PortableDemo.py'}
        self.assertEqual([name for name in changed if name not in allowed and '/profiles/' not in name], [])

    def test_notification_constructors_never_contact_network(self):
        import tempfile
        from LineNotify import Line_Notify
        from DiscordNotify import Discord_Notify
        with tempfile.TemporaryDirectory() as directory, patch('requests.get') as request:
            for cls, attr in ((Line_Notify, 'LINE_TOKEN_PATH'), (Discord_Notify, 'DISCORD_SETTING_PATH')):
                path = Path(directory) / (cls.__name__ + '.ini')
                with patch.object(cls, attr, str(path)):
                    obj = cls()
                    self.assertIsInstance(str(obj), str)
                    path.write_bytes(b'')
                    self.assertFalse(obj.is_utf8_file_with_bom(path))
            request.assert_not_called()

    def test_disabled_camera_does_not_open_hardware(self):
        from plus_camera import PlusCamera
        with patch('cv2.VideoCapture') as capture:
            camera = PlusCamera()
            camera.openCamera(-1)
            self.assertIsNone(camera.readFrame())
            self.assertFalse(camera.isOpened())
            capture.assert_not_called()


if __name__ == '__main__':
    unittest.main()
