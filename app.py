"""Portable launcher for the original Tk interface. MIT."""
import argparse
import configparser
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent


def acquire_profile(profiles, name):
    """Claim the first free persistent settings slot, without a check/open race."""
    import errno
    import msvcrt
    for number in range(1, 10001):
        suffix = '' if number == 1 else f'-{number}'
        candidate = name[:48 - len(suffix)] + suffix
        profile = Path(profiles) / candidate
        profile.mkdir(parents=True, exist_ok=True)
        lock = (profile / '.instance.lock').open('a+b')
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            lock.close()
            if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise
            continue
        return candidate, profile, lock
    raise OSError('空いている設定枠がありません。不要なウィンドウを終了してください。')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', '-p', default='default')
    parser.add_argument('--mcp', action=argparse.BooleanOptionalAction, default=None, help='Override saved MCP setting (default: disabled)')
    parser.add_argument('--demo', action='store_true', help='Synthetic camera; serial and keyboard disabled')
    parser.add_argument('--smoke-test', type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r'[\w -]{1,48}', args.profile) or args.profile.endswith(' '):
        parser.error('Invalid profile name')
    if args.profile.upper() in {'CON', 'PRN', 'AUX', 'NUL', *[f'{p}{i}' for p in ('COM', 'LPT') for i in range(1, 10)]}:
        parser.error('Reserved profile name')
    serial = ROOT / 'SerialController'
    sys.path.insert(0, str(serial))
    os.chdir(serial)
    logs = serial / 'log'
    logs.mkdir(exist_ok=True)
    if sys.stdout is None:
        sys.stdout = open(logs / f'console-{os.getpid()}.log', 'a', encoding='utf-8', buffering=1)
    if sys.stderr is None:
        sys.stderr = sys.stdout
    import tkinter as tk
    import Settings
    import PokeConLogger
    import Window
    root = tk.Tk()
    try:
        args.profile, profile, lock = acquire_profile(serial / 'profiles', args.profile)
    except OSError as error:
        from tkinter.messagebox import showerror
        showerror('起動できません', f'設定フォルダーを開けません。\n{error}', parent=root)
        root.destroy()
        return 1
    settings = profile / 'settings.ini'
    Settings.GuiSettings.SETTING_PATH = str(settings)
    if args.demo:
        from demo_camera import install
        install()
    PokeConLogger.root_logger()
    from plus_preferences import Preferences
    try:
        preferences = Preferences(profile / 'plus-settings.json')
        if not settings.exists() and not settings.with_name(settings.name + '.bak').exists():
            Settings.GuiSettings()
        app = Window.PokeControllerApp(root, args.profile)
    except (OSError, ValueError, configparser.Error) as error:
        from tkinter.messagebox import showerror
        showerror('起動できません', f'設定や起動に必要なファイルを確認してください。\n{profile}\n\n{error}', parent=root)
        root.destroy()
        lock.close()
        return 1
    from AppLifecycle import Lifecycle
    app.lifecycle = Lifecycle(app)
    def report_ui_error(kind, error, traceback):
        import logging
        logging.getLogger(__name__).error('画面操作でエラーが発生しました', exc_info=(kind, error, traceback))
        print(f'画面操作でエラーが発生しました: {kind.__name__}: {error}')
    root.report_callback_exception = report_ui_error
    api = None
    enabled = tk.BooleanVar(value=preferences.values['mcp_enabled'] if args.mcp is None else args.mcp)
    def toggle_mcp(save=True):
        nonlocal api
        try:
            if enabled.get() and api is None:
                from local_control import LocalControl
                api = LocalControl(app, ROOT / 'runtime', demo=args.demo)
            elif not enabled.get() and api is not None:
                api.close()
                api = None
        except Exception:
            enabled.set(api is not None)
            raise
        if save:
            preferences.set('mcp_enabled', enabled.get())
    mcp_menu = tk.Menu(app.menu, tearoff=False)
    mcp_menu.add_checkbutton(label='MCPを有効にする', variable=enabled, command=toggle_mcp)
    mcp_menu.add_command(label='接続方法', command=lambda: os.startfile(ROOT / 'MCP.md'))
    app.menu.add_cascade(label='MCP', menu=mcp_menu)
    from plus_settings import SettingsWindow
    settings_window = SettingsWindow(app, ROOT, preferences, enabled, toggle_mcp)
    app.open_plus_settings = settings_window.show
    toggle_mcp(save=False)
    if args.smoke_test:
        import json
        def report():
            args.smoke_test.write_text(json.dumps({'ready': True, 'python': sys.executable, 'profile': args.profile,
                'python_scripts': len(app.py_classes), 'mcu_scripts': len(app.mcu_classes),
                'mcp_endpoint': str(api.path) if api else None}), encoding='utf-8')
        root.after(1200, report)
        def finish_test():
            if args.smoke_test.with_suffix('.stop').exists():
                app.exit(confirm=False)
            else:
                root.after(100, finish_test)
        root.after(100, finish_test)
    try:
        app.run()
    finally:
        if api:
            api.close()
        lock.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
