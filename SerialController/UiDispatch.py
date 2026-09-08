"""MIT. Bounded, nonblocking dispatch from worker threads to the Tk thread."""
import functools
import logging
import queue
import threading
import time

_current = None


class Dispatcher:
    def __init__(self, root):
        global _current
        self.root = root
        self.owner = threading.get_ident()
        self.pending = queue.Queue(maxsize=2048)
        self.critical = queue.SimpleQueue()
        self.closed = False
        self.dropped = 0
        _current = self
        root.after(15, self.drain)

    def post(self, function, *args, **kwargs):
        if self.closed:
            return False
        try:
            self.pending.put_nowait((function, args, kwargs))
            return True
        except queue.Full:
            self.dropped += 1
            return False

    def drain(self):
        if self.closed:
            return
        deadline = time.monotonic() + .008
        while time.monotonic() < deadline:
            try:
                try:
                    function, args, kwargs = self.critical.get_nowait()
                except queue.Empty:
                    function, args, kwargs = self.pending.get_nowait()
            except queue.Empty:
                break
            try:
                function(*args, **kwargs)
            except Exception:
                logging.getLogger(__name__).exception('画面更新に失敗しました')
        if self.dropped:
            logging.getLogger(__name__).warning('画面更新の過負荷: %s 件を省略', self.dropped)
            self.dropped = 0
        self.root.after(15, self.drain)

    def close(self):
        self.closed = True


def on_ui(function):
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        dispatcher = _current
        if dispatcher is None or threading.get_ident() == dispatcher.owner:
            return function(*args, **kwargs)
        if not dispatcher.closed:
            dispatcher.critical.put((function, args, kwargs))
    return wrapper


def on_ui_log(function):
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        dispatcher = _current
        if dispatcher is None or threading.get_ident() == dispatcher.owner:
            return function(*args, **kwargs)
        dispatcher.post(function, *args, **kwargs)
    return wrapper


def trim_log(widget):
    if int(widget.index('end-1c').split('.')[0]) > 2000:
        widget.delete('1.0', 'end-2000l')
    if widget.count('1.0', 'end', 'chars')[0] > 200000:
        widget.delete('1.0', 'end-200000c')
