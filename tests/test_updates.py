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

