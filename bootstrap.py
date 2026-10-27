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
try:
    runpy.run_path(str(root / script), run_name='__main__')
except Exception:
    # pythonw has no console, so an import or startup failure would otherwise vanish silently.
    import traceback
    log = root / 'startup-error.log'
    log.write_text(traceback.format_exc(), encoding='utf-8')
    if script == 'app.py':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, f'起動できませんでした。詳細は次のファイルを確認してください。\n{log}',
                                         'Poke-Controller', 0x10)
    raise SystemExit(1)
