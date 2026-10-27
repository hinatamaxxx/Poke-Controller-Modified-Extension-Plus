"""MCP stdio adapter for running Poke Controller Plus instances."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

from mcp.server import MCPServer
from mcp.types import ImageContent, TextContent, ToolAnnotations
import app_paths
from product import NAME

RUNTIME = app_paths.RUNTIME
STARTUP_WAIT = 45


def start_background_app():
    """Start the app without a window so Claude can use it without the user opening it first."""
    exe = app_paths.PROGRAM / 'PokeController.exe'
    if exe.is_file():
        command = [str(exe), '--background']
    else:
        python = Path(sys.executable)
        gui = python.with_name('pythonw.exe')
        command = [str(gui if gui.is_file() else python), str(app_paths.PROGRAM / 'app.py'), '--background']
    # Detached and outside the client's job object, so closing the MCP client does not end the app.
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    options = dict(cwd=str(app_paths.PROGRAM), close_fds=True,
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        subprocess.Popen(command, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **options)
        return
    except OSError:
        pass
    # The client's job forbids breakaway (e.g. kill-on-close jobs). A process created through WMI starts outside it.
    script = ("$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments "
              "@{CommandLine=$env:PC_COMMAND; CurrentDirectory=$env:PC_CWD}; exit $r.ReturnValue")
    env = {**os.environ, 'PC_COMMAND': subprocess.list2cmdline(command), 'PC_CWD': str(app_paths.PROGRAM)}
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], env=env,
                                stdin=subprocess.DEVNULL, capture_output=True, timeout=30,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode == 0:
            return
    except (OSError, subprocess.SubprocessError):
        pass
    subprocess.Popen(command, creationflags=flags, **options)  # ends with the client, but works meanwhile


def build_server(endpoint_path=None, autostart=True):
    server = MCPServer(NAME, instructions=(
        'Use list_sessions to identify the exact session before any operation. Each session is one Switch '
        '(the tabs in the app); every Switch runs in its own process, so one that crashes does not stop the others, '
        'and the app restarts it by itself. add_switch, close_switch, rename_switch and restart_switch manage them. '
        'Run timing-sensitive work as an existing Python script. '
        'After starting a script, inspect its status and logs; an accepted start is not completion. '
        'For manual play, use press_buttons (or run_sequence for timed series) and check the result with get_capture '
        'or find_template. Keep the user informed with set_status, and leave findings with add_note. '
        'Scripts may wait on dialogues: see get_dialogs and answer_dialog. '
        'The app has no window of its own: get_web_url returns the page to open in a browser to watch and operate it, '
        'including settings (camera, COM port) and dialogues that scripts show. '
        'To turn what the user describes into a script: start_recording, do it yourself step by step '
        '(press_buttons / run_sequence, checking each screen with get_capture and find_template), stop_recording once '
        'it works, confirm with the user that it matches what they wanted, then draft_script_from_recording, refine '
        'the draft (save_template for screens to wait for, loop and stop conditions) and write_script; run it with '
        'start_script and watch one cycle. Recordings of the user playing can be studied the same way '
        '(get_recording_overview, get_recording_frame, get_recording_inputs). '
        'For long loops (e.g. shiny resets), the app watches for errors, a frozen picture and lost devices, notifies the '
        "user's Discord/LINE, and can restart the script; if the user asked you to look after a run, wait with "
        'wait_for_incident, look with get_capture, and try to recover the game.'))
    read_only = ToolAnnotations(read_only_hint=True, open_world_hint=False)
    control = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
    routes = {}

    def discover():
        """Collect sessions from every running app; each app writes its own endpoint file."""
        from controller_api import call as local_call
        candidates = [endpoint_path] if endpoint_path else sorted(RUNTIME.glob('controller-*.json'))
        found = []
        routes.clear()
        for candidate in candidates:
            try:
                items = local_call(candidate, 'sessions', retries=3)
            except (OSError, ValueError):
                continue  # Closed or crashed app; its file may be stale.
            for session in items:
                routes[session['id']] = candidate
                found.append(session)
        return found

    def sessions():
        from mcp.server.mcpserver.exceptions import ToolError
        found = discover()
        if not found and autostart and endpoint_path is None:
            start_background_app()
            deadline = time.monotonic() + STARTUP_WAIT
            while not found and time.monotonic() < deadline:
                time.sleep(.5)
                found = discover()
        if not found:
            raise ToolError('Poke-Controller を起動できませんでした。アプリを一度手動で起動して、エラーが出ないか確認してください。')
        return found

    def call(session_id, method, params=None):
        from controller_api import call as local_call
        from mcp.server.mcpserver.exceptions import ToolError
        if session_id not in routes:
            sessions()
        if session_id not in routes:
            raise ToolError('Session not found. Use list_sessions to get a current ID.')
        try:
            # 'via' lets the app show the user what the assistant did.
            return local_call(routes[session_id], method, {**(params or {}), 'id': session_id, 'via': 'mcp'})
        except (ValueError, OSError) as exc:
            raise ToolError(str(exc)) from exc

    def get(session_id):
        for session in sessions():
            if session['id'] == session_id:
                return session
        from mcp.server.mcpserver.exceptions import ToolError
        raise ToolError('Session not found. Use list_sessions to get a current ID.')

    @server.tool(annotations=read_only)
    def list_sessions() -> list[dict]:
        """List the Switches (one session each, shown as tabs in the app) with IDs, names and status.
        switch_state is ready, starting, restarting (after a crash) or crashed (stopped after repeated crashes).
        Starts the app in the background when none is running."""
        keys = ('id', 'label', 'switch_state', 'profile', 'ready', 'running', 'paused', 'command', 'camera_live',
                'serial_open', 'demo', 'exited')
        return [{k: s.get(k) for k in keys} for s in sessions()]

    def hub_call(method, params, session_id=None):
        # Every session of an app routes to the same hub, which manages the Switches.
        found = sessions()
        return call(session_id or found[0]['id'], method, params)

    @server.tool(annotations=control)
    def add_switch(label: str = '') -> dict:
        """Add a Switch (a new tab with its own camera, COM port and scripts; notification settings are copied from
        the first). Returns its session ID once listed; connect its camera and COM port in the app (機器接続)."""
        added = hub_call('switch_add', {'label': label})
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            current = next((s for s in sessions() if s['id'] == added['id']), None)
            if current and current.get('switch_state') == 'ready':
                return {'session_id': added['id'], 'label': added['label'], 'ready': True}
            time.sleep(1)
        return {'session_id': added['id'], 'label': added['label'], 'ready': False}

    @server.tool(annotations=control)
    def close_switch(session_id: str) -> dict:
        """Close a Switch's tab: its script is stopped and its process ends. Settings are kept; the user can reopen
        it from ＋. The last open Switch cannot be closed."""
        return hub_call('switch_close', {'switch': session_id}, session_id)

    @server.tool(annotations=control)
    def rename_switch(session_id: str, label: str) -> dict:
        """Rename a Switch (the tab name, also used in notifications)."""
        return hub_call('switch_rename', {'switch': session_id, 'label': label}, session_id)

    @server.tool(annotations=control)
    def restart_switch(session_id: str) -> dict:
        """Start a Switch's process again, e.g. when it stopped after repeated crashes (switch_state crashed) or
        does not respond. Its script is not resumed; start it again with start_script."""
        return hub_call('switch_restart', {'switch': session_id}, session_id)

    @server.tool(annotations=read_only)
    def list_scripts(session_id: str) -> dict:
        """List Python and MCU script names available in a specific session."""
        catalog = get(session_id).get('catalog', {})
        return {key: catalog.get(key, []) for key in ('python', 'mcu')}

    @server.tool(annotations=read_only)
    def get_logs(session_id: str) -> dict:
        """Read recent log output and current execution state for one session."""
        session = get(session_id)
        return {key: session.get(key) for key in ('profile', 'running', 'paused', 'command', 'log', 'log2')}

    @server.tool(annotations=read_only, structured_output=False)
    def get_capture(session_id: str) -> list[ImageContent]:
        """Get the latest capture image for one session. Fails if no live capture exists."""
        result = call(session_id, 'frame')
        return [ImageContent(type='image', data=result['data'], mime_type=result['mimeType'])]

    @server.tool(annotations=control)
    def start_script(session_id: str, name: str, kind: str = 'python') -> dict:
        """Start an existing script in exactly one session. Returns acceptance, not completion."""
        call(session_id, 'command', {'action': 'start', 'values': {'name': name, 'kind': kind}})
        return {'accepted': True, 'session_id': session_id, 'name': name}

    @server.tool(annotations=control)
    def press_buttons(session_id: str, buttons: list[str], duration: float = 0.1) -> dict:
        """Press controller inputs together for duration seconds (0.08-5), then release.
        Names: A B X Y L R ZL ZR PLUS MINUS HOME CAPTURE LCLICK RCLICK, D-pad UP DOWN LEFT RIGHT,
        sticks LS_UP LS_DOWN LS_LEFT LS_RIGHT RS_UP RS_DOWN RS_LEFT RS_RIGHT.
        Rejected while a script runs or the COM port is closed. Returns acceptance, not completion."""
        call(session_id, 'command', {'action': 'press', 'values': {'buttons': buttons, 'duration': duration}})
        return {'accepted': True, 'buttons': buttons, 'duration': duration}

    @server.tool(annotations=read_only)
    def get_web_url(session_id: str) -> dict:
        """Get the local browser UI URL (live video, buttons, scripts, logs) for one session.
        The URL contains an access token; open it only in a local browser and do not share it."""
        return call(session_id, 'web_url')

    @server.tool(annotations=control)
    def tilt_stick(session_id: str, stick: str, x: int, y: int) -> dict:
        """Hold an analog stick at x/y (0-255 each, 128 = center, y grows downward) until moved again.
        stick is L or R. Send x=128, y=128 to release. Rejected while a script runs or the COM port is closed."""
        call(session_id, 'command', {'action': 'stick', 'values': {'stick': stick.upper(), 'x': x, 'y': y}})
        return {'accepted': True, 'stick': stick.upper(), 'x': x, 'y': y}

    @server.tool(annotations=control)
    def run_sequence(session_id: str, steps: list[dict]) -> dict:
        """Run button presses back to back inside the app, with exact timing. Each step:
        {"buttons": ["A"], "duration": 0.1, "wait": 0.5} (buttons may be empty for a pure wait).
        Up to 200 steps / 600 s. Returns at once; follow progress with get_assist or list_sessions,
        and cancel with cancel_sequence. Rejected while a script runs or the COM port is closed."""
        return call(session_id, 'command', {'action': 'sequence', 'values': {'steps': steps}})

    @server.tool(annotations=control)
    def cancel_sequence(session_id: str) -> dict:
        """Stop a running button sequence and release all inputs."""
        return call(session_id, 'command', {'action': 'sequence_cancel'})

    @server.tool(annotations=read_only)
    def list_templates(session_id: str) -> dict:
        """List template image paths (relative to the Template folder) that find_template can use."""
        return call(session_id, 'templates')

    @server.tool(annotations=read_only)
    def find_template(session_id: str, name: str, threshold: float = 0.85) -> dict:
        """Check whether a Template image is on screen now (grayscale match, like scripts' isContainTemplate).
        Returns found, similarity (0-1) and the best position in capture pixels; the user sees a frame on the video."""
        return call(session_id, 'find_template', {'name': name, 'threshold': threshold})

    @server.tool(annotations=control)
    def set_status(session_id: str, doing: str, task: str = '', progress: str = '') -> dict:
        """Show the user, at the top of their screen, what you are working on. Write for a person watching the game,
        in plain Japanese and game terms, not tool or code terms:
        task = the goal (e.g. "色違いのヒトカゲを厳選"), doing = what is happening in the game now
        (e.g. "タマゴが孵るまで自転車で往復中"), progress = optional count (e.g. "12/50" or "3匹目").
        Update it when the situation changes; call with doing="" and task="" to clear it when you finish."""
        return call(session_id, 'command', {'action': 'status', 'values': {'doing': doing, 'task': task, 'progress': progress}})

    @server.tool(annotations=control)
    def add_note(session_id: str, text: str) -> dict:
        """Leave a note the user will read later in the app (kept per profile). Write it for a person, in plain Japanese:
        what you did in the game, what happened (results, finds, problems), where things stand and what comes next,
        e.g. "ヒトカゲのタマゴを50個孵化。色違いは出ず。ボックス3まで埋まったので、次はボックス4から。"
        Mention similarity scores, coordinates or button sequences only when the user needs them to act."""
        return call(session_id, 'command', {'action': 'note', 'values': {'text': text}})

    @server.tool(annotations=read_only)
    def get_assist(session_id: str) -> dict:
        """Read notes (yours and the user's), the status line, recent assistant activity and the button sequence state."""
        return get(session_id).get('assist', {})

    @server.tool(annotations=read_only)
    def get_dialogs(session_id: str) -> list[dict]:
        """List dialogues a running script is waiting on (title, description, fields with types and defaults)."""
        return get(session_id).get('dialogs', [])

    @server.tool(annotations=control)
    def answer_dialog(session_id: str, dialog_id: int, values: list | None) -> dict:
        """Answer a script dialogue: values in field order, skipping 'next' separators; null cancels it."""
        return call(session_id, 'command', {'action': 'answer', 'values': {'dialog': dialog_id, 'values': values}})

    @server.tool(annotations=control)
    def configure_devices(session_id: str, camera_path: str | None = None, port: str | None = None,
                          serial_format: str | None = None) -> dict:
        """Choose the capture device (path from list_devices; "" for none) and/or connect a COM port (e.g. "COM5")."""
        if camera_path is not None:
            call(session_id, 'command', {'action': 'camera', 'values': {'path': camera_path}})
        if port is not None:
            call(session_id, 'command', {'action': 'connect', 'values': {'port': port, 'format': serial_format}})
        return {'accepted': True}

    @server.tool(annotations=read_only)
    def list_devices(session_id: str) -> dict:
        """List capture devices (name, path) and COM ports on this PC."""
        return call(session_id, 'devices')

    @server.tool(annotations=control)
    def stop_script(session_id: str) -> dict:
        """Request a script to stop. Inspect status afterward to verify it has stopped."""
        call(session_id, 'command', {'action': 'stop'})
        return {'accepted': True}

    @server.tool(annotations=control)
    def pause_script(session_id: str) -> dict:
        """Pause the current script in one session, if running."""
        call(session_id, 'command', {'action': 'suspend'})
        return {'accepted': True}

    @server.tool(annotations=control)
    def resume_script(session_id: str) -> dict:
        """Resume a paused script in one session."""
        call(session_id, 'command', {'action': 'resume'})
        return {'accepted': True}

    # ---- recordings: study gameplay to write scripts ----
    @server.tool(annotations=control)
    def start_recording(session_id: str, seconds: float = 60, fps: float = 5, label: str = '') -> dict:
        """Record the capture video (640x360, up to 10 fps, up to 600 s) together with every controller input sent
        meanwhile, by the user, a script or you. Stops by itself after seconds. label: what is being recorded."""
        return call(session_id, 'command', {'action': 'record_start', 'values': {'seconds': seconds, 'fps': fps, 'label': label}})

    @server.tool(annotations=control)
    def stop_recording(session_id: str) -> dict:
        """Stop the current recording early. Returns its id, frame and input counts."""
        return call(session_id, 'command', {'action': 'record_stop'})

    @server.tool(annotations=read_only)
    def list_recordings(session_id: str) -> dict:
        """Saved recordings (newest first) and the one in progress."""
        return call(session_id, 'recordings')

    @server.tool(annotations=read_only)
    def get_recording_overview(session_id: str, recording: str, start: float = 0, end: float | None = None,
                               count: int = 12) -> list:
        """A contact sheet of up to 24 evenly spaced frames between start and end seconds, each labelled with its
        time, plus a text timeline of the inputs sent between frames. Narrow start/end to look closer."""
        result = call(session_id, 'recording_overview', {'recording': recording, 'start': start, 'end': end, 'count': count})
        return [ImageContent(type='image', data=result['data'], mime_type=result['mimeType']),
                TextContent(type='text', text=result['timeline'] or '(no inputs)')]

    @server.tool(annotations=read_only)
    def get_recording_frame(session_id: str, recording: str, at: float) -> list:
        """One recorded frame (640x360) nearest to at seconds."""
        result = call(session_id, 'recording_frame', {'recording': recording, 'at': at})
        return [ImageContent(type='image', data=result['data'], mime_type=result['mimeType']),
                TextContent(type='text', text=f"{result['at']:.2f}s")]

    @server.tool(annotations=read_only)
    def get_recording_inputs(session_id: str, recording: str, start: float = 0, end: float | None = None) -> dict:
        """Every controller input in a recording (time, input/inputEnd/hold/holdEnd/neutral, button names).
        The time between input and inputEnd is how long a button was held."""
        return call(session_id, 'recording_inputs', {'recording': recording, 'start': start, 'end': end})

    @server.tool(annotations=read_only)
    def draft_script_from_recording(session_id: str, recording: str, name: str, loop: bool = True, start: float = 0,
                                    end: float | None = None, max_wait: float = 3) -> dict:
        """Turn what was done during a recording (your press_buttons / run_sequence / tilt_stick / find_template, or
        the user's input) into a Python script draft: presses with measured durations, waits (capped at max_wait; the
        measured time stays as a comment, since it includes your thinking time), template checks, and an endless loop
        with a counter when loop is true. Not saved: refine it (replace waits with isContainTemplate checks, add the
        stop condition such as a shiny check) and save with write_script."""
        return call(session_id, 'recording_draft', {'recording': recording, 'name': name, 'loop': loop, 'start': start,
                                                    'end': end, 'max_wait': max_wait})

    # ---- scripts and templates ----
    @server.tool(annotations=read_only)
    def list_script_files(session_id: str) -> dict:
        """Python script files under Commands/PythonCommands (paths relative to it)."""
        return call(session_id, 'script_files')

    @server.tool(annotations=read_only)
    def read_script(session_id: str, path: str) -> dict:
        """Read a script file (path relative to Commands/PythonCommands), e.g. to follow an existing one's style."""
        return call(session_id, 'read_script', {'path': path})

    @server.tool(annotations=control)
    def write_script(session_id: str, path: str, content: str, overwrite: bool = False) -> dict:
        """Save a Python script under Commands/PythonCommands (e.g. "Claude/ShinyReset.py") and reload scripts.
        Write a class deriving from ImageProcPythonCommand (or PythonCommand) with a NAME and do(); use
        self.press(Button.A, duration, wait), self.wait(s), self.isContainTemplate("name.png", threshold) and
        print() for progress. Existing files are backed up to Backups/scripts and replaced only with overwrite.
        Returns the script names it registered (use them with start_script) or the load error to fix."""
        return call(session_id, 'command', {'action': 'write_script', 'values': {'path': path, 'content': content,
                                                                                  'overwrite': overwrite}})

    @server.tool(annotations=control)
    def save_template(session_id: str, name: str, x: int, y: int, width: int, height: int, overwrite: bool = False) -> dict:
        """Cut an area of the current capture (pixels of get_capture's image) into Template/<name>.png for
        isContainTemplate. Pick a part that only appears on the screen you want to detect."""
        return call(session_id, 'command', {'action': 'save_template', 'values': {
            'name': name, 'x': x, 'y': y, 'width': width, 'height': height, 'overwrite': overwrite}})

    # ---- watching long runs ----
    @server.tool(annotations=read_only)
    def get_incidents(session_id: str, after: int = 0) -> dict:
        """Incidents after the given id: a script error, the picture frozen (game or Switch hung), the capture device
        or COM port lost, or a script that finished. Each has a saved screen image path. Also returns watch settings."""
        return call(session_id, 'incidents', {'after': after})

    @server.tool(annotations=read_only)
    def wait_for_incident(session_id: str, after: int = 0, timeout: float = 240) -> dict:
        """Wait up to timeout seconds (max 900) for an incident newer than after (use last_id from the previous call),
        to look after a long run. Then check get_capture and recover: close error dialogs, return to HOME and restart
        the game, start the script again. Tell the user what happened with add_note."""
        deadline = time.monotonic() + min(max(float(timeout), 1), 900)
        while True:
            result = call(session_id, 'incidents', {'after': after})
            if result['incidents'] or time.monotonic() >= deadline:
                return {'incidents': result['incidents'], 'last_id': result['watch']['last_id'],
                        'timed_out': not result['incidents']}
            time.sleep(2)

    @server.tool(annotations=control)
    def set_watch(session_id: str, enabled: bool | None = None, freeze_seconds: int | None = None,
                  notify: bool | None = None, auto_restart: bool | None = None, restart_limit: int | None = None) -> dict:
        """Change the watcher: enabled, freeze_seconds (picture unchanged this long while a script runs = frozen;
        0 turns it off; 30-3600), notify (Discord/LINE/Windows as set up in the app), auto_restart (start the script
        again after an error or a freeze) and restart_limit."""
        values = {k: v for k, v in dict(enabled=enabled, freeze_seconds=freeze_seconds, notify=notify,
                                         auto_restart=auto_restart, restart_limit=restart_limit).items() if v is not None}
        return call(session_id, 'command', {'action': 'watch', 'values': values})

    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--endpoint', type=Path, help='Limit to one app (runtime/controller-PID.json); default: all running apps')
    parser.add_argument('--no-autostart', action='store_true', help='Do not start the app in the background when none is running')
    args = parser.parse_args()
    build_server(args.endpoint, autostart=not args.no_autostart).run(transport='stdio')
