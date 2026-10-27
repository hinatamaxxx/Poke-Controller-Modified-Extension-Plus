"""MCP stdio adapter for running Poke Controller Plus instances."""
import argparse
from pathlib import Path
import subprocess
import sys
import time

from mcp.server import MCPServer
from mcp.types import ImageContent, ToolAnnotations
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
    except OSError:
        subprocess.Popen(command, creationflags=flags, **options)  # the job forbids breakaway


def build_server(endpoint_path=None, autostart=True):
    server = MCPServer(NAME, instructions=(
        'Use list_sessions to identify the exact session before any operation. '
        'Run timing-sensitive work as an existing Python script. '
        'After starting a script, inspect its status and logs; an accepted start is not completion. '
        'For manual play, use press_buttons and check the result with get_capture. '
        'The app has no window of its own: get_web_url returns the page to open in a browser to watch and operate it, '
        'including settings (camera, COM port) and dialogues that scripts show.'))
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
            return local_call(routes[session_id], method, {**(params or {}), 'id': session_id})
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
        """List open controller sessions (one per app window) with IDs and status.
        Starts the app in the background when none is running."""
        keys = ('id', 'profile', 'ready', 'running', 'paused', 'command', 'camera_live', 'serial_open', 'demo', 'exited')
        return [{k: s.get(k) for k in keys} for s in sessions()]

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

    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--endpoint', type=Path, help='Limit to one app (runtime/controller-PID.json); default: all running apps')
    parser.add_argument('--no-autostart', action='store_true', help='Do not start the app in the background when none is running')
    args = parser.parse_args()
    build_server(args.endpoint, autostart=not args.no_autostart).run(transport='stdio')
