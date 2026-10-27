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
