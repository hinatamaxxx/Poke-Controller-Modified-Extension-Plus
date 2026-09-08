"""Verify two packaged profiles run independently without physical controller input."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controller_api import call
from integration import until

package = Path(sys.argv[1]).resolve()
processes, reports, endpoints = [], [], []
with tempfile.TemporaryDirectory(prefix='poke-multi-') as folder:
    try:
        for number in range(2):
            report = Path(folder) / f'{number}.json'
            profile = 'qa-multi-' + uuid.uuid4().hex[:8]
            processes.append(subprocess.Popen([str(package / 'PokeController.exe'), '--profile', profile,
                                               '--demo', '--mcp', '--smoke-test', str(report)]))
            reports.append(report)
        for report in reports:
            until(report.exists, timeout=45)
            endpoints.append(Path(json.loads(report.read_text())['mcp_endpoint']))
        descriptors = [json.loads(path.read_text()) for path in endpoints]
        assert descriptors[0]['url'] != descriptors[1]['url']
        assert descriptors[0]['token'] != descriptors[1]['token']
        sessions = [call(path, 'sessions')[0] for path in endpoints]
        assert sessions[0]['id'] != sessions[1]['id']
        def command(number, action):
            session = sessions[number]
            name = next(name for name in session['catalog']['python'] if name.startswith('PortableDemo /'))
            return call(endpoints[number], 'command', {'id': session['id'], 'action': action,
                                                      'values': {'kind': 'python', 'name': name}})
        command(0, 'start')
        until(lambda: call(endpoints[0], 'sessions')[0]['running'])
        assert not call(endpoints[1], 'sessions')[0]['running']
        command(1, 'start')
        until(lambda: call(endpoints[1], 'sessions')[0]['running'])
        command(0, 'suspend')
        assert call(endpoints[0], 'sessions')[0]['paused']
        assert not call(endpoints[1], 'sessions')[0]['paused']
        command(0, 'stop')
        until(lambda: not call(endpoints[0], 'sessions')[0]['running'])
        assert call(endpoints[1], 'sessions')[0]['running']
        try:
            call(endpoints[1], 'sessions', token_override=descriptors[0]['token'])
            raise AssertionError('Cross-instance token accepted')
        except HTTPError as error:
            assert error.code == 403
        print('PASS: two EXEs, distinct profiles/endpoints/tokens, independent start/pause/stop, cross-token rejection')
    finally:
        for report in reports:
            report.with_suffix('.stop').touch()
        for process in processes:
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                raise
