"""Regression tests use virtual devices only; never send physical controller input."""
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'SerialController')]


class StabilityTests(unittest.TestCase):
    def test_stop_long_wait_cleans_up_on_worker_once(self):
        from Commands.PythonCommandBase import PythonCommand
        started = threading.Event()
        command = PythonCommand()
        def work():
            started.set()
            command.wait(30)
        command.do = work
        keys, callback = Mock(), Mock()
        owners = []
        keys.end.side_effect = lambda: owners.append(threading.get_ident())
        with patch('Commands.PythonCommandBase.KeyPress', return_value=keys):
            command.start(Mock(), callback)
            self.assertTrue(started.wait(2))
            command.sendStopRequest()
            command.thread.join(1)
        self.assertFalse(command.thread.is_alive())
        self.assertEqual(owners, [command.thread.ident])
        callback.assert_called_once_with()
        self.assertIsNone(command.keys)

    def test_script_initialization_error_still_calls_completion(self):
        from Commands.PythonCommandBase import PythonCommand
        command = PythonCommand()
        command.print_t = Mock()
        callback = Mock()
        with patch('Commands.PythonCommandBase.KeyPress', side_effect=OSError('unplugged')):
            command.start(Mock(), callback)
            command.thread.join(2)
        callback.assert_called_once_with()
        self.assertFalse(command.alive)
        self.assertIn('unplugged', command.print_t.call_args.args[0])

    def test_serial_short_write_latches_error_and_stops_sending(self):
        from Commands.Sender import Sender
        sender = Sender(Mock())
        port = Mock()
        port.write.return_value = 1
        sender.ser = port
        self.assertFalse(sender._write(b'abcd'))
        self.assertTrue(sender.last_error)
        self.assertFalse(sender._write(b'abcd'))
        port.write.assert_called_once()
        port.close.assert_called_once()

    def test_log_flood_cannot_drop_completion(self):
        import UiDispatch
        root = Mock()
        old = UiDispatch._current
        dispatcher = UiDispatch.Dispatcher(root)
        called = []
        @UiDispatch.on_ui
        def completed():
            called.append(threading.get_ident())
        try:
            for _ in range(3000):
                dispatcher.post(lambda: None)
            worker = threading.Thread(target=completed)
            worker.start()
            worker.join(1)
            dispatcher.drain()
            self.assertEqual(called, [threading.get_ident()])
            self.assertLessEqual(dispatcher.pending.qsize(), 2048)
        finally:
            dispatcher.close()
            UiDispatch._current = old

    def test_camera_blocked_read_does_not_block_caller(self):
        from Camera import Camera
        entered, release = threading.Event(), threading.Event()
        capture, lease = Mock(), Mock()
        owners = []
        def read():
            entered.set()
            release.wait(3)
            return False, None
        capture.read.side_effect = read
        capture.release.side_effect = lambda: owners.append(threading.get_ident())
        with patch('WindowsDevices.enumerate_cameras', return_value=[{'path': 'virtual'}]), patch('WindowsDevices.CameraLease', return_value=lease), patch('cv2.VideoCapture', return_value=capture):
            camera = Camera()
            try:
                camera.openCamera(0)
                self.assertTrue(entered.wait(2))
                before = time.monotonic()
                self.assertIsNone(camera.readFrame())
                camera.destroy()
                self.assertLess(time.monotonic() - before, .1)
                capture.release.assert_not_called()
            finally:
                release.set()
                camera.thread.join(3)
        self.assertEqual(owners, [camera.thread.ident])
        lease.close.assert_called_once()

    def test_shutdown_waits_for_producer_and_upgrades_disconnect(self):
        from AppLifecycle import Lifecycle
        app = Mock()
        app.cur_command = SimpleNamespace(thread=Mock(), alive=True)
        app.cur_command.thread.is_alive.return_value = True
        app.procon_thread = None
        app.keyboard = None
        app.ser.last_error = ''
        life = Lifecycle(app)
        life.request()
        life.request(closing=True)
        life.tick()
        app.ser.closeSerial.assert_not_called()
        app._finish_exit.assert_not_called()
        app.cur_command.thread.is_alive.return_value = False
        life.tick()
        app.ser.closeSerial.assert_called_once()
        app._finish_exit.assert_called_once()

    def test_virtual_gamepads_are_isolated_and_hat_releases(self):
        import pygame
        from virtual_gamepad import VirtualPads
        from Commands.ProController import ProController
        controller = ProController()
        controller.current_hat = 0
        with VirtualPads(2) as pads:
            controller.instance_id = pads.sticks[0].get_instance_id()
            def events():
                return controller.controller_events(pygame.event.get())
            pads.sdl.SDL_JoystickSetVirtualButton(pads.handles[1], 2, 1)
            self.assertFalse(any(e.type == pygame.JOYBUTTONDOWN for e in events()))
            pads.sdl.SDL_JoystickSetVirtualHat(pads.handles[0], 0, 1)
            self.assertTrue(any(e.type == pygame.JOYBUTTONDOWN and e.button == 11 for e in events()))
            pads.sdl.SDL_JoystickSetVirtualHat(pads.handles[0], 0, 0)
            self.assertTrue(any(e.type == pygame.JOYBUTTONUP and e.button == 11 for e in events()))
            pads.detach(1)
            events()
            pads.detach(0)
            with self.assertRaisesRegex(RuntimeError, '切断'):
                events()


if __name__ == '__main__':
    unittest.main()
