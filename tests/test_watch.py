"""Watcher incidents, script drafts from recordings, and script file checks, without hardware."""
import json
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'SerialController')]

import script_files  # noqa: E402
from recorder import Recorder  # noqa: E402
from watch import Watch  # noqa: E402


class FakeCore:
    def __init__(self):
        self.lock = threading.RLock()
        self.running = False
        self.demo = False
        self.exit_requested = False
        self.dialogs = types.SimpleNamespace(current=lambda: [])
        self.profile = self.label = 'test'
        self.recorder = types.SimpleNamespace(root=os.path.join(os.getcwd(), 'Captures', 'recordings'))
        self.cur_command = None
        self.ser = types.SimpleNamespace(last_error='')
        self.camera = types.SimpleNamespace(image_bgr=np.zeros((72, 128, 3), np.uint8))
        self.live = True
        self.records = []
        self.started = []
        self.assist = types.SimpleNamespace(record=lambda source, text: self.records.append(text))

    def camera_live(self):
        return self.live

    def notification_settings(self):
        return {'discord_webhook_set': False, 'line_token_set': False}

    def script_alive(self):
        return False

    def stop_script(self):
        self.running = False

    def start_script(self, kind, name, restart=False):
        self.started.append((kind, name, restart))


class WatchTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.dir.name)
        self.core = FakeCore()
        self.watch = Watch(self.core, self.dir.name)
        self.watch.settings['notify'] = False

    def tearDown(self):
        os.chdir(self.cwd)
        self.dir.cleanup()

    def run_script(self):
        self.core.running = True
        self.watch.script_started('python', 'Loop')

    def end_script(self, error=None):
        self.core.cur_command = types.SimpleNamespace(last_error=error)
        self.core.running = False
        self.watch.tick()

    def test_error_is_reported_with_screen(self):
        self.run_script()
        self.end_script(ValueError('boom'))
        incident = self.watch.since(0)[-1]
        self.assertEqual(incident['kind'], 'error')
        self.assertIn('boom', incident['detail'])
        self.assertTrue(os.path.isfile(incident['image']))

    def test_incident_keeps_the_last_seconds_of_video(self):
        self.run_script()
        for n in range(3):
            self.watch.history._next = 0
            self.core.camera.image_bgr = np.full((72, 128, 3), n * 50, np.uint8)
            self.watch.tick()
        self.end_script(ValueError('boom'))
        clip = self.watch.since(0)[-1]['clip']
        recorder = Recorder(self.core)
        self.assertEqual(recorder.list()[0]['id'], clip)
        self.assertEqual(recorder.list()[0]['frames'], 3)
        image, _ = recorder.overview(clip)
        self.assertEqual(image[:2], bytes([0xff, 0xd8]))

    def test_user_stop_is_not_an_incident(self):
        self.run_script()
        self.watch.expect_stop()
        self.end_script()
        self.assertEqual(self.watch.since(0), [])

    def test_normal_end_is_finished(self):
        self.run_script()
        self.end_script()
        self.assertEqual([i['kind'] for i in self.watch.since(0)], ['finished'])

    def test_frozen_picture(self):
        self.watch.settings['freeze_seconds'] = 30
        self.run_script()
        clock = [1000.0]
        with mock.patch('watch.time.monotonic', lambda: clock[0]):
            for _ in range(40):
                self.watch.tick()
                clock[0] += 1
        self.assertEqual([i['kind'] for i in self.watch.since(0)], ['frozen'])
        with mock.patch('watch.time.monotonic', lambda: clock[0]):
            self.watch.tick()  # reported once until the picture changes
        self.assertEqual(len(self.watch.since(0)), 1)

    def test_moving_picture_is_not_frozen(self):
        self.watch.settings['freeze_seconds'] = 30
        self.run_script()
        clock = [1000.0]
        with mock.patch('watch.time.monotonic', lambda: clock[0]):
            for n in range(40):
                self.core.camera.image_bgr = np.full((72, 128, 3), (n * 37) % 255, np.uint8)
                self.watch.tick()
                clock[0] += 1
        self.assertEqual(self.watch.since(0), [])

    def test_paused_or_waiting_for_dialog_is_not_frozen(self):
        self.watch.settings['freeze_seconds'] = 30
        self.run_script()
        self.core.dialogs = types.SimpleNamespace(current=lambda: [{'id': 1}])
        clock = [1000.0]
        with mock.patch('watch.time.monotonic', lambda: clock[0]):
            for _ in range(40):
                self.watch.tick()
                clock[0] += 1
        self.assertEqual(self.watch.since(0), [])

    def test_restart_skipped_after_user_stop(self):
        self.watch.settings.update(auto_restart=True, restart_limit=3)
        self.run_script()
        with mock.patch('watch.time.sleep', side_effect=lambda s: self.watch.expect_stop()):
            self.watch._restart('error', ('python', 'Loop'))
        self.assertEqual(self.core.started, [])

    def test_camera_lost_during_script(self):
        self.run_script()
        self.watch.tick()
        self.core.live = False
        self.watch._next_check = 0
        self.watch.tick()
        self.assertEqual([i['kind'] for i in self.watch.since(0)], ['camera'])

    def test_auto_restart_respects_limit(self):
        self.watch.settings.update(auto_restart=True, restart_limit=1)
        with mock.patch('watch.time.sleep'):
            self.run_script()
            self.end_script(RuntimeError('x'))
            deadline = time.time() + 5
            while not self.core.started and time.time() < deadline:
                time.sleep(.05)
            self.assertEqual(self.core.started, [('python', 'Loop', True)])
            self.core.running = True
            self.watch.script_started('python', 'Loop', restart=True)
            self.end_script(RuntimeError('y'))
        self.assertFalse(self.watch.since(0)[-1]['restarted'])

    def test_settings_saved_and_validated(self):
        self.watch.configure({'freeze_seconds': 60, 'auto_restart': True})
        saved = json.loads(Path(self.dir.name, 'watch.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['freeze_seconds'], 60)
        self.assertEqual(Watch(self.core, self.dir.name).settings['auto_restart'], True)
        with self.assertRaises(ValueError):
            self.watch.configure({'freeze_seconds': 5})
        with self.assertRaises(ValueError):
            self.watch.configure({'unknown': 1})


class DraftTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.dir.name)
        self.recorder = Recorder(FakeCore())
        folder = Path(self.recorder.root, 'r1')
        folder.mkdir(parents=True)
        inputs = [
            {'t': 1.0, 'action': 'hold', 'buttons': ['A'], 'code': ['Button.A']},
            {'t': 1.2, 'action': 'holdEnd', 'buttons': ['A'], 'code': ['Button.A']},
            {'t': 9.2, 'action': 'check', 'template': 'battle.png', 'threshold': .9, 'found': True, 'similarity': .97},
            {'t': 9.5, 'action': 'stick', 'sticks': {'L': [40, 200], 'R': [128, 128]}},
            {'t': 10.0, 'action': 'stick', 'sticks': {'L': [128, 128], 'R': [128, 128]}},
            {'t': 10.5, 'action': 'hold', 'buttons': ['HOME'], 'code': ['Button.HOME']},
            {'t': 10.6, 'action': 'neutral'},
        ]
        (folder / 'timeline.json').write_text(json.dumps({'id': 'r1', 'frames': [{'t': 0, 'file': 'x.jpg'}], 'inputs': inputs}))

    def tearDown(self):
        os.chdir(self.cwd)
        self.dir.cleanup()

    def test_draft_compiles_and_keeps_timing(self):
        code = self.recorder.draft_script('r1', 'Reset', loop=True)
        compile(code, 'draft.py', 'exec')
        self.assertIn("NAME = 'Reset'", code)
        self.assertIn('self.press(Button.A, duration=0.20, wait=3.00)  # 試したときは 8.0秒', code)
        self.assertIn("if self.isContainTemplate('battle.png', threshold=0.9):", code)
        # Logged in the send format (y downward); Direction counts y upward.
        self.assertIn('self.hold(Direction(Stick.LEFT, (40, 55)))', code)
        self.assertIn('self.holdEnd(Direction(Stick.LEFT, (40, 55)))', code)
        self.assertIn('self.holdEnd([Button.HOME])', code)
        self.assertIn('while True:', code)

    def test_draft_without_loop_and_unknown_recording(self):
        code = self.recorder.draft_script('r1', 'Once', loop=False, end=2)
        compile(code, 'draft.py', 'exec')
        self.assertNotIn('while True', code)
        with self.assertRaises(ValueError):
            self.recorder.draft_script('../r1', 'X')


class ScriptFilesTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.dir.name)

    def tearDown(self):
        os.chdir(self.cwd)
        self.dir.cleanup()

    def test_write_backup_and_limits(self):
        self.assertEqual(script_files.write('A/b.py', 'x = 1\n'), '')
        with self.assertRaises(ValueError):
            script_files.write('A/b.py', 'x = 2\n')
        backup = script_files.write('A/b.py', 'x = 2\n', overwrite=True)
        self.assertTrue(os.path.isfile(backup))
        self.assertEqual(script_files.read('A/b.py'), 'x = 2\n')
        self.assertEqual(script_files.module_name('A/b.py'), 'Commands.PythonCommands.A.b')
        for bad in ('../x.py', '..\\..\\x.py', 'A/b.txt'):
            with self.assertRaises(ValueError):
                script_files.write(bad, 'x = 1\n')
        with self.assertRaises(ValueError):
            script_files.write('A/c.py', 'def x(:\n')

    def test_save_template(self):
        frame = np.zeros((100, 200, 3), np.uint8)
        self.assertEqual(script_files.save_template(frame, 'ボタン.png', 10, 10, 20, 20), 'ボタン.png')
        with self.assertRaises(ValueError):
            script_files.save_template(frame, 'out.png', 190, 10, 20, 20)
        with self.assertRaises(ValueError):
            script_files.save_template(frame, '../x.png', 10, 10, 20, 20)


if __name__ == '__main__':
    unittest.main()
