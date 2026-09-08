import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest
import tkinter as tk
from tkinter import ttk
sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[1] / 'SerialController')]
from Camera import Camera
from CameraSelection import CameraSelection

A = {'index': 0, 'name': 'USB Video', 'path': 'device-a'}
B = {'index': 1, 'name': 'USB Video', 'path': 'device-b'}


class CameraSelectionTests(unittest.TestCase):
    def test_unplug_does_not_open_device_reusing_index(self):
        camera = Camera()
        with patch('WindowsDevices.enumerate_cameras', return_value=[dict(B, index=0)]), patch('cv2.VideoCapture') as open_device:
            camera._capture_loop(0, 'device-a')
        open_device.assert_not_called()
        self.assertIn('未接続', camera.error)

    def test_reorder_resolves_identity_and_checks_after_open(self):
        camera = Camera()
        camera._stop.set()
        devices = [dict(B, index=0), dict(A, index=1)]
        with patch('WindowsDevices.enumerate_cameras', return_value=devices), patch('WindowsDevices.CameraLease') as lease, patch('cv2.VideoCapture') as open_device:
            camera._capture_loop(0, 'device-a')
            self.assertEqual(open_device.call_args.args[0], 1)
            lease.assert_called_once_with('device-a')
        self.assertEqual(camera.device_path, 'device-a')

    def test_unplug_during_open_releases_without_reading(self):
        camera = Camera()
        with patch('WindowsDevices.enumerate_cameras', side_effect=[[A, B], [dict(B, index=0)]]), patch('WindowsDevices.CameraLease'), patch('cv2.VideoCapture') as open_device:
            camera._capture_loop(0, 'device-a')
            open_device.return_value.read.assert_not_called()
            open_device.return_value.release.assert_called_once()
        self.assertIn('一覧が変わりました', camera.error)

    def test_gui_refresh_and_selection_use_identity_not_name(self):
        root = tk.Tk()
        root.withdraw()
        try:
            camera = Mock(thread=None, error='', device_path='')
            camera.isOpened.return_value = False
            app = SimpleNamespace(root=root, settings=SimpleNamespace(camera_path='device-a', camera_name='USB Video'),
                                  camera_id=tk.IntVar(root, value=0), camera_name_cb=ttk.Combobox(root), camera_status=ttk.Label(root), camera=camera)
            with patch('CameraSelection.enumerate_cameras', return_value=[A, B]) as enumerate_devices:
                choice = CameraSelection(app)
                self.assertNotEqual(app.camera_name_cb['values'][1], app.camera_name_cb['values'][2])
                enumerate_devices.return_value = [dict(B, index=0)]
                choice.connect()
                camera.openCamera.assert_not_called()
                self.assertIn('未接続', app.camera_name_cb.get())
                self.assertEqual(choice.path, 'device-a')
                app.camera_name_cb.current(1)
                choice.select()
                camera.openCamera.assert_called_once_with(0, device_path='device-b')
                self.assertEqual(app.settings.camera_path, 'device-b')
                app.camera_name_cb.current(0)
                choice.select()
                self.assertEqual(app.settings.camera_path, '')
        finally:
            root.destroy()
