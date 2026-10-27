"""The hub's list of Switches and its crash handling, without starting processes."""
import collections
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'SerialController')]

import hub  # noqa: E402


class RegistryTest(unittest.TestCase):
    def test_first_switch_is_created_and_new_ones_get_the_notifications(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'main').mkdir()
            (Path(folder) / 'main' / 'discord_token.ini').write_text('[DISCORD_WEBHOOK]\nwebhook_url = x\n')
            registry = hub.Registry(folder, 'main')
            self.assertEqual([(e['profile'], e['label']) for e in registry.entries], [('main', 'Switch 1')])
            added = registry.add('  サブ   機 ')
            self.assertEqual((added['profile'], added['label']), ('main-2', 'サブ 機'))
            self.assertTrue((Path(folder) / 'main-2' / 'discord_token.ini').is_file())
            self.assertEqual(registry.add()['label'], 'Switch 3')
            registry.update(added['id'], open=False)
            again = hub.Registry(folder, 'main')
            self.assertEqual([e['open'] for e in again.entries], [True, False, True])
            self.assertEqual(again.add()['profile'], 'main-4')

    def test_broken_list_starts_over_with_the_first_switch(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'main').mkdir()
            (Path(folder) / 'main' / 'switches.json').write_text('{broken')
            self.assertEqual(len(hub.Registry(folder, 'main').entries), 1)


class CrashTest(unittest.TestCase):
    def setUp(self):
        self.hub = types.SimpleNamespace(incidents=collections.defaultdict(list), incident_id=iter(range(1, 100)).__next__,
                                         profiles=Path(tempfile.gettempdir()), closed=False)
        self.worker = hub.Worker(self.hub, {'id': 'a' * 32, 'profile': 'qa-crash', 'label': '2号機', 'open': True})
        patcher = mock.patch.object(hub.Worker, 'notify')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_restarts_with_growing_delays_then_gives_up(self):
        self.worker.summary = {'running': True, 'auto_restart': True, 'script': ['python', 'Loop'], 'command': 'Loop'}
        with mock.patch('hub.time.monotonic', return_value=1000.0):
            self.worker.crashed('テスト')
        self.assertEqual((self.worker.state, self.worker.restart_at, self.worker.resume), ('restarting', 1002.0, ['python', 'Loop']))
        incident = self.hub.incidents[self.worker.id][-1]
        self.assertEqual(incident['kind'], 'crash')
        self.assertIn('スクリプトも再開します', incident['message'])
        for n, delay in ((2, 10), (3, 30)):
            with mock.patch('hub.time.monotonic', return_value=1000.0 + n):
                self.worker.crashed('テスト')
            self.assertEqual(self.worker.restart_at, 1000.0 + n + delay)
            self.assertIsNone(self.worker.resume)  # no summary since the last crash
        with mock.patch('hub.time.monotonic', return_value=1010.0):
            self.worker.crashed('テスト')
        self.assertEqual(self.worker.state, 'crashed')
        self.assertFalse(self.hub.incidents[self.worker.id][-1]['restarted'])

    def test_old_crashes_are_forgotten(self):
        for at in (0.0, 1.0, 2.0):
            with mock.patch('hub.time.monotonic', return_value=at):
                self.worker.crashed('テスト')
        with mock.patch('hub.time.monotonic', return_value=2000.0):
            self.worker.crashed('テスト')
        self.assertEqual(self.worker.state, 'restarting')
        self.assertEqual(len(self.worker.crashes), 1)

    def test_no_resume_without_auto_restart(self):
        self.worker.summary = {'running': True, 'auto_restart': False, 'script': ['python', 'Loop']}
        self.worker.crashed('テスト')
        self.assertIsNone(self.worker.resume)
        self.assertNotIn('スクリプトも再開します', self.hub.incidents[self.worker.id][-1]['message'])


if __name__ == '__main__':
    unittest.main()
