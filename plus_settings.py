"""Profile settings (settings.ini) without a window, on top of the fork origin's AppSettings. MIT.

The fork origin's Settings.GuiSettings turns the fields that its screens edit into tkinter variables, which need a Tk
root. This app has no Tk window, so the same fields become Var (get/set) instead. Settings that only this app has are
kept in their own section, [PokeControllerPlus], because the fork origin's save() rewrites General Setting and
Notification from its own list of fields.
"""
import configparser

from safe_settings import read_config, write_config
from services.settings_store import VARIABLE_FIELDS, AppSettings

PLUS = 'PokeControllerPlus'
# This app's own settings: name -> (type, default). Older versions of this app kept them in General Setting
# (camera_*) and Notification (is_discord_*), which are read once when [PokeControllerPlus] is missing.
PLUS_FIELDS = {'camera_path': (str, ''), 'camera_name': (str, ''),
               'is_discord_switch_capture': (bool, False), 'is_discord_clip': (bool, False)}
OLD_SECTIONS = {'camera_path': 'General Setting', 'camera_name': 'General Setting',
                'is_discord_switch_capture': 'Notification', 'is_discord_clip': 'Notification'}
VAR_FIELDS = frozenset(name for name, _ in VARIABLE_FIELDS) | {'is_discord_switch_capture', 'is_discord_clip'}

# The keyboard mapping a new profile starts with (also what 初期設定に戻す restores). Unlike the fork origin, the arrow
# keys play the D-pad; the left stick is unassigned until chosen in the key settings.
DEFAULT_KEYMAPS = {
    'KeyMap-Button': {
        'Button.Y': 'y', 'Button.B': 'b', 'Button.X': 'x', 'Button.A': 'a', 'Button.L': 'l', 'Button.R': 'r',
        'Button.ZL': 'k', 'Button.ZR': 'e', 'Button.MINUS': 'm', 'Button.PLUS': 'p', 'Button.LCLICK': 'q',
        'Button.RCLICK': 'w', 'Button.HOME': 'h', 'Button.CAPTURE': 'c',
    },
    'KeyMap-Direction': {
        'Direction.UP': '20100', 'Direction.RIGHT': '20101', 'Direction.DOWN': '20110', 'Direction.LEFT': '20111',
        'Direction.UP_RIGHT': '20001', 'Direction.DOWN_RIGHT': '20002', 'Direction.DOWN_LEFT': '20010',
        'Direction.UP_LEFT': '20011',
    },
    'KeyMap-Hat': {
        'Hat.TOP': 'Key.up', 'Hat.TOP_RIGHT': '10001', 'Hat.RIGHT': 'Key.right', 'Hat.BTM_RIGHT': '10011',
        'Hat.BTM': 'Key.down', 'Hat.BTM_LEFT': '10101', 'Hat.LEFT': 'Key.left', 'Hat.TOP_LEFT': '10111',
        'Hat.CENTER': '11000',
    },
}


class Var:
    """The get/set part of a tkinter variable."""

    def __init__(self, value=None):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


def _validate(config):
    """A settings file this app can use (anything else is restored from its backup)."""
    for section in ('General Setting', 'Output', 'KeyMap-Button', 'KeyMap-Direction', 'KeyMap-Hat'):
        if section not in config:
            raise ValueError('Missing section')
    general = config['General Setting']
    for key in ('camera_id', 'com_port', 'baud_rate'):
        int(general.get(key, '0') or 0)
    for key in ('area_size', 'stdout_destination'):
        config['Output'][key]


class HeadlessSettings(AppSettings):
    """settings.ini of one profile. SETTING_PATH is set for the profile before it is created."""

    def __init__(self):
        super().__init__()
        for name, _ in VARIABLE_FIELDS:
            setattr(self, name, Var(getattr(self, name)))
        self.command_name_dict = {number: Var(name) for number, name in self.command_name_dict.items()}

    def _read_values(self):
        super()._read_values()
        plus = self.setting[PLUS] if self.setting.has_section(PLUS) else None
        for name, (kind, default) in PLUS_FIELDS.items():
            source = plus if plus is not None else (
                self.setting[OLD_SECTIONS[name]] if self.setting.has_section(OLD_SECTIONS[name]) else None)
            if source is None or name not in source:
                value = default
            elif kind is bool:
                try:
                    value = source.getboolean(name)
                except ValueError:
                    value = default
            else:
                value = source.get(name)
            setattr(self, name, Var(value) if name in VAR_FIELDS else value)

    def load(self):
        """Read settings.ini; a damaged file is restored from its backup (safe_settings)."""
        self.setting = read_config(self.SETTING_PATH, _validate)

    def generate(self):
        super().generate()
        for section, values in DEFAULT_KEYMAPS.items():
            self.setting[section] = dict(values)
        write_config(self.SETTING_PATH, self.setting)

    def _value(self, name):
        value = getattr(self, name)
        return value.get() if isinstance(value, Var) else value

    def _shortcut_name(self, number):
        return self.command_name_dict[number].get()

    def save(self, path=None):
        """The fork origin's save, then this app's own section, written through safe_settings: the file before this save
        becomes the backup (.bak) that a damaged file is restored from."""
        from pathlib import Path
        path = Path(self.SETTING_PATH)
        before = path.read_bytes() if path.exists() else None
        super().save()
        try:
            config = read_config(self.SETTING_PATH)
        except ValueError:
            config = self.setting
        config[PLUS] = {name: str(self._value(name)) for name in PLUS_FIELDS}
        if before is not None:
            path.write_bytes(before)
        write_config(self.SETTING_PATH, config)
        self.setting = config
