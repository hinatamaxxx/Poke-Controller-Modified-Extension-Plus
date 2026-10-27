"""Where the app keeps programs, user files, settings and logs. MIT.

Installed copies follow the Windows layout (program, Documents workspace, %APPDATA%, %LOCALAPPDATA%).
A source checkout or a folder with a `portable` marker keeps everything beside the program, as before.
"""
import json
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
    DEFAULT_WORKSPACE = PROGRAM / 'SerialController'
    CONFIG = DEFAULT_WORKSPACE
    LOCAL = PROGRAM
else:
    DEFAULT_WORKSPACE = documents() / APP_NAME
    CONFIG = Path(os.environ['APPDATA']) / APP_NAME
    LOCAL = Path(os.environ['LOCALAPPDATA']) / APP_NAME
WORKSPACE = DEFAULT_WORKSPACE

PROFILES = CONFIG / 'profiles'
RUNTIME = LOCAL / 'runtime'  # endpoint files for MCP and the browser page
LOGS = DEFAULT_WORKSPACE / 'log' if PORTABLE else LOCAL / 'log'
APP_SETTINGS = (PROGRAM if PORTABLE else CONFIG) / 'app-settings.json'
# Folders the user moved (settings: フォルダー); missing keys keep the defaults.
FOLDER_CHOICES = (PROGRAM if PORTABLE else CONFIG) / 'folders.json'
CHOOSABLE = ('workspace', 'captures')


def folder_choices():
    try:
        data = json.loads(FOLDER_CHOICES.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if k in CHOOSABLE and isinstance(v, str) and v} if isinstance(data, dict) else {}


def apply_folder_choices():
    """Set WORKSPACE, CAPTURES and FOLDERS from the user's choices (at start, and in the hub after a change)."""
    global WORKSPACE, CAPTURES, FOLDERS
    chosen = folder_choices()
    WORKSPACE = Path(chosen['workspace']) if chosen.get('workspace') else DEFAULT_WORKSPACE
    CAPTURES = Path(chosen['captures']) if chosen.get('captures') else WORKSPACE / 'Captures'
    # Folders the user can open from the app (settings page, menus).
    FOLDERS = {'workspace': WORKSPACE, 'scripts': WORKSPACE / 'Commands' / 'PythonCommands', 'captures': CAPTURES,
               'settings': PROFILES, 'logs': LOGS}


def captures_dir():
    """Where screenshots, recordings and watch records go: the chosen folder, or Captures in the working directory
    (the work folder, which every process changes into)."""
    return str(CAPTURES) if folder_choices().get('captures') else os.path.join(os.getcwd(), 'Captures')


def choose_folder(name, path):
    """Remember a folder (None goes back to the default). A new work folder that is empty gets the current one's
    contents, so the user's scripts and images come along."""
    from safe_settings import write_text
    if name not in CHOOSABLE:
        raise ValueError('Unknown folder')
    chosen = folder_choices()
    if path:
        target = Path(path).resolve()
        if name == 'workspace' and target != WORKSPACE.resolve():
            if target.exists() and any(target.iterdir()):
                pass  # an existing folder is used as it is
            else:
                shutil.copytree(WORKSPACE, target, dirs_exist_ok=True)
        target.mkdir(parents=True, exist_ok=True)
        chosen[name] = str(target)
    else:
        chosen.pop(name, None)
    FOLDER_CHOICES.parent.mkdir(parents=True, exist_ok=True)
    write_text(FOLDER_CHOICES, json.dumps(chosen, ensure_ascii=False, indent=1))
    apply_folder_choices()


apply_folder_choices()


def prepare_workspace():
    """Copy bundled scripts, images and data the user does not have yet; never overwrite their edits."""
    if PORTABLE:
        CAPTURES.mkdir(parents=True, exist_ok=True)
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
    (WORKSPACE / 'Controller_Log').mkdir(parents=True, exist_ok=True)
    CAPTURES.mkdir(parents=True, exist_ok=True)
