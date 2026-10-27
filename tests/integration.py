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
        assert len(tools.tools) == 36
        session = call(endpoint, 'sessions')[0]
        sid = session['id']
        demo_name = next(name for name in session['catalog']['python'] if name.startswith('PortableDemo /'))
        for tool, params in [('list_sessions', {}), ('list_scripts', {'session_id': sid}),
                             ('get_capture', {'session_id': sid}), ('get_web_url', {'session_id': sid}),
                             ('press_buttons', {'session_id': sid, 'buttons': ['A', 'UP', 'LS_LEFT']}),
                             ('start_script', {'session_id': sid, 'name': demo_name})]:
            result = await client.call_tool(tool, params)
            assert not result.is_error, (tool, result)
        until(lambda: call(endpoint, 'sessions')[0]['running'])
        result = await client.call_tool('press_buttons', {'session_id': sid, 'buttons': ['A']})
        assert result.is_error, 'Manual input must be rejected while a script runs'
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


def browser(endpoint):
    """Exercise the browser UI: token login, cookie auth, host checks, state, frames and input."""
    # curl, like a browser, is not intercepted by security software that breaks Python's loopback HTTP
    # (AdGuard's localhost filtering stalls large responses to Python clients).
    web_url = json.loads(Path(endpoint).read_text(encoding='utf-8'))['web_url']
    base = web_url.split('?')[0]
    jar = Path(tempfile.mkdtemp()) / 'cookies.txt'

    def status(url, data=None, headers=None):
        command = ['curl.exe', '-s', '--max-time', '10', '-b', str(jar), '-c', str(jar), '-o', '-', '-w', '\n%{http_code}']
        for key, value in (headers or {}).items():
            command += ['-H', f'{key}: {value}']
        if data is not None:
            command += ['--data-binary', '@-']
        for attempt in range(4):
            result = subprocess.run(command + [url], input=data, capture_output=True)
            if result.returncode == 0:
                body, _, code = result.stdout.rpartition(b'\n')
                return int(code), body
            time.sleep(.2)
        raise AssertionError(f'curl failed: {result.returncode}')

    assert status(base)[0] == 403, 'Page must require the token'
    assert status(base + '?token=wrong')[0] == 403
    assert status(base + 'api/state')[0] == 403
    assert status(web_url)[0] == 303, 'The token link must set the cookie and redirect'
    code, page = status(base)
    assert code == 200 and b'<title>' in page
    assert status(base, headers={'Host': 'evil.example'})[0] == 403, 'Host header must be checked'
    code, body = status(base + 'api/state')
    assert code == 200 and json.loads(body)['result']['serial_open']
    code, frame = status(base + 'frame.jpg')
    assert code == 200 and frame[:2] == b'\xff\xd8'
    def post(params, origin=base.rstrip('/')):
        return status(base + 'api/call', data=json.dumps({'method': 'command', 'params': params}).encode(),
                      headers={'Content-Type': 'application/json', 'Origin': origin})
    assert post({'action': 'hold', 'values': {'buttons': ['B']}})[0] == 200
    until(lambda: json.loads(status(base + 'api/state')[1])['result']['held'] == ['B'])
    assert post({'action': 'release', 'values': {'buttons': ['B']}})[0] == 200
    until(lambda: json.loads(status(base + 'api/state')[1])['result']['held'] == [])
    assert post({'action': 'neutral'}, origin='http://evil.example')[0] == 403, 'Origin must be checked'
    code, body = post({'action': 'press', 'values': {'buttons': ['NOPE']}})
    assert code == 200 and not json.loads(body)['ok']


async def autostart(command, args):
    """With no app running, the MCP server starts one in the background on first use."""
    from mcp.client import Client
    from mcp.client.stdio import StdioServerParameters
    runtime = ROOT / 'runtime'
    assert not any(runtime.glob('controller-*.json')), 'another app is still running'
    async with Client(StdioServerParameters(command=command, args=args)) as client:
        result = await client.call_tool('list_sessions', {})
        assert not result.is_error, result
    endpoint = next(runtime.glob('controller-*.json'))
    session = call(endpoint, 'sessions')[0]
    call(endpoint, 'command', {'id': session['id'], 'action': 'quit'})
    until(lambda: not endpoint.exists(), timeout=20)


def main():
    with tempfile.TemporaryDirectory(prefix='poke-qa-') as temporary:
        report = Path(temporary) / 'report.json'
        profile = 'qa-' + uuid.uuid4().hex[:8]
        command = [sys.executable, str(ROOT / 'app.py')]
        mcp_command, mcp_args = sys.executable, [str(ROOT / 'controller_mcp.py')]
        process = subprocess.Popen(command + ['--demo', '--profile', profile, '--smoke-test', str(report)])
        try:
            until(lambda: report.exists() or process.poll() is not None, timeout=45)
            assert report.exists(), f'App failed: {process.returncode}'
            state = json.loads(report.read_text())
            endpoint = Path(state['mcp_endpoint'])
            assert state['python_scripts'] >= 30 and state['mcu_scripts'] == 4
            assert json.loads(endpoint.read_text())['pipe'], 'local calls must use the named pipe'
            try:
                call(endpoint, 'sessions', token_override='invalid')
                raise AssertionError('Missing authentication')
            except PermissionError:
                pass
            browser(endpoint)
            asyncio.run(protocol(mcp_command, mcp_args, endpoint))  # discovers running apps without --endpoint
        finally:
            report.with_suffix('.stop').touch()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                raise
        asyncio.run(autostart(mcp_command, mcp_args))
        print('PASS: window-less startup, authentication, browser UI, 36 MCP tools, capture, button input, '
              'start/pause/resume/stop, logs, error handling, background autostart', flush=True)


if __name__ == '__main__':
    main()
