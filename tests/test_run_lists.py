"""Run lists and the schedule: the fork origin's services, saved and checked through the app's Core."""
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'SerialController')]
import plus_runtime  # noqa: E402

plus_runtime.install()


class RunListTest(unittest.TestCase):
    def setUp(self):
        from services.settings_store import AppSettings
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = patch.object(AppSettings, 'SETTING_PATH', str(Path(folder.name) / 'settings.ini'))
        patcher.start()
        self.addCleanup(patcher.stop)
        import core
        self.core = core
        self.owner = Mock(lock=threading.RLock())
        self.owner.find_entry.side_effect = lambda name, kind: object() if name == 'A (x/a)' else None
        self.owner.run_loader.load.return_value = []
        self.owner.py_entries = []
        self.owner._reload_run_lists = lambda: None

    def save(self, data, original=''):
        return self.core.Core.save_run_list(self.owner, data, original)

    def test_save_rename_and_reject(self):
        from services import run_list
        item = {'type': 'Python', 'name': 'A (x/a)', 'repeat': 2, 'limit_minutes': None}
        self.save({'name': '朝', 'items': [item], 'interval_seconds': 1, 'on_error': 'stop', 'loops': 1})
        self.assertEqual([r.name for r in run_list.load_lists()], ['朝'])
        self.save({'name': '夜', 'items': [item], 'interval_seconds': 1, 'on_error': 'next', 'loops': 0}, '朝')
        lists = run_list.load_lists()
        self.assertEqual([(r.name, r.on_error, r.loops) for r in lists], [('夜', 'next', 0)])
        with self.assertRaisesRegex(ValueError, '見つかりません'):
            self.save({'name': '別', 'items': [dict(item, name='B (x/b)')], 'interval_seconds': 1, 'on_error': 'stop', 'loops': 1})
        with self.assertRaisesRegex(ValueError, '名前'):
            self.save({'name': ' ', 'items': [item], 'interval_seconds': 1, 'on_error': 'stop', 'loops': 1})
        with self.assertRaisesRegex(ValueError, '制限時間'):
            self.save({'name': 'MCU', 'items': [{'type': 'Mcu', 'name': 'A (x/a)', 'repeat': 1, 'limit_minutes': None}],
                       'interval_seconds': 1, 'on_error': 'stop', 'loops': 1})

    def test_schedule_start_needs_a_script(self):
        from services.run_schedule import RunSchedule
        self.owner.schedule = RunSchedule(Mock(return_value=True), Mock(), lambda: False, lambda text: None)
        with self.assertRaisesRegex(ValueError, 'スクリプト'):
            self.core.Core.set_schedule(self.owner, {'start': {'time': '23:30', 'kind': 'python', 'name': 'none'}})
        self.core.Core.set_schedule(self.owner, {'start': {'time': '23:30', 'kind': 'python', 'name': 'A (x/a)'}})
        self.assertEqual(self.owner.schedule.start_target, ('Python', 'A (x/a)'))
        self.core.Core.set_schedule(self.owner, {'cancel': 'start'})
        self.assertIsNone(self.owner.schedule.start_at)


if __name__ == '__main__':
    unittest.main()
