"""Token-authenticated localhost API and browser UI for the window-less app core."""
import base64
import contextlib
import hmac
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import threading
import time
from urllib.parse import parse_qs, urlparse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WEB_PAGE = Path(__file__).resolve().parent / 'web' / 'index.html'
BUTTONS = ('A', 'B', 'X', 'Y', 'L', 'R', 'ZL', 'ZR', 'MINUS', 'PLUS', 'HOME', 'CAPTURE', 'LCLICK', 'RCLICK')
HATS = {'UP': 'TOP', 'DOWN': 'BTM', 'LEFT': 'LEFT', 'RIGHT': 'RIGHT'}
STICK_ANGLES = {'UP': 90, 'DOWN': -90, 'LEFT': -180, 'RIGHT': 0}
MIN_PRESS = .08
MAX_PRESS = 5.0
MAX_STREAMS = 4
# Pages the app opens in the default browser (where the user is signed in, so the private repository shows).
LINKS = {'guide': 'https://github.com/hinatamaxxx/Poke-Controller-Modified-Extension-Plus#使い方',
         'github': 'https://github.com/hinatamaxxx/Poke-Controller-Modified-Extension-Plus',
         'discord_webhook': 'https://support.discord.com/hc/ja/articles/228383668'}


def parse_inputs(names):
    """Map names such as A, UP, LS_LEFT or RS_UP to controller inputs."""
    from Commands.Keys import Button, Direction, Hat, Stick
    if not isinstance(names, list) or not 0 < len(names) <= 8:
        raise ValueError('buttons must be a list of 1-8 names')
    result = []
    for name in names:
        key = str(name).upper()
        if key in BUTTONS:
            value = Button[key]
        elif key in HATS:
            value = Hat[HATS[key]]
        elif key[:3] in ('LS_', 'RS_') and key[3:] in STICK_ANGLES:
            value = Direction(Stick.LEFT if key[0] == 'L' else Stick.RIGHT, STICK_ANGLES[key[3:]], showName=key)
        else:
            raise ValueError(f'Unknown button: {name}')
        if not contains(result, value):
            result.append(value)
    return result


def contains(items, value):
    # Hat and Button are int enums, so plain `in` treats Hat.RIGHT and Button.B as equal.
    return any(type(item) is type(value) and item == value for item in items)


def process_alive(pid):
    """True unless Windows reports the process as gone. os.kill(pid, 0) would terminate it on Windows."""
    import ctypes
    kernel = ctypes.windll.kernel32
    handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ctypes.GetLastError() == 5  # access denied: exists under another account
    try:
        code = ctypes.c_ulong()
        return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259  # STILL_ACTIVE
    finally:
        kernel.CloseHandle(handle)


def remove_stale_endpoints(runtime):
    """Delete endpoint files left by apps that crashed or were killed."""
    for path in Path(runtime).glob('controller-*.json'):
        try:
            pid = int(path.stem.split('-', 1)[1])
        except ValueError:
            continue
        if pid != os.getpid() and not process_alive(pid):
            path.unlink(missing_ok=True)


