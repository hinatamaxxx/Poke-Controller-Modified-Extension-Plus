"""Read-only release/version checks. Application updates are performed manually. MIT."""
import json
from pathlib import Path
import re
from urllib.parse import quote
import requests
from product import REPOSITORY, REPOSITORY_URL, VERSION

ASSET_NAME = 'PokeController-portable-win64.zip'
API = 'https://api.github.com/repos/' + REPOSITORY


def version_key(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc)\.(\d+))?', value)
    if not match:
        raise ValueError('Unsupported version')
    major, minor, patch, phase, number = match.groups()
    return (int(major), int(minor), int(patch), {None: 3, 'alpha': 0, 'beta': 1, 'rc': 2}[phase], int(number or 0))


def github_get(path, token=''):
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'PokeController-Update',
               'X-GitHub-Api-Version': '2022-11-28'}
    if token:
        headers['Authorization'] = 'Bearer ' + token.strip()
    response = requests.get(API + path, headers=headers, timeout=(5, 15))
    if response.status_code in (401, 403, 404):
        code = response.status_code
        response.close()
        raise RuntimeError(f'GitHubにアクセスできません（HTTP {code}）。非公開リポジトリでは、このリポジトリのContents読み取り権限を持つトークンが必要です。403の場合はAPI制限も確認してください。')
    try:
        response.raise_for_status()
    except Exception:
        response.close()
        raise
    return response


def find_release(token='', prereleases=True):
    with github_get('/releases?per_page=100', token) as response:
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
    return REPOSITORY_URL + '/releases/tag/' + quote(tag, safe='')


def installed_libraries(root):
    from library_update import inventory, runtime_path
    if (Path(root) / 'runtime-python').is_dir():
        return inventory(runtime_path(root))
    path = Path(root) / 'licenses/dependencies.json'
    if path.exists():
        data = json.loads(path.read_text(encoding='utf-8'))
    else:
        import importlib.metadata
        data = [{'name': item.metadata['Name'], 'version': item.version} for item in importlib.metadata.distributions()]
    return sorted(data, key=lambda item: item['name'].casefold())
