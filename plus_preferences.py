"""App-wide preferences (shared by every profile); no credentials are stored here. MIT."""
import json
from pathlib import Path
from safe_settings import read_checked, write_text


class Preferences:
    def __init__(self, path):
        self.path = Path(path)
        self.values = {'auto_update': True, 'prereleases': True, 'pad_colors': 'Default'}
        if self.path.exists() or self.path.with_name(self.path.name + '.bak').exists():
            def parse(text):
                data = json.loads(text)
                if not isinstance(data, dict) or any(key in data and not isinstance(data[key], type(self.values[key]))
                                                     for key in self.values):
                    raise ValueError('Invalid preferences')
                return data
            data = read_checked(self.path, parse)
            for key in self.values:
                if key in data:
                    self.values[key] = data[key]

    def set(self, key, value):
        if key not in self.values or not isinstance(value, type(self.values[key])):
            raise ValueError('Invalid preference')
        changed = {**self.values, key: value}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_text(self.path, json.dumps(changed, indent=2))
        self.values = changed
