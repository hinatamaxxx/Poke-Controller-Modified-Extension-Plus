"""Build the release ZIP: app files, the tray app, the MCP launcher and install scripts. Python is set up at install time."""
from pathlib import Path
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / 'packaging'
EXCLUDED_PARTS = {'profiles', 'log', 'runtime', 'Captures', 'Controller_Log', '__pycache__'}
# The fork origin's own launchers, uv setup, docs and tests stay in the repository (so its updates merge cleanly)
# but are not part of this app's install.
UPSTREAM_ONLY = ('bootstrap/', 'docs/', 'SerialController/tests/', 'pyproject.toml', 'uv.lock', 'ruff.toml',
                 'requirements-web.txt', '.python-version', 'CONTRIBUTING.md')


def version():
    return re.search(r"VERSION = '([^']+)'", (ROOT / 'product.py').read_text(encoding='utf-8-sig')).group(1)


def compile_launchers(out):
    icon = out / 'PokeController.ico'
    subprocess.run([sys.executable, str(PACKAGING / 'make_icon.py'), str(icon)], check=True)
    numeric = re.match(r'(\d+\.\d+\.\d+)', version()).group(1) + '.0'
    info = out / 'AssemblyInfo.cs'
    info.write_text(
        'using System.Reflection;\n'
        '[assembly: AssemblyTitle("Poke-Controller")]\n'
        '[assembly: AssemblyProduct("Poke-Controller Modified Extension Plus")]\n'
        '[assembly: AssemblyCompany("hinatamaxxx")]\n'
        f'[assembly: AssemblyVersion("{numeric}")]\n'
        f'[assembly: AssemblyFileVersion("{numeric}")]\n'
        f'[assembly: AssemblyInformationalVersion("{version()}")]\n', encoding='utf-8')
    compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET' / 'Framework64' / 'v4.0.30319' / 'csc.exe'
    common = [str(compiler), '/nologo', '/optimize+', '/codepage:65001', '/win32icon:' + str(icon),
              '/win32manifest:' + str(PACKAGING / 'app.manifest')]
    # The tray app: notification area icon, the WebView2 window and the install/uninstall screens.
    webview2 = PACKAGING / 'webview2'
    references = ['System.dll', 'System.Drawing.dll', 'System.Windows.Forms.dll', 'System.Web.Extensions.dll',
                  str(webview2 / 'Microsoft.Web.WebView2.Core.dll'), str(webview2 / 'Microsoft.Web.WebView2.WinForms.dll')]
    sources = sorted(str(path) for path in (PACKAGING / 'tray').glob('*.cs'))
    subprocess.run(common + ['/target:winexe', '/out:' + str(out / 'PokeController.exe'), '/resource:' + str(icon) + ',PokeController.ico']
                   + ['/r:' + name for name in references] + sources + [str(info)], check=True)
    # The MCP launcher: hands its stdio to controller_mcp.py.
    subprocess.run(common + ['/target:exe', '/define:MCP', '/out:' + str(out / 'PokeControllerMCP.exe'),
                             str(PACKAGING / 'Launcher.cs'), str(info)], check=True)
    info.unlink()
    for name in ('Microsoft.Web.WebView2.Core.dll', 'Microsoft.Web.WebView2.WinForms.dll', 'WebView2Loader.dll'):
        shutil.copy2(webview2 / name, out / name)  # WebView2Loader.dll is the x64 build
    for name in ('LICENSE.txt', 'NOTICE.txt'):
        shutil.copy2(webview2 / name, out / ('WebView2-' + name))


def build(out):
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    # Only files tracked by git are shipped, so local profiles, logs and caches never leak into a release.
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    for name in tracked:
        if not name or name.startswith(('.git', '.claude-plugin/', '.codex-plugin/', '.agents/', 'plugin/', 'packaging/', 'tests/', 'Images/')) or set(Path(name).parts) & EXCLUDED_PARTS \
                or name.startswith(UPSTREAM_ONLY) or (name.endswith('.bat') and '/' not in name):
            continue
        source = ROOT / name
        if source.is_file():
            target = out / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    for script in ('install.ps1', 'uninstall.ps1'):
        shutil.copy2(PACKAGING / script, out / script)
    compile_launchers(out)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    (out / 'BUILD_INFO.txt').write_text(f'Version: {version()}\nSource commit: {revision}\n', encoding='utf-8')


def archive(out):
    release = ROOT / 'release'
    release.mkdir(exist_ok=True)
    target = release / 'PokeController-win64.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(out.rglob('*')):
            if path.is_file():
                bundle.write(path, Path('PokeController') / path.relative_to(out))
    with target.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    target.with_name(target.name + '.sha256').write_text(f'{digest}  {target.name}\n', encoding='ascii')
    shutil.copy2(PACKAGING / 'get.ps1', release / 'get.ps1')
    print(target, f'{target.stat().st_size / 1024 / 1024:.1f} MB')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'dist' / 'PokeController')
    options = parser.parse_args()
    build(options.output)
    archive(options.output)
