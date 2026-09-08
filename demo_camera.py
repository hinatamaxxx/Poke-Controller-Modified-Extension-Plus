"""Hardware-free validation camera. No controller writes are possible in this mode."""
import time


def install():
    import numpy as np
    from Camera import Camera
    from Commands.Sender import Sender
    import Window
    from pynput.keyboard import Listener

    def read(self):
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        x = int(time.monotonic() * 100) % 560
        frame[100:180, x:x+80] = (80, 200, 80)
        self.image_bgr, self.frame_at = frame, time.time()
        return frame

    Camera.openCamera = lambda self, *a, **kw: None
    Camera.isOpened = lambda self: True
    Camera.readFrame = read
    Sender.openSerial = lambda self, *a, **kw: False
    Sender.writeRow = lambda self, *a, **kw: None
    Sender.writeRow_wo_perf_counter = lambda self, *a, **kw: None
    Listener.start = lambda self: None
