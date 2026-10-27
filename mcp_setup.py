"""Build MCP client registrations for this installation. MIT."""
import json
import os
from pathlib import Path
import subprocess
import sys
from safe_settings import read_checked, write_text

SERVER_NAME = 'poke-controller'


def server_entry(root):
    """Command for this copy: the packaged exe, or the source checkout's Python."""
    root = Path(root).resolve()
    exe = root / 'PokeControllerMCP.exe'
    if exe.is_file():
        return {'command': str(exe), 'args': []}
    python = Path(sys.executable)
    if python.name.lower() == 'pythonw.exe':
        python = python.with_name('python.exe')  # stdio needs a console interpreter
    return {'command': str(python), 'args': [str(root / 'controller_mcp.py')]}


def config_json(root):
    return json.dumps({'mcpServers': {SERVER_NAME: server_entry(root)}}, indent=2, ensure_ascii=False)


def claude_code_command(root):
    entry = server_entry(root)
    return subprocess.list2cmdline(['claude', 'mcp', 'add', '--scope', 'user', SERVER_NAME, '--',
                                    entry['command'], *entry['args']])


def desktop_configs():
    """Existing Claude Desktop config files (standard and packaged installs)."""
    found = []
    appdata, local = os.environ.get('APPDATA'), os.environ.get('LOCALAPPDATA')
    if appdata:
        found.append(Path(appdata) / 'Claude' / 'claude_desktop_config.json')
    if local:
        found += sorted((Path(local) / 'Claude-Data').glob('*/claude_desktop_config.json'))
        found += sorted((Path(local) / 'Packages').glob('Claude_*/LocalCache/Roaming/Claude/claude_desktop_config.json'))
    return [path for path in found if path.is_file()]


def register_desktop(path, root):
    """Add or replace this server in a Claude Desktop config, keeping other settings and a .bak copy."""
    def parse(text):
        data = json.loads(text) if text.strip() else {}
        if not isinstance(data, dict) or not isinstance(data.get('mcpServers', {}), dict):
            raise ValueError('Unexpected Claude Desktop config format')
        return data
    data = read_checked(path, parse)
    data.setdefault('mcpServers', {})[SERVER_NAME] = server_entry(root)
    write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + '\n')
