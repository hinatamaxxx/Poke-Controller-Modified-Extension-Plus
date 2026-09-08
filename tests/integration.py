"""Exercise actual packaged EXEs and MCP protocol without physical input."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controller_api import call


def until(callback, timeout=25):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = callback()
        if result:
            return result
        time.sleep(.1)
    raise AssertionError('Condition timed out')


async def protocol(command, args, endpoint):
    from mcp.client import Client
    from mcp.client.stdio import StdioServerParameters
    async with Client(StdioServerParameters(command=command, args=args)) as client:
        tools = await client.list_tools()
        assert len(tools.tools) == 8
        session = call(endpoint, 'sessions')[0]
        sid = session['id']
        demo_name = next(name for name in session['catalog']['python'] if name.startswith('PortableDemo /'))
        for tool, params in [('list_sessions', {}), ('list_scripts', {'session_id': sid}),
                             ('get_capture', {'session_id': sid}),
                             ('start_script', {'session_id': sid, 'name': demo_name})]:
            result = await client.call_tool(tool, params)
            assert not result.is_error, (tool, result)
        until(lambda: call(endpoint, 'sessions')[0]['running'])
        for tool, paused in [('pause_script', True), ('resume_script', False)]:
            result = await client.call_tool(tool, {'session_id': sid})
            assert not result.is_error, result
            assert call(endpoint, 'sessions')[0]['paused'] == paused
        until(lambda: any('PortableDemo:' in value for key, value in call(endpoint, 'sessions')[0].items() if key in ('log', 'log2')))
        result = await client.call_tool('get_logs', {'session_id': sid})
        assert not result.is_error
        result = await client.call_tool('stop_script', {'session_id': sid})
        assert not result.is_error
        until(lambda: not call(endpoint, 'sessions')[0]['running'])
        result = await client.call_tool('start_script', {'session_id': sid, 'name': 'missing'})
        assert result.is_error
        result = await client.call_tool('get_capture', {'session_id': 'wrong'})
        assert result.is_error
        # Leave a script running to verify cooperative application shutdown.
        result = await client.call_tool('start_script', {'session_id': sid, 'name': demo_name})
        assert not result.is_error
        until(lambda: call(endpoint, 'sessions')[0]['running'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path)
    parser.add_argument('--mcp-disabled', action='store_true')
    options = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='poke-qa-') as temporary:
        report = Path(temporary) / 'report.json'
        profile = 'qa-' + uuid.uuid4().hex[:8]
        if options.package:
            command = [str(options.package / 'PokeController.exe')]
            mcp_command, mcp_args = str(options.package / 'PokeControllerMCP.exe'), []
        else:
            command = [sys.executable, str(ROOT / 'app.py')]
            mcp_command, mcp_args = sys.executable, [str(ROOT / 'controller_mcp.py')]
        env = os.environ.copy()
        if options.package:
            env.update(PYTHONHOME='C:\\nonexistent-python', PYTHONPATH='C:\\nonexistent-python',
                       PATH=os.path.join(os.environ['WINDIR'], 'System32'))
        if not options.mcp_disabled:
            command += ['--mcp']
        process = subprocess.Popen(command + ['--demo', '--profile', profile,
                                   '--smoke-test', str(report)], env=env)
        try:
            until(lambda: report.exists() or process.poll() is not None, timeout=45)
            assert report.exists(), f'App failed: {process.returncode}'
            state = json.loads(report.read_text())
            if options.mcp_disabled:
                assert state['mcp_endpoint'] is None
                print('PASS: MCP is disabled by default', flush=True)
                return
            endpoint = Path(state['mcp_endpoint'])
            assert state['python_scripts'] >= 30 and state['mcu_scripts'] == 4
            if options.package:
                assert Path(state['python']).is_relative_to(options.package)
            from urllib.error import HTTPError
            try:
                call(endpoint, 'sessions', token_override='invalid')
                raise AssertionError('Missing authentication')
            except HTTPError as exc:
                assert exc.code == 403
            asyncio.run(protocol(mcp_command, mcp_args + ['--endpoint', str(endpoint)], endpoint))
            print('PASS: app startup, bundled runtime, authentication, eight MCP tools, capture, start/pause/resume/stop, logs, error handling', flush=True)
        finally:
            report.with_suffix('.stop').touch()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                raise


if __name__ == '__main__':
    main()
