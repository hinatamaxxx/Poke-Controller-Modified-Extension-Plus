"""Window-less Poke-Controller. MIT.

The hub (the default) serves the browser page, the MCP endpoint and the tray channel, and runs every Switch in its
own worker process (`--worker`), so one Switch crashing does not stop the others.
"""
import argparse
import logging
import os
from pathlib import Path
import re
import sys
import time

import app_paths

ROOT = app_paths.PROGRAM


def acquire_profile(profiles, name, exact=False):
    """Claim the first free persistent settings slot, without a check/open race (only `name` itself when exact)."""
    import errno
    import msvcrt
    for number in range(1, 2 if exact else 10001):
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


def running_hub(profile):
    """The endpoint file of a running hub for this set of Switches, if any."""
    import json
    from controller_api import call
    for endpoint in sorted(app_paths.RUNTIME.glob('controller-*.json')):
        try:
            info = json.loads(endpoint.read_text(encoding='utf-8'))
            if info.get('profile') != profile:
                continue
            call(endpoint, 'web_url', retries=2)
            return endpoint, info
        except (OSError, ValueError, KeyError):
            continue
    return None


def lock_file(path):
    """An exclusive lock held while the returned file stays open, or None when another process holds it."""
    import msvcrt
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open('a+b')
    stream.seek(0)
    try:
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        return stream
    except OSError:
        stream.close()
        return None


