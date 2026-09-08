"""Run with the bundled python -I, pointing only to the packaged application."""
from pathlib import Path
import os
import sys
import tempfile

package = Path(sys.argv[1]).resolve()
assert Path(sys.executable).is_relative_to(package / 'runtime-python')
sys.path[:0] = [str(package), str(package / 'SerialController')]
os.chdir(package / 'SerialController')
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import cv2
import numpy as np
import pygame
import pynput
from Commands.PythonCommands.bridge_functions.bridge_functions import BridgeFunctions
from Commands.PythonCommandBase import ImageProcPythonCommand
from unittest.mock import Mock

for module in (cv2, np, pygame, pynput):
    assert Path(module.__file__).is_relative_to(package / 'runtime-python')
bridge = BridgeFunctions(Mock())
assert bridge.check_pokecon_extension()
bridge.bf_print_w('compatibility')
assert len(list(Path('Template/Samples').glob('*.png'))) == 14
assert all(cv2.imread(str(path)) is not None for path in Path('Template/Samples').glob('*.png'))
assert pygame.transform.scale(pygame.Surface((8, 8)), (16, 16)).get_size() == (16, 16)
listener = pynput.keyboard.Listener()
listener.start()
listener.wait()
listener.stop()
listener.join(3)
assert not listener.is_alive()
with tempfile.TemporaryDirectory() as folder:
    filename = str(Path(folder) / 'video.avi')
    writer = cv2.VideoWriter(filename, cv2.CAP_FFMPEG, cv2.VideoWriter_fourcc(*'MJPG'), 10, (64, 48))
    assert writer.isOpened()
    writer.write(np.full((48, 64, 3), 128, np.uint8))
    writer.release()
    reader = cv2.VideoCapture(filename, cv2.CAP_FFMPEG)
    assert reader.isOpened() and reader.read()[0]
    reader.release()
assert (package / 'licenses/pygame/LGPL.txt').is_file()
assert (package / 'licenses/sources/pynput-1.8.1.tar.gz').is_file()
assert not list(package.rglob('*DirectShowLib*'))
print('PASS: bundled pygame/pynput, original bridge, 14 template images, FFmpeg roundtrip, notices, DirectShowLib exclusion')
