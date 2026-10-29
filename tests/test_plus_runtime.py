"""What this app adds to the fork origin's runtime (plus_runtime, plus_camera, plus_logger). No real devices are used."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'SerialController')]
import plus_runtime  # noqa: E402

plus_runtime.install()


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


def wait_calls(mock, count=1, timeout=3):
    deadline = time.monotonic() + timeout
    while mock.call_count < count and time.monotonic() < deadline:
        time.sleep(.01)


class ScriptLifecycleTests(unittest.TestCase):
    def run_script(self, do, keys=None):
        from Commands.PythonCommandBase import PythonCommand
        command = PythonCommand()
        command.do = do.__get__(command)
        callback = Mock()
        with patch('Commands.PythonCommandBase.KeyPress', return_value=keys or Mock()), quiet():
            command.start(Mock(), callback)
            return command, callback

    def test_stop_from_the_app_ends_a_long_wait_and_calls_back_once(self):
        started = threading.Event()

        def do(self):
            started.set()
            self.wait(30)
        command, callback = self.run_script(do)
        self.assertTrue(started.wait(2))
        with quiet():
            command.end(Mock())
            command.end(Mock())  # pressing stop again never raises in the app's thread
        deadline = time.monotonic() + 3
        while callback.call_count == 0 and time.monotonic() < deadline:
            time.sleep(.02)
        callback.assert_called_once_with()
        self.assertFalse(command.finished_itself)

    def test_an_error_in_the_script_is_reported_and_calls_back(self):
        def do(self):
            raise RuntimeError('boom')
        command, callback = self.run_script(do)
        wait_calls(callback)
        callback.assert_called_once_with()
        self.assertIsInstance(command.last_error, RuntimeError)
        self.assertFalse(command.alive)

    def test_finish_in_the_script_ends_it_as_finished_by_itself(self):
        reached = []

        def do(self):
            self.finish()
            reached.append('after finish')
        command, callback = self.run_script(do)
        wait_calls(callback)
        callback.assert_called_once_with()
        self.assertEqual(reached, [])
        self.assertTrue(command.finished_itself)

    def test_a_script_can_be_started_again(self):
        runs = []

        def do(self):
            runs.append(1)
        command, callback = self.run_script(do)
        wait_calls(callback)
        with patch('Commands.PythonCommandBase.KeyPress', return_value=Mock()), quiet():
            command.start(Mock(), callback)
        wait_calls(callback, 2)
        self.assertEqual(runs, [1, 1])
        self.assertEqual(callback.call_count, 2)


class ImageLookupTests(unittest.TestCase):
    def test_template_images_are_looked_up_next_to_the_script(self):
        from Commands.PythonCommandBase import ImageProcPythonCommand
        import Paths
        command = ImageProcPythonCommand.__new__(ImageProcPythonCommand)
        command.template_path_name = './Template/'
        with patch.object(Paths, 'find_image', return_value='found') as find:
            self.assertEqual(command.get_filespec('a.png', 't'), 'found')
        find.assert_called_once_with('a.png', 'Commands.PythonCommandBase')
        command.template_path_name = 'Other/'
        self.assertEqual(command.get_filespec('a.png', 't'), 'Other/a.png')
        self.assertEqual(command.get_filespec('a.png', 'c'), command.capture_path_name + 'a.png')


class CameraTests(unittest.TestCase):
    def test_device_is_chosen_by_path_and_released(self):
        from plus_camera import PlusCamera
        capture, lease = Mock(), Mock()
        capture.isOpened.return_value = True
        capture.read.return_value = (True, __import__('numpy').zeros((4, 4, 3), 'uint8'))
        capture.get.return_value = 0
        devices = [{'path': 'other', 'name': 'a'}, {'path': 'wanted', 'name': 'b'}]
        with patch('WindowsDevices.enumerate_cameras', return_value=devices), \
                patch('WindowsDevices.CameraLease', return_value=lease), \
                patch('cv2.VideoCapture', return_value=capture) as video, quiet():
            camera = PlusCamera()
            camera.openCamera(device_path='wanted')
            self.assertEqual(video.call_args.args[0], 1)
            deadline = time.monotonic() + 2
            while not camera.frame_at and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(camera.frame_at)
            self.assertEqual(camera.error, '')
            camera.destroy()
        lease.close.assert_called_once()

    def test_missing_device_is_an_error_not_an_exception(self):
        from plus_camera import PlusCamera
        with patch('WindowsDevices.enumerate_cameras', return_value=[]), quiet():
            camera = PlusCamera()
            camera.openCamera(device_path='gone')
        self.assertIn('未接続', camera.error)
        self.assertFalse(camera.isOpened())

    def test_demo_source_moves(self):
        from plus_camera import DemoSource
        source = DemoSource()
        ok, first = source.read()
        time.sleep(.05)
        ok, second = source.read()
        self.assertTrue(ok)
        self.assertFalse((first == second).all())


class LoggerTests(unittest.TestCase):
    def test_urllib3_debug_is_not_logged(self):
        import logging
        import plus_logger
        root = logging.getLogger()
        saved = (root.handlers[:], root.level, getattr(root, '_poke_configured', False))
        urllib3_logger = logging.getLogger('urllib3')
        try:
            with tempfile.TemporaryDirectory() as folder, patch.object(plus_logger.Paths, 'LOGS', folder):
                root._poke_configured = False
                plus_logger.root_logger()
                self.assertFalse(urllib3_logger.isEnabledFor(logging.DEBUG))
                for handler in root.handlers[:]:
                    if handler not in saved[0]:
                        root.removeHandler(handler)
                        handler.close()
        finally:
            root.setLevel(saved[1])
            root._poke_configured = saved[2]


if __name__ == '__main__':
    unittest.main()
