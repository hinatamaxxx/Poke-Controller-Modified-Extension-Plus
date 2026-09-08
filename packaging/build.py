"""Build a portable CPython distribution from a dedicated Windows build venv."""
from pathlib import Path
import hashlib
import importlib.metadata as metadata
import json
import os
import shutil
import subprocess
import sys
import zipfile
import argparse
import tarfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist' / 'PokeController'


def build():
    if sys.prefix == sys.base_prefix:
        raise RuntimeError('Run this using the dedicated build .venv')
    assert OUT.resolve().parent == ROOT.resolve() / 'dist'
    if OUT.exists():
        raise RuntimeError('Build output already exists. Move it aside before rebuilding.')
    OUT.mkdir(parents=True)
    runtime = OUT / 'runtime-python'
    base = Path(sys.base_prefix)
    runtime.mkdir()
    for item in base.iterdir():
        if item.is_file() and (item.suffix in ('.exe', '.dll', '.txt')):
            shutil.copy2(item, runtime / item.name)
    for name in ('Lib', 'DLLs', 'tcl'):
        shutil.copytree(base / name, runtime / name, ignore=shutil.ignore_patterns(
            'site-packages', '__pycache__', '*.pyc', 'test', 'tests', 'idlelib', 'ensurepip'))
    site = runtime / 'Lib' / 'site-packages'
    shutil.copytree(Path(sys.prefix) / 'Lib' / 'site-packages', site, ignore=shutil.ignore_patterns(
        '__pycache__', '*.pyc', 'tests', 'test'))
    # Keep original pygame and OpenCV plugins intact for script/media compatibility.
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    for name in tracked:
        if not name or name.startswith(('.git', 'packaging/', 'tests/')) or set(Path(name).parts) & {'profiles', 'log', 'runtime', 'Captures', 'Controller_Log'}:
            continue
        source = ROOT / name
        if source.is_file():
            target = OUT / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    licenses = OUT / 'licenses'
    licenses.mkdir(exist_ok=True)
    shutil.copytree(ROOT / 'packaging' / 'sources', licenses / 'sources')
    # pygame's Windows wheel omits its license directory; copy from the matching sdist.
    with tarfile.open(ROOT / 'packaging/sources/pygame-2.6.1.tar.gz') as source:
        for member in source.getmembers():
            if member.isfile() and (member.name.startswith('pygame-2.6.1/docs/licenses/') or member.name in ('pygame-2.6.1/docs/LGPL.txt', 'pygame-2.6.1/README.rst')):
                target = licenses / 'pygame' / Path(member.name).name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.extractfile(member).read())
    inventory = []
    for dist in metadata.distributions(path=[str(site)]):
        name = dist.metadata['Name']
        inventory.append({'name': name, 'version': dist.version,
                          'license': dist.metadata.get('License-Expression') or dist.metadata.get('License', '')})
        for file in dist.files or []:
            if any(word in file.name.lower() for word in ('license', 'copying', 'notice')):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    target = licenses / name / str(file).replace('../', '')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    shutil.copy2(base / 'LICENSE.txt', licenses / 'Python-LICENSE.txt')
    (licenses / 'dependencies.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8')
    compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET' / 'Framework64' / 'v4.0.30319' / 'csc.exe'
    for name, mode in [('PokeController', '/target:winexe'), ('PokeControllerMCP', '/define:MCP')]:
        subprocess.run([str(compiler), '/nologo', '/optimize+', mode,
                        '/out:' + str(OUT / (name + '.exe')), str(ROOT / 'packaging/Launcher.cs')], check=True)
    forbidden = [p for p in OUT.rglob('*') if any(word in p.name.lower() for word in (
        'directshowlib', 'pythonnet'))]
    if forbidden:
        raise RuntimeError('Excluded dependency present: ' + str(forbidden))
    print(OUT)


def archive():
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    (OUT / 'BUILD_INFO.txt').write_text(f'Source commit: {revision}\nBuild Python: {sys.version}\n', encoding='utf-8')
    release = ROOT / 'release'
    release.mkdir(exist_ok=True)
    target = release / 'PokeController-portable-win64.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in OUT.rglob('*'):
            relative = path.relative_to(OUT)
            if path.is_file() and not set(relative.parts) & {'profiles', 'log', 'runtime', '__pycache__', 'Captures', 'Controller_Log', '.runtime-updates'} and not relative.name.startswith('runtime-choice.txt'):
                z.write(path, Path('PokeController') / relative)
    digest = hashlib.file_digest(target.open('rb'), 'sha256').hexdigest()
    target.with_suffix('.zip.sha256').write_text(f'{digest}  {target.name}\n', encoding='ascii')
    print(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-name', default='PokeController')
    parser.add_argument('--archive-only', action='store_true')
    options = parser.parse_args()
    if not options.output_name or Path(options.output_name).name != options.output_name or options.output_name in ('.', '..'):
        parser.error('output-name must be a directory name')
    OUT = ROOT / 'dist' / options.output_name
    if not options.archive_only:
        build()
    archive()
