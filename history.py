"""The last seconds of video, kept in memory and saved as a recording when something goes wrong. MIT.

Modelled on Pokémon Automation's stream history: after an error, a freeze or a crash, the clip shows what led up to
it, and Claude can look at it with the recording tools (get_recording_overview / get_recording_frame).
"""
import collections
import json
import os
import threading
import time

WIDTH = 640


class FrameHistory:
    def __init__(self, seconds=30, fps=4):
        self.seconds, self.fps = seconds, fps
        self.frames = collections.deque(maxlen=int(seconds * fps))
        self.lock = threading.Lock()
        self._next = 0

    def set_fps(self, fps):
        """Keep `fps` frames a second from now on (the clip sent to Discord needs more than the default)."""
        if fps == self.fps:
            return
        with self.lock:
            self.fps = fps
            self.frames = collections.deque(self.frames, maxlen=int(self.seconds * fps))

    def due(self):
        return time.monotonic() >= self._next

    def add_frame(self, frame):
        """Add a BGR frame, at most `fps` times a second."""
        if not self.due() or frame is None:
            return
        import cv2
        height = int(frame.shape[0] * WIDTH / frame.shape[1])
        small = cv2.resize(frame, (WIDTH, height), interpolation=cv2.INTER_AREA)
        ok, encoded = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ok:
            self.add_jpeg(encoded.tobytes())

    def add_jpeg(self, data):
        if not self.due() or not data:
            return
        self._next = time.monotonic() + 1 / self.fps
        with self.lock:
            self.frames.append((time.time(), data))

    def save(self, root, label):
        """Write the clip in the recorder's format; returns its recording ID, or '' when there is nothing to save."""
        with self.lock:
            frames = list(self.frames)
        if not frames:
            return ''
        rec_id = time.strftime('%Y%m%d-%H%M%S') + '-clip'
        while os.path.exists(os.path.join(root, rec_id)):
            rec_id += 'a'
        folder = os.path.join(root, rec_id)
        os.makedirs(folder)
        start = frames[0][0]
        listed = []
        for index, (at, data) in enumerate(frames):
            name = f'{index:05d}.jpg'
            with open(os.path.join(folder, name), 'wb') as stream:
                stream.write(data)
            listed.append({'t': round(at - start, 2), 'file': name})
        data = {'id': rec_id, 'label': label, 'fps': self.fps, 'started': start, 'frames': listed, 'inputs': [],
                'duration': listed[-1]['t']}
        with open(os.path.join(folder, 'timeline.json'), 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False)
        return rec_id

    def encode_mp4(self, since=None):
        """The kept frames (from `since`, a time.time()) as an MP4 file's bytes, H.264 so Discord plays it in the
        chat; b'' when there is nothing to encode."""
        import cv2
        import numpy as np
        import tempfile
        with self.lock:
            frames = [f for f in self.frames if since is None or f[0] >= since]
        if len(frames) < 2:
            return b''
        first = cv2.imdecode(np.frombuffer(frames[0][1], np.uint8), cv2.IMREAD_COLOR)
        height, width = first.shape[:2]
        size = (width - width % 2, height - height % 2)  # H.264 needs even sizes
        fps = max(1.0, (len(frames) - 1) / max(.1, frames[-1][0] - frames[0][0]))
        handle, path = tempfile.mkstemp(suffix='.mp4')
        os.close(handle)
        try:
            # Windows' own encoder (Media Foundation) makes H.264; the plain MPEG-4 one is the fallback.
            writer = cv2.VideoWriter(path, cv2.CAP_MSMF, cv2.VideoWriter_fourcc(*'H264'), fps, size)
            if not writer.isOpened():
                writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'mp4v'), fps, size)
            if not writer.isOpened():
                return b''
            try:
                for _at, data in frames:
                    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
                    if image is None:
                        continue
                    if image.shape[1::-1] != size:
                        image = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
                    writer.write(image)
            finally:
                writer.release()
            with open(path, 'rb') as stream:
                return stream.read()
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
