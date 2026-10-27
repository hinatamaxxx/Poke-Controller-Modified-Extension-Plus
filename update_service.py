"""Find, verify and apply new releases from this repository's GitHub Releases. MIT."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import zipfile

import requests

import app_paths
from product import REPOSITORY, REPOSITORY_URL, VERSION

ASSET_NAME = 'PokeController-win64.zip'
API = 'https://api.github.com/repos/' + REPOSITORY
DOWNLOAD = REPOSITORY_URL + '/releases/download/'  # fixed source; nothing else is accepted
STATE = app_paths.LOCAL / 'update-state.json'


class UpdateUnavailable(RuntimeError):
    """Releases cannot be read (offline, rate limited, or the repository is private)."""


def version_key(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc)\.(\d+))?', value)
    if not match:
        raise ValueError('Unsupported version')
    major, minor, patch, phase, number = match.groups()
    return (int(major), int(minor), int(patch), {None: 3, 'alpha': 0, 'beta': 1, 'rc': 2}[phase], int(number or 0))


def github_get(path):
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'PokeController-Update',
               'X-GitHub-Api-Version': '2022-11-28'}
    try:
        response = requests.get(API + path, headers=headers, timeout=(5, 15))
    except requests.RequestException as exc:
        raise UpdateUnavailable(f'GitHubに接続できません: {exc}') from exc
    if response.status_code in (403, 404):
        code = response.status_code
        response.close()
        raise UpdateUnavailable(f'GitHubのリリースを読めません（HTTP {code}）。リポジトリが非公開か、API制限の可能性があります。')
    response.raise_for_status()
    return response


def find_release(prereleases=True):
    with github_get('/releases?per_page=100') as response:
        releases = response.json()
    candidates = []
    for release in releases:
        if release.get('draft') or (release.get('prerelease') and not prereleases):
            continue
        try:
            newer = version_key(release['tag_name']) > version_key(VERSION)
        except (ValueError, KeyError):
            continue
        if newer and any(asset.get('name') == ASSET_NAME for asset in release.get('assets', [])):
            candidates.append(release)
    return max(candidates, key=lambda item: version_key(item['tag_name']), default=None)


def release_page(release):
    tag = release['tag_name']
    version_key(tag)
    return REPOSITORY_URL + '/releases/tag/' + tag


def download(url, target):
    with requests.get(url, stream=True, timeout=(5, 60)) as response:
        response.raise_for_status()
        with open(target, 'wb') as stream:
            for chunk in response.iter_content(1 << 16):
                stream.write(chunk)


def apply_release(release, progress=print):
    """Download the release ZIP, check its SHA-256 and version, then run its installer in update mode."""
    tag = release['tag_name']
    version_key(tag)
    folder = app_paths.LOCAL / 'updates'
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    archive = folder / ASSET_NAME
    progress(f'{tag} をダウンロードしています…')
    download(DOWNLOAD + tag + '/' + ASSET_NAME, archive)
    download(DOWNLOAD + tag + '/' + ASSET_NAME + '.sha256', folder / 'expected.sha256')
    expected = (folder / 'expected.sha256').read_text(encoding='ascii').split()[0].lower()
    with archive.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != expected:
        raise RuntimeError('ダウンロードしたファイルのSHA-256が一致しません。更新を中止しました。')
    progress('ファイルを確認しています…')
    extracted = folder / 'release'
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(extracted)
    source = extracted / 'PokeController'
    inner = (source / 'product.py').read_text(encoding='utf-8-sig')
    if f"VERSION = '{tag.lstrip('v')}'" not in inner:
        raise RuntimeError('リリースの版と中身の版が一致しません。更新を中止しました。')
    progress('更新を適用しています…')
    # stdin is not inherited: under the tray it is the request pipe, and a child must never read from it.
    result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                             str(source / 'install.ps1'), '-Update', '-Source', str(source)],
                            stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8', errors='replace',
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=1800)
    if result.returncode:
        # install.ps1 exits with 1 when the program folder was not changed, and 2 when files may be partly replaced.
        if result.returncode == 1:
            summary = '更新に失敗しました。今の版のまま使えます。'
        else:
            summary = '更新の途中で失敗しました。アプリのファイルが一部だけ置き換わっている可能性があります。最新版を入れ直してください。'
        raise RuntimeError(summary + '\n' + (result.stdout + result.stderr)[-1500:])
    shutil.rmtree(folder, ignore_errors=True)
    return f'{tag} に更新しました。次にアプリを起動したときから新しい版になります。'


def read_state():
    try:
        return json.loads(STATE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'last_check': 0, 'failures': 0, 'last_error': '', 'notified': False}


def write_state(state):
    from safe_settings import write_text
    STATE.parent.mkdir(parents=True, exist_ok=True)
    write_text(STATE, json.dumps(state, ensure_ascii=False, indent=2))


def run_check(prereleases, progress=print):
    """One update attempt; records the outcome and returns (message, should_notify)."""
    state = read_state()
    state['last_check'] = time.time()
    state.pop('result', None)
    state.pop('message', None)
    try:
        release = find_release(prereleases)
        message = apply_release(release, progress) if release else '最新の版です。'
        state.update(failures=0, last_error='', notified=False)
        write_state(state)
        return message, False
    except UpdateUnavailable as exc:
        # Being offline or private is not a failure worth a notification.
        state['last_error'] = str(exc)
        write_state(state)
        return str(exc), False
    except Exception as exc:
        state['failures'] = state.get('failures', 0) + 1
        state['last_error'] = str(exc)
        notify = state['failures'] >= 2 and not state.get('notified')
        state['notified'] = state.get('notified') or notify
        write_state(state)
        return str(exc), notify


def check_portable(prereleases):
    """A source checkout is never updated in place; it only reports, and records the check so the tray stops waiting."""
    state = read_state()
    state['last_check'] = time.time()
    state['result'] = 'portable'
    try:
        release = find_release(prereleases)
        message = f"新しい版があります：{release['tag_name']}" if release else '最新の版です。'
        state.update(last_error='', message=message)
    except Exception as exc:
        message = str(exc)
        state.update(last_error=message, message='')
    try:
        write_state(state)
    except Exception:
        pass
    return message


CHECK_INTERVAL = 24 * 3600
_busy = threading.Lock()


def notify(message):
    """Windows toast for update problems the user should know about."""
    try:
        from plyer import notification
        notification.notify(title='Poke-Controller の更新', message=message[:250], timeout=10)
    except Exception:
        pass


def check_now(preferences, manual=False):
    """One check/update; returns the message. Skips when another check is running."""
    if not _busy.acquire(blocking=False):
        return '確認中です。'
    try:
        if app_paths.PORTABLE:
            return check_portable(preferences.values['prereleases'])
        message, should_notify = run_check(preferences.values['prereleases'])
        print('アプリの更新: ' + message)
        if should_notify and not manual:
            notify(message)
        return message
    except Exception as exc:
        return str(exc)
    finally:
        _busy.release()


def start_background_updates(preferences):
    """Daily automatic update for installed copies; silent unless it keeps failing."""
    if app_paths.PORTABLE:
        return
    def loop():
        time.sleep(30)
        while True:
            due = time.time() - read_state().get('last_check', 0) >= CHECK_INTERVAL
            if preferences.values['auto_update'] and due:
                check_now(preferences)
            time.sleep(3600)
    threading.Thread(target=loop, daemon=True).start()
