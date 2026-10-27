"""Where the app keeps programs, user files, settings and logs. MIT.

Installed copies follow the Windows layout (program, Documents workspace, %APPDATA%, %LOCALAPPDATA%).
A source checkout or a folder with a `portable` marker keeps everything beside the program, as before.
"""
import os
from pathlib import Path
import shutil

PROGRAM = Path(__file__).resolve().parent
APP_NAME = 'PokeController'
PORTABLE = (PROGRAM / 'portable').exists() or (PROGRAM / '.git').exists()
# Folders scripts and images expect relative to the working directory (original SerialController layout).
SEEDED = ('Commands/PythonCommands', 'Commands/McuCommands', 'Template', 'db')


def documents():
    """The user's Documents folder, following OneDrive or other redirection."""
    import ctypes
    from ctypes import wintypes
    folder_id = (ctypes.c_byte * 16).from_buffer_copy(
        bytes.fromhex('d0 9a d3 fd 8f 23 af 46 ad b4 6c 85 48 03 69 c7'))  # FOLDERID_Documents
    path = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(path)) == 0:
        try:
            return Path(path.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(path)
    return Path.home() / 'Documents'


if PORTABLE:
    WORKSPACE = PROGRAM / 'SerialController'
    CONFIG = WORKSPACE
    LOCAL = PROGRAM
else:
    WORKSPACE = documents() / APP_NAME
    CONFIG = Path(os.environ['APPDATA']) / APP_NAME
    LOCAL = Path(os.environ['LOCALAPPDATA']) / APP_NAME

PROFILES = CONFIG / 'profiles'
RUNTIME = LOCAL / 'runtime'  # endpoint files for MCP and the browser page
LOGS = WORKSPACE / 'log' if PORTABLE else LOCAL / 'log'
APP_SETTINGS = (PROGRAM if PORTABLE else CONFIG) / 'app-settings.json'
# Folders the user can open from the app (settings page, menus).
FOLDERS = {'workspace': WORKSPACE, 'scripts': WORKSPACE / 'Commands' / 'PythonCommands', 'captures': WORKSPACE / 'Captures',
           'settings': PROFILES, 'logs': LOGS}


def prepare_workspace():
    """Copy bundled scripts, images and data the user does not have yet; never overwrite their edits."""
    if PORTABLE:
        return
    source = PROGRAM / 'SerialController'
    for name in SEEDED:
        for item in (source / name).rglob('*'):
            if item.is_dir() or '__pycache__' in item.parts:
                continue
            target = WORKSPACE / item.relative_to(source)
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
    for name in ('Captures', 'Controller_Log'):
        (WORKSPACE / name).mkdir(parents=True, exist_ok=True)
