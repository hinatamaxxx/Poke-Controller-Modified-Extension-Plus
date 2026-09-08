from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from library_update import requirements, runtime_path, reset_libraries, update_libraries


class LibraryTests(unittest.TestCase):
    def test_unchecked_versions_are_pinned(self):
        items = [{'name': 'numpy', 'version': '2.0'}, {'name': 'Pillow', 'version': '12.0'}]
        self.assertEqual(requirements(items, ['NUMPY']), ['numpy', 'Pillow==12.0'])
        self.assertEqual(requirements(items, ['numpy', 'pillow']), ['numpy', 'Pillow'])
        with self.assertRaises(ValueError): requirements(items, ['unknown'])

    def test_reject_external_runtime_and_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'runtime-choice.txt').write_text('../external')
            with self.assertRaises(ValueError): runtime_path(root)
            reset_libraries(root)
            self.assertEqual(runtime_path(root), root / 'runtime-python')

    def test_failure_preserves_pointer_success_switches_after_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / 'runtime-python'
            runtime.mkdir()
            (runtime / 'python.exe').touch()
            items = [{'name': 'numpy', 'version': '2.0'}]
            with patch('library_update.inventory', return_value=items), patch('library_update.run', side_effect=RuntimeError('offline')):
                with self.assertRaises(RuntimeError): update_libraries(root, ['numpy'])
                self.assertFalse((root / 'runtime-choice.txt').exists())
            with patch('library_update.inventory', return_value=items), patch('library_update.run') as run:
                update_libraries(root, ['numpy'])
                self.assertEqual(run.call_count, 3)
                self.assertTrue(runtime_path(root).is_relative_to(root / '.runtime-updates'))
                self.assertTrue((runtime / 'python.exe').exists())
