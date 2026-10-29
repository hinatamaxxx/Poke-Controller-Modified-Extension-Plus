"""Regression tests use virtual devices only; never send physical controller input."""
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'SerialController')]


class StabilityTests(unittest.TestCase):
    def test_log_flood_cannot_drop_completion(self):
        import UiDispatch
        root = Mock()
        old = UiDispatch._current
        dispatcher = UiDispatch.Dispatcher(root)
        called = []
        @UiDispatch.on_ui
        def completed():
            called.append(threading.get_ident())
        try:
            for _ in range(3000):
                dispatcher.post(lambda: None)
            worker = threading.Thread(target=completed)
            worker.start()
            worker.join(1)
            dispatcher.drain()
            self.assertEqual(called, [threading.get_ident()])
            self.assertLessEqual(dispatcher.pending.qsize(), 2048)
        finally:
            dispatcher.close()
            UiDispatch._current = old


if __name__ == '__main__':
    unittest.main()