def show_error(message):
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, message, 'Poke-Controller', 0x10)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', '-p')
    parser.add_argument('--background', action='store_true', help='Do not open the browser (used by the MCP server)')
    parser.add_argument('--host', action='store_true', help='Run under the tray app, talking JSON lines over stdin/stdout')
    parser.add_argument('--new', action='store_true', help=argparse.SUPPRESS)  # older launchers; Switches are tabs now
    parser.add_argument('--demo', action='store_true', help='Synthetic camera; serial disabled')
    parser.add_argument('--smoke-test', type=Path)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--session-id', help=argparse.SUPPRESS)
    parser.add_argument('--label', default='', help=argparse.SUPPRESS)
    parser.add_argument('--hub-pid', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--resume', help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.profile = args.profile or 'default'
    if not re.fullmatch(r'[\w -]{1,48}', args.profile) or args.profile.endswith(' '):
        parser.error('Invalid profile name')
    if args.profile.upper() in {'CON', 'PRN', 'AUX', 'NUL', *[f'{p}{i}' for p in ('COM', 'LPT') for i in range(1, 10)]}:
        parser.error('Reserved profile name')
    serial = ROOT / 'SerialController'
    app_paths.prepare_workspace()
    # The workspace comes first so its copies of the scripts win over the bundled originals.
    for path in dict.fromkeys([serial, app_paths.WORKSPACE]):
        sys.path.insert(0, str(path))
    os.chdir(app_paths.WORKSPACE)
    app_paths.LOGS.mkdir(parents=True, exist_ok=True)
    import Paths
    Paths.PROFILES, Paths.LOGS = str(app_paths.PROFILES), str(app_paths.LOGS)
    return run_worker(args) if args.worker else run_hub(args)


def run_hub(args):
    import webbrowser
    import json
    lock = lock_file(app_paths.PROFILES / args.profile / '.hub.lock')
    if lock is None:
        running = running_hub(args.profile)
        if args.host and running:
            # The tray takes over from a hub started in the background (e.g. by the MCP server).
            from controller_api import call
            try:
                call(running[0], 'command', {'action': 'quit'})
            except (OSError, ValueError):
                pass
            deadline = time.monotonic() + 30
            while lock is None and time.monotonic() < deadline:
                time.sleep(.5)
                lock = lock_file(app_paths.PROFILES / args.profile / '.hub.lock')
        if lock is None:
            if running and not (args.background or args.smoke_test or args.host):
                webbrowser.open(running[1]['web_url'])
            return 0 if running else 1
    console_path = app_paths.LOGS / f'console-{os.getpid()}.log'
    channel = None
    if args.host:
        # Claim stdio for the tray before libraries print their banners.
        from host_channel import HostChannel
        channel = HostChannel(console_path)
    console = open(console_path, 'a', encoding='utf-8', buffering=1)
    if sys.stderr is None:
        sys.stderr = console
    if sys.stdout is None:
        sys.stdout = console
    import plus_logger
    plus_logger.root_logger()
    from plus_preferences import Preferences
    import update_service
    from hub import Hub
    preferences = Preferences(app_paths.APP_SETTINGS)
    try:
        hub = Hub(app_paths.PROFILES, args.profile, app_paths.RUNTIME, demo=args.demo, preferences=preferences)
    except (OSError, ValueError) as error:
        show_error(f'起動できません。\n{error}')
        lock.close()
        return 1
    update_service.start_background_updates(preferences)
    if channel is not None:
        channel.send({'event': 'ready', 'web_url': hub.web_url, 'profile': args.profile, 'pid': os.getpid()})
        channel.serve(hub, hub)
    elif not (args.background or args.smoke_test):
        webbrowser.open(hub.web_url)
    reported = False
    try:
        while not hub.exit_requested:
            if args.smoke_test:
                if args.smoke_test.with_suffix('.stop').exists():
                    break
                if not reported:
                    reported = smoke_report(hub, args)
            time.sleep(.2)
    except KeyboardInterrupt:
        pass
    finally:
        hub.exit_requested = True
        hub.close()
        lock.close()
        if channel is not None:
            channel.send({'event': 'exit'})
    return 0


def smoke_report(hub, args):
    """Once the first Switch answers, write what the tests check."""
    import json
    worker = hub.open_workers()[0]
    if worker.state != 'ready':
        return False
    state = worker.call('sessions')[0]
    args.smoke_test.write_text(json.dumps({'ready': True, 'python': sys.executable, 'profile': args.profile,
        'python_scripts': len(state['catalog'].get('python', [])), 'mcu_scripts': len(state['catalog'].get('mcu', [])),
        'mcp_endpoint': str(hub.path), 'workspace': str(app_paths.WORKSPACE)}), encoding='utf-8')
    return True


def run_worker(args):
    """One Switch: its camera, controller and scripts. Ends with the hub."""
    import faulthandler
    import json
    import logging
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, 'reconfigure'):
            # The hub hands over its log file; the system code page could not write every character a script prints.
            stream.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    faulthandler.enable()  # a native crash leaves its stack in the worker log the hub reads
    console = sys.stdout if sys.stdout is not None else open(os.devnull, 'w')
    try:
        args.profile, profile, lock = acquire_profile(app_paths.PROFILES, args.profile, exact=True)
    except OSError as error:
        print(f'設定フォルダーを開けません（ほかで使用中）: {error}', file=sys.stderr, flush=True)
        return 3
    import plus_logger
    plus_logger.root_logger()
    from core import Core
    from local_control import LocalControl, process_alive
    from plus_preferences import Preferences
    core = Core(args.profile, str(profile), demo=args.demo, console_mirror=console, label=args.label)
    core.preferences = Preferences(app_paths.APP_SETTINGS)
    api = LocalControl(core, app_paths.RUNTIME / 'workers', session_id=args.session_id, http=False)
    if args.resume:
        try:
            kind, name = json.loads(args.resume)
            with core.lock:
                core.start_script(kind, name, restart=True)
            print(f'止まる前のスクリプトを再開しました: {name}')
        except Exception as exc:
            print(f'止まる前のスクリプトを再開できませんでした: {exc}')
    next_check = 0
    try:
        while not core.exit_requested:
            if args.hub_pid and time.monotonic() >= next_check:
                next_check = time.monotonic() + 2
                if not process_alive(args.hub_pid):
                    break
            try:
                core.tick()
            except Exception:
                logging.getLogger(__name__).exception('定期処理でエラーが発生しました')
                time.sleep(1)
            time.sleep(.05)
    except KeyboardInterrupt:
        pass
    finally:
        core.exit_requested = True
        core.close()
        api.close()
        lock.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
