from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import acquire_profile


class ProfileSlotsTests(unittest.TestCase):
    def test_slots_are_isolated_and_reused_with_saved_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            locks = []
            try:
                first, p1, lock = acquire_profile(folder, 'default')
                locks.append(lock)
                second, p2, lock = acquire_profile(folder, 'default')
                locks.append(lock)
                self.assertEqual((first, second), ('default', 'default-2'))
                (p2 / 'settings.ini').write_text('saved second window')
                third, _, lock = acquire_profile(folder, 'default')
                locks.append(lock)
                self.assertEqual(third, 'default-3')
                locks[1].close()
                reused, path, lock = acquire_profile(folder, 'default')
                locks.append(lock)
                self.assertEqual(reused, second)
                self.assertEqual((path / 'settings.ini').read_text(), 'saved second window')
                self.assertFalse((p1 / 'settings.ini').exists())
            finally:
                for lock in locks:
                    lock.close()
