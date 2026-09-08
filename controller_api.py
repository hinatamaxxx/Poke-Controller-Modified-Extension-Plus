"""Authenticated local calls with replay-safe retries after transport failures."""
import http.client
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, ProxyHandler
import uuid


def call(endpoint_path, method, params=None, *, token_override=None, request_id=None):
    endpoint = json.loads(Path(endpoint_path).read_text(encoding='utf-8'))
    url = urlparse(endpoint['url'])
    if url.scheme != 'http' or url.hostname != '127.0.0.1':
        raise ValueError('Only the local controller endpoint is supported')
    data = json.dumps({'method': method, 'params': params or {}, 'request_id': request_id or uuid.uuid4().hex}).encode()
    token = endpoint['token'] if token_override is None else token_override
    opener = build_opener(ProxyHandler({}))
    for attempt in range(4):
        request = Request(endpoint['url'], data=data, headers={
            'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        try:
            with opener.open(request, timeout=18) as response:
                result = json.load(response)
            if not result.get('ok'):
                raise ValueError(result.get('error', 'Controller operation failed'))
            return result.get('result')
        except HTTPError:
            raise
        except (OSError, URLError, http.client.HTTPException):
            if attempt == 3:
                raise
            time.sleep(.1 * (attempt + 1))
