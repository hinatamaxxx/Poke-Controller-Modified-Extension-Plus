"""Token-authenticated localhost API and browser UI. All app access runs on Tk's thread."""
import base64
import hmac
import json
import os
from pathlib import Path
import queue
import secrets
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


class LocalControl:
    def __init__(self, app, runtime, demo=False):
        self.app = app
        self.demo = demo
        self.id = uuid.uuid4().hex
        self.queue = queue.Queue(maxsize=64)
        self.cache = {}
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
                        frame_at = getattr(owner.app.camera, 'frame_at', 0)
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

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        port = self.server.server_port
        self.cookie = f'pokecon_{port}'
        self.web_url = f'http://127.0.0.1:{port}/?token={self.web_token}'
        runtime = Path(runtime)
        runtime.mkdir(parents=True, exist_ok=True)
        remove_stale_endpoints(runtime)
        self.path = runtime / f'controller-{os.getpid()}.json'
        self.path.write_text(json.dumps({'url': f'http://127.0.0.1:{port}/', 'web_url': self.web_url,
                                        'token': self.token, 'pid': os.getpid(), 'profile': app.profile}),
                             encoding='utf-8')
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.timer = app.root.after(30, self.tick)

    def submit(self, payload):
        """Queue a request for the Tk thread and wait for its result."""
        job = {'payload': payload, 'done': threading.Event(), 'expires': time.monotonic() + 10}
        try:
            self.queue.put_nowait(job)
        except queue.Full:
            return {'ok': False, 'error': 'Too many requests; retry later'}, 400
        if not job['done'].wait(12):
            return {'ok': False, 'error': 'UI did not respond; operation may be pending. Check status.'}, 400
        return job['result'], 200

    def encode_frame(self):
        import cv2
        camera = self.app.camera
        image = getattr(camera, 'image_bgr', None)
        if image is None or time.time() - getattr(camera, 'frame_at', 0) >= 2:
            return None
        ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return encoded.tobytes() if ok else None

    def tick(self):
        if self.closed:
            return
        for _ in range(8):
            try:
                job = self.queue.get_nowait()
            except queue.Empty:
                break
            payload = job['payload']
            request_id = payload.get('request_id', '')
            signature = json.dumps(payload, sort_keys=True)
            now = time.monotonic()
            self.cache = {k: v for k, v in self.cache.items() if now - v[0] < 300}
            try:
                if not isinstance(request_id, str) or len(request_id) != 32 or any(c not in '0123456789abcdef' for c in request_id):
                    raise ValueError('Invalid request ID')
                if request_id in self.cache:
                    _, original, result = self.cache[request_id]
                    if original != signature:
                        raise ValueError('Request ID reused with different parameters')
                else:
                    if now > job['expires']:
                        raise ValueError('Request expired before execution')
                    if len(self.cache) >= 4096:
                        raise ValueError('Too many requests; retry later')
                    try:
                        result = {'ok': True, 'result': self.execute(payload['method'], payload.get('params', {}))}
                    except Exception as exc:
                        result = {'ok': False, 'error': str(exc)}
                    if payload.get('method') == 'command':
                        self.cache[request_id] = (now, signature, result)
                job['result'] = result
            except Exception as exc:
                job['result'] = {'ok': False, 'error': str(exc)}
            finally:
                job['done'].set()
        self.timer = self.app.root.after(30, self.tick)

    def snapshot(self):
        from Commands.CommandBase import Command
        app = self.app
        live = getattr(app.camera, 'image_bgr', None) is not None and time.time() - getattr(app.camera, 'frame_at', 0) < 2
        return {'id': self.id, 'profile': app.profile, 'ready': True,
                'running': str(app.start_button['text']) == '停止', 'paused': bool(Command.isPause),
                'command': Command.cur_command_name, 'demo': self.demo, 'exited': False,
                'camera_live': live, 'serial_open': self.demo or app.ser.isOpened(),
                'held': [getattr(b, 'showName', None) or b.name for b in app.keys_software_controller.holdButton],
                'catalog': {'python': [c.NAME for c in app.py_classes],
                            'mcu': [c.NAME for c in app.mcu_classes]},
                'log': app.text_area_1.get('end-100l', 'end')[-16000:],
                'log2': app.text_area_2.get('end-100l', 'end')[-16000:]}

    def check_manual_input(self):
        snapshot = self.snapshot()
        if snapshot['running']:
            raise ValueError('Stop the running script before manual input')
        if not snapshot['serial_open']:
            raise ValueError('COM port is not connected')

    def press(self, values):
        """Hold the inputs, then release after the requested duration."""
        self.check_manual_input()
        duration = float(values.get('duration', .1))
        if not MIN_PRESS <= duration <= MAX_PRESS:
            raise ValueError(f'duration must be {MIN_PRESS}-{MAX_PRESS} seconds')
        inputs = self.hold(parse_inputs(values.get('buttons')))
        self.app.root.after(int(duration * 1000), lambda: self.release(inputs))

    def hold(self, inputs):
        keys = self.app.keys_software_controller
        new = [b for b in inputs if not contains(keys.holdButton, b)]
        if new:
            keys.hold(new)
            for b in new:
                self.held_at[repr(b)] = time.monotonic()
        return new

    def release(self, inputs):
        keys = self.app.keys_software_controller
        held = [b for b in inputs if contains(keys.holdButton, b)]
        if not held:
            return
        # Keep very short browser taps long enough for the console to register them.
        wait = max(self.held_at.get(repr(b), 0) + MIN_PRESS - time.monotonic() for b in held)
        if wait > 0:
            self.app.root.after(int(wait * 1000) + 1, lambda: self.release(held))
            return
        for b in held:
            self.held_at.pop(repr(b), None)
        keys.holdEnd(held)

    def execute(self, method, params):
        from Commands.CommandBase import Command
        if method == 'sessions':
            return [self.snapshot()]
        if params.get('id') != self.id:
            raise ValueError('Session not found')
        app = self.app
        if method == 'frame':
            frame = self.encode_frame()
            if frame is None:
                raise ValueError('No live camera frame')
            return {'data': base64.b64encode(frame).decode(), 'mimeType': 'image/jpeg'}
        if method == 'web_url':
            return {'url': self.web_url}
        if method != 'command':
            raise ValueError('Unknown method')
        action = params.get('action')
        values = params.get('values', {})
        if not isinstance(values, dict):
            raise ValueError('values must be an object')
        running = self.snapshot()['running']
        if action == 'start':
            if hasattr(app, 'lifecycle') and (app.lifecycle.busy() or app.lifecycle.closing or app.lifecycle.disconnecting):
                raise ValueError('The previous operation is still stopping')
            if running:
                raise ValueError('A script is already running')
            kind, name = values.get('kind', 'python'), values.get('name')
            if kind not in ('python', 'mcu'):
                raise ValueError('Unknown script kind')
            classes = app.py_classes if kind == 'python' else app.mcu_classes
            if name not in [c.NAME for c in classes]:
                raise ValueError('Script not found')
            if self.demo and not any(c.NAME == name and c.__module__ == 'Commands.PythonCommands.Samples.PortableDemo' for c in classes):
                raise ValueError('Demo mode only runs PortableDemo')
            app.command_nb.select(0 if kind == 'python' else 1)
            (app.py_cb if kind == 'python' else app.mcu_cb).set(name)
            app.startPlay()
        elif action == 'stop':
            if running:
                app.stopPlay()
        elif action == 'suspend':
            if running and not Command.isPause:
                app.pausePlay()
        elif action == 'resume':
            if running and Command.isPause:
                app.restartPlay()
        elif action == 'press':
            self.press(values)
        elif action == 'hold':
            self.check_manual_input()
            self.hold(parse_inputs(values.get('buttons')))
        elif action == 'release':
            self.release(parse_inputs(values.get('buttons')))
        elif action == 'neutral':
            self.held_at.clear()
            app.holdForceEnd()
        else:
            raise ValueError('Unknown action')
        return {'accepted': True}

    def close(self):
        self.closed = True
        self.path.unlink(missing_ok=True)
        self.server.shutdown()
        self.server.server_close()
