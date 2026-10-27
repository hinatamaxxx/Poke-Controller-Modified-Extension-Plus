"""Authenticated local calls with replay-safe retries after transport failures."""
import http.client
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, ProxyHandler
import uuid


def _pipe_call(endpoint, payload, token, timeout):
    from multiprocessing.connection import Client
    with Client(endpoint['pipe'], family='AF_PIPE', authkey=token.encode()) as connection:
        connection.send(payload)
        if not connection.poll(timeout):
            raise TimeoutError('The app did not answer in time')
        return connection.recv()


def call(endpoint_path, method, params=None, *, token_override=None, request_id=None, retries=4):
    """Call a running app. The named pipe is preferred; HTTP is the fallback for older apps."""
    endpoint = json.loads(Path(endpoint_path).read_text(encoding='utf-8'))
    url = urlparse(endpoint['url'])
    if url.scheme != 'http' or url.hostname != '127.0.0.1':
        raise ValueError('Only the local controller endpoint is supported')
    payload = {'method': method, 'params': params or {}, 'request_id': request_id or uuid.uuid4().hex}
    token = endpoint['token'] if token_override is None else token_override
    opener = build_opener(ProxyHandler({}))
    for attempt in range(retries):
        try:
            if endpoint.get('pipe'):
                from multiprocessing import AuthenticationError
                try:
                    result = _pipe_call(endpoint, payload, token, 18)
                except AuthenticationError as exc:
                    raise PermissionError('Unauthorized') from exc
            else:
                request = Request(endpoint['url'], data=json.dumps(payload).encode(), headers={
                    'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
                with opener.open(request, timeout=18) as response:
                    result = json.load(response)
            if not result.get('ok'):
                raise ValueError(result.get('error', 'Controller operation failed'))
            return result.get('result')
        except (HTTPError, PermissionError):
            raise
        except (OSError, EOFError, URLError, http.client.HTTPException):
            if attempt == retries - 1:
                raise
            time.sleep(.1 * (attempt + 1))
