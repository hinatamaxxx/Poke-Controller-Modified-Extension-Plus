"""Token-authenticated localhost API. All app access runs on Tk's thread."""
import base64
import hmac
import json
import os
from pathlib import Path
import queue
import secrets
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class LocalControl:
    def __init__(self, app, runtime, demo=False):
        self.app = app
        self.demo = demo
        self.id = uuid.uuid4().hex
        self.queue = queue.Queue(maxsize=64)
        self.cache = {}
        self.token = secrets.token_hex(32)
        self.closed = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            wbufsize = 65536
            def log_message(self, *args):
                pass

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
                if hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + owner.token):
                    try:
                        payload = json.loads(body)
                        if not isinstance(payload, dict) or not isinstance(payload.get('params', {}), dict):
                            raise ValueError('Request and params must be objects')
                        job = {'payload': payload, 'done': threading.Event(), 'expires': time.monotonic() + 10}
                        owner.queue.put_nowait(job)
                        if not job['done'].wait(12):
                            raise ValueError('UI did not respond; operation may be pending. Check status.')
                        result, status = job['result'], 200
                    except Exception as exc:
                        result, status = {'ok': False, 'error': str(exc)}, 400
                data = json.dumps(result).encode()
                try:
                    self.send_response(status)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    self.wfile.flush()
                except OSError:
                    pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        runtime = Path(runtime)
        runtime.mkdir(parents=True, exist_ok=True)
        self.path = runtime / f'controller-{os.getpid()}.json'
        self.path.write_text(json.dumps({'url': f'http://127.0.0.1:{self.server.server_port}/',
                                        'token': self.token, 'pid': os.getpid()}), encoding='utf-8')
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.timer = app.root.after(30, self.tick)

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
                'running': str(app.start_button['text']) == 'Stop', 'paused': bool(Command.isPause),
                'command': Command.cur_command_name, 'demo': self.demo, 'exited': False,
                'camera_live': live, 'catalog': {'python': [c.NAME for c in app.py_classes],
                                                'mcu': [c.NAME for c in app.mcu_classes]},
                'log': app.text_area_1.get('end-100l', 'end')[-16000:],
                'log2': app.text_area_2.get('end-100l', 'end')[-16000:]}

    def execute(self, method, params):
        from Commands.CommandBase import Command
        if method == 'sessions':
            return [self.snapshot()]
        if params.get('id') != self.id:
            raise ValueError('Session not found')
        app = self.app
        if method == 'frame':
            import cv2
            if not self.snapshot()['camera_live']:
                raise ValueError('No live camera frame')
            ok, encoded = cv2.imencode('.jpg', app.camera.image_bgr.copy())
            if not ok:
                raise ValueError('Capture encoding failed')
            return {'data': base64.b64encode(encoded).decode(), 'mimeType': 'image/jpeg'}
        if method != 'command':
            raise ValueError('Unknown method')
        action = params.get('action')
        running = self.snapshot()['running']
        if action == 'start':
            if hasattr(app, 'lifecycle') and (app.lifecycle.busy() or app.lifecycle.closing or app.lifecycle.disconnecting):
                raise ValueError('The previous operation is still stopping')
            if running:
                raise ValueError('A script is already running')
            values = params.get('values', {})
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
        else:
            raise ValueError('Unknown action')
        return {'accepted': True}

    def close(self):
        self.closed = True
        self.path.unlink(missing_ok=True)
        self.server.shutdown()
        self.server.server_close()
