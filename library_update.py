"""Prepare independent runtimes; never modify libraries loaded by an app. MIT."""
from pathlib import Path
import importlib.metadata as metadata
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from safe_settings import write_text


def normalize(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def runtime_path(root):
    root = Path(root).resolve()
    pointer = root / 'runtime-choice.txt'
    value = pointer.read_text(encoding='utf-8').strip() if pointer.exists() else 'runtime-python'
    if not re.fullmatch(r'runtime-python|\.runtime-updates/[a-f0-9]{32}', value):
        raise ValueError('更新ライブラリの参照先が不正です。runtime-choice.txtを確認してください。')
    return root / value


def inventory(runtime):
    return sorted([{'name': d.metadata['Name'], 'version': d.version}
                   for d in metadata.distributions(path=[str(Path(runtime) / 'Lib/site-packages')])],
                  key=lambda d: d['name'].lower())


def requirements(items, selected):
    selected = {normalize(n) for n in selected}
    known = {normalize(d['name']) for d in items}
    if not selected or not selected <= known:
        raise ValueError('更新するライブラリを選択してください。')
    return [d['name'] if normalize(d['name']) in selected else d['name'] + '==' + d['version'] for d in items]


def run(command, log):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(('PYTHON', 'PIP_'))}
    env['PIP_CONFIG_FILE'] = os.devnull
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            encoding='utf-8', errors='replace', env=env,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=1800)
    with Path(log).open('a', encoding='utf-8') as stream:
        stream.write(result.stdout + '\n')
    if result.returncode:
        raise RuntimeError(f'ライブラリ更新に失敗しました。現在の環境は維持されます。\n詳細：{log}\n{result.stdout[-1500:]}')
    return result.stdout


def update_libraries(root, selected):
    root = Path(root).resolve()
    if not (root / 'runtime-python/python.exe').is_file():
        raise RuntimeError('ライブラリ更新は配布版のexeから利用してください。')
    folder = root / '.runtime-updates'
    folder.mkdir(exist_ok=True)
    # Serialize updates across profiles and separate application windows.
    import msvcrt
    with (folder / 'update.lock').open('a+b') as lock:
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError('別の画面でライブラリを更新中です。')
        current = runtime_path(root)
        items = inventory(current)
        specs = requirements(items, selected)
        target = folder / uuid.uuid4().hex
        shutil.copytree(current, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        log = target / 'update.log'
        python = str(target / 'python.exe')
        run([python, '-I', '-m', 'pip', '--isolated', 'install', '--index-url', 'https://pypi.org/simple',
             '--upgrade', '--only-binary=:all:', '--no-warn-script-location', '--disable-pip-version-check', *specs], log)
        run([python, '-I', '-m', 'pip', 'check'], log)
        run([python, '-I', '-c', 'import tkinter, cv2, numpy, pygame, pynput, requests; from mcp.client import Client, StdioServerParameters; from mcp.server import MCPServer; r=tkinter.Tk(); r.withdraw(); r.destroy()'], log)
        # All unselected versions must remain unchanged, even as dependencies.
        updated = {normalize(d['name']): d['version'] for d in inventory(target)}
        selected_keys = {normalize(n) for n in selected}
        for item in items:
            if normalize(item['name']) not in selected_keys and updated.get(normalize(item['name'])) != item['version']:
                raise RuntimeError('選択していないライブラリが変更されたため、更新を適用しません。')
        write_text(root / 'runtime-choice.txt', target.relative_to(root).as_posix())
        return '更新を準備しました。全ウィンドウとMCPを終了し、同じexeを起動し直すと反映されます。'


def reset_libraries(root):
    root = Path(root)
    folder = root / '.runtime-updates'
    folder.mkdir(exist_ok=True)
    import msvcrt
    with (folder / 'update.lock').open('a+b') as lock:
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError('別の画面でライブラリを更新中です。完了後に戻してください。')
        write_text(root / 'runtime-choice.txt', 'runtime-python')
    return '次回起動から配布時のライブラリを使用します。全ウィンドウとMCPを終了して起動し直してください。'
