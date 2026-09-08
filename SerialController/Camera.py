#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import List, TYPE_CHECKING

import cv2
import datetime
import os
import time
import threading
from logging import getLogger, DEBUG, NullHandler

if TYPE_CHECKING:
    import numpy


def imwrite(filename: str, img: numpy.ndarray, params: int = None):
    _logger = getLogger(__name__)
    _logger.addHandler(NullHandler())
    _logger.setLevel(DEBUG)
    _logger.propagate = True
    try:
        ext = os.path.splitext(filename)[1]
        result, n = cv2.imencode(ext, img, params)

        if result:
            with open(filename, mode="w+b") as f:
                n.tofile(f)
            return True
        else:
            return False
    except Exception as e:
        print(e)
        _logger.error(f"Image Write Error: {e}")
        return False


CAPTURE_DIR = "./Captures/"


def _get_save_filespec(filename: str) -> str:
    """
    画像ファイルの保存パスを取得する。

    入力が絶対パスの場合は、`CAPTURE_DIR`につなげずに返す。

    Args:
        filename (str): 保存名／保存パス

    Returns:
        str: _description_
    """
    if os.path.isabs(filename):
        return filename
    else:
        return os.path.join(CAPTURE_DIR, filename)


class Camera:
    def __init__(self, fps: int = 45):
        self.camera = None
        self.lease = None
        self.capture_size = (1280, 720)
        # self.capture_size = (1920, 1080)
        self.capture_dir = "Captures"
        self.fps = int(fps)
        self.image_bgr = None
        self.frame_at = 0
        self.error = ''
        self.device_path = ''
        self._opened = False
        self._stop = threading.Event()
        self.thread = None

        self._logger = getLogger(__name__)
        self._logger.addHandler(NullHandler())
        self._logger.setLevel(DEBUG)
        self._logger.propagate = True

    def openCamera(self, cameraId: int, device_path=None):
        self.destroy()
        if cameraId < 0:
            return
        if self.thread is not None and self.thread.is_alive():
            self.error = '前のカメラを終了しています。少し待ってから再接続してください。'
            print(self.error)
            return
        self.error = ''
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._capture_loop, args=(cameraId, device_path), daemon=True)
        self.thread.start()

    def _capture_loop(self, cameraId, device_path=None):
        capture, lease = None, None
        try:
            from WindowsDevices import enumerate_cameras, CameraLease
            devices = enumerate_cameras()
            if device_path is not None:
                cameraId = next((i for i, d in enumerate(devices) if d['path'] == device_path), -1)
                if cameraId < 0:
                    raise RuntimeError('選択したキャプチャ機器が未接続です')
            if cameraId >= len(devices):
                raise RuntimeError('キャプチャ機器が見つかりません')
            identity = devices[cameraId]['path'] or str(cameraId)
            lease = CameraLease(identity)
            capture = cv2.VideoCapture(cameraId, cv2.CAP_DSHOW)
            if not capture.isOpened():
                raise RuntimeError('カメラを開けません。他のアプリで使用していないか確認してください。')
            current = enumerate_cameras()
            if cameraId >= len(current) or (current[cameraId]['path'] or str(cameraId)) != identity:
                raise RuntimeError('接続中に機器の一覧が変わりました。再接続してください。')
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.capture_size[0])
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.capture_size[1])
            self.camera, self.lease = capture, lease
            self.device_path = identity
            self._opened = not self._stop.is_set()
            failures = 0
            while not self._stop.is_set():
                ok, frame = capture.read()
                if self._stop.is_set():
                    break
                if not ok or frame is None:
                    failures += 1
                    self.image_bgr, self.frame_at = None, 0
                    if failures >= 5:
                        raise RuntimeError('カメラ映像が途切れました。USB接続を確認して再接続してください。')
                    self._stop.wait(.05)
                    continue
                failures = 0
                self.image_bgr, self.frame_at = frame, time.time()
                self._stop.wait(.001)
        except Exception as exc:
            self.error = str(exc)
            print('カメラ: ' + self.error)
            self._logger.exception('カメラ処理に失敗しました')
        finally:
            self._opened = False
            self.image_bgr, self.frame_at = None, 0
            if capture is not None:
                capture.release()
            if lease is not None:
                lease.close()
            self.camera, self.lease = None, None

    # self.camera.set(cv2.CAP_PROP_SETTINGS, 0)

    def isOpened(self):
        return self._opened

    def readFrame(self):
        if time.time() - self.frame_at > 2:
            return None
        return self.image_bgr

    def saveCapture(self, filename: str = None, crop: int = None, crop_ax: List[int] = None, img: numpy.ndarray = None):
        if crop_ax is None:
            crop_ax = [0, 0, 1280, 720]
        else:
            pass
            # print(crop_ax)

        dt_now = datetime.datetime.now()
        if filename is None or filename == "":
            filename = dt_now.strftime("%Y-%m-%d_%H-%M-%S") + ".png"
        else:
            filename = filename + ".png"

        if crop is None:
            image = self.image_bgr
        elif crop == 1 or crop == "1":
            image = self.image_bgr[crop_ax[1] : crop_ax[3], crop_ax[0] : crop_ax[2]]
        elif crop == 2 or crop == "2":
            image = self.image_bgr[crop_ax[1] : crop_ax[1] + crop_ax[3], crop_ax[0] : crop_ax[0] + crop_ax[2]]
        elif img is not None:
            image = img
        else:
            image = self.image_bgr

        save_path = _get_save_filespec(filename)

        if not os.path.exists(os.path.dirname(save_path)) or not os.path.isdir(os.path.dirname(save_path)):
            # 保存先ディレクトリが存在しないか、同名のファイルが存在する場合（existsはファイルとフォルダを区別しない）
            os.makedirs(os.path.dirname(save_path))
            self._logger.debug("Created Capture folder")

        try:
            imwrite(save_path, image)
            self._logger.debug(f"Capture succeeded: {save_path}")
            print("capture succeeded: " + save_path)
        except cv2.error as e:
            print("Capture Failed")
            self._logger.error(f"Capture Failed :{e}")

    def destroy(self):
        self._stop.set()
        self._opened = False
        self.image_bgr, self.frame_at = None, 0
