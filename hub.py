"""The hub: one app, one page and one MCP endpoint for every Switch, each Switch in its own worker process. MIT.

Like tabs in Chrome, a crash or a hang in one Switch's process does not stop the others. The hub notices, saves the
last seconds of video, tells the user (the page, Discord/LINE, Windows), and starts that Switch again; a script that
was running is resumed when the Switch's watcher allows restarts. The page and Claude use the same list of Switches.
"""
import collections
import configparser
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid

import app_paths
from local_control import ApiServer

RESTART_DELAYS = (2, 10, 30)  # seconds before starting a crashed Switch again
CRASH_WINDOW, CRASH_LIMIT = 600, 4  # this many crashes within the window: stop restarting and ask the user
HANG_SECONDS = 45  # no answer this long: the process is stuck, so it is ended and started again
START_SECONDS = 120
COPIED = ('discord_token.ini', 'line_token.ini', 'watch.json')  # a new Switch gets the first one's notifications
APP_ACTIONS = ('app_options', 'update_now', 'open_folder', 'quit')
STATES = {'starting': '起動しています', 'restarting': '再起動を待っています', 'crashed': '停止しました', 'stopped': '閉じています'}


class Registry:
    """The Switches and their names, kept in the first Switch's settings folder."""

    def __init__(self, profiles, primary):
        self.profiles, self.primary = Path(profiles), primary
        self.path = self.profiles / primary / 'switches.json'
        self.lock = threading.Lock()
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            self.entries = [e for e in data['switches'] if isinstance(e, dict) and {'id', 'profile', 'label'} <= set(e)]
        except (OSError, ValueError, KeyError, TypeError):
            self.entries = []
        if not any(e['profile'] == primary for e in self.entries):
            self.entries.insert(0, {'id': uuid.uuid4().hex, 'profile': primary, 'label': 'Switch 1', 'open': True})
        for entry in self.entries:
            entry['open'] = bool(entry.get('open', True))
        if not any(e['open'] for e in self.entries):  # one Switch is always open
            self.entries[0]['open'] = True
        self.save()

    def save(self):
        from safe_settings import write_text
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_text(self.path, json.dumps({'switches': self.entries}, ensure_ascii=False, indent=1))

    def get(self, switch_id):
        entry = next((e for e in self.entries if e['id'] == switch_id), None)
        if entry is None:
            raise ValueError('Switch not found')
        return entry

    def add(self, label=''):
        with self.lock:
            used = {e['profile'] for e in self.entries}
            number = 2
            while f'{self.primary}-{number}' in used:
                number += 1
            profile = f'{self.primary}-{number}'
            folder = self.profiles / profile
            folder.mkdir(parents=True, exist_ok=True)
            for name in COPIED:
                source = self.profiles / self.primary / name
                if source.is_file() and not (folder / name).exists():
                    shutil.copy2(source, folder / name)
            entry = {'id': uuid.uuid4().hex, 'profile': profile, 'open': True,
                     'label': clean_label(label) or f'Switch {len(self.entries) + 1}'}
            self.entries.append(entry)
            self.save()
            return entry

    def update(self, switch_id, **values):
        with self.lock:
            self.get(switch_id).update(values)
            self.save()


def clean_label(label):
    return ' '.join(str(label or '').split())[:40]


