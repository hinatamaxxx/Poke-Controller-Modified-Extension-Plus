"""Line-based JSON channel to the tray app over the process's own stdin/stdout. MIT.

The tray starts this process with redirected stdio. Each request is one line
{"id": n, "method": ..., "params": {...}} and each reply one line {"id": n, "ok": ..., "result"|"error": ...}.
Events are lines without an id: {"event": "ready", "web_url": ..., "profile": ...}.
Closing stdin (the tray exited) asks the app to quit, so no server is left behind.
"""
import json
import os
import sys
import threading


class HostChannel:
    def __init__(self, log_path):
        # Keep the protocol stream for ourselves and send everything else written to fd 1
        # (library banners, C-level output) to the console log instead of the tray.
        self._out = os.fdopen(os.dup(1), 'w', encoding='utf-8', newline='\n', buffering=1)
        self._in = os.fdopen(os.dup(0), 'r', encoding='utf-8')
        # The original fd 0 (the tray's request pipe) is replaced, so child processes never inherit it and read requests.
        null = os.open(os.devnull, os.O_RDONLY)
        os.dup2(null, 0)
        os.close(null)
        sys.stdin = open(0, 'r', encoding='utf-8', closefd=False)
        # stderr (tracebacks, C-level warnings) goes to the console log too; the tray does not read it.
        log = os.open(str(log_path), os.O_WRONLY | os.O_APPEND | os.O_CREAT)
        os.dup2(log, 1)
        os.dup2(log, 2)
        os.close(log)
        sys.stdout = open(1, 'w', encoding='utf-8', buffering=1, closefd=False)
        sys.stderr = open(2, 'w', encoding='utf-8', errors='backslashreplace', buffering=1, closefd=False)
        self._lock = threading.Lock()
        self.closed = threading.Event()

    def send(self, message):
        with self._lock:
            try:
                self._out.write(json.dumps(message, ensure_ascii=False) + '\n')
                self._out.flush()
            except (OSError, ValueError):
                self.closed.set()

    def serve(self, api, core):
        """Answer requests until the tray closes stdin, then ask the app to quit."""
        def run():
            for line in self._in:
                try:
                    request = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(request, dict):
                    continue
                params = request.get('params') or {}
                if not isinstance(params, dict):
                    params = {}
                params = dict(params, id=api.id)
                import uuid
                result, _ = api.submit({'method': request.get('method'), 'params': params, 'request_id': uuid.uuid4().hex})
                self.send(dict(result, id=request.get('id')))
            self.closed.set()
            core.exit_requested = True
        threading.Thread(target=run, daemon=True).start()
