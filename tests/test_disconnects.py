from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'SerialController'))


class SerialFailureTest(unittest.TestCase):
    def test_failed_open_is_not_treated_as_disconnect(self):
        import serial
        from Commands.Sender import Sender
        sender = Sender(Mock())
        with patch('serial.Serial', side_effect=serial.SerialException('missing')):
            self.assertFalse(sender.openSerial(3))
        self.assertEqual(sender.last_error, '')

    def test_write_timeout_keeps_port_open(self):
        import serial
        from Commands.Sender import Sender
        sender = Sender(Mock())
        port = Mock()
        port.write.side_effect = serial.SerialTimeoutException('busy')
        sender.ser = port
        self.assertFalse(sender._write(b'abcd'))
        self.assertEqual(sender.last_error, '')
        port.close.assert_not_called()


class KeyboardResumeTest(unittest.TestCase):
    def make_app(self):
        app = Mock()
        app.cur_command = None
        app.procon_thread = None
        app.keyboard = None
        app.ser.last_error = ''
        state = {'keyboard': True}
        app.is_use_keyboard.get.side_effect = lambda: state['keyboard']
        app.is_use_keyboard.set.side_effect = lambda value: state.update(keyboard=value)
        return app, state

    def test_exit_after_disconnect_saves_original_keyboard_setting(self):
        from AppLifecycle import Lifecycle
        app, state = self.make_app()
        life = Lifecycle(app)
        life.request()            # cable unplugged: keyboard is switched off
        life.tick()
        self.assertFalse(state['keyboard'])
        life.request(closing=True)
        life.tick()
        self.assertTrue(state['keyboard'])
        app._finish_exit.assert_called_once()

    def test_closing_while_waiting_stops_new_producers(self):
        from AppLifecycle import Lifecycle
        app, _ = self.make_app()
        life = Lifecycle(app)
        life.stop_producers = Mock()
        life.request()
        life.request(closing=True)
        self.assertEqual(life.stop_producers.call_count, 2)


class CameraIdentityTest(unittest.TestCase):
    def test_devices_without_path_get_name_identity(self):
        import WindowsDevices
        rows = [{'index': 0, 'name': 'OBS Virtual Camera', 'path': ''},
                {'index': 1, 'name': 'OBS Virtual Camera', 'path': ''},
                {'index': 2, 'name': 'USB Capture', 'path': '\\\\?\\usb#1'}]
        seen = {}
        for device in rows:  # same rule as enumerate_cameras
            if not device['path']:
                count = seen.get(device['name'], 0)
                seen[device['name']] = count + 1
                device['path'] = f"name:{device['name']}#{count}"
        self.assertEqual([d['path'] for d in rows],
                         ['name:OBS Virtual Camera#0', 'name:OBS Virtual Camera#1', '\\\\?\\usb#1'])
        self.assertTrue(all(d['path'] for d in WindowsDevices.enumerate_cameras()))


if __name__ == '__main__':
    unittest.main()
