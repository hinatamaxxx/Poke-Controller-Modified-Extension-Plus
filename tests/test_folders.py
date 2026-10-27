"""Choosing the work folder and the capture folder (settings: フォルダー)."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'SerialController')]

import app_paths  # noqa: E402


class FolderChoiceTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        default = self.folder / 'default'
        (default / 'Commands' / 'PythonCommands').mkdir(parents=True)
        (default / 'Commands' / 'PythonCommands' / 'Mine.py').write_text('# mine', encoding='utf-8')
        patches = [mock.patch.object(app_paths, 'FOLDER_CHOICES', self.folder / 'folders.json'),
                   mock.patch.object(app_paths, 'DEFAULT_WORKSPACE', default)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(app_paths.apply_folder_choices)
        app_paths.apply_folder_choices()

    def test_a_new_empty_work_folder_gets_the_current_contents(self):
        target = self.folder / 'new work'
        app_paths.choose_folder('workspace', str(target))
        self.assertEqual(app_paths.WORKSPACE, target.resolve())
        self.assertTrue((target / 'Commands' / 'PythonCommands' / 'Mine.py').is_file())
        self.assertEqual(app_paths.CAPTURES, target.resolve() / 'Captures')  # captures follow the work folder

    def test_captures_can_go_elsewhere_and_back(self):
        target = self.folder / 'shots'
        app_paths.choose_folder('captures', str(target))
        self.assertEqual(app_paths.FOLDERS['captures'], target.resolve())
        self.assertEqual(app_paths.captures_dir(), str(target.resolve()))
        app_paths.choose_folder('captures', None)
        self.assertEqual(app_paths.FOLDERS['captures'], app_paths.WORKSPACE / 'Captures')
        self.assertEqual(app_paths.captures_dir(), os.path.join(os.getcwd(), 'Captures'))

    def test_only_the_two_folders_can_be_chosen(self):
        with self.assertRaises(ValueError):
            app_paths.choose_folder('settings', str(self.folder))


if __name__ == '__main__':
    unittest.main()
