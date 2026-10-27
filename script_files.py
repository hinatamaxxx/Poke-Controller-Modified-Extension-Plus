"""Reading and writing Python scripts and templates in the workspace, so an assistant can author scripts. MIT.

Scripts live in スクリプト (one folder per script, images in its 画像) and, for the bundled samples and older
scripts, Commands/PythonCommands. Paths are relative to スクリプト; "Commands/PythonCommands/..." names the other one.
Only .py files there can be written. An existing file is copied to Backups/scripts first.
"""
import os
import time

SCRIPTS = 'スクリプト'
ROOT = os.path.join('Commands', 'PythonCommands')
LEGACY = 'Commands/PythonCommands/'
MAX_BYTES = 512 * 1024


def _root(legacy=False):
    return os.path.realpath(os.path.join(os.getcwd(), ROOT if legacy else SCRIPTS))


def _split(relative):
    relative = str(relative or '').replace('\\', '/')
    if relative.startswith(LEGACY):
        return True, relative[len(LEGACY):]
    if relative.startswith(SCRIPTS + '/'):
        return False, relative[len(SCRIPTS) + 1:]
    return False, relative


def resolve(relative):
    legacy, rest = _split(relative)
    root = _root(legacy)
    path = os.path.realpath(os.path.join(root, rest))
    if os.path.commonpath([root, path]) != root or path == root:
        raise ValueError('The path must be inside スクリプト (or Commands/PythonCommands)')
    return path


def list_files():
    found = []
    for legacy in (False, True):
        root = _root(legacy)
        for folder, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(('.', '__'))]
            for name in files:
                if name.endswith('.py') and not name.startswith('__'):
                    path = os.path.join(folder, name)
                    relative = os.path.relpath(path, root).replace(os.sep, '/')
                    found.append({'path': (LEGACY if legacy else '') + relative, 'size': os.path.getsize(path)})
    return sorted(found, key=lambda f: (f['path'].startswith(LEGACY), f['path']))


def read(relative):
    path = resolve(relative)
    if not path.endswith('.py'):
        raise ValueError('Only .py files can be read')
    with open(path, encoding='utf-8-sig') as stream:
        return stream.read(MAX_BYTES)


def write(relative, content, overwrite=False):
    """Check the syntax, back up any existing file, and write. Returns the backup path ('' when new)."""
    path = resolve(relative)
    if not path.endswith('.py'):
        raise ValueError('Scripts must be .py files')
    content = str(content)
    if len(content.encode('utf-8')) > MAX_BYTES:
        raise ValueError('The script is too large')
    try:
        compile(content, path, 'exec')
    except SyntaxError as exc:
        raise ValueError(f'Syntax error at line {exc.lineno}: {exc.msg}') from None
    backup = ''
    if os.path.exists(path):
        if not overwrite:
            raise ValueError('The file exists; pass overwrite to replace it')
        folder = os.path.join(os.getcwd(), 'Backups', 'scripts')
        os.makedirs(folder, exist_ok=True)
        name = os.path.relpath(path, os.getcwd())[:-3].replace(os.sep, '_')
        backup = os.path.join(folder, f"{name}-{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}.py")
        with open(path, 'rb') as source, open(backup, 'wb') as target:
            target.write(source.read())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(content)
    return backup


def module_name(relative):
    path = resolve(relative)
    legacy = _split(relative)[0]
    prefix = 'Commands.PythonCommands.' if legacy else SCRIPTS + '.'
    return prefix + os.path.relpath(path[:-3], _root(legacy)).replace(os.sep, '.')


def image_path(name):
    """A template image: relative to Template, or "スクリプト/..." for a script's own 画像 or 共通/画像."""
    name = str(name or '').replace('\\', '/')
    if name.startswith(SCRIPTS + '/'):
        root, name = _root(), name[len(SCRIPTS) + 1:]
    else:
        root = os.path.realpath(os.path.join(os.getcwd(), 'Template'))
    path = os.path.realpath(os.path.join(root, name))
    if os.path.commonpath([root, path]) != root or path == root:
        raise ValueError('The image must be inside Template or スクリプト')
    return path


def image_names():
    """Images find_template can use: Template ones by their name there, the others as "スクリプト/..."."""
    found = []
    for prefix, root in (('', os.path.join(os.getcwd(), 'Template')), (SCRIPTS + '/', _root())):
        for folder, _, files in os.walk(root):
            for name in files:
                if name.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
                    found.append(prefix + os.path.relpath(os.path.join(folder, name), root).replace(os.sep, '/'))
                    if len(found) >= 2000:
                        return sorted(found)
    return sorted(found)


def save_template(frame, name, x, y, width, height, overwrite=False):
    """Crop the current frame (camera pixels) into an image for isContainTemplate: Template/<name>, or a script's
    画像 with "スクリプト/<script folder>/画像/<name>.png"."""
    import cv2
    path = image_path(name)
    if not path.lower().endswith('.png'):
        raise ValueError('The template must be a .png')
    x, y, width, height = (int(v) for v in (x, y, width, height))
    h, w = frame.shape[:2]
    if width < 4 or height < 4 or x < 0 or y < 0 or x + width > w or y + height > h:
        raise ValueError(f'The area must fit inside the {w}x{h} frame')
    if os.path.exists(path) and not overwrite:
        raise ValueError('The template exists; pass overwrite to replace it')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ok, encoded = cv2.imencode('.png', frame[y:y + height, x:x + width])  # imwrite cannot take non-ASCII paths
    if not ok:
        raise ValueError('Could not save the template')
    with open(path, 'wb') as stream:
        stream.write(encoded.tobytes())
    return str(name).replace('\\', '/')
