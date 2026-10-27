"""Token-authenticated localhost API and browser UI for the window-less app core."""
import base64
import hmac
import json
import os
from pathlib import Path
import secrets
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
    def handle_error(self, request, client_address):
        # A browser closing the video stream or a page is normal, not an error worth a traceback.
        if isinstance(sys.exc_info()[1], ConnectionError):
            return
        super().handle_error(request, client_address)


class LocalControl:
    def __init__(self, core, runtime):
        self.core = core
        self.demo = core.demo
        self.id = uuid.uuid4().hex
        self.cache = {}
        self.cache_lock = threading.Lock()
        self.token = secrets.token_hex(32)
        self.web_token = secrets.token_hex(32)
        self.held_at = {}
        self.streams = threading.BoundedSemaphore(MAX_STREAMS)
        self.closed = False
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
                    result, status = owner.submit({'method': 'sessions', 'params': {}, 'request_id': uuid.uuid4().hex})
                    if result.get('ok'):
                        result = {'ok': True, 'result': result['result'][0]}
                    return self.reply(status, json.dumps(result).encode())
                if url.path == '/frame.jpg':
                    frame = owner.encode_frame()
                    if frame is None:
                        return self.reply(404, b'No live camera frame', 'text/plain')
                    return self.reply(200, frame, 'image/jpeg')
                if url.path == '/stream.mjpg':
                    return self.stream()
                self.reply(404, b'Not found', 'text/plain')

            def stream(self):
                if not owner.streams.acquire(blocking=False):
                    return self.reply(429, b'Too many streams', 'text/plain')
                try:
                    self.close_connection = True
                    self.send_response(200)
                    self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    last = None
                    while not owner.closed:
                        frame_at = getattr(owner.core.camera, 'frame_at', 0)
                        frame = owner.encode_frame() if frame_at != last else None
                        if frame is not None:
                            last = frame_at
                            self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '
                                             + str(len(frame)).encode() + b'\r\n\r\n' + frame + b'\r\n')
                            self.wfile.flush()
                        time.sleep(1 / 20)
                except OSError:
                    pass
                finally:
                    owner.streams.release()

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
                            params = dict(payload.get('params', {}), id=owner.id)
                            result, status = owner.submit({'method': payload.get('method'), 'params': params,
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

        self.server = QuietServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        port = self.server.server_port
        self.cookie = f'pokecon_{port}'
        self.web_url = f'http://127.0.0.1:{port}/?token={self.web_token}'
        runtime = Path(runtime)
        runtime.mkdir(parents=True, exist_ok=True)
        remove_stale_endpoints(runtime)
        self.path = runtime / f'controller-{os.getpid()}.json'
        # MCP and other local programs use a named pipe: some security software (e.g. AdGuard's
        # localhost filtering) breaks loopback TCP for Python clients, but leaves pipes alone.
        from multiprocessing.connection import Listener
        self.pipe = rf'\\.\pipe\PokeController-{os.getpid()}-{secrets.token_hex(8)}'
        self.listener = Listener(self.pipe, family='AF_PIPE', authkey=self.token.encode())
        self.path.write_text(json.dumps({'url': f'http://127.0.0.1:{port}/', 'web_url': self.web_url, 'pipe': self.pipe,
                                        'token': self.token, 'pid': os.getpid(), 'profile': core.profile}),
                             encoding='utf-8')
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
            signature = json.dumps(payload, sort_keys=True)
            with self.cache_lock:
                now = time.monotonic()
                self.cache = {k: v for k, v in self.cache.items() if now - v[0] < 300}
                if request_id in self.cache:
                    _, original, result = self.cache[request_id]
                    if original != signature:
                        raise ValueError('Request ID reused with different parameters')
                    return result, 200
                if len(self.cache) >= 4096:
                    raise ValueError('Too many requests; retry later')
            try:
                with self.core.lock:
                    result = {'ok': True, 'result': self.execute(payload['method'], payload.get('params', {}))}
            except Exception as exc:
                result = {'ok': False, 'error': str(exc)}
            if payload.get('method') == 'command':
                with self.cache_lock:
                    self.cache[request_id] = (time.monotonic(), signature, result)
            return result, 200
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}, 400

    def encode_frame(self):
        import cv2
        camera = self.core.camera
        image = getattr(camera, 'image_bgr', None)
        if image is None or time.time() - getattr(camera, 'frame_at', 0) >= 2:
            return None
        ok, encoded = cv2.imencode('.jpg', self.core.overlay.draw(image), [cv2.IMWRITE_JPEG_QUALITY, 80])
        return encoded.tobytes() if ok else None

    def snapshot(self):
        state = self.core.snapshot()
        import app_paths
        import update_service
        from product import VERSION
        preferences = getattr(self.core, 'preferences', None)
        state['app'] = {'version': VERSION, 'portable': app_paths.PORTABLE, 'workspace': str(app_paths.WORKSPACE),
                        'auto_update': preferences.values['auto_update'] if preferences else False,
                        'prereleases': preferences.values['prereleases'] if preferences else False,
                        'update': update_service.read_state()}
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

    def neutral(self):
        self.held_at.clear()
        keys = self.core.keys_software_controller
        keys.neutral()
        if not self.core.running and self.core.serial_open():
            for which in ('L', 'R'):
                self.stick({'stick': which, 'x': 128, 'y': 128})

    def execute(self, method, params):
        core = self.core
        if method == 'sessions':
            return [self.snapshot()]
        if params.get('id') != self.id:
            raise ValueError('Session not found')
        if method == 'frame':
            frame = self.encode_frame()
            if frame is None:
                raise ValueError('No live camera frame')
            return {'data': base64.b64encode(frame).decode(), 'mimeType': 'image/jpeg'}
        if method == 'web_url':
            return {'url': self.web_url}
        if method == 'devices':
            return {'cameras': core.cameras(), 'ports': core.ports()}
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
        elif action == 'clear_log':
            core.clear_log(1 if values.get('log') == 1 else 2)
        elif action == 'app_options':
            for key in ('auto_update', 'prereleases'):
                if key in values:
                    core.preferences.set(key, values[key])
        elif action == 'update_now':
            import update_service
            threading.Thread(target=update_service.check_now, args=(core.preferences, True), daemon=True).start()
        elif action == 'open_folder':
            import app_paths
            folders = {'workspace': app_paths.WORKSPACE, 'settings': app_paths.PROFILES, 'logs': app_paths.LOGS,
                       'captures': app_paths.WORKSPACE / 'Captures', 'scripts': app_paths.WORKSPACE / 'Commands' / 'PythonCommands'}
            folder = folders.get(values.get('folder'))
            if folder is None:
                raise ValueError('Unknown folder')
            folder.mkdir(parents=True, exist_ok=True)
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
        elif action == 'quit':
            core.exit_requested = True
        else:
            raise ValueError('Unknown action')
        return {'accepted': True}

    def close(self):
        self.closed = True
        self.path.unlink(missing_ok=True)
        self.listener.close()
        self.server.shutdown()
        self.server.server_close()
