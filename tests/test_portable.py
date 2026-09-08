import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'SerialController')]


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

    def test_right_stick_unchanged_does_not_resend(self):
        from Commands.ProController import ProController
        controller = ProController()
        stick = Mock()
        stick.get_axis.side_effect = lambda i: [0, 0, .7, -.4][i]
        controller.joystick_move_detection(stick)
        self.assertEqual(controller.bits_16 & 1, 1)
        controller.joystick_move_detection(stick)
        self.assertEqual(controller.bits_16 & 1, 0)

    def test_original_bridge_restored_unchanged(self):
        import subprocess
        folder = 'SerialController/Commands/PythonCommands/bridge_functions'
        for name in ('bridge_functions.py', 'License.txt', 'README.md', 'Sample/bf_sample.py'):
            expected = subprocess.check_output(['git', 'show', '3274e77:' + folder + '/' + name], cwd=ROOT)
            self.assertEqual((ROOT / folder / name).read_bytes(), expected)

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
        from Camera import Camera
        with patch('cv2.VideoCapture') as capture:
            camera = Camera()
            camera.openCamera(-1)
            self.assertIsNone(camera.readFrame())
            self.assertFalse(camera.isOpened())
            capture.assert_not_called()


if __name__ == '__main__':
    unittest.main()
