from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'SerialController')]


class CompatibilityTests(unittest.TestCase):
    def test_sample_images_match_upstream(self):
        import subprocess
        prefix = 'SerialController/Template/Samples/'
        names = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', '3274e77', '--', prefix], cwd=ROOT).decode().splitlines()
        self.assertEqual(len(names), 14)
        for name in names:
            self.assertEqual((ROOT / name).read_bytes(), subprocess.check_output(['git', 'show', '3274e77:' + name], cwd=ROOT))

    def test_original_bridge_api_delegates(self):
        from Commands.PythonCommands.bridge_functions.bridge_functions import BridgeFunctions
        command = Mock()
        bridge = BridgeFunctions(command)
        bridge.is_extension = True
        bridge.bf_print_w('example')
        command.print_tb.assert_called_once_with('w', 'example', sep=' ', end='\n')

    def test_pygame_full_modules_available(self):
        import pygame
        self.assertTrue(callable(pygame.mixer.Sound))
        image = pygame.Surface((12, 8))
        self.assertEqual(pygame.transform.scale(image, (24, 16)).get_size(), (24, 16))

    def test_ffmpeg_video_roundtrip(self):
        import cv2
        import numpy as np
        with tempfile.TemporaryDirectory() as folder:
            filename = str(Path(folder) / 'movie.avi')
            writer = cv2.VideoWriter(filename, cv2.CAP_FFMPEG, cv2.VideoWriter_fourcc(*'MJPG'), 10, (64, 48))
            try:
                self.assertTrue(writer.isOpened())
                for _ in range(3):
                    writer.write(np.full((48, 64, 3), 120, np.uint8))
            finally:
                writer.release()
            reader = cv2.VideoCapture(filename, cv2.CAP_FFMPEG)
            try:
                self.assertTrue(reader.isOpened())
                self.assertEqual(reader.getBackendName(), 'FFMPEG')
                ok, frame = reader.read()
                self.assertTrue(ok)
                self.assertEqual(frame.shape, (48, 64, 3))
            finally:
                reader.release()

if __name__ == '__main__':
    unittest.main()
