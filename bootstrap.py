"""Establish a trusted module path while ignoring machine/user Python settings."""
from pathlib import Path
import runpy
import sys

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root))
script = sys.argv.pop(1)
if script not in ('app.py', 'controller_mcp.py'):
    raise SystemExit('Unknown entrypoint')
sys.argv[0] = str(root / script)
runpy.run_path(str(root / script), run_name='__main__')
