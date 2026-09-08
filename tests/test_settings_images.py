import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'SerialController')]
import safe_settings
from plus_preferences import Preferences


class SafeSettingsTests(unittest.TestCase):
    def test_backup_keeps_previous_distinct_value(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.ini'
            for data in ('first', 'second', 'second'):
                safe_settings.write_text(path, data)
            self.assertEqual(path.read_text(), 'second')
            self.assertEqual(path.with_name('settings.ini.bak').read_text(), 'first')

    def test_failed_replace_preserves_original_and_removes_temp(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.ini'
            safe_settings.write_text(path, 'original')
            replace = safe_settings.os.replace
            def fail_target(source, target):
                if Path(target) == path:
                    raise PermissionError('locked')
                return replace(source, target)
            with patch('safe_settings.os.replace', side_effect=fail_target):
                with self.assertRaises(PermissionError):
                    safe_settings.write_text(path, 'changed')
            self.assertEqual(path.read_text(), 'original')
            self.assertEqual(path.with_name('settings.ini.bak').read_text(), 'original')
            self.assertFalse(list(Path(folder).glob('*.tmp')))

    def test_json_recovery_keeps_corrupt_copy_and_valid_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'plus-settings.json'
            preferences = Preferences(path)
            preferences.set('mcp_enabled', True)
            preferences.set('mcp_enabled', False)
            backup = path.with_name(path.name + '.bak').read_bytes()
            path.write_text('{broken')
            self.assertTrue(Preferences(path).values['mcp_enabled'])
            self.assertEqual(path.with_name(path.name + '.bak').read_bytes(), backup)
            self.assertEqual(next(Path(folder).glob('*.corrupt-*')).read_text(), '{broken')

    def test_unrecoverable_settings_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'plus-settings.json'
            path.write_text('{broken')
            with self.assertRaisesRegex(ValueError, '元のファイルは変更していません'):
                Preferences(path)
            self.assertEqual(path.read_text(), '{broken')

    def test_main_settings_recover_and_preserve_new_keymap(self):
        import tkinter as tk
        from Settings import GuiSettings
        root = tk.Tk()
        root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as folder, patch.object(GuiSettings, 'SETTING_PATH', str(Path(folder) / 'settings.ini')):
                settings = GuiSettings()
                settings.fps.set('60')
                settings.save()
                changed = safe_settings.read_config(settings.SETTING_PATH)
                changed['KeyMap-Button']['Button.A'] = 'q'
                safe_settings.write_config(settings.SETTING_PATH, changed)
                settings.fps.set('30')
                settings.save()
                self.assertEqual(safe_settings.read_config(settings.SETTING_PATH)['KeyMap-Button']['Button.A'], 'q')
                Path(settings.SETTING_PATH).write_text('[broken')
                recovered = GuiSettings()
                self.assertEqual(recovered.fps.get(), '60')
                self.assertEqual(recovered.setting['KeyMap-Button']['Button.A'], 'q')
        finally:
            root.destroy()


class ImageErrorTests(unittest.TestCase):
    def test_missing_and_invalid_images_name_the_file(self):
        from ImageProcessing import getImage
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '見本画像.png'
            with self.assertRaisesRegex(FileNotFoundError, '見本画像.png'):
                getImage(path)
            path.write_bytes(b'not an image')
            with self.assertRaisesRegex(ValueError, '画像として読み込めません'):
                getImage(path)

    def test_japanese_path_and_valid_template_match(self):
        import cv2
        import numpy as np
        from ImageProcessing import getImage, ImageProcessing
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '見本画像.png'
            template = np.random.default_rng(42).integers(0, 255, (10, 12, 3), dtype=np.uint8)
            path.write_bytes(cv2.imencode('.png', template)[1].tobytes())
            decoded = getImage(path)
            np.testing.assert_array_equal(decoded, template)
            scene = np.zeros((40, 50, 3), dtype=np.uint8)
            scene[7:17, 5:17] = decoded
            matched = ImageProcessing().isContainTemplate(scene, decoded)
            self.assertTrue(matched[0])
            self.assertEqual(matched[1], (5, 7))

    def test_missing_frame_bad_crop_oversized_template_and_bad_mask(self):
        import numpy as np
        from ImageProcessing import doPreprocessImage, ImageProcessing
        frame = np.zeros((20, 20, 3), dtype=np.uint8)
        with self.assertRaisesRegex(ValueError, 'キャプチャ'):
            doPreprocessImage(None)
        with self.assertRaisesRegex(ValueError, '切り抜き'):
            doPreprocessImage(frame, crop=[100, 120, 100, 120])
        with self.assertRaisesRegex(ValueError, 'より大きい'):
            ImageProcessing().doTemplateMatch(frame, np.zeros((30, 30, 3), np.uint8))
        with self.assertRaisesRegex(ValueError, 'マスク'):
            ImageProcessing().doTemplateMatch(frame, frame, np.zeros((2, 2), np.uint8))
