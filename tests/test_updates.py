from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'SerialController')]
from plus_preferences import Preferences
from update_service import ASSET_NAME, find_release, version_key, release_page


class UpdateTests(unittest.TestCase):
    def test_default_mcp_off_and_choice_persists(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'plus-settings.json'
            preferences = Preferences(path)
            self.assertFalse(preferences.values['mcp_enabled'])
            preferences.set('mcp_enabled', True)
            self.assertTrue(Preferences(path).values['mcp_enabled'])

    def test_release_selection_excludes_drafts_older_and_missing_assets(self):
        releases = [
            {'tag_name': 'v0.1.0', 'assets': [{'name': ASSET_NAME}]},
            {'tag_name': 'v2.0.0', 'draft': True, 'assets': [{'name': ASSET_NAME}]},
            {'tag_name': 'v1.2.0', 'assets': []},
            {'tag_name': 'v1.0.0', 'assets': [{'name': ASSET_NAME}]},
            {'tag_name': 'v1.1.0-alpha.2', 'prerelease': True, 'assets': [{'name': ASSET_NAME}]},
        ]
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock()
        response.json.return_value = releases
        with patch('update_service.github_get', return_value=response):
            self.assertEqual(find_release(prereleases=False)['tag_name'], 'v1.0.0')
            self.assertEqual(find_release(prereleases=True)['tag_name'], 'v1.1.0-alpha.2')
        self.assertGreater(version_key('v1.0.0'), version_key('1.0.0-rc.2'))

    def test_download_link_uses_our_repository_not_response_url(self):
        self.assertEqual(release_page({'tag_name': 'v1.0.0', 'html_url': 'file:///bad'}),
                         'https://github.com/hinatamaxxx/Poke-Controller-Modified-Extension-Plus/releases/tag/v1.0.0')

    def test_settings_menu_opens_manual_update_screen(self):
        import tkinter as tk
        from plus_settings import SettingsWindow
        from Menubar import PokeController_Menubar
        from UiDispatch import Dispatcher
        import UiDispatch
        previous = UiDispatch._current
        root = tk.Tk()
        root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as folder:
                app = Mock(root=root, dispatcher=Dispatcher(root))
                enabled = tk.BooleanVar(root, value=False)
                settings = SettingsWindow(app, ROOT, Preferences(Path(folder) / 'prefs.json'), enabled, Mock())
                settings.show('updates')
                root.update()
                self.assertEqual(len(settings.tabs.tabs()), 3)
                self.assertEqual(len(settings.checked_libraries()), len(settings.library_table.get_children()))
                settings.select_libraries(False)
                self.assertEqual(settings.checked_libraries(), [])
                settings.select_libraries(True)
                self.assertFalse(hasattr(settings, 'apply_update'))
                app.open_plus_settings = settings.show
                menu = PokeController_Menubar(app)
                for index in range(menu.menu.index('end') + 1):
                    if menu.menu.type(index) == 'command' and menu.menu.entrycget(index, 'label') == '設定':
                        menu.menu.invoke(index)
                        break
                self.assertEqual(settings.tabs.select(), str(settings.pages['general']))
                menu.CheckUpdate()
                self.assertEqual(settings.tabs.select(), str(settings.pages['updates']))
                settings.release = {'tag_name': 'v1.0.0'}
                with patch('plus_settings.webbrowser.open') as browser:
                    settings.download_update()
                    browser.assert_called_once_with(release_page(settings.release))
                menu.destroy()
                settings.window.destroy()
                app.dispatcher.close()
        finally:
            root.destroy()
            UiDispatch._current = previous
