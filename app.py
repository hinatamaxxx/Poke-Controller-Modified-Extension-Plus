"""Window-less Poke-Controller: serves the browser UI and the MCP endpoint. MIT."""
import argparse
import os
from pathlib import Path
import re
import sys
import time

import app_paths

ROOT = app_paths.PROGRAM


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
    raise OSError('空いている設定枠がありません。不要な Poke-Controller を終了してください。')


def running_page():
    """The browser page of an already running copy, if any."""
    import json
    from controller_api import call
    for endpoint in sorted(app_paths.RUNTIME.glob('controller-*.json')):
        try:
            call(endpoint, 'sessions', retries=2)
            return json.loads(endpoint.read_text(encoding='utf-8'))['web_url']
        except (OSError, ValueError, KeyError):
            continue
    return None


def show_error(message):
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, message, 'Poke-Controller', 0x10)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', '-p')
    parser.add_argument('--background', action='store_true', help='Do not open the browser (used by the MCP server)')
    parser.add_argument('--host', action='store_true', help='Run under the tray app, talking JSON lines over stdin/stdout')
    parser.add_argument('--new', action='store_true', help='Start another copy even if one is running')
    parser.add_argument('--demo', action='store_true', help='Synthetic camera; serial disabled')
    parser.add_argument('--smoke-test', type=Path)
    args = parser.parse_args()
    explicit_profile = args.profile is not None
    args.profile = args.profile or 'default'
    if not re.fullmatch(r'[\w -]{1,48}', args.profile) or args.profile.endswith(' '):
        parser.error('Invalid profile name')
    if args.profile.upper() in {'CON', 'PRN', 'AUX', 'NUL', *[f'{p}{i}' for p in ('COM', 'LPT') for i in range(1, 10)]}:
        parser.error('Reserved profile name')
    import webbrowser
    if not (explicit_profile or args.new or args.background or args.smoke_test or args.host):
        page = running_page()
        if page:
            webbrowser.open(page)
            return 0
    serial = ROOT / 'SerialController'
    app_paths.prepare_workspace()
    # The workspace comes first so its copies of the scripts win over the bundled originals.
    for path in dict.fromkeys([serial, app_paths.WORKSPACE]):
        sys.path.insert(0, str(path))
    os.chdir(app_paths.WORKSPACE)
    app_paths.LOGS.mkdir(parents=True, exist_ok=True)
    console_path = app_paths.LOGS / f'console-{os.getpid()}.log'
    channel = None
    if args.host:
        # Claim stdio for the tray before libraries print their banners.
        from host_channel import HostChannel
        channel = HostChannel(console_path)
    console = open(console_path, 'a', encoding='utf-8', buffering=1)
    if sys.stderr is None:
        sys.stderr = console
    import Paths
    Paths.PROFILES, Paths.LOGS = str(app_paths.PROFILES), str(app_paths.LOGS)
    try:
        args.profile, profile, lock = acquire_profile(app_paths.PROFILES, args.profile)
    except OSError as error:
        show_error(f'設定フォルダーを開けません。\n{error}')
        return 1
    if args.demo:
        from demo_camera import install
        install()
    import PokeConLogger
    PokeConLogger.root_logger()
    from core import Core
    from local_control import LocalControl
    try:
        core = Core(args.profile, str(profile), demo=args.demo, console_mirror=console)
    except (OSError, ValueError) as error:
        show_error(f'起動できません。設定ファイルを確認してください。\n{profile}\n\n{error}')
        lock.close()
        return 1
    api = LocalControl(core, app_paths.RUNTIME)
    from plus_preferences import Preferences
    import update_service
    core.preferences = Preferences(app_paths.APP_SETTINGS)
    update_service.start_background_updates(core.preferences)
    if args.smoke_test:
        import json
        args.smoke_test.write_text(json.dumps({'ready': True, 'python': sys.executable, 'profile': args.profile,
            'python_scripts': len(core.py_classes), 'mcu_scripts': len(core.mcu_classes),
            'mcp_endpoint': str(api.path), 'workspace': str(app_paths.WORKSPACE)}), encoding='utf-8')
    elif channel is not None:
        channel.send({'event': 'ready', 'web_url': api.web_url, 'profile': args.profile, 'pid': os.getpid()})
        channel.serve(api, core)
    elif not args.background:
        webbrowser.open(api.web_url)
    try:
        while not core.exit_requested:
            if args.smoke_test and args.smoke_test.with_suffix('.stop').exists():
                break
            core.tick()
            time.sleep(.05)
    except KeyboardInterrupt:
        pass
    finally:
        core.exit_requested = True
        core.close()
        api.close()
        lock.close()
        if channel is not None:
            channel.send({'event': 'exit'})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
