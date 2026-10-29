"""The capture device, on top of the fork origin's Camera. MIT.

The fork origin's Camera opens a device by its DirectShow number and reads it on its own thread. This app chooses the
device by its path (the number changes when devices are plugged in or out), keeps other apps from opening the same
device (CameraLease), and tells the page when the picture stopped (error, frame_at) so it can reconnect.
"""
import time

from Camera import Camera

DROPOUT_SECONDS = 2  # how long reads may fail (signal change, USB hiccup) before the picture counts as lost


class _Watched:
    """The capture object with its reads timed: the camera's frame_at and error follow the picture."""

    def __init__(self, capture, owner):
        self._capture, self._owner, self._failing_since = capture, owner, None

    def read(self):
        ok, frame = self._capture.read()
        owner = self._owner
        if ok and frame is not None:
            self._failing_since = None
            owner.frame_at = time.time()
        else:
            self._failing_since = self._failing_since or time.monotonic()
            if time.monotonic() - self._failing_since > DROPOUT_SECONDS and not owner.error:
                owner.error = 'カメラ映像が途切れました。USB接続を確認して再接続してください。'
                print('カメラ: ' + owner.error)
                if owner._reader_stop is not None:
                    owner._reader_stop.set()
        return ok, frame

    def __getattr__(self, name):
        return getattr(self._capture, name)


class PlusCamera(Camera):
    def __init__(self, fps=45, capture_size='1280x720'):
        super().__init__(fps, capture_size)
        self.error = ''
        self.frame_at = 0
        self.device_path = ''
        self.lease = None

    @property
    def thread(self):
        """The reading thread (None when not reading)."""
        return self._reader

    def openCamera(self, cameraId=0, window=None, device_path=None):
        """Open the device with this path (or the number, or a window / extra source as in the fork origin)."""
        self.destroy()
        self.error = ''
        if window:
            super().openCamera(cameraId, window)
            if not self.isOpened():
                self.error = '映像を取り込めません'
            return
        try:
            from WindowsDevices import enumerate_cameras, CameraLease
            devices = enumerate_cameras()
            if device_path is not None:
                cameraId = next((i for i, d in enumerate(devices) if d['path'] == device_path), -1)
                if cameraId < 0:
                    raise RuntimeError('選択したキャプチャ機器が未接続です')
            if cameraId < 0 or cameraId >= len(devices):
                raise RuntimeError('キャプチャ機器が見つかりません')
            identity = devices[cameraId]['path'] or str(cameraId)
            self.lease = CameraLease(identity)
            super().openCamera(cameraId)
            if not self.isOpened():
                raise RuntimeError('カメラを開けません。他のアプリで使用していないか確認してください。')
            current = enumerate_cameras()
            if cameraId >= len(current) or (current[cameraId]['path'] or str(cameraId)) != identity:
                raise RuntimeError('接続中に機器の一覧が変わりました。再接続してください。')
            self.device_path = identity
        except Exception as exc:
            self.error = str(exc)
            print('カメラ: ' + self.error)
            self._logger.exception('カメラを開けませんでした')
            self.destroy()
            self.error = str(exc)

    def _start_reader(self):
        if self.camera is not None and not isinstance(self.camera, _Watched):
            self.camera = _Watched(self.camera, self)
        super()._start_reader()

    def destroy(self):
        super().destroy()
        self.frame_at = 0
        if self.lease is not None:
            self.lease.close()
            self.lease = None


class DemoSource:
    """A moving square instead of a capture device (the demo has no hardware). Registered in Camera.EXTRA_SOURCES."""
    NAME = 'demo'

    def __init__(self, name=None, size=(640, 360)):
        self.opened, self._last = True, 0

    def isOpened(self):
        return self.opened

    def read(self):
        import numpy as np
        wait = 1 / 30 - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        x = int(time.monotonic() * 100) % 560
        frame[100:180, x:x + 80] = (80, 200, 80)
        return True, frame

    def get(self, prop):
        return 0

    def set(self, prop, value):
        return False

    def release(self):
        self.opened = False


def install_demo():
    import Camera as camera_module
    camera_module.EXTRA_SOURCES[DemoSource.NAME] = ('デモ', DemoSource)
