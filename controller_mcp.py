"""MCP stdio adapter for an already-running Poke Controller Plus instance."""
import argparse
from pathlib import Path

from mcp.server import MCPServer
from mcp.types import ImageContent, ToolAnnotations
from product import NAME


def build_server(endpoint_path=None):
    server = MCPServer(NAME, instructions=(
        'Use list_sessions to identify the exact session before any operation. '
        'Run timing-sensitive work as an existing Python script. '
        'After starting a script, inspect its status and logs; an accepted start is not completion.'))
    read_only = ToolAnnotations(read_only_hint=True, open_world_hint=False)
    control = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)

    def call(method, params=None):
        from controller_api import call as local_call
        from mcp.server.mcpserver.exceptions import ToolError
        try:
            selected = endpoint_path
            if selected is None:
                active = []
                for candidate in (Path(__file__).resolve().parent / 'runtime').glob('controller-*.json'):
                    try:
                        local_call(candidate, 'sessions')
                        active.append(candidate)
                    except (OSError, ValueError):
                        continue
                if len(active) != 1:
                    raise ValueError('アプリを1つ起動してください。複数起動時は --endpoint で接続先を指定してください。')
                selected = active[0]
            return local_call(selected, method, params)
        except (ValueError, OSError) as exc:
            raise ToolError(str(exc)) from exc

    def get(session_id):
        sessions = call('sessions')
        for session in sessions:
            if session['id'] == session_id:
                return session
        from mcp.server.mcpserver.exceptions import ToolError
        raise ToolError('Session not found')

    @server.tool(annotations=read_only)
    def list_sessions() -> list[dict]:
        """List open controller sessions, their stable IDs and execution status."""
        keys = ('id', 'profile', 'ready', 'running', 'paused', 'command', 'camera_live', 'demo', 'exited')
        return [{k: s.get(k) for k in keys} for s in call('sessions')]

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
        result = call('frame', {'id': session_id})
        return [ImageContent(type='image', data=result['data'], mime_type=result['mimeType'])]

    @server.tool(annotations=control)
    def start_script(session_id: str, name: str, kind: str = 'python') -> dict:
        """Start an existing script in exactly one session. Returns acceptance, not completion."""
        call('command', {'id': session_id, 'action': 'start', 'values': {'name': name, 'kind': kind}})
        return {'accepted': True, 'session_id': session_id, 'name': name}

    @server.tool(annotations=control)
    def stop_script(session_id: str) -> dict:
        """Request a script to stop. Inspect status afterward to verify it has stopped."""
        call('command', {'id': session_id, 'action': 'stop'})
        return {'accepted': True}

    @server.tool(annotations=control)
    def pause_script(session_id: str) -> dict:
        """Pause the current script in one session, if running."""
        call('command', {'id': session_id, 'action': 'suspend'})
        return {'accepted': True}

    @server.tool(annotations=control)
    def resume_script(session_id: str) -> dict:
        """Resume a paused script in one session."""
        call('command', {'id': session_id, 'action': 'resume'})
        return {'accepted': True}

    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--endpoint', type=Path)
    args = parser.parse_args()
    build_server(args.endpoint).run(transport='stdio')
