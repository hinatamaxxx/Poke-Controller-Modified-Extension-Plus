import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'SerialController')]
import safe_settings
import plus_runtime

plus_runtime.install()
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
            preferences.set('auto_update', False)
            preferences.set('auto_update', True)
            backup = path.with_name(path.name + '.bak').read_bytes()
            path.write_text('{broken')
            self.assertFalse(Preferences(path).values['auto_update'])
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
        from plus_settings import HeadlessSettings
        with tempfile.TemporaryDirectory() as folder, patch.object(HeadlessSettings, 'SETTING_PATH', str(Path(folder) / 'settings.ini')):
            settings = HeadlessSettings()
            settings.fps.set('60')
            settings.camera_path = 'persistent-device-id'
            settings.camera_name = 'USB Video'
            settings.save()
            self.assertEqual(HeadlessSettings().camera_path, 'persistent-device-id')
            changed = safe_settings.read_config(settings.SETTING_PATH)
            changed['KeyMap-Button']['Button.A'] = 'q'
            safe_settings.write_config(settings.SETTING_PATH, changed)
            settings.fps.set('30')
            settings.save()
            self.assertEqual(safe_settings.read_config(settings.SETTING_PATH)['KeyMap-Button']['Button.A'], 'q')
            Path(settings.SETTING_PATH).write_text('[broken')
            recovered = HeadlessSettings()
            self.assertEqual(recovered.fps.get(), '60')
            self.assertEqual(recovered.setting['KeyMap-Button']['Button.A'], 'q')

    def test_settings_of_an_older_version_keep_this_apps_values(self):
        # Before the fork origin's settings were adopted, the camera and the Discord switches sat in other sections.
        from plus_settings import HeadlessSettings
        with tempfile.TemporaryDirectory() as folder, patch.object(HeadlessSettings, 'SETTING_PATH', str(Path(folder) / 'settings.ini')):
            HeadlessSettings()
            config = safe_settings.read_config(HeadlessSettings.SETTING_PATH)
            config.remove_section('PokeControllerPlus')
            config['General Setting']['camera_path'] = 'old-device'
            config['Notification']['is_discord_clip'] = 'True'
            safe_settings.write_config(HeadlessSettings.SETTING_PATH, config)
            settings = HeadlessSettings()
            self.assertEqual(settings.camera_path, 'old-device')
            self.assertTrue(settings.is_discord_clip.get())
            settings.save()
            again = HeadlessSettings()
            self.assertEqual(again.camera_path, 'old-device')
            self.assertTrue(again.is_discord_clip.get())

    def test_keymap_reset_restores_defaults(self):
        import threading
        import core
        from plus_settings import DEFAULT_KEYMAPS, HeadlessSettings
        with tempfile.TemporaryDirectory() as folder, patch.object(HeadlessSettings, 'SETTING_PATH', str(Path(folder) / 'settings.ini')):
            owner = type('Owner', (), {'KEY_NAMES': core.Core.KEY_NAMES, 'HAT_NAMES': core.Core.HAT_NAMES,
                                       'STICK_NAMES': core.Core.STICK_NAMES})()
            owner.settings, owner.lock = HeadlessSettings(), threading.RLock()
            core.Core.set_keymap(owner, {'A': 'z', 'LS_UP': 'i'})
            self.assertEqual(core.Core.keymap(owner)['z'], 'A')
            core.Core.reset_keymap(owner)
            config = safe_settings.read_config(owner.settings.SETTING_PATH)
            for section, values in DEFAULT_KEYMAPS.items():
                self.assertEqual(dict(config[section]), values)
            self.assertEqual(core.Core.keymap(owner)['a'], 'A')
            self.assertNotIn('i', core.Core.keymap(owner))


class ImageErrorTests(unittest.TestCase):
    def test_missing_and_invalid_images_name_the_file(self):
        # The fork origin: a missing or unreadable image is None, and the file is named in the output.
        import contextlib
        import io
        from ImageProcessing import getImage
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '見本画像.png'
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertIsNone(getImage(str(path)))
            self.assertIn('見本画像.png', output.getvalue())
            path.write_bytes(b'not an image')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(getImage(str(path)))

    def test_japanese_path_and_valid_template_match(self):
        import cv2
        import numpy as np
        from ImageProcessing import getImage, ImageProcessing
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '見本画像.png'
            template = np.random.default_rng(42).integers(0, 255, (10, 12, 3), dtype=np.uint8)
            path.write_bytes(cv2.imencode('.png', template)[1].tobytes())
            decoded = getImage(str(path))
            np.testing.assert_array_equal(decoded, template)
            scene = np.zeros((40, 50, 3), dtype=np.uint8)
            scene[7:17, 5:17] = decoded
            matched = ImageProcessing().isContainTemplate(scene, decoded)
            self.assertTrue(matched[0])
            self.assertEqual(matched[1], (5, 7))