class Worker:
    """One Switch's process: started, watched for crashes and hangs, and started again."""

    def __init__(self, hub, entry):
        self.hub, self.entry = hub, entry
        self.process = None
        self.endpoint = None
        self.state = 'stopped'
        self.summary = None
        self.error = ''
        self.crashes = collections.deque()
        self.restart_at = 0
        self.resume = None
        self.stopping = False
        self.started_at = self.last_ok = 0
        from history import FrameHistory
        self.history = FrameHistory(seconds=30, fps=2)
        self.lock = threading.RLock()
        self.thread = None

    id = property(lambda self: self.entry['id'])
    profile = property(lambda self: self.entry['profile'])
    label = property(lambda self: self.entry['label'])
    endpoint_path = property(lambda self: self.hub.workers_dir / f'worker-{self.id}.json')

    # ---- process ----
    def start(self, resume=None):
        with self.lock:
            if self.process is not None:
                return
            self.endpoint_path.unlink(missing_ok=True)
            try:
                self.hub.copy_shared_files(self)
            except OSError:
                pass
            command = [sys.executable]
            if sys.flags.ignore_environment:
                command.append('-E')
            if sys.flags.no_user_site:
                command.append('-s')
            command += [str(app_paths.PROGRAM / 'bootstrap.py'), 'app.py', '--worker', '--profile', self.profile,
                        '--session-id', self.id, '--label', self.label, '--hub-pid', str(os.getpid())]
            if self.hub.demo:
                command.append('--demo')
            if resume:
                command += ['--resume', json.dumps(resume)]
            app_paths.LOGS.mkdir(parents=True, exist_ok=True)
            with open(app_paths.LOGS / f'worker-{self.profile}.log', 'ab') as log:
                log.write(f"\n==== {time.strftime('%Y-%m-%d %H:%M:%S')} {self.label} を起動\n".encode())
                log.flush()
                self.process = subprocess.Popen(command, cwd=str(app_paths.PROGRAM), stdin=subprocess.DEVNULL,
                                                stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
            self.state, self.endpoint, self.stopping = 'starting', None, False
            self.started_at = time.monotonic()
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self.watch, daemon=True)
                self.thread.start()

    def kill(self):
        process = self.process
        if process is not None and process.poll() is None:
            # The tree, so the real Python under a virtual environment's launcher ends too.
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)

    def stop(self, wait=10):
        """End the process cleanly (scripts stopped, buttons released, settings saved)."""
        with self.lock:
            self.stopping = True
            process = self.process
            self.state = 'stopped'
        if process is None:
            return
        try:
            self.call('command', {'action': 'quit'}, timeout=5)
        except Exception:
            pass
        try:
            process.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            self.kill()
        deadline = time.monotonic() + 10
        while self.process is process and time.monotonic() < deadline:  # the watch thread takes note of the exit
            time.sleep(.1)

    def restart(self, graceful=True):
        """Start again from scratch (after closing the tab, or when the user restarts a stuck Switch)."""
        if graceful:
            self.stop(wait=5)
        with self.lock:
            if self.process is not None:
                return
            self.crashes.clear()
            self.state, self.resume, self.restart_at, self.error = 'stopped', None, 0, ''
            self.start()

    def call(self, method, params=None, timeout=18, request_id=None):
        endpoint = self.endpoint
        if endpoint is None:
            raise ValueError(f'{self.label}: {STATES.get(self.state, self.state)}')
        from controller_api import _pipe_call
        payload = {'method': method, 'params': dict(params or {}, id=self.id), 'request_id': request_id or uuid.uuid4().hex}
        result = _pipe_call(endpoint, payload, endpoint['token'], timeout)
        if not result.get('ok'):
            raise ValueError(result.get('error', 'Operation failed'))
        return result.get('result')

    # ---- supervision ----
    def watch(self):
        last_frame, next_frame = None, 0
        while not self.hub.closed:
            with self.lock:
                process = self.process
                if process is None:
                    if self.stopping or not self.entry.get('open') or self.state == 'crashed':
                        self.thread = None
                        return
                    if time.monotonic() >= self.restart_at:
                        self.start(self.resume)
                    process = self.process
            if process is None:
                time.sleep(.5)
                continue
            code = process.poll()
            if code is not None:
                with self.lock:
                    self.process, self.endpoint = None, None
                    if self.stopping:
                        self.state = 'stopped'
                        self.thread = None
                        return
                self.crashed(f'プロセスが終了しました（終了コード {code}）')
                continue
            now = time.monotonic()
            if self.endpoint is None:
                try:
                    self.endpoint = json.loads(self.endpoint_path.read_text(encoding='utf-8'))
                    self.last_ok = now
                except (OSError, ValueError):
                    if now - self.started_at > START_SECONDS:
                        self.kill()
                        process.wait()
                        with self.lock:
                            self.process = None
                        self.crashed('起動が終わりませんでした')
                    time.sleep(.5)
                    continue
            try:
                self.summary = self.call('summary', timeout=10)
                self.last_ok = now
                if self.state != 'ready':
                    self.state, self.error = 'ready', ''
                    self.resume = None
                    threading.Thread(target=self.hub.take_shared_settings, args=(self,), daemon=True).start()
                if now >= next_frame:
                    next_frame = now + 1 / self.history.fps
                    frame = self.call('frame_raw', {'small': True, 'after': last_frame}, timeout=5)
                    last_frame = frame['at']
                    if frame['jpeg']:
                        self.history.add_jpeg(frame['jpeg'])
            except Exception:
                if self.state == 'ready' and time.monotonic() - self.last_ok > HANG_SECONDS:
                    self.kill()
                    process.wait()
                    with self.lock:
                        self.process, self.endpoint = None, None
                    self.crashed(f'{HANG_SECONDS}秒以上応答しませんでした')
                    continue
            time.sleep(.5)

    def crashed(self, reason):
        now = time.monotonic()
        summary = self.summary or {}
        self.summary = None
        with self.lock:
            self.crashes.append(now)
            while self.crashes and now - self.crashes[0] > CRASH_WINDOW:
                self.crashes.popleft()
            gave_up = len(self.crashes) >= CRASH_LIMIT
            self.resume = summary.get('script') if summary.get('running') and summary.get('auto_restart') else None
            if gave_up:
                self.state = 'crashed'
            else:
                self.state = 'restarting'
                self.restart_at = now + RESTART_DELAYS[min(len(self.crashes), len(RESTART_DELAYS)) - 1]
            self.error = reason
        detail = self.log_tail()
        clip = ''
        try:
            clip = self.history.save(str(app_paths.WORKSPACE / 'Captures' / 'recordings'), f'{self.label}: {reason}')
        except OSError:
            pass
        message = f'{self.label} が止まりました: {reason}。' + (
            '何度も止まるため、自動での再起動をやめました。' if gave_up else
            '自動で起動し直します' + ('（スクリプトも再開します）。' if self.resume else '。'))
        incident = {'id': self.hub.incident_id(), 'at': time.time(), 'kind': 'crash', 'message': message, 'detail': detail,
                    'script': summary.get('command', ''), 'image': '', 'clip': clip, 'restarted': not gave_up}
        self.hub.incidents[self.id].append(incident)
        print(f'司令塔: {message} {detail}', flush=True)
        threading.Thread(target=self.notify, args=(message, detail), daemon=True).start()

    def log_tail(self):
        try:
            with open(app_paths.LOGS / f'worker-{self.profile}.log', 'rb') as stream:
                stream.seek(0, 2)
                stream.seek(max(0, stream.tell() - 4000))
                lines = stream.read().decode('utf-8', 'replace').splitlines()
            useful = [line for line in lines if line.strip() and not line.startswith('====')]
            return '\n'.join(useful[-6:])[-600:]
        except OSError:
            return ''

    def notify(self, message, detail):
        """Send to whatever this Switch has set up (its watcher's notify setting decides)."""
        folder = self.hub.profiles / self.profile
        try:
            watch = json.loads((folder / 'watch.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            watch = {}
        if not watch.get('enabled', True) or not watch.get('notify', True):
            return
        from product import NAME
        text = f'{NAME} ({self.label})\n{message}' + (f'\n{detail[-300:]}' if detail else '')
        frame = None
        if self.history.frames:
            import cv2
            import numpy as np
            frame = cv2.imdecode(np.frombuffer(self.history.frames[-1][1], np.uint8), cv2.IMREAD_COLOR)
        with self.hub.notify_lock:  # the notifiers keep their settings path on the class
            discord = read_config(folder / 'discord_token.ini')
            if str(discord['DISCORD_WEBHOOK'].get('webhook_url', '') if 'DISCORD_WEBHOOK' in discord else '').strip():
                try:
                    from DiscordNotify import Discord_Notify
                    Discord_Notify.DISCORD_SETTING_PATH = str(folder / 'discord_token.ini')
                    Discord_Notify().send_message(text, image=frame)
                except Exception as exc:
                    print(f'Discordへの通知に失敗しました: {exc}')
            line = read_config(folder / 'line_token.ini')
            if 'LINE' in line and line['LINE'].get('token', '').strip():
                try:
                    from LineNotify import Line_Notify
                    Line_Notify.LINE_TOKEN_PATH = str(folder / 'line_token.ini')
                    Line_Notify().send_message(text)
                except Exception as exc:
                    print(f'LINEへの通知に失敗しました: {exc}')
        try:
            from plyer import notification
            notification.notify(title='Poke-Controller', message=text[-250:], timeout=10)
        except Exception:
            pass

    def info(self):
        """What the tabs show."""
        summary = self.summary or {}
        return {'id': self.id, 'label': self.label, 'profile': self.profile, 'open': bool(self.entry.get('open')),
                'primary': self.profile == self.hub.registry.primary, 'state': self.state,
                'state_text': STATES.get(self.state, ''), 'error': self.error,
                'running': bool(summary.get('running')), 'paused': bool(summary.get('paused')),
                'command': summary.get('command', ''), 'camera_live': bool(summary.get('camera_live')),
                'serial_open': bool(summary.get('serial_open')), 'port': summary.get('port', ''),
                'camera_path': summary.get('camera_path', ''), 'recording': bool(summary.get('recording')),
                'dialog': bool(summary.get('dialog')), 'incident': summary.get('incident'),
                'crash': (self.hub.incidents[self.id][-1] if self.hub.incidents[self.id] else None)}


def read_config(path):
    config = configparser.ConfigParser(interpolation=None)
    try:
        config.read(path, encoding='utf-8-sig')
    except (OSError, configparser.Error):
        pass
    return config


class Hub(ApiServer):
    def __init__(self, profiles, primary, runtime, demo=False, preferences=None):
        self.profiles = Path(profiles)
        self.registry = Registry(profiles, primary)
        self.demo = demo
        self.preferences = preferences
        self.exit_requested = False
        self.notify_lock = threading.Lock()
        self.incidents = collections.defaultdict(lambda: collections.deque(maxlen=20))
        self._incident_id = 0
        self.workers_dir = Path(runtime) / 'workers'
        self.workers_dir.mkdir(parents=True, exist_ok=True)
        self.workers = {e['id']: Worker(self, e) for e in self.registry.entries}
        super().__init__(runtime, f'controller-{os.getpid()}.json', {'profile': primary, 'hub': True})
        for worker in self.workers.values():
            if worker.entry.get('open'):
                worker.start()

    # ---- settings shared by every Switch ----
    # Notifications, the watch, the log/dialog layout and the key map are the same on every Switch; the camera, COM
    # port and what is shown in the tabs stay per Switch. A change made on one Switch is applied to the others, and a
    # Switch that starts takes them from one that is already running.
    SHARED_OPTIONS = ('win_start', 'win_end', 'line_start', 'line_end', 'discord_start', 'discord_end', 'keyboard')
    SHARED_CHOICES = ('stdout_destination', 'dialog_buttons')
    SHARED_FILES = ('discord_token.ini', 'line_token.ini', 'watch.json')

    def shared_command(self, params):
        """The part of a command that every Switch takes, or None."""
        action, values = params.get('action'), params.get('values') or {}
        if action in ('notification', 'watch', 'keymap'):
            return {'action': action, 'values': values}
        if action == 'options':
            shared = {k: v for k, v in values.items() if k in self.SHARED_OPTIONS}
            return {'action': action, 'values': shared} if shared else None
        if action == 'choice' and values.get('name') in self.SHARED_CHOICES:
            return {'action': action, 'values': values}
        return None

    def share(self, origin, command):
        for worker in self.open_workers():
            if worker is not origin and worker.state == 'ready':
                try:
                    worker.call('command', command, timeout=10)
                except Exception:
                    pass  # it takes the settings again when it starts

    def settings_source(self, worker):
        """The Switch whose settings the others follow: the first open one (the left tab)."""
        first = self.open_workers()[:1]
        return first[0] if first and first[0] is not worker else None

    def copy_shared_files(self, worker):
        # Before a Switch's process starts: the token files and the watch settings of the first Switch.
        source = self.settings_source(worker)
        if source is None:
            return
        for name in self.SHARED_FILES:
            path = self.profiles / source.profile / name
            if path.is_file():
                (self.profiles / worker.profile).mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, self.profiles / worker.profile / name)

    def take_shared_settings(self, worker):
        """Once a Switch is ready: the settings kept in settings.ini, from the first Switch (or, when it is the first
        one, to the Switches that were ready before it)."""
        source = self.settings_source(worker)
        if source is None:
            for other in self.open_workers()[1:]:
                if other.state == 'ready':
                    self.copy_settings(worker, other)
        elif source.state == 'ready':
            self.copy_settings(source, worker)

    def copy_settings(self, source, worker):
        try:
            theirs = source.call('sessions', timeout=10)[0]
            mine = worker.call('sessions', timeout=10)[0]
            options = {k: v for k, v in theirs['options'].items() if k in self.SHARED_OPTIONS}
            worker.call('command', {'action': 'options', 'values': options}, timeout=10)
            for name in self.SHARED_CHOICES:
                if mine['choices'].get(name) != theirs['choices'].get(name):
                    worker.call('command', {'action': 'choice', 'values': {'name': name, 'value': theirs['choices'][name]}}, timeout=10)
            wanted = {name: key for key, name in theirs['keymap'].items()}
            if {name: key for key, name in mine['keymap'].items()} != wanted:
                mapping = {name: wanted.get(name, '') for name in set(wanted) | set(mine['keymap'].values())}
                worker.call('command', {'action': 'keymap', 'values': {'mapping': mapping}}, timeout=10)
            if mine['watch']['settings'] != theirs['watch']['settings']:
                worker.call('command', {'action': 'watch', 'values': theirs['watch']['settings']}, timeout=10)
        except Exception:
            pass

    @property
    def id(self):  # the tray's channel addresses the first open Switch
        return next(e['id'] for e in self.registry.entries if e.get('open'))

    def incident_id(self):
        self._incident_id = max(self._incident_id + 1, int(time.time() * 1000))
        return self._incident_id

    def open_workers(self):
        return [self.workers[e['id']] for e in self.registry.entries if e.get('open')]

    def worker(self, switch_id):
        if not switch_id:
            return self.open_workers()[0]
        worker = self.workers.get(switch_id)
        if worker is None:
            raise ValueError('Session not found')
        return worker

    def app_info(self):
        import update_service
        from product import VERSION
        values = self.preferences.values if self.preferences else {}
        return {'version': VERSION, 'portable': app_paths.PORTABLE, 'workspace': str(app_paths.WORKSPACE),
                'auto_update': values.get('auto_update', False), 'prereleases': values.get('prereleases', False),
                'update': update_service.read_state(), 'folders': {k: str(v) for k, v in app_paths.FOLDERS.items()}}

    def placeholder(self, worker):
        """The page's state for a Switch whose process is not answering (starting, restarting or stopped)."""
        return {'id': worker.id, 'profile': worker.profile, 'label': worker.label, 'ready': False, 'exited': False,
                'switch_state': worker.state, 'switch_error': worker.error, 'running': False, 'paused': False,
                'command': '', 'demo': self.demo, 'camera_live': False, 'serial_open': False, 'held': []}

    def snapshot(self, worker, request_id=None):
        try:
            state = worker.call('sessions', request_id=request_id)[0] if worker.state == 'ready' else None
        except Exception:
            state = None
        state = state or self.placeholder(worker)
        state.update(id=worker.id, label=worker.label, switch_state=worker.state, app=self.app_info())
        crashes = list(self.incidents[worker.id])
        if crashes and isinstance(state.get('watch'), dict):  # the page lists the crashes with the watcher's incidents
            watch = state['watch']
            watch['incidents'] = sorted(watch['incidents'] + [dict(i) for i in crashes], key=lambda i: i['id'])[-10:]
            watch['last_id'] = max(watch.get('last_id', 0), crashes[-1]['id'])
        return state

    # ---- requests ----
    def cached(self, method):
        return method == 'command' or str(method).startswith('switch_')

    def browser_params(self, params):
        params = dict(params)
        params['id'] = params.pop('session', '') or self.id
        return params

    def handle(self, method, params, request_id):
        if method == 'sessions':
            workers = self.open_workers()
            results = [None] * len(workers)
            def fetch(index, worker):
                results[index] = self.snapshot(worker)
            threads = [threading.Thread(target=fetch, args=(i, w), daemon=True) for i, w in enumerate(workers)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            return results
        if method == 'switches':
            return self.switch_list(include_closed=True)
        if method == 'switch_add':
            entry = self.registry.add(params.get('label', ''))
            worker = self.workers[entry['id']] = Worker(self, entry)
            worker.start()
            return worker.info()
        if method in ('switch_close', 'switch_open', 'switch_rename', 'switch_restart'):
            worker = self.worker(params.get('switch') or params.get('id'))
            if method == 'switch_close':
                if [w.id for w in self.open_workers()] == [worker.id]:
                    raise ValueError('最後の Switch は閉じられません')
                self.registry.update(worker.id, open=False)
                threading.Thread(target=worker.stop, daemon=True).start()
            elif method == 'switch_open':
                self.registry.update(worker.id, open=True)
                threading.Thread(target=worker.restart, daemon=True).start()
            elif method == 'switch_rename':
                label = clean_label(params.get('label'))
                if not label:
                    raise ValueError('名前を入力してください')
                self.registry.update(worker.id, label=label)
                if worker.state == 'ready':
                    worker.call('command', {'action': 'label', 'values': {'label': label}})
            else:
                threading.Thread(target=worker.restart, daemon=True).start()
            return worker.info()
        if method == 'web_url':
            return {'url': self.web_url}
        action = params.get('action') if method == 'command' else None
        if action in APP_ACTIONS:
            return self.app_command(action, params.get('values') or {})
        worker = self.worker(params.get('id'))
        if method == 'incidents':
            return self.merged_incidents(worker, params)
        result = worker.call(method, params, request_id=request_id)
        shared = self.shared_command(params) if method == 'command' else None
        if shared:
            self.share(worker, shared)
        return result

    def merged_incidents(self, worker, params):
        after = params.get('after', 0)
        try:
            result = worker.call('incidents', params)
        except Exception:
            result = {'incidents': [], 'watch': {'last_id': 0}}
        crashes = [dict(i) for i in self.incidents[worker.id] if i['id'] > after]
        result['incidents'] = sorted(result['incidents'] + crashes, key=lambda i: i['id'])
        result['watch']['last_id'] = max([result['watch'].get('last_id', 0)] + [i['id'] for i in self.incidents[worker.id]])
        return result

    def app_command(self, action, values):
        if action == 'app_options':
            for key in ('auto_update', 'prereleases'):
                if key in values:
                    self.preferences.set(key, values[key])
        elif action == 'update_now':
            import update_service
            threading.Thread(target=update_service.check_now, args=(self.preferences, True), daemon=True).start()
        elif action == 'open_folder':
            folders = {'workspace': app_paths.WORKSPACE, 'settings': app_paths.PROFILES, 'logs': app_paths.LOGS,
                       'captures': app_paths.WORKSPACE / 'Captures', 'scripts': app_paths.WORKSPACE / 'Commands' / 'PythonCommands'}
            folder = folders.get(values.get('folder'))
            if folder is None:
                raise ValueError('Unknown folder')
            folder.mkdir(parents=True, exist_ok=True)
            os.startfile(folder)
        elif action == 'quit':
            self.exit_requested = True
        return {'accepted': True}

    def switch_list(self, include_closed=False):
        return [self.workers[e['id']].info() for e in self.registry.entries if include_closed or e.get('open')]

    # ---- the page ----
    def page_state(self, session):
        try:
            worker = self.worker(session)
            if not worker.entry.get('open'):
                worker = self.worker('')
        except ValueError:
            worker = self.worker('')
        return {'ok': True, 'result': self.snapshot(worker), 'switches': self.switch_list(include_closed=True)}, 200

    def frame_jpeg(self, session):
        try:
            return self.worker(session).call('frame_raw', timeout=5)['jpeg']
        except Exception:
            return None

    def stream_frames(self, session):
        """Frames from the Switch's process over one pipe connection; the last frame is repeated now and then so a
        closed page is noticed."""
        try:
            worker = self.worker(session)
        except ValueError:
            return
        from multiprocessing.connection import Client
        connection, last_at, last, sent_at = None, None, None, 0
        try:
            while not self.closed:
                endpoint = worker.endpoint
                if endpoint is None:
                    connection = None
                    yield None
                    time.sleep(.5)
                    continue
                try:
                    if connection is None:
                        connection = Client(endpoint['pipe'], family='AF_PIPE', authkey=endpoint['token'].encode())
                    connection.send({'method': 'frame_raw', 'params': {'id': worker.id, 'after': last_at},
                                     'request_id': uuid.uuid4().hex})
                    if not connection.poll(5):
                        raise TimeoutError
                    result = connection.recv()
                except Exception:
                    connection = None
                    yield None
                    time.sleep(.5)
                    continue
                frame = (result.get('result') or {}) if result.get('ok') else {}
                if frame.get('jpeg'):
                    last_at, last, sent_at = frame['at'], frame['jpeg'], time.monotonic()
                    yield last
                elif last is not None and time.monotonic() - sent_at > 2:
                    sent_at = time.monotonic()
                    yield last
                else:
                    yield None
                time.sleep(1 / 20)
        finally:
            if connection is not None:
                connection.close()

    def close(self):
        """Stop every Switch cleanly, then the servers."""
        threads = [threading.Thread(target=w.stop, daemon=True) for w in self.workers.values()]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(15)
        super().close()
