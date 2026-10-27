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
