"""The スクリプト folder: one folder per script, its images in 画像, shared ones in 共通/画像, Template last."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'SerialController')]

import Paths  # noqa: E402
import script_files  # noqa: E402

SCRIPT = '''from Commands.PythonCommandBase import ImageProcPythonCommand


class Entei(ImageProcPythonCommand):
    NAME = 'エンテイ厳選'

    def do(self):
        pass
'''


class ScriptFolderTest(unittest.TestCase):
    def setUp(self):
        self.previous = os.getcwd()
        self.folder = Path(tempfile.mkdtemp())
        os.chdir(self.folder)
        sys.path.insert(0, str(self.folder))
        self.addCleanup(self.restore)
        script = self.folder / 'スクリプト' / 'BDSP' / 'エンテイ'
        for folder in (script / '画像', self.folder / 'スクリプト' / 'BDSP' / '画像', self.folder / 'スクリプト' / '共通' / '画像',
                       self.folder / 'Template', self.folder / 'Commands' / 'PythonCommands' / 'Old'):
            folder.mkdir(parents=True)
        (script / 'エンテイ.py').write_text(SCRIPT, encoding='utf-8')
        (self.folder / 'Commands' / 'PythonCommands' / 'Old' / 'old.py').write_text(SCRIPT.replace('エンテイ厳選', '古い'), encoding='utf-8')

    def restore(self):
        os.chdir(self.previous)
        sys.path.remove(str(self.folder))
        for name in [n for n in sys.modules if n.startswith(('スクリプト', 'Commands.PythonCommands.Old'))]:
            del sys.modules[name]

    def image(self, relative):
        path = self.folder / relative
        path.write_bytes(b'png')
        return path

    def test_images_are_looked_for_from_the_script_outwards(self):
        importlib.invalidate_caches()
        module = importlib.import_module('スクリプト.BDSP.エンテイ.エンテイ')
        name = module.__name__
        found = lambda: Path(Paths.find_image('x.png', name)).resolve()  # noqa: E731
        self.image('Template/x.png')
        self.assertEqual(found(), (self.folder / 'Template' / 'x.png').resolve())
        for place in ('スクリプト/共通/画像', 'スクリプト/BDSP/画像', 'スクリプト/BDSP/エンテイ', 'スクリプト/BDSP/エンテイ/画像'):
            expected = self.image(f'{place}/x.png').resolve()
            self.assertEqual(found(), expected)
        # A name that is nowhere points at the script's own 画像, so the error says where to put it.
        self.assertEqual(Path(Paths.find_image('none.png', name)).resolve(),
                         (self.folder / 'スクリプト' / 'BDSP' / 'エンテイ' / '画像' / 'none.png').resolve())
        self.assertEqual(Paths.find_image('none.png', 'Commands.PythonCommands.Old.old'), os.path.join(Paths.TEMPLATE, 'none.png'))
        # A script outside スクリプト (the samples) uses 共通 and Template only.
        self.assertEqual(Paths.image_folders('Commands.PythonCommands.Old.old')[0],
                         os.path.join(os.path.realpath('スクリプト'), '共通', '画像'))

    def test_both_folders_are_loaded_with_their_own_names(self):
        from CommandLoader import CommandLoader
        from Commands.PythonCommandBase import PythonCommand
        names = sorted(c.NAME for c in CommandLoader([os.path.join('Commands', 'PythonCommands'), 'スクリプト'], PythonCommand).load())
        self.assertEqual(names, ['エンテイ厳選 (BDSP/エンテイ)', '古い (Old/old)'])

    def test_script_files_use_スクリプト_unless_named_otherwise(self):
        self.assertEqual([f['path'] for f in script_files.list_files()],
                         ['BDSP/エンテイ/エンテイ.py', 'Commands/PythonCommands/Old/old.py'])
        self.assertEqual(script_files.module_name('BDSP/エンテイ/エンテイ.py'), 'スクリプト.BDSP.エンテイ.エンテイ')
        self.assertEqual(script_files.module_name('スクリプト/BDSP/エンテイ/エンテイ.py'), 'スクリプト.BDSP.エンテイ.エンテイ')
        self.assertEqual(script_files.module_name('Commands/PythonCommands/Old/old.py'), 'Commands.PythonCommands.Old.old')
        self.assertIn('古い', script_files.read('Commands/PythonCommands/Old/old.py'))
        with self.assertRaises(ValueError):
            script_files.resolve('../app.py')
        self.assertEqual(script_files.image_path('スクリプト/共通/画像/a.png'),
                         os.path.realpath('スクリプト/共通/画像/a.png'))
        with self.assertRaises(ValueError):
            script_files.image_path('スクリプト/../app.png')
        self.image('スクリプト/BDSP/エンテイ/画像/y.png')
        self.assertIn('スクリプト/BDSP/エンテイ/画像/y.png', script_files.image_names())


if __name__ == '__main__':
    unittest.main()