class QuietServer(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR would let us bind a port another program is listening on; ask for it exclusively.
    allow_reuse_address = False

    def handle_error(self, request, client_address):
        # A browser closing the video stream or a page is normal, not an error worth a traceback.
        if isinstance(sys.exc_info()[1], ConnectionError):
            return
        super().handle_error(request, client_address)


class ApiServer:
    """Token-authenticated browser page (HTTP) and local API (named pipe) with an endpoint file in `runtime`.

    Subclasses answer requests (`handle`) and provide the page's state and video for a session."""

    def __init__(self, runtime, endpoint_name, info=None, http=True):
        self.cache = {}
        self.cache_lock = threading.Lock()
        self.token = secrets.token_hex(32)
        self.web_token = secrets.token_hex(32)
        self.streams = threading.BoundedSemaphore(MAX_STREAMS)
        self.closed = False
        self.server = None
        self.web_url = ''
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            wbufsize = 65536
            def log_message(self, *args):
                pass

            def reply(self, status, data, content_type='application/json', headers=()):
                try:
                    self.send_response(status)
                    self.send_header('Content-Type', content_type)
                    self.send_header('Content-Length', str(len(data)))
                    self.send_header('Cache-Control', 'no-store')
                    for header in headers:
                        self.send_header(*header)
                    self.end_headers()
                    self.wfile.write(data)
                    self.wfile.flush()
                except OSError:
                    self.close_connection = True

            def local_host(self):
                # Rejecting other Host names blocks DNS rebinding from web pages.
                port = owner.server.server_port
                return self.headers.get('Host', '') in (f'127.0.0.1:{port}', f'localhost:{port}')

            def browser_authorized(self):
                cookies = dict(part.strip().split('=', 1) for part in self.headers.get('Cookie', '').split(';') if '=' in part)
                return self.local_host() and hmac.compare_digest(cookies.get(owner.cookie, ''), owner.web_token)

            def do_GET(self):
                self.connection.settimeout(5)
                url = urlparse(self.path)
                session = parse_qs(url.query).get('session', [''])[0]
                if not self.local_host():
                    return self.reply(403, b'Forbidden', 'text/plain')
                if url.path == '/':
                    token = parse_qs(url.query).get('token', [''])[0]
                    if token and hmac.compare_digest(token, owner.web_token):
                        # Move the token into a cookie so it does not stay in the address bar.
                        return self.reply(303, b'', 'text/plain', [
                            ('Location', '/'),
                            ('Set-Cookie', f'{owner.cookie}={owner.web_token}; HttpOnly; SameSite=Strict; Path=/')])
                    if not self.browser_authorized():
                        message = 'トークン付きのURLで開いてください。URLはアプリのMCPメニュー「ブラウザで開く」、またはMCPの get_web_url で取得できます。'
                        return self.reply(403, message.encode(), 'text/plain; charset=utf-8')
                    return self.reply(200, WEB_PAGE.read_bytes(), 'text/html; charset=utf-8',
                                      [('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self'")])
                if not self.browser_authorized():
                    return self.reply(403, b'Forbidden', 'text/plain')
                if url.path == '/api/state':
                    result, status = owner.page_state(session)
                    return self.reply(status, json.dumps(result).encode())
                if url.path == '/frame.jpg':
                    frame = owner.frame_jpeg(session)
                    if frame is None:
                        return self.reply(404, b'No live camera frame', 'text/plain')
                    return self.reply(200, frame, 'image/jpeg')
                if url.path == '/stream.mjpg':
                    return self.stream(session)
                self.reply(404, b'Not found', 'text/plain')

            def stream(self, session):
                if not owner.streams.acquire(blocking=False):
                    return self.reply(429, b'Too many streams', 'text/plain')
                try:
                    self.close_connection = True
                    self.send_response(200)
                    self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    for frame in owner.stream_frames(session):
                        if owner.closed or (frame is None and self.client_gone()):
                            break
                        if frame is not None:
                            self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '
                                             + str(len(frame)).encode() + b'\r\n\r\n' + frame + b'\r\n')
                            self.wfile.flush()
                except OSError:
                    pass
                finally:
                    owner.streams.release()

            def client_gone(self):
                # The page sends nothing on a stream, so a readable socket means it was closed.
                import select
                try:
                    readable, _, _ = select.select([self.connection], [], [], 0)
                    return bool(readable) and not self.connection.recv(1, socket.MSG_PEEK)
                except (OSError, ValueError):
                    return True

            def do_POST(self):
                self.connection.settimeout(5)
                try:
                    size = int(self.headers.get('Content-Length', 0))
                    if not 0 < size <= 65536:
                        self.send_error(413)
                        self.close_connection = True
                        return
                    body = self.rfile.read(size)
                except (ValueError, OSError):
                    self.close_connection = True
                    return
                result, status = {'ok': False, 'error': 'Unauthorized'}, 403
                path = urlparse(self.path).path
                if path == '/api/call':
                    # Same-origin JSON only; cross-site forms cannot set this content type without CORS.
                    origin = self.headers.get('Origin')
                    if (self.browser_authorized() and origin == 'http://' + self.headers.get('Host', '')
                            and self.headers.get('Content-Type', '').startswith('application/json')):
                        try:
                            payload = json.loads(body)
                            if not isinstance(payload, dict) or not isinstance(payload.get('params', {}), dict):
                                raise ValueError('Request and params must be objects')
                            result, status = owner.submit({'method': payload.get('method'),
                                                           'params': owner.browser_params(payload.get('params', {})),
                                                           'request_id': uuid.uuid4().hex})
                        except ValueError as exc:
                            result, status = {'ok': False, 'error': str(exc)}, 400
                elif hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + owner.token):
                    try:
                        payload = json.loads(body)
                        if not isinstance(payload, dict) or not isinstance(payload.get('params', {}), dict):
                            raise ValueError('Request and params must be objects')
                        result, status = owner.submit(payload)
                    except ValueError as exc:
                        result, status = {'ok': False, 'error': str(exc)}, 400
                self.reply(status, json.dumps(result).encode())

        runtime = Path(runtime)
        runtime.mkdir(parents=True, exist_ok=True)
        remove_stale_endpoints(runtime)
        endpoint = {'url': '', 'web_url': '', 'pid': os.getpid(), **(info or {})}
        if http:
            # The same port as last time when it is free: the page's origin stays the same, so what the browser
            # keeps (the chosen Switch, each Switch's bottom tab, the controller's place) survives a restart.
            port_file = runtime / 'web-port.txt'
            try:
                wanted = int(port_file.read_text(encoding='ascii'))
            except (OSError, ValueError):
                wanted = 0
            try:
                self.server = QuietServer(('127.0.0.1', wanted), Handler)
            except OSError:
                self.server = QuietServer(('127.0.0.1', 0), Handler)
            self.server.daemon_threads = True
            port = self.server.server_port
            try:
                port_file.write_text(str(port), encoding='ascii')
            except OSError:
                pass
            self.cookie = f'pokecon_{port}'
            self.web_url = f'http://127.0.0.1:{port}/?token={self.web_token}'
            endpoint.update(url=f'http://127.0.0.1:{port}/', web_url=self.web_url)
        self.path = runtime / endpoint_name
        # MCP and other local programs use a named pipe: some security software (e.g. AdGuard's
        # localhost filtering) breaks loopback TCP for Python clients, but leaves pipes alone.
        from multiprocessing.connection import Listener
        self.pipe = rf'\\.\pipe\PokeController-{os.getpid()}-{secrets.token_hex(8)}'
        self.listener = Listener(self.pipe, family='AF_PIPE', authkey=self.token.encode())
        endpoint.update(pipe=self.pipe, token=self.token)
        self.path.write_text(json.dumps(endpoint), encoding='utf-8')
        if http:
            threading.Thread(target=self.server.serve_forever, daemon=True).start()
        threading.Thread(target=self.serve_pipe, daemon=True).start()

    def serve_pipe(self):
        from multiprocessing import AuthenticationError
        while not self.closed:
            try:
                connection = self.listener.accept()
            except AuthenticationError:
                continue
            except OSError:
                if self.closed:
                    return
                continue
            threading.Thread(target=self.pipe_client, args=(connection,), daemon=True).start()

    def pipe_client(self, connection):
        with connection:
            while not self.closed:
                try:
                    payload = connection.recv()
                except (EOFError, OSError):
                    return
                if not isinstance(payload, dict) or not isinstance(payload.get('params', {}), dict):
                    result = {'ok': False, 'error': 'Request and params must be objects'}
                else:
                    result, _ = self.submit(payload)
                try:
                    connection.send(result)
                except OSError:
                    return

    def submit(self, payload):
        """Run one request. Commands are cached by request ID so a retried request is not applied twice."""
        request_id = payload.get('request_id', '')
        try:
            if not isinstance(request_id, str) or len(request_id) != 32 or any(c not in '0123456789abcdef' for c in request_id):
                raise ValueError('Invalid request ID')
            signature = json.dumps(payload, sort_keys=True, default=str)
            with self.cache_lock:
                now = time.monotonic()
                self.cache = {k: v for k, v in self.cache.items() if now - v[0] < 300}
                if request_id in self.cache:
                    _, original, result = self.cache[request_id]
                    if original != signature:
                        raise ValueError('Request ID reused with different parameters')
                    return result, 200
                while len(self.cache) >= 4096:
                    # The browser sends many short-lived commands (sticks at 20/s); drop the oldest, never refuse.
                    self.cache.pop(next(iter(self.cache)))
            try:
                result = {'ok': True, 'result': self.handle(payload['method'], payload.get('params', {}), request_id)}
            except Exception as exc:
                result = {'ok': False, 'error': str(exc)}
            if self.cached(payload.get('method')):
                with self.cache_lock:
                    self.cache[request_id] = (time.monotonic(), signature, result)
            return result, 200
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}, 400

    def cached(self, method):
        return method == 'command'

    def close(self):
        self.closed = True
        self.path.unlink(missing_ok=True)
        self.listener.close()
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()


class LocalControl(ApiServer):
    """One Switch: its controller, camera and scripts. Runs in a worker process; the hub routes the page and MCP here."""

    def __init__(self, core, runtime, session_id=None, http=True):
        self.core = core
        self.demo = core.demo
        self.id = session_id or uuid.uuid4().hex
        self.held_at = {}
        name = f'worker-{self.id}.json' if session_id else f'controller-{os.getpid()}.json'
        super().__init__(runtime, name, {'profile': core.profile, 'session': self.id}, http=http)

    def browser_params(self, params):
        return dict(params, id=self.id)

    def handle(self, method, params, request_id):
        unlocked = method in self.UNLOCKED or (
            method == 'command' and isinstance(params, dict) and params.get('action') in self.UNLOCKED_ACTIONS)
        # Slow work that does not touch the controller runs outside core.lock, so button releases are not delayed.
        with contextlib.nullcontext() if unlocked else self.core.lock:
            return self.execute(method, params)

    def page_state(self, session):
        result, status = self.submit({'method': 'sessions', 'params': {}, 'request_id': uuid.uuid4().hex})
        if result.get('ok'):
            result = {'ok': True, 'result': result['result'][0]}
        return result, status

    def frame_jpeg(self, session):
        return self.encode_frame()

    def stream_frames(self, session):
        last = None
        while not self.closed:
            frame_at = getattr(self.core.camera, 'frame_at', 0)
            frame = self.encode_frame() if frame_at != last else None
            if frame is not None:
                last = frame_at
            yield frame
            time.sleep(1 / 20)

    def encode_frame(self, width=None):
        import cv2
        camera = self.core.camera
        image = getattr(camera, 'image_bgr', None)
        if image is None or time.time() - getattr(camera, 'frame_at', 0) >= 2:
            return None
        if width:
            image = cv2.resize(image, (width, int(image.shape[0] * width / image.shape[1])), interpolation=cv2.INTER_AREA)
            ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 70])
        else:
            ok, encoded = cv2.imencode('.jpg', self.core.overlay.draw(image), [cv2.IMWRITE_JPEG_QUALITY, 80])
        return encoded.tobytes() if ok else None

    def summary(self):
        """What the hub needs every second: health, what is running, and which devices this Switch holds."""
        from Commands.CommandBase import Command
        core = self.core
        watch = core.watch.snapshot()
        last = watch['incidents'][-1] if watch['incidents'] else None
        return {'id': self.id, 'profile': core.profile, 'label': core.label, 'running': core.running,
                'paused': bool(Command.isPause), 'command': Command.cur_command_name if core.running else '', 'camera_live': core.camera_live(),
                'serial_open': core.serial_open(), 'port': core.serial_target() if core.serial_open() else '',
                'camera_path': core.settings.camera_path, 'recording': bool(core.recorder.state()),
                'script': watch['script'], 'auto_restart': watch['settings']['auto_restart'] and watch['settings']['enabled'],
                'incident': last and {'kind': last['kind'], 'at': last['at']},
                'dialog': bool(core.dialogs.current())}

    def snapshot(self):
        state = self.core.snapshot()
        import app_paths
        import update_service
        from product import VERSION
        preferences = getattr(self.core, 'preferences', None)
        state['app'] = {'version': VERSION, 'portable': app_paths.PORTABLE, 'workspace': str(app_paths.WORKSPACE),
                        'auto_update': preferences.values['auto_update'] if preferences else False,
                        'prereleases': preferences.values['prereleases'] if preferences else False,
                        'update': update_service.read_state(), 'folders': {k: str(v) for k, v in app_paths.FOLDERS.items()}}
        state.update(id=self.id, ready=True, exited=False,
                     catalog={kind: [item['name'] for item in items] for kind, items in self.core.catalog().items()},
                     tags=self.core.catalog())
        return state

    def check_manual_input(self):
        if self.core.running:
            raise ValueError('Stop the running script before manual input')
        if not self.core.serial_open():
            raise ValueError('COM port is not connected')

    def press(self, values):
        """Hold the inputs, then release after the requested duration."""
        self.check_manual_input()
        duration = float(values.get('duration', .1))
        if not MIN_PRESS <= duration <= MAX_PRESS:
            raise ValueError(f'duration must be {MIN_PRESS}-{MAX_PRESS} seconds')
        inputs = self.hold(parse_inputs(values.get('buttons')))
        self.later(duration, lambda: self.release(inputs))

    def later(self, seconds, callback):
        def run():
            with self.core.lock:
                callback()
        timer = threading.Timer(seconds, run)
        timer.daemon = True
        timer.start()

    def hold(self, inputs):
        keys = self.core.keys_software_controller
        new = [b for b in inputs if not contains(keys.holdButton, b)]
        if new:
            keys.hold(new)
            for b in new:
                self.held_at[repr(b)] = time.monotonic()
        return new

    def stick(self, values):
        """Tilt one analog stick to x/y (0-255, 128 = center, y grows downward)."""
        from Commands.Keys import Direction, Stick
        self.check_manual_input()
        which = str(values.get('stick', '')).upper()
        if which not in ('L', 'R'):
            raise ValueError('stick must be L or R')
        x, y = values.get('x'), values.get('y')
        if not all(isinstance(v, int) and 0 <= v <= 255 for v in (x, y)):
            raise ValueError('x and y must be integers 0-255')
        keys = self.core.keys_software_controller
        target = Stick.LEFT if which == 'L' else Stick.RIGHT
        # An analog position replaces any held direction button of the same stick.
        keys.holdButton = [b for b in keys.holdButton if not (isinstance(b, Direction) and b.stick == target)]
        state = keys.format
        if which == 'L':
            state.format['lx'], state.format['ly'] = x, y
            state.L_stick_changed = True
        else:
            state.format['rx'], state.format['ry'] = x, y
            state.R_stick_changed = True
        keys.input([])

    def release(self, inputs):
        keys = self.core.keys_software_controller
        held = [b for b in inputs if contains(keys.holdButton, b)]
        if not held:
            return
        # Keep very short browser taps long enough for the console to register them.
        wait = max(self.held_at.get(repr(b), 0) + MIN_PRESS - time.monotonic() for b in held)
        if wait > 0:
            self.later(wait + .001, lambda: self.release(held))
            return
        for b in held:
            self.held_at.pop(repr(b), None)
        keys.holdEnd(held)

    UNLOCKED = {'frame', 'frame_raw', 'summary', 'recordings', 'recording_overview', 'recording_frame', 'recording_inputs', 'recording_draft',
                'script_files', 'read_script', 'incidents', 'templates', 'web_url', 'devices', 'about'}
    UNLOCKED_ACTIONS = {'notify_test', 'record_stop'}

    def neutral(self):
        self.held_at.clear()
        if self.core.running:  # the script owns the controller
            return
        keys = self.core.keys_software_controller
        keys.neutral()
        if not self.core.running and self.core.serial_open():
            for which in ('L', 'R'):
                self.stick({'stick': which, 'x': 128, 'y': 128})

    ACTIVITY = {'start': lambda v: f"スクリプトを開始: {v.get('name')}", 'stop': lambda v: 'スクリプトを停止',
                'suspend': lambda v: '一時停止', 'resume': lambda v: '再開',
                'press': lambda v: f"ボタン: {'+'.join(v.get('buttons') or [])} ({v.get('duration', .1)}秒)",
                'stick': lambda v: f"スティック{v.get('stick')}: {v.get('x')},{v.get('y')}",
                'sequence': lambda v: f"連続操作: {len(v.get('steps') or [])}手順", 'sequence_cancel': lambda v: '連続操作を中止',
                'answer': lambda v: 'ダイアログに回答' if v.get('values') is not None else 'ダイアログを閉じる',
                'camera': lambda v: 'カメラを変更', 'connect': lambda v: f"{v.get('port')} に接続", 'disconnect': lambda v: '切断',
                'note': lambda v: 'メモを追加', 'record_start': lambda v: '録画を開始', 'record_stop': lambda v: '録画を停止',
                'write_script': lambda v: f"スクリプトを保存: {v.get('path')}",
                'save_template': lambda v: f"テンプレート画像を保存: {v.get('name')}", 'watch': lambda v: '見張りの設定を変更'}

    def execute(self, method, params):
        core = self.core
        via_mcp = params.get('via') == 'mcp'
        if via_mcp and method == 'command' and params.get('action') in self.ACTIVITY:
            values = params.get('values') if isinstance(params.get('values'), dict) else {}
            try:
                core.assist.record('claude', self.ACTIVITY[params['action']](values))
            except Exception:
                pass
        if method == 'sessions':
            return [self.snapshot()]
        if params.get('id') != self.id:
            raise ValueError('Session not found')
        if method == 'frame':
            frame = self.encode_frame()
            if frame is None:
                raise ValueError('No live camera frame')
            return {'data': base64.b64encode(frame).decode(), 'mimeType': 'image/jpeg'}
        if method == 'frame_raw':
            camera = core.camera
            at = getattr(camera, 'frame_at', 0)
            if params.get('after') == at:
                return {'jpeg': None, 'at': at}
            return {'jpeg': self.encode_frame(width=640 if params.get('small') else None), 'at': at}
        if method == 'about':
            return self.core.about()
        if method == 'summary':
            return self.summary()
        if method == 'web_url':
            return {'url': self.web_url}
        if method == 'devices':
            return {'cameras': core.cameras(), 'ports': core.ports()}
        if method == 'templates':
            return {'templates': core.assist.templates()}
        if method == 'find_template':
            result = core.assist.find_template(params.get('name'), params.get('threshold', .85))
            if via_mcp:
                core.assist.record('claude', f"画像を照合: {params.get('name')} → {result['similarity']}")
            return result
        if method == 'recordings':
            return {'recordings': core.recorder.list(), 'current': core.recorder.state()}
        if method == 'recording_overview':
            image, text = core.recorder.overview(params.get('recording'), params.get('start', 0), params.get('end'),
                                                 params.get('count', 12))
            return {'data': base64.b64encode(image).decode(), 'mimeType': 'image/jpeg', 'timeline': text}
        if method == 'recording_frame':
            image, at = core.recorder.frame(params.get('recording'), params.get('at', 0))
            return {'data': base64.b64encode(image).decode(), 'mimeType': 'image/jpeg', 'at': at}
        if method == 'recording_inputs':
            return {'inputs': core.recorder.inputs(params.get('recording'), params.get('start', 0), params.get('end'))}
        if method == 'recording_draft':
            return {'content': core.recorder.draft_script(params.get('recording'), params.get('name') or 'Draft',
                                                          bool(params.get('loop', True)), params.get('start', 0),
                                                          params.get('end'), float(params.get('max_wait', 3)))}
        if method == 'script_files':
            import script_files
            return {'files': script_files.list_files()}
        if method == 'read_script':
            import script_files
            return {'path': params.get('path'), 'content': script_files.read(params.get('path'))}
        if method == 'incidents':
            return {'incidents': core.watch.since(params.get('after', 0)), 'watch': core.watch.snapshot()}
        if method != 'command':
            raise ValueError('Unknown method')
        action = params.get('action')
        values = params.get('values', {})
        if not isinstance(values, dict):
            raise ValueError('values must be an object')
        if action == 'start':
            core.start_script(values.get('kind', 'python'), values.get('name'))
        elif action == 'stop':
            core.stop_script()
        elif action == 'suspend':
            core.pause(True)
        elif action == 'resume':
            core.pause(False)
        elif action == 'reload':
            core.reload_scripts()
        elif action == 'press':
            self.press(values)
        elif action == 'hold':
            self.check_manual_input()
            self.hold(parse_inputs(values.get('buttons')))
        elif action == 'release':
            self.release(parse_inputs(values.get('buttons')))
        elif action == 'stick':
            self.stick(values)
        elif action == 'neutral':
            self.neutral()
        elif action == 'camera':
            core.select_camera(values.get('path', ''))
        elif action == 'connect':
            core.connect_serial(values.get('port'), values.get('baud'), values.get('format'))
        elif action == 'disconnect':
            core.disconnect_serial()
        elif action == 'options':
            core.set_options(values)
        elif action == 'answer':
            core.dialogs.answer(values.get('dialog'), values.get('values'))
        elif action == 'capture':
            core.save_capture()
        elif action == 'discord_image':
            core.send_discord_image()
        elif action == 'clear_log':
            core.clear_log(1 if values.get('log') == 1 else 2)
        elif action == 'app_options':
            for key in ('auto_update', 'prereleases'):
                if key in values:
                    core.preferences.set(key, values[key])
        elif action == 'update_now':
            import update_service
            threading.Thread(target=update_service.check_now, args=(core.preferences, True), daemon=True).start()
        elif action == 'open_url':
            import webbrowser
            url = LINKS.get(values.get('link'))
            if url is None:
                raise ValueError('Unknown link')
            webbrowser.open(url)
        elif action == 'open_folder':
            import app_paths
            folder = app_paths.FOLDERS.get(values.get('folder'))
            if folder is None:
                raise ValueError('Unknown folder')
            folder.mkdir(parents=True, exist_ok=True)
            os.startfile(folder)
        elif action == 'open_script_folder':
            import Paths
            import app_paths
            cls = next((c for c in core.py_classes if c.NAME == values.get('name')), None)
            folder = Paths.script_folder(cls.__module__) if cls else ''
            folder = folder or str(app_paths.FOLDERS['scripts'])
            os.makedirs(folder, exist_ok=True)
            os.startfile(folder)
        elif action == 'choice':
            core.set_choice(values.get('name'), values.get('value'))
        elif action == 'shortcut':
            core.set_shortcut(values.get('slot'), values.get('kind'), values.get('name', ''))
        elif action == 'keymap':
            mapping = values.get('mapping')
            if not isinstance(mapping, dict):
                raise ValueError('mapping must be an object')
            core.set_keymap(mapping)
        elif action == 'notification':
            core.set_notification(values)
        elif action == 'notify_test':
            core.notify_test(values.get('channel'))
        elif action == 'camera_reconnect':
            core.reconnect_camera_now()
        elif action == 'status':
            core.assist.set_status(values.get('doing', values.get('text', '')), values.get('task', ''), values.get('progress', ''))
        elif action == 'note':
            return core.assist.add_note(values.get('text'), 'claude' if via_mcp else 'user')
        elif action == 'note_delete':
            core.assist.delete_note(values.get('id'))
        elif action == 'sequence':
            sequence_id = core.assist.run_sequence(values.get('steps'), self.check_manual_input, self.hold,
                                                   lambda inputs: self.release(inputs), self.neutral)
            return {'accepted': True, 'sequence': sequence_id}
        elif action == 'sequence_cancel':
            core.assist.cancel_sequence()
        elif action == 'record_start':
            return {'accepted': True, **core.recorder.start(values.get('seconds', 60), values.get('fps', 5), values.get('label', ''))}
        elif action == 'record_stop':
            return {'accepted': True, **core.recorder.stop()}
        elif action == 'write_script':
            return {'accepted': True, **core.write_script(values.get('path'), values.get('content', ''), bool(values.get('overwrite')))}
        elif action == 'save_template':
            import script_files
            frame = core.camera.image_bgr if core.camera_live() else None
            if frame is None:
                raise ValueError('No live camera frame')
            name = script_files.save_template(frame, values.get('name'), values.get('x'), values.get('y'),
                                              values.get('width'), values.get('height'), bool(values.get('overwrite')))
            x, y = int(values['x']), int(values['y'])
            core.overlay.ImgRect(x, y, x + int(values['width']), y + int(values['height']), outline='green', tag='assist-template', ms=2500)
            return {'accepted': True, 'name': name}
        elif action == 'watch':
            core.watch.configure(values)
        elif action == 'quit':
            core.exit_requested = True
        elif action == 'label':
            core.label = str(values.get('label') or core.profile)[:40]
        else:
            raise ValueError('Unknown action')
        return {'accepted': True}
