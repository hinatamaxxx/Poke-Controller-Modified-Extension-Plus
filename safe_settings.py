"""Atomic UTF-8 settings writes and recovery from a validated previous copy. MIT."""
import configparser
import io
import os
from pathlib import Path
import tempfile
import uuid


def _replace_bytes(path, data):
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_text(path, text):
    path = Path(path)
    data = text.encode('utf-8')
    if path.exists():
        previous = path.read_bytes()
        if previous == data:
            return  # Repeated saves must not consume the useful previous version.
        # Keep the original file intact if writing its backup fails.
        _replace_bytes(path.with_name(path.name + '.bak'), previous)
    _replace_bytes(path, data)


def write_config(path, config):
    stream = io.StringIO()
    config.write(stream)
    write_text(path, stream.getvalue())


def read_checked(path, parse):
    path = Path(path)
    failures = (FileNotFoundError, UnicodeError, ValueError, configparser.Error, KeyError)
    try:
        return parse(path.read_text(encoding='utf-8-sig'))
    except failures as original:
        backup = path.with_name(path.name + '.bak')
        try:
            data = backup.read_bytes()
            result = parse(data.decode('utf-8-sig'))
        except failures:
            raise ValueError(f'設定を読み込めません：{path}\n正常なバックアップ（.bak）も見つかりません。元のファイルは変更していません。') from original
        if path.exists():
            damaged = path.with_name(path.name + '.corrupt-' + uuid.uuid4().hex[:8])
            _replace_bytes(damaged, path.read_bytes())
        _replace_bytes(path, data)  # Do not replace the valid backup with corrupt data.
        print(f'設定をバックアップから復元しました：{path.name}')
        return result


def read_config(path, validate=None):
    def parse(text):
        config = configparser.ConfigParser()
        config.optionxform = str
        config.read_string(text)
        if not config.sections():
            raise ValueError('Empty settings')
        if validate:
            validate(config)
        return config
    return read_checked(path, parse)
