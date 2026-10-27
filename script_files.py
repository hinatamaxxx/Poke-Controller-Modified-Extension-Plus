"""Reading and writing Python scripts and templates in the workspace, so an assistant can author scripts. MIT.

Only Commands/PythonCommands/**.py can be written. An existing file is copied to Backups/scripts first.
"""
import os
import time

ROOT = os.path.join('Commands', 'PythonCommands')
MAX_BYTES = 512 * 1024


def _root():
    return os.path.realpath(os.path.join(os.getcwd(), ROOT))


def resolve(relative):
    root = _root()
    path = os.path.realpath(os.path.join(root, str(relative or '')))
    if os.path.commonpath([root, path]) != root or path == root:
        raise ValueError('The path must be inside Commands/PythonCommands')
    return path


def list_files():
    root, found = _root(), []
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(('.', '__'))]
        for name in files:
            if name.endswith('.py') and not name.startswith('__'):
                path = os.path.join(folder, name)
                found.append({'path': os.path.relpath(path, root).replace(os.sep, '/'), 'size': os.path.getsize(path)})
    return sorted(found, key=lambda f: f['path'])


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
        name = os.path.relpath(path, _root())[:-3].replace(os.sep, '_')
        backup = os.path.join(folder, f"{name}-{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}.py")
        with open(path, 'rb') as source, open(backup, 'wb') as target:
            target.write(source.read())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(content)
    return backup


def module_name(relative):
    path = resolve(relative)
    return 'Commands.PythonCommands.' + os.path.relpath(path[:-3], _root()).replace(os.sep, '.')


def save_template(frame, name, x, y, width, height, overwrite=False):
    """Crop the current frame (camera pixels) into the Template folder for isContainTemplate."""
    import cv2
    root = os.path.realpath(os.path.join(os.getcwd(), 'Template'))
    path = os.path.realpath(os.path.join(root, str(name)))
    if os.path.commonpath([root, path]) != root or not path.lower().endswith('.png'):
        raise ValueError('The template must be a .png inside the Template folder')
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
    return os.path.relpath(path, root).replace(os.sep, '/')
