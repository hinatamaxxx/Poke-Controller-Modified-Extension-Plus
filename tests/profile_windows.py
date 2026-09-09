"""Check simultaneous launch of real packaged windows without using hardware."""
import json
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

package = Path(__file__).resolve().parents[1] / 'dist/PokeController-initial-alpha1'
name = 'qa-' + uuid.uuid4().hex[:12]
with tempfile.TemporaryDirectory() as folder:
    reports = [Path(folder) / f'{i}.json' for i in range(2)]
    processes = []
    try:
        for report in reports:
            processes.append(subprocess.Popen([str(package / 'PokeController.exe'), '--profile', name,
                                              '--demo', '--no-mcp', '--smoke-test', str(report)], cwd=package))
        deadline = time.monotonic() + 40
        while not all(report.exists() for report in reports) and time.monotonic() < deadline:
            time.sleep(.1)
        assert all(report.exists() for report in reports), 'Both windows must start without a dialog'
        profiles = {json.loads(report.read_text())['profile'] for report in reports}
        assert profiles == {name, name + '-2'}, profiles
        print('PASS: two packaged windows started with separate automatic settings slots')
    finally:
        for report in reports:
            report.with_suffix('.stop').touch()
        for process in processes:
            process.wait(timeout=20)
