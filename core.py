"""Window-less Poke-Controller: camera, serial, scripts, logs, overlays and dialogues for the browser UI. MIT.

Scripts written for the original Tk app keep working: they still see Command.text_area_1/2, Command.canvas,
the dialogue functions and the same settings files, backed here by objects the browser UI reads.
"""
import itertools
import logging
import sys
import threading
import time

LOG_LINES = 2000
LOG_CHARS = 200000
DEMO_SCRIPT = 'Commands.PythonCommands.Samples.PortableDemo'

from plus_settings import Var  # noqa: E402  (settings fields and this app's own switches)


def serial_formats():
    """The Data Format names the fork origin's transports offer here (Default, NX Macro, Qingpi, 3DS ...)."""
    from Commands.transport.registry import transport_names
    return transport_names()


class Mock_typer:
    """Just enough of KeyboardTyper for its unavailable_reason (which only looks at the port and the format)."""

    def __init__(self, ser):
        self.ser = ser


class AudioSettings:
    """The fork origin's AudioService reads and writes plain values; this profile keeps them as Var."""

    def __init__(self, settings):
        object.__setattr__(self, '_settings', settings)

    def __getattr__(self, name):
        value = getattr(self._settings, name)
        return value.get() if isinstance(value, Var) else value

    def __setattr__(self, name, value):
        current = getattr(self._settings, name)
        if isinstance(current, Var):
            current.set(value)
        else:
            setattr(self._settings, name, value)


class DemoPort:
    """The demo's sender as open (like serial_open()): its writes go nowhere."""

    def __init__(self, ser):
        self._ser = ser

    def isOpened(self):
        return True

    def __getattr__(self, name):
        return getattr(self._ser, name)


class RunListService:
    """What the fork origin's run lists (services/run_list) need from the app: find a script and create it."""

    def __init__(self, core):
        self.core = core

    def find_class(self, command_type, name):
        kind = 'python' if command_type == 'Python' else 'mcu'
        entry = self.core.find_entry(name, kind)
        return None if entry is None else self.core.script_class(entry, kind)

    def create(self, command_type, command_class):
        return self.core.create_command(command_class, 'python' if command_type == 'Python' else 'mcu')


class ScriptLoader:
    """Scripts in the workspace's スクリプト folder, named after their folder (BDSP/固定シンボル/エンテイ) rather than
    the fork origin's file-based name."""

    def __init__(self, path, base_class):
        from CommandLoader import CommandLoader
        self.loader = CommandLoader(path, base_class)

    def _named(self, entries):
        for entry in entries:
            parts = entry.module_name.split('.')[1:]
            folder = parts[:-1] if len(parts) > 1 else parts
            entry.name = f"{entry.name.rsplit(' (', 1)[0]} ({'/'.join(folder)})"
            entry.tags = [t for t in entry.tags if not str(t).startswith('@')] + ['@' + t for t in folder[:-1]]
        return entries

    def load(self):
        return self._named(self.loader.load())

    def reload(self):
        return self._named(self.loader.reload())

    def findEntry(self, name):
        return next((e for e in self.loader.entries if e.name == name), None)

    def getCommandClass(self, entry, reload=False):
        return self.loader.getCommandClass(entry, reload)


class LogArea:
    """Thread-safe log buffer offering the subset of tkinter.Text that scripts call."""

    def __init__(self):
        self._lock = threading.Lock()
        self._text = ''

    def insert(self, index, text):
        with self._lock:
            self._text += str(text)
            if len(self._text) > LOG_CHARS:
                self._text = self._text[-LOG_CHARS:]
            lines = self._text.split('\n')
            if len(lines) > LOG_LINES:
                self._text = '\n'.join(lines[-LOG_LINES:])

    def delete(self, start='1.0', end='end'):
        with self._lock:
            self._text = ''

    def get(self, start='1.0', end='end'):
        with self._lock:
            return self._text

    def tail(self, chars=16000):
        with self._lock:
            return self._text[-chars:]

    def index(self, position):
        with self._lock:
            return f'{self._text.count(chr(10)) + 1}.0'

    def count(self, start, end, kind='chars'):
        with self._lock:
            return (len(self._text),)

    def config(self, **options):
        pass

    configure = config

    def see(self, *args):
        pass


class Console:
    """sys.stdout replacement: the chosen log area plus the console log file."""

    def __init__(self, area, mirror):
        self.area, self.mirror = area, mirror

    def write(self, text):
        self.area.insert('end', text)
        if self.mirror is not None:
            try:
                self.mirror.write(text)
            except (OSError, ValueError):
                pass
        return len(text)

    def flush(self):
        if self.mirror is not None:
            try:
                self.mirror.flush()
            except (OSError, ValueError):
                pass


class Overlay:
    """Stand-in for the preview canvas: rectangles and text that scripts draw are painted on the stream."""
    COLORS = {'red': (0, 0, 255), 'blue': (255, 0, 0), 'green': (0, 200, 0), 'yellow': (0, 220, 255),
              'white': (255, 255, 255), 'black': (0, 0, 0), 'orange': (0, 140, 255), 'purple': (200, 0, 160),
              'cyan': (255, 255, 0), 'magenta': (255, 0, 255), 'pink': (180, 105, 255), 'gray': (128, 128, 128)}

    def __init__(self):
        self._lock = threading.Lock()
        self._items = {}
        self._ids = itertools.count()

    def _color(self, value):
        value = str(value or 'red').strip().lower()
        if value.startswith('#') and len(value) == 7:
            r, g, b = (int(value[i:i + 2], 16) for i in (1, 3, 5))
            return (b, g, r)
        return self.COLORS.get(value, (0, 0, 255))

    def _add(self, tag, item, ms, keep):
        expires = None if keep is False else time.monotonic() + max(int(ms or 0), 200) / 1000
        with self._lock:
            self._items[tag if tag is not None else next(self._ids)] = (item, expires)

    def ImgRect(self, x1, y1, x2, y2, outline='red', tag=None, ms=1000, flag=True):
        self._add(tag, ('rect', (int(x1), int(y1), int(x2), int(y2)), self._color(outline)), ms, flag)

    def ImgText(self, x1, y1, txt='', tag=None, ms=1000, ft=None, color='black', flag=True):
        size = int(ft[1]) if isinstance(ft, (tuple, list)) and len(ft) > 1 else 20
        self._add(tag, ('text', (int(x1), int(y1)), str(txt), size, self._color(color)), ms, flag)

    def delete(self, tag='all'):
        with self._lock:
            if tag == 'all':
                self._items.clear()
            else:
                self._items.pop(tag, None)

    def draw(self, frame):
        now = time.monotonic()
        with self._lock:
            self._items = {k: v for k, v in self._items.items() if v[1] is None or v[1] > now}
            items = [v[0] for v in self._items.values()]
        if not items:
            return frame
        import cv2
        frame = frame.copy()
        texts = []
        for item in items:
            if item[0] == 'rect':
                x1, y1, x2, y2 = item[1]
                cv2.rectangle(frame, (x1 - 1, y1 - 1), (x2 + 1, y2 + 1), (255, 255, 255), 4)
                cv2.rectangle(frame, (x1, y1), (x2, y2), item[2], 2)
            else:
                texts.append(item)
        if texts:
            # PIL draws Japanese text, which cv2.putText cannot.
            from PIL import Image, ImageDraw, ImageFont
            image = Image.fromarray(frame[:, :, ::-1])
            pen = ImageDraw.Draw(image)
            for _, (x, y), text, size, (b, g, r) in texts:
                try:
                    font = ImageFont.truetype('meiryo.ttc', size)
                except OSError:
                    font = ImageFont.load_default()
                pen.text((x, y), text, font=font, fill=(r, g, b), stroke_width=2, stroke_fill=(255, 255, 255))
            frame = __import__('numpy').asarray(image)[:, :, ::-1].copy()
        return frame


class Dialogs:
    """Script dialogues answered from the browser. The script thread waits; stopping the script cancels."""

    def __init__(self):
        self._lock = threading.Lock()
        self._pending = {}
        self._ids = itertools.count(1)

    @staticmethod
    def fields(message, mode):
        if mode == 0:
            labels = message if isinstance(message, list) else [message]
            return [{'type': 'entry', 'label': str(label), 'value': ''} for label in labels]
        result = []
        for widget in message:
            kind = str(widget[0]).lower()
            if kind == 'next':
                result.append({'type': 'next'})
            elif kind == 'check':
                result.append({'type': 'check', 'label': str(widget[1]), 'value': bool(widget[2])})
            elif kind == 'entry':
                result.append({'type': 'entry', 'label': str(widget[1]), 'value': str(widget[2])})
            elif kind in ('combo', 'radio', 'spin'):
                result.append({'type': kind, 'label': str(widget[1]), 'options': [str(v) for v in widget[2]],
                               'value': str(widget[3])})
            elif kind == 'scale':
                digit = int(widget[5]) if len(widget) > 5 else 0
                result.append({'type': 'scale', 'label': str(widget[1]), 'min': widget[2], 'max': widget[3],
                               'value': widget[4], 'digit': digit})
            else:
                raise ValueError(f'Unknown dialogue widget: {widget[0]}')
        return result

    def ask(self, title, message, desc=None, mode=0, need=list):
        fields = self.fields(message, mode)
        entry = {'id': next(self._ids), 'title': str(title), 'desc': str(desc if desc is not None else title),
                 'fields': fields, 'event': threading.Event(), 'answer': None}
        with self._lock:
            self._pending[entry['id']] = entry
        try:
            entry['event'].wait()
        finally:
            with self._lock:
                self._pending.pop(entry['id'], None)
        values = entry['answer']
        if values is None:
            return False
        inputs = [f for f in fields if f['type'] != 'next']
        converted = []
        for field, value in zip(inputs, values):
            if field['type'] == 'check':
                value = bool(value)
            elif field['type'] == 'scale':
                value = round(float(value), field['digit']) if field['digit'] > 0 else int(round(float(value)))
            else:
                value = str(value)
            converted.append(value)
        if need is dict:
            return {f['label']: v for f, v in zip(inputs, converted)}
        return converted

    def handle(self, command, title, message, desc=None, need=list, mode=0, pos=2):
        """Command.dialogue_handler: the fork origin's scripts ask their dialogues through this."""
        return self.ask(title, message, desc, mode, need)

    def answer(self, dialog_id, values):
        with self._lock:
            entry = self._pending.get(dialog_id)
        if entry is None:
            raise ValueError('Dialogue not found')
        if values is not None:
            expected = sum(1 for f in entry['fields'] if f['type'] != 'next')
            if not isinstance(values, list) or len(values) != expected:
                raise ValueError(f'Expected {expected} values')
            for field, value in zip([f for f in entry['fields'] if f['type'] != 'next'], values):
                if field['type'] == 'scale':
                    try:
                        float(value)
                    except (TypeError, ValueError):
                        raise ValueError(f"{field['label']}: a number is required") from None
        entry['answer'] = values
        entry['event'].set()

    def cancel_all(self):
        with self._lock:
            entries = list(self._pending.values())
        for entry in entries:
            entry['answer'] = None
            entry['event'].set()

    def current(self):
        with self._lock:
            return [{k: e[k] for k in ('id', 'title', 'desc', 'fields')} for e in self._pending.values()]


class Core:
    """Everything the Tk window used to own, driven by the browser UI and MCP."""

    def __init__(self, profile, profile_dir, demo=False, console_mirror=None, label=''):
        import os
        import plus_runtime
        plus_runtime.install()
        from plus_settings import HeadlessSettings
        from services.settings_store import AppSettings
        from Commands.CommandBase import Command
        from Commands.Keys import KeyPress
        from plus_camera import PlusCamera
        from LineNotify import Line_Notify
        from DiscordNotify import Discord_Notify
        from ExternalTools import SocketCommunications, MQTTCommunications
        from product import NAME, VERSION
        self._logger = logging.getLogger(__name__)
        self.lock = threading.RLock()
        self.profile, self.demo = profile, demo
        self.label = label or profile  # the Switch's name, shown in notifications
        self.exit_requested = False
        AppSettings.SETTING_PATH = HeadlessSettings.SETTING_PATH = os.path.join(profile_dir, 'settings.ini')
        Line_Notify.LINE_TOKEN_PATH = os.path.join(profile_dir, 'line_token.ini')
        Discord_Notify.DISCORD_SETTING_PATH = os.path.join(profile_dir, 'discord_token.ini')
        SocketCommunications.SOCKET_TOKEN_PATH = os.path.join(profile_dir, 'external_token.ini')
        MQTTCommunications.MQTT_TOKEN_PATH = os.path.join(profile_dir, 'external_token.ini')
        self.settings = HeadlessSettings()
        self.log1, self.log2 = LogArea(), LogArea()
        self.overlay, self.dialogs = Overlay(), Dialogs()
        import script_windows
        script_windows.track_tkinter()
        self.windows = script_windows.ScriptWindows()
        Command.text_area_1, Command.text_area_2 = self.log1, self.log2
        Command.canvas = self.overlay
        Command.app_name = f'{NAME} ver.{VERSION}'
        Command.profilename = profile
        Command.dialogue_handler = self.dialogs.handle
        self.console_mirror = console_mirror
        self.apply_options()
        self.camera = PlusCamera(int(self.settings.fps.get() or 45), self.settings.capture_size.get() or '1280x720')
        # Screenshots go to the chosen capture folder (settings: フォルダー).
        import app_paths
        import Camera as camera_module
        if app_paths.folder_choices().get('captures'):
            camera_module.CAPTURE_DIR = str(app_paths.CAPTURES)
            self.camera.capture_dir = str(app_paths.CAPTURES)
        self.camera_missing, self.next_camera_check = False, 0
        self._apply_mask_filter()
        self.audio = None
        self.show_serial = Var(bool(self.settings.is_show_serial.get()))
        self.ser = plus_runtime.make_sender(self.show_serial.get())
        if demo:
            plus_runtime.install_demo_sender(self.ser)
        KeyPress.serial_data_format_name = self.settings.serial_data_format_name.get() or 'Default'
        self.keys_software_controller = KeyPress(self.ser)
        self.cur_command, self.running = None, False
        self.starting = None  # name of a script whose setup (e.g. its own settings window) is still open
        self.keyboard_session = None
        self.reported_error = ''
        from assist import Assist
        self.assist = Assist(self, profile_dir)
        from watch import Watch
        from recorder import Recorder
        self.watch = Watch(self, profile_dir)
        self.watch.history.set_fps(self.clip_fps())
        self._clip_pending = False
        Discord_Notify.after_send = self.discord_after_send
        self.recorder = Recorder(self)
        # The fork origin's SleepWatch: after the PC slept, a running script is stopped (the Switch kept going).
        from services.sleep_watch import SleepWatch
        self.sleep_watch = SleepWatch(self._resumed)
        self.sleep_watch.start()
        threading.Thread(target=self.apply_audio, name='audio', daemon=True).start()
        # The fork origin's schedule: start a script at a time, stop at a time or after some minutes.
        from services.run_schedule import RunSchedule
        self.schedule = RunSchedule(self._scheduled_start, self.stop_script, lambda: self.running, print)
        self.load_scripts()
        self.open_camera()
        self.open_serial()

    # ---- options and logs ----
    def apply_options(self):
        from Commands.CommandBase import Command
        s = self.settings
        Command.isSimilarity = bool(s.is_show_value.get())
        Command.isGuide = bool(s.is_show_guide.get())
        Command.isWinNotStart = bool(s.is_win_notification_start.get())
        Command.isWinNotEnd = bool(s.is_win_notification_end.get())
        Command.isLineNotStart = bool(s.is_line_notification_start.get())
        Command.isLineNotEnd = bool(s.is_line_notification_end.get())
        Command.isDiscordNotStart = bool(s.is_discord_notification_start.get())
        Command.isDiscordNotEnd = bool(s.is_discord_notification_end.get())
        Command.isDiscordSwitchCapture = bool(s.is_discord_switch_capture.get())
        from Commands.PythonCommandBase import PythonCommand
        PythonCommand.isDiscordSwitchCapture = Command.isDiscordSwitchCapture
        if getattr(self, 'watch', None) is not None:
            self.watch.history.set_fps(self.clip_fps())
        Command.stdout_destination = str(s.stdout_destination or '1')
        Command.pos_dialogue_buttons = str(getattr(s, 'pos_dialogue_buttons', '2') or '2')
        sys.stdout = Console(self.log1 if Command.stdout_destination == '1' else self.log2, self.console_mirror)

    OPTIONS = {'show_realtime': 'is_show_realtime', 'show_value': 'is_show_value', 'show_guide': 'is_show_guide',
               'show_serial': 'is_show_serial', 'keyboard': 'is_use_keyboard',
               'win_start': 'is_win_notification_start', 'win_end': 'is_win_notification_end',
               'line_start': 'is_line_notification_start', 'line_end': 'is_line_notification_end',
               'discord_start': 'is_discord_notification_start', 'discord_end': 'is_discord_notification_end',
               'discord_capture': 'is_discord_switch_capture', 'discord_clip': 'is_discord_clip'}

    def options(self):
        return {key: bool(getattr(self.settings, name).get()) for key, name in self.OPTIONS.items()}

    def set_options(self, values):
        with self.lock:
            for key, value in values.items():
                if key not in self.OPTIONS or not isinstance(value, bool):
                    raise ValueError(f'Unknown option: {key}')
                getattr(self.settings, self.OPTIONS[key]).set(value)
            self.show_serial.set(bool(self.settings.is_show_serial.get()))
            self.ser.set_show_serial(self.show_serial.get())
            self.apply_options()
            self.save()

    # Settings from the original app's tabs that still mean something without its window.
    CHOICES = {'stdout_destination': ('1', '2'), 'dialog_buttons': ('1', '2', '3'), 'fps': ('15', '30', '45', '60')}

    def choices(self):
        s = self.settings
        return {'stdout_destination': str(s.stdout_destination or '1'),
                'dialog_buttons': str(getattr(s, 'pos_dialogue_buttons', '2') or '2'),
                'fps': str(s.fps.get() or '45')}

    def set_choice(self, name, value):
        with self.lock:
            value = str(value)
            if value not in self.CHOICES.get(name, ()):
                raise ValueError(f'Invalid value for {name}')
            if name == 'stdout_destination':
                self.settings.stdout_destination = value
            elif name == 'dialog_buttons':
                self.settings.pos_dialogue_buttons = value
            else:
                self.settings.fps.set(value)
                self.camera.fps = int(value)
            self.apply_options()
            self.save()

    def shortcuts(self):
        s = self.settings
        result = []
        for slot in range(1, 11):
            kind = str(s.command_class_dict.get(str(slot), 'None'))
            name = s.command_name_dict[str(slot)].get()
            kind = {'Python': 'python', 'Mcu': 'mcu'}.get(kind)
            result.append({'slot': slot, 'kind': kind, 'name': name if kind else ''})
        return result

    def set_shortcut(self, slot, kind, name):
        with self.lock:
            if not isinstance(slot, int) or not 1 <= slot <= 10:
                raise ValueError('slot must be 1-10')
            key = str(slot)
            if not name:
                self.settings.command_class_dict[key] = 'None'
                self.settings.command_name_dict[key].set('(empty)')
            else:
                entries = self.py_entries if kind == 'python' else self.mcu_entries if kind == 'mcu' else None
                if entries is None or name not in [e.name for e in entries]:
                    raise ValueError('Script not found')
                self.settings.command_class_dict[key] = 'Python' if kind == 'python' else 'Mcu'
                self.settings.command_name_dict[key].set(name)
            self.save()

    def set_keymap(self, mapping):
        """Save input -> key pairs into settings.ini (KeyMap-*), the format the original key config used."""
        from safe_settings import read_config, write_config
        reverse_keys = {v: k for k, v in self.KEY_NAMES.items()}
        reverse_hats = {v: k for k, v in self.HAT_NAMES.items()}
        reverse_sticks = {v: k for k, v in self.STICK_NAMES.items()}
        with self.lock:
            config = read_config(self.settings.SETTING_PATH)
            for target, key in mapping.items():
                key = str(key or '')
                if key and len(key) != 1 and key not in reverse_keys:
                    raise ValueError(f'Unsupported key: {key}')
                stored = reverse_keys.get(key, key.lower())
                if target in reverse_hats:
                    section, name = 'KeyMap-Hat', reverse_hats[target]
                elif target in reverse_sticks:
                    section, name = 'KeyMap-Direction', reverse_sticks[target]
                else:
                    section, name = 'KeyMap-Button', 'Button.' + str(target)
                    if section not in config or name not in config[section]:
                        raise ValueError(f'Unknown input: {target}')
                if section not in config:
                    config[section] = {}
                keymaps = [s for s in ('KeyMap-Button', 'KeyMap-Hat', 'KeyMap-Direction') if s in config]

                def placeholder():
                    # The original app marks an unassigned entry with a number no key produces; keep them unique.
                    used = {v for s in keymaps for v in config[s].values()}
                    return next(str(n) for n in range(30000, 40000) if str(n) not in used)
                if stored:
                    # One key drives one input: unassign it wherever else it was used.
                    for other in keymaps:
                        for other_name, value in list(config[other].items()):
                            if value == stored and (other, other_name) != (section, name):
                                config[other][other_name] = placeholder()
                else:
                    stored = placeholder()
                config[section][name] = stored
            write_config(self.settings.SETTING_PATH, config)
            self.settings.load()

    def notification_settings(self):
        import configparser
        from LineNotify import Line_Notify
        from DiscordNotify import Discord_Notify
        def read(path):
            config = configparser.ConfigParser(interpolation=None)
            try:
                config.read(path, encoding='utf-8-sig')
            except (OSError, configparser.Error):
                pass
            return config
        line = read(Line_Notify.LINE_TOKEN_PATH)
        discord = read(Discord_Notify.DISCORD_SETTING_PATH)
        hook = discord['DISCORD_WEBHOOK'] if 'DISCORD_WEBHOOK' in discord else {}
        return {'line_token_set': bool(line['LINE'].get('token', '').strip()) if 'LINE' in line else False,
                'discord_webhook_set': bool(str(hook.get('webhook_url', '')).strip()),
                'discord_username': str(hook.get('username', ''))}

    def discord_webhook(self):
        """The saved webhook URL, for the settings page only (not part of the state sent with every update)."""
        import configparser
        from DiscordNotify import Discord_Notify
        config = configparser.ConfigParser(interpolation=None)
        try:
            config.read(Discord_Notify.DISCORD_SETTING_PATH, encoding='utf-8-sig')
        except (OSError, configparser.Error):
            return ''
        return config.get('DISCORD_WEBHOOK', 'webhook_url', fallback='').strip()

    WEBHOOK_URL = r'^https://([\w-]+\.)?discord(app)?\.com/api/webhooks/\d+/[\w-]+$'

    def discord_destinations(self):
        """The webhooks besides DISCORD_WEBHOOK that scripts can send to by name (name=...), with their URLs: for the
        settings page only."""
        import DiscordNotify
        setting = DiscordNotify.load_setting(DiscordNotify.Discord_Notify.DISCORD_SETTING_PATH)
        return [{'name': name, 'url': setting.get(name, 'webhook_url', fallback='').strip()}
                for name in DiscordNotify.webhook_names(setting) if name != DiscordNotify.DEFAULT_WEBHOOK]

    def save_discord_destination(self, name, url, original=''):
        """Add or change a named webhook (original: its name before this edit). Raises ValueError with the reason."""
        import re
        import DiscordNotify
        name, url, original = str(name).strip(), str(url).strip(), str(original).strip()
        error = DiscordNotify.check_webhook_name(name)
        if error is None and name == DiscordNotify.DEFAULT_WEBHOOK:
            error = f'{name} は上の「Webhook URL」で設定します。'
        if error is None and not re.match(Core.WEBHOOK_URL, url):
            error = 'Discord の Webhook URL（https://discord.com/api/webhooks/… ）を入力してください。'
        path = DiscordNotify.Discord_Notify.DISCORD_SETTING_PATH
        with self.lock:
            setting = DiscordNotify.load_setting(path)
            names = DiscordNotify.webhook_names(setting)
            if error is None and name != original and name in names:
                error = f'「{name}」という送り先は、すでにあります。'
            if error:
                raise ValueError(error)
            if original and original != name and original != DiscordNotify.DEFAULT_WEBHOOK:
                setting.remove_section(original)
            setting[name] = {'webhook_url': url, 'username': '', 'avatar_url': ''}
            DiscordNotify.save_setting(path, setting)

    def delete_discord_destination(self, name):
        import DiscordNotify
        name = str(name).strip()
        if name in (DiscordNotify.DEFAULT_WEBHOOK, DiscordNotify.RECEIVE_SECTION):
            raise ValueError(f'{name} は削除できません。')
        path = DiscordNotify.Discord_Notify.DISCORD_SETTING_PATH
        with self.lock:
            setting = DiscordNotify.load_setting(path)
            if setting.remove_section(name):
                DiscordNotify.save_setting(path, setting)

    def set_notification(self, values):
        """Write LINE / Discord settings into the profile's token files, keeping other entries."""
        import configparser
        import os
        from LineNotify import Line_Notify
        from DiscordNotify import Discord_Notify
        def update(path, section, items, required=()):
            config = configparser.ConfigParser(interpolation=None)
            if os.path.isfile(path):
                config.read(path, encoding='utf-8-sig')
            if section not in config:
                config[section] = {}
            for key in required:
                # The notifier reads these keys directly; a missing one breaks every script start.
                config[section].setdefault(key, '')
            for key, value in items.items():
                config[section][key] = value
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as stream:
                config.write(stream)
        with self.lock:
            if 'line_token' in values:
                update(Line_Notify.LINE_TOKEN_PATH, 'LINE', {'token': str(values['line_token']).strip()})
            discord = {k: str(values[f'discord_{k}']).strip() for k in ('webhook_url', 'username') if f'discord_{k}' in values}
            if discord:
                path = Discord_Notify.DISCORD_SETTING_PATH
                update(path, 'DISCORD_WEBHOOK', discord, required=('webhook_url', 'username', 'avatar_url'))

    def notify_test(self, channel):
        from product import NAME
        message = f'{NAME} ({self.label}) のテスト通知です。'
        if channel == 'win':
            from plyer import notification
            notification.notify(title='Poke-Controller', message=message, timeout=5)
        elif channel == 'line':
            from LineNotify import Line_Notify
            Line_Notify().send_message(message)
        elif channel == 'discord':
            from DiscordNotify import Discord_Notify
            Discord_Notify().send_message(message, follow_up=False)
        else:
            raise ValueError('Unknown channel')

    def send_discord_image(self):
        # The original window's Discord button: the current frame to the Discord webhook.
        from product import NAME
        from DiscordNotify import Discord_Notify
        frame = self.camera.readFrame() if self.camera_live() else None
        if frame is None:
            raise ValueError('送る映像がありません')
        if not self.notification_settings()['discord_webhook_set']:
            raise ValueError('Discord の Webhook URL が設定されていません（設定の「Discord 連携」）')
        frame = frame.copy()
        self.switch_capture()
        Discord_Notify().send_message(f'{NAME} ({self.label}) の画面', image=frame)

    # ---- Discord 連携: Switch 本体の録画と、直前の映像の添付 ----
    CLIP_FPS = 10  # frames a second kept for the clip while attaching it is on (the watch's own clips use 4)
    CLIP_AFTER = 3  # seconds of video after the notification that go into the clip too
    CLIP_MAX_BYTES = 9_500_000  # Discord takes files up to 10 MB without Nitro

    def clip_fps(self):
        return self.CLIP_FPS if self.settings.is_discord_clip.get() else 4

    def switch_capture(self):
        """For the page's send-to-Discord button: record on the Switch when that is turned on and no script runs (a
        running script records from its own thread, keeping what it holds)."""
        from Commands.Keys import Button
        from Commands import PythonCommandBase
        if not self.settings.is_discord_switch_capture.get():
            return False
        with self.lock:
            if self.running or not self.serial_open():
                return False
            self.keys_software_controller.hold(Button.CAPTURE)
        try:
            time.sleep(PythonCommandBase.PythonCommand.SWITCH_CAPTURE_SECONDS)
        finally:
            with self.lock:
                self.keys_software_controller.holdEnd(Button.CAPTURE)
        PythonCommandBase.PythonCommand._last_switch_capture = time.monotonic()
        print('Switch 本体で直前の映像を録画しました。')
        return True

    def discord_after_send(self, notify, keys):
        """After a Discord notification: attach the app's video of the last 30 seconds, when that is turned on."""
        if not self.settings.is_discord_clip.get() or self._clip_pending:
            return
        self._clip_pending = True
        started = time.time() - self.watch.history.seconds

        def send():
            try:
                time.sleep(self.CLIP_AFTER)
                data = self.watch.history.encode_mp4(since=started)
                if not data:
                    print('Discord: 添付する映像がありません。')
                elif len(data) > self.CLIP_MAX_BYTES:
                    print(f'Discord: 映像が大きすぎるため添付しませんでした（{len(data) // 1_000_000}MB）。')
                else:
                    notify.send_file(keys, f"pokecon_{time.strftime('%Y%m%d-%H%M%S')}.mp4", data)
            except Exception as exc:
                print(f'Discord: 映像を添付できませんでした: {exc}')
            finally:
                self._clip_pending = False

        threading.Thread(target=send, daemon=True).start()

    def about(self):
        """Versions for the version window and the question template (the original help menu)."""
        import platform
        from importlib import metadata
        from pathlib import Path
        from product import NAME, VERSION
        root = Path(__file__).resolve().parent

        def read(name):
            try:
                return (root / name).read_text(encoding='utf-8-sig')
            except OSError:
                return ''
        libraries = []
        for line in read('requirements.txt').splitlines():
            name = line.split('#')[0].split('==')[0].split('>=')[0].strip()
            if not name:
                continue
            try:
                libraries.append([name, metadata.version(name)])
            except metadata.PackageNotFoundError:
                libraries.append([name, ''])
        command = self.cur_command
        script = {}
        if command is not None:
            script = {'name': str(getattr(command, 'NAME', '') or ''), 'file': str(getattr(command, 'FILENAME', '') or ''),
                      'developer': str(getattr(command, 'DEVELOPER', '') or '')}
        return {'name': NAME, 'version': VERSION, 'os': platform.platform(), 'python': sys.version.split(' ')[0],
                'libraries': libraries, 'script': script, 'license': read('LICENSE'), 'changelog': read('changelog.txt')}

    def reconnect_camera_now(self):
        with self.lock:
            self.camera_missing = False
            self.open_camera()

    def clear_log(self, which):
        (self.log1 if which == 1 else self.log2).delete()

    def save(self):
        try:
            self.settings.save()
        except (OSError, ValueError):
            self._logger.exception('設定の保存に失敗しました')

    # ---- scripts ----
    # The fork origin's loaders list scripts from their source (nothing is imported until a script runs).
    def load_scripts(self):
        import Utility as util
        from CommandLoader import CommandLoader, CombinedLoader
        from Commands import PythonCommandBase, McuCommandBase
        import Paths
        from services.run_list import RunListLoader
        self.run_loader = RunListLoader(RunListService(self))
        self.py_loader = CombinedLoader(CommandLoader(util.ospath('Commands/PythonCommands'), PythonCommandBase.PythonCommand),
                                        ScriptLoader(Paths.SCRIPTS, PythonCommandBase.PythonCommand), self.run_loader)
        self.mcu_loader = CommandLoader(util.ospath('Commands/McuCommands'), McuCommandBase.McuCommand)
        self.py_entries = self.py_loader.load()
        self.mcu_entries = self.mcu_loader.load()
        self.reload_next = set()

    def reload_scripts(self):
        with self.lock:
            if self.running:
                raise ValueError('Stop the running script before reloading')
            self.py_entries = self.py_loader.reload()
            self.mcu_entries = self.mcu_loader.reload()
            # Edited files are read again when their script next starts.
            self.reload_next = {e.module_name for e in self.py_entries + self.mcu_entries}
            print('スクリプトを再読み込みしました。')

    def find_entry(self, name, kind=None):
        """The listed script with this name ("NAME (folder/file)"), or None."""
        lists = {'python': self.py_entries, 'mcu': self.mcu_entries}
        for key in ([kind] if kind else ['python', 'mcu']):
            entry = next((e for e in lists.get(key, []) if e.name == name), None)
            if entry is not None:
                return entry
        return None

    def script_class(self, entry, kind):
        """Import the script (again after a reload) and return its class."""
        loader = self.py_loader if kind == 'python' else self.mcu_loader
        reload = entry.module_name in self.reload_next
        cls = loader.getCommandClass(entry, reload=reload)
        self.reload_next.discard(entry.module_name)
        return cls

    def write_script(self, path, content, overwrite=False):
        """Save a script, reload, and report the script names it defines or why it could not be loaded."""
        import importlib
        import os
        import sys
        import traceback
        import script_files
        with self.lock:
            backup = script_files.write(path, content, overwrite)
            module = script_files.module_name(path)
            result = {'path': str(path), 'backup': backup, 'names': [], 'error': ''}
            if self.running:
                result['error'] = 'スクリプトの実行中なので、再読み込みしていません。止めてから reload してください。'
                return result
            # Forget the old module so nothing of the previous version stays when the new one fails to load.
            sys.modules.pop(module, None)
            importlib.invalidate_caches()
            self.reload_scripts()
            names = [e.name for e in self.py_entries if e.module_name == module]
            if names:
                try:
                    self.script_class(self.find_entry(names[0], 'python'), 'python')
                except Exception:
                    lines = traceback.format_exc().splitlines(True)
                    first = next((n for n, line in enumerate(lines) if script_files.resolve(path) in line), 0)
                    result['error'] = ''.join(lines[first:][-12:])
                    return result
            result['names'] = names
            if not result['names']:
                try:
                    importlib.import_module(module)
                    result['error'] = 'NAME を持つ PythonCommand（または ImageProcPythonCommand）のクラスがありません。'
                except Exception:
                    lines = traceback.format_exc().splitlines(True)
                    first = next((n for n, line in enumerate(lines) if script_files.resolve(path) in line), 0)
                    result['error'] = ''.join(lines[first:][-12:])
            return result

    def catalog(self):
        import app_paths
        bundled = app_paths.PROGRAM / 'SerialController'

        def is_sample(entry):
            # A script that came with the app (its file is in the program's copy), listed after the user's own.
            module = entry.module_name.split('.')
            return module[:2] == ['Commands', 'PythonCommands'] and bundled.joinpath(*module).with_suffix('.py').is_file()

        def describe(entries):
            return [{'name': e.name, 'tags': list(e.tags or []), 'sample': is_sample(e)} for e in entries]
        return {'python': describe(self.py_entries), 'mcu': describe(self.mcu_entries)}

    def start_script(self, kind, name, restart=False):
        from Commands.CommandBase import Command
        from Commands import PythonCommandBase
        with self.lock:
            if self.running:
                raise ValueError('A script is already running')
            if kind not in ('python', 'mcu'):
                raise ValueError('Unknown script kind')
            entry = self.find_entry(name, kind)
            if entry is None:
                raise ValueError('Script not found')
            if self.demo and not self._demo_allows(entry):
                raise ValueError('Demo mode only runs PortableDemo')
            if not self.serial_open():
                raise ValueError('COM port is not connected')
            if self.starting:
                raise ValueError('A script is already starting')
            self.starting = name
        # A script may open its own settings window while it is created and wait there. Create it on its own thread,
        # so the app keeps answering (and shows that window) until the user closes it.
        threading.Thread(target=self._create_and_start, args=(entry, kind, name, restart), daemon=True,
                         name='script-setup').start()

    def _demo_allows(self, entry):
        """The demo runs PortableDemo, and run lists made only of it."""
        if entry.module_name:
            return entry.module_name == DEMO_SCRIPT
        run_list = self.run_loader._lists.get(entry.name)
        demo = [e.name for e in self.py_entries if e.module_name == DEMO_SCRIPT]
        return run_list is not None and all(item.name in demo for item in run_list.items)

    def create_command(self, cls, kind):
        """An instance of a script class (an image script gets the camera and the overlay)."""
        from Commands import PythonCommandBase
        if kind == 'python' and issubclass(cls, PythonCommandBase.ImageProcPythonCommand):
            try:
                return cls(self.camera, self.overlay)
            except TypeError:
                return cls(self.camera)
        return cls()

    def _create_and_start(self, entry, kind, name, restart):
        from Commands.CommandBase import Command
        try:
            command = self.create_command(self.script_class(entry, kind), kind)
        except BaseException as error:
            with self.lock:
                if self.starting == name:
                    self.starting = None
                    print(f'開始できませんでした: {name}: {type(error).__name__}: {error}')
            return
        with self.lock:
            if self.starting != name or self.running:
                return  # stopped while its setup was open
            self.starting = None
            if not self.serial_open():
                print(f'開始できませんでした: {name}: COM ポートがつながっていません')
                return
            self.keys_software_controller.neutral()
            Command.isPause = False
            Command.cur_command_name = name
            self.cur_command, self.running = command, True
            print('開始 ' + name)
            command.start(self.ser, self._finished)
            self.watch.script_started(kind, name, restart)

    # ---- run lists and the schedule (the fork origin's services/run_list and run_schedule) ----
    def run_lists(self):
        from services import run_list
        return [run_list._to_dict(r) for r in run_list.load_lists()]

    def save_run_list(self, data, original=''):
        """Add or replace a run list (original: its name before this edit). Raises ValueError with the reason."""
        from services import run_list
        try:
            new = run_list._from_dict(data)
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ValueError('実行リストの形が正しくありません。')
        with self.lock:
            lists = run_list.load_lists()
            error = run_list.check_list(new, [r.name for r in lists if r.name != original])
            for index, item in enumerate(new.items, start=1):
                kind = 'python' if item.command_type == run_list.PYTHON else 'mcu'
                if not error and not run_list.is_list_name(item.command_type, item.name) and self.find_entry(item.name, kind) is None:
                    error = f'{index} 行目: スクリプトが見つかりません（{item.name}）。'
            if error:
                raise ValueError(error)
            names = [r.name for r in lists]
            target = original if original in names else new.name
            if target in names:
                lists[names.index(target)] = new
            else:
                lists.append(new)
            run_list.save_lists(lists)
            self._reload_run_lists()

    def delete_run_list(self, name):
        from services import run_list
        with self.lock:
            run_list.save_lists([r for r in run_list.load_lists() if r.name != name])
            self._reload_run_lists()

    def _reload_run_lists(self):
        """Show saved run lists in the script list (the scripts themselves are not read again)."""
        self.py_entries = [e for e in self.py_entries if e.module_name] + self.run_loader.load()

    def _scheduled_start(self, command_type, name):
        try:
            self.start_script('python' if command_type == 'Python' else 'mcu', name)
            return True
        except ValueError as error:
            print(f'予約: {error}')
            return False

    def set_schedule(self, values):
        """values: start {time 'HH:MM', kind, name} / stop {time 'HH:MM'} or {minutes} / cancel 'start'|'stop'."""
        import datetime
        from services import run_schedule
        with self.lock:
            cancel = values.get('cancel')
            if cancel == 'start':
                self.schedule.cancel_start()
            elif cancel == 'stop':
                self.schedule.cancel_stop()
            if 'start' in values:
                start = values['start'] or {}
                kind, name = start.get('kind', 'python'), str(start.get('name', ''))
                if self.find_entry(name, kind) is None:
                    raise ValueError('スクリプトを選んでください。')
                when = run_schedule.parse_clock(str(start.get('time', '')), datetime.datetime.now())
                self.schedule.reserve_start(when, 'Python' if kind == 'python' else 'Mcu', name)
            if 'stop' in values:
                stop = values['stop'] or {}
                if stop.get('time'):
                    self.schedule.reserve_stop_at(run_schedule.parse_clock(str(stop['time']), datetime.datetime.now()))
                else:
                    error = self.schedule.reserve_stop_after(run_schedule.parse_minutes(str(stop.get('minutes', ''))))
                    if error:
                        raise ValueError(error)

    def schedule_state(self):
        start, stop = self.schedule.describe()
        return {'start': start if self.schedule.start_at else '', 'stop': stop if (self.schedule.stop_at or self.schedule.stop_after_minutes) else ''}

    # ---- the capture board's sound (the fork origin's Audio tab: AudioService with sounddevice). Heard on this PC's
    # speakers, with a level meter on the page.
    AUDIO_FIELDS = ('is_use_audio', 'audio_device', 'audio_output_device', 'is_audio_playback', 'audio_volume')

    def _audio(self):
        if self.audio is None:
            import plus_audio
            from services.audio_service import AudioService
            plus_audio.install()
            self.audio = AudioService(AudioSettings(self.settings))
            if self.audio.available:
                self.audio.refresh(self._audio_cameras())
        return self.audio

    def _audio_cameras(self):
        """The camera this Switch uses, as the fork origin's {number: device path} (to find the same board's sound)."""
        path = self.settings.camera_path
        return {0: path} if path else {}

    def apply_audio(self):
        audio = self._audio()
        if audio.available:
            with self.lock:
                audio.apply(self._audio_cameras(), 0)

    def audio_state(self):
        audio = self.audio
        if audio is None:
            return {'available': None}
        if not audio.available:
            from Audio import AUDIO_IMPORT_ERROR
            return {'available': False, 'error': str(AUDIO_IMPORT_ERROR or '')}
        settings = AudioSettings(self.settings)
        from services.audio_service import OUTPUT_DEFAULT
        return {'available': True, 'use': bool(settings.is_use_audio), 'running': audio.is_running,
                'input': settings.audio_device, 'inputs': list(audio.inputs),  # this Switch's capture board first
                'playback': bool(settings.is_audio_playback), 'output': settings.audio_output_device or OUTPUT_DEFAULT,
                'outputs': [OUTPUT_DEFAULT] + list(audio.outputs), 'volume': int(settings.audio_volume or 0),
                'meter': audio.meter()}

    def set_audio(self, values):
        """values: use, input, playback, output, volume (0-100), refresh (list the devices again)."""
        audio = self._audio()
        if not audio.available:
            raise ValueError('音声を扱うライブラリ（sounddevice）が使えません。')
        settings = AudioSettings(self.settings)
        with self.lock:
            if values.get('refresh'):
                audio.refresh(self._audio_cameras())
            restart = False
            if 'input' in values and str(values['input']) != settings.audio_device:
                settings.audio_device, restart = str(values['input']), True
            if 'use' in values and bool(values['use']) != bool(settings.is_use_audio):
                settings.is_use_audio, restart = bool(values['use']), True
            if restart:
                audio.apply(self._audio_cameras(), 0)
            if 'output' in values:
                settings.audio_output_device = str(values['output'])
                audio.apply_output_device()
            if 'playback' in values:
                settings.is_audio_playback = bool(values['playback'])
                audio.apply_playback()
            if 'volume' in values:
                settings.audio_volume = min(max(int(values['volume']), 0), 100)
                audio.apply_volume()
            self.settings.save()

    # ---- covering parts of the picture (the fork origin's Mask tab: settings.ini [Mask]). The camera image itself is
    # not changed, so scripts still see everything; the masks are drawn on what the page shows and, when chosen, on
    # screenshots.
    MAX_MASKS = 20

    def masks(self):
        from Mask import Mask
        result = []
        for text in self.settings.masks:
            try:
                result.append(Mask.from_text(text))
            except ValueError:
                pass
        return result

    def masks_state(self):
        from dataclasses import asdict
        return {'show': bool(self.settings.is_show_mask), 'apply': bool(self.settings.is_mask_apply_to_capture),
                'items': [asdict(mask) for mask in self.masks()]}

    def set_masks(self, values):
        """values: show, apply (bool) and/or items [{shape, x1, y1, x2, y2, color, enabled}] (camera image pixels)."""
        from Mask import MASK_SHAPES, Mask, hex_to_bgr
        with self.lock:
            if 'items' in values:
                items = []
                for item in list(values['items'] or [])[:self.MAX_MASKS]:
                    shape, color = str(item.get('shape', '')), str(item.get('color', '#000000'))
                    if shape not in MASK_SHAPES:
                        raise ValueError('目隠しの形が正しくありません。')
                    hex_to_bgr(color)
                    mask = Mask(shape, *(int(item.get(key, 0)) for key in ('x1', 'y1', 'x2', 'y2')), color,
                                bool(item.get('enabled', True))).normalized()
                    if mask.x2 - mask.x1 >= 2 and mask.y2 - mask.y1 >= 2:
                        items.append(mask)
                self.settings.masks = [mask.to_text() for mask in items]
            if 'show' in values:
                self.settings.is_show_mask = bool(values['show'])
            if 'apply' in values:
                self.settings.is_mask_apply_to_capture = bool(values['apply'])
            self._apply_mask_filter()
            self.settings.save()

    def _apply_mask_filter(self):
        on = self.settings.is_show_mask and self.settings.is_mask_apply_to_capture
        self.camera.capture_filter = self.mask_image if on else None

    def mask_image(self, image):
        """The picture as the page shows it (with the masks, when they are shown)."""
        from Mask import draw_masks
        if image is None or not self.settings.is_show_mask:
            return image
        return draw_masks(image, self.masks())

    # ---- typing on the Switch's keyboard (the fork origin's KeyboardSession; the microcontroller types as a USB keyboard)
    def keyboard_unavailable(self):
        """Why text cannot be typed on the Switch now ('' when it can)."""
        if self.running:
            return 'スクリプトの実行中は使えません。'
        if self.demo:
            return ''
        from services.keyboard_typer import KeyboardTyper
        return KeyboardTyper.unavailable_reason(Mock_typer(self.ser))

    def switch_keyboard(self, values):
        """values: text (+ enter) to type, or key 'backspace' / 'space' / 'enter' / 'ok'."""
        from services.keyboard_session import KeyboardSession
        reason = self.keyboard_unavailable()
        if reason:
            raise ValueError(reason)
        with self.lock:
            if self.keyboard_session is None:
                self.keyboard_session = KeyboardSession(DemoPort(self.ser) if self.demo else self.ser, on_message=lambda text, error: print('キーボード: ' + text))
            session = self.keyboard_session
        key = values.get('key')
        if key == 'ok':
            accepted = session.ok()
        elif key:
            accepted = session.special(str(key))
        else:
            accepted = session.send_text(str(values.get('text', '')), True, bool(values.get('enter')))
        if not accepted and not key and values.get('text'):
            raise ValueError('送れませんでした（ログを見てください）。')

    def _resumed(self, seconds):
        """The PC was suspended for this many seconds: stop the running script and say why."""
        with self.lock:
            if not self.running or self.cur_command is None:
                return
            self.watch.expect_stop()
            self.watch.report('sleep', f'約{int(seconds)}秒')
            self.dialogs.cancel_all()
            self.cur_command.end(self.ser)

    def _finished(self):
        self.running = False
        self.dialogs.cancel_all()

    def stop_script(self):
        from Commands.CommandBase import Command
        with self.lock:
            self.assist.cancel_sequence()
            if self.starting:
                print('停止 ' + self.starting + '（開始前）')
                self.starting = None
                self.windows.close_all()
            if self.running and self.cur_command is not None:
                self.watch.expect_stop()
                print('停止 ' + str(Command.cur_command_name or self.cur_command.NAME))
                Command.isPause = False
                self.dialogs.cancel_all()
                self.cur_command.end(self.ser)

    def pause(self, paused):
        from Commands.CommandBase import Command
        with self.lock:
            if self.running:
                Command.isPause = bool(paused)

    def script_alive(self):
        command = self.cur_command
        if command is None:
            return False
        thread = getattr(command, 'thread', None)
        return (thread is not None and thread.is_alive()) or bool(getattr(command, 'isRunning', False))

    # ---- camera ----
    def cameras(self):
        from WindowsDevices import enumerate_cameras
        return [{'name': d['name'], 'path': d['path']} for d in enumerate_cameras()]

    def open_camera(self):
        path = self.settings.camera_path
        if self.demo:
            from plus_camera import DemoSource, install_demo
            install_demo()
            self.camera.openCamera(window=DemoSource.NAME)
            return
        if not path:
            self.camera.destroy()
            return
        self.camera.openCamera(device_path=path)

    def select_camera(self, path):
        with self.lock:
            if path:
                device = next((d for d in self.cameras() if d['path'] == path), None)
                if device is None:
                    raise ValueError('Camera not found')
                self.settings.camera_path, self.settings.camera_name = device['path'], device['name']
            else:
                self.settings.camera_path, self.settings.camera_name = '', ''
            self.camera_missing = False
            self.save()
            self.open_camera()

    def camera_live(self):
        return getattr(self.camera, 'image_bgr', None) is not None and time.time() - getattr(self.camera, 'frame_at', 0) < 2

    def save_capture(self):
        with self.lock:
            if not self.camera_live():
                raise ValueError('No live camera frame')
            self.camera.saveCapture()

    # ---- serial ----
    def ports(self):
        from serial.tools import list_ports
        return [{'port': p.device, 'description': p.description} for p in sorted(list_ports.comports(), key=lambda p: p.device)]

    def serial_open(self):
        return self.demo or self.ser.isOpened()

    def serial_target(self):
        name = self.settings.com_port_name.get()
        number = int(self.settings.com_port.get() or 0)
        return name or (f'COM{number}' if number > 0 else '')

    def open_serial(self):
        name = self.settings.com_port_name.get() or ''
        number = int(self.settings.com_port.get() or 0)
        if not name and number <= 0:
            return False
        if self.ser.openSerial(number, name, int(self.settings.baud_rate.get() or 9600)):
            print(f'{self.serial_target()} に接続しました。')
            return True
        return False

    def connect_serial(self, port, baud=None, fmt=None):
        from Commands.Keys import KeyPress
        with self.lock:
            if self.running:
                raise ValueError('Stop the running script before changing the connection')
            fmt = fmt or self.settings.serial_data_format_name.get() or 'Default'
            if fmt not in serial_formats():
                raise ValueError('Unknown serial format')
            baud = int(baud or (115200 if '3DS Controller' in fmt else 9600))
            port = str(port or '').strip()
            if self.ser.isOpened():
                self.ser.closeSerial()
            if port.upper().startswith('COM') and port[3:].isdigit():
                self.settings.com_port.set(int(port[3:]))
                self.settings.com_port_name.set('')
            else:
                self.settings.com_port.set(0)
                self.settings.com_port_name.set(port)
            self.settings.baud_rate.set(baud)
            self.settings.serial_data_format_name.set(fmt)
            KeyPress.serial_data_format_name = fmt
            self.save()
            if port and not self.open_serial():
                raise ValueError(f'{port} に接続できません。ほかのアプリが使っていないか確認してください。')

    def disconnect_serial(self):
        with self.lock:
            if self.running:
                raise ValueError('Stop the running script before disconnecting')
            if self.ser.isOpened():
                try:
                    self.keys_software_controller.end()
                finally:
                    self.ser.closeSerial()
                print('シリアル接続を切断しました。')

    # ---- periodic work on the main thread ----
    def tick(self):
        with self.lock:
            error = self.ser.last_error
            if error and error != self.reported_error:
                # A lost port stops the script so it cannot keep sending into nothing.
                self.reported_error = error
                print(error)
                if self.running and self.cur_command is not None:
                    self.watch.serial_lost(error)
                    self.dialogs.cancel_all()
                    self.cur_command.end(self.ser)
            if not error:
                self.reported_error = ''
            if self.running and not self.script_alive():
                self.running = False
            self.watch.tick()
            self.schedule.tick()
            self.reconnect_camera()

    def reconnect_camera(self):
        """After the capture device was unplugged, reconnect once it is listed again."""
        camera, path = self.camera, self.settings.camera_path
        if self.demo or not path or not camera.error or time.monotonic() < self.next_camera_check:
            return
        if camera.thread is not None and camera.thread.is_alive():
            return
        self.next_camera_check = time.monotonic() + 3
        try:
            present = any(d['path'] == path for d in self.cameras())
        except OSError:
            return
        if not present:
            self.camera_missing = True
        elif self.camera_missing:
            self.camera_missing = False
            print('カメラ: 機器が再接続されたため接続し直します')
            self.open_camera()

    KEY_NAMES = {'Key.up': 'ArrowUp', 'Key.down': 'ArrowDown', 'Key.left': 'ArrowLeft', 'Key.right': 'ArrowRight',
                 'Key.space': ' ', 'Key.enter': 'Enter', 'Key.tab': 'Tab', 'Key.backspace': 'Backspace'}
    HAT_NAMES = {'Hat.TOP': 'UP', 'Hat.BTM': 'DOWN', 'Hat.LEFT': 'LEFT', 'Hat.RIGHT': 'RIGHT'}
    def reset_keymap(self):
        """Put the keyboard mapping back to what a new profile starts with."""
        from safe_settings import read_config, write_config
        from plus_settings import DEFAULT_KEYMAPS
        with self.lock:
            config = read_config(self.settings.SETTING_PATH)
            for section, values in DEFAULT_KEYMAPS.items():
                config[section] = dict(values)
            write_config(self.settings.SETTING_PATH, config)
            self.settings.load()

    STICK_NAMES = {'Direction.UP': 'LS_UP', 'Direction.DOWN': 'LS_DOWN', 'Direction.LEFT': 'LS_LEFT', 'Direction.RIGHT': 'LS_RIGHT'}

    def keymap(self):
        """The profile's keyboard mapping (settings.ini KeyMap-*) as browser key -> input name.
        Unassigned entries (the numeric placeholders of the original app) are left out."""
        result = {}
        setting = self.settings.setting
        sections = (('KeyMap-Button', lambda name: name.split('.', 1)[1] if name.startswith('Button.') else None),
                    ('KeyMap-Hat', self.HAT_NAMES.get), ('KeyMap-Direction', self.STICK_NAMES.get))
        for section, convert in sections:
            if section not in setting:
                continue
            for name, key in setting[section].items():
                target = convert(name)
                key = self.KEY_NAMES.get(key, key)
                if target and key and not key.isdigit() and (len(key) == 1 or key in self.KEY_NAMES.values()):
                    result[key.lower() if len(key) == 1 else key] = target
        return result

    def snapshot(self):
        from Commands.CommandBase import Command
        keys = self.keys_software_controller
        return {'profile': self.profile, 'label': self.label, 'running': self.running, 'paused': bool(Command.isPause),
                'starting': self.starting or '', 'windows': self.windows.list(), 'schedule': self.schedule_state(),
                'keyboard': self.keyboard_unavailable(), 'masks': self.masks_state(), 'audio': self.audio_state(),
                'command': Command.cur_command_name if self.running else '', 'demo': self.demo,
                'camera_live': self.camera_live(), 'camera': {'name': self.settings.camera_name, 'path': self.settings.camera_path,
                                                              'error': self.camera.error},
                'serial_open': self.serial_open(),
                'serial': {'port': self.serial_target(), 'baud': int(self.settings.baud_rate.get() or 9600),
                           'format': self.settings.serial_data_format_name.get() or 'Default', 'formats': serial_formats(),
                           'error': self.ser.last_error},
                'held': [getattr(b, 'showName', None) or b.name for b in keys.holdButton],
                'options': self.options(), 'dialogs': self.dialogs.current(), 'keymap': self.keymap(),
                'choices': self.choices(), 'shortcuts': self.shortcuts(), 'notification': self.notification_settings(),
                'assist': self.assist.snapshot(), 'watch': self.watch.snapshot(), 'recording': self.recorder.state(),
                'log': self.log1.tail(), 'log2': self.log2.tail()}

    def close(self):
        """Stop the script, release the port and camera, and save settings."""
        self.sleep_watch.stop()
        if self.audio is not None:
            self.audio.stop()
        if self.keyboard_session is not None:
            self.keyboard_session.close()
        self.stop_script()
        if self.recorder.current and self.recorder.current['thread'].is_alive():
            self.recorder.stop()
        deadline = time.monotonic() + 5
        while self.script_alive() and time.monotonic() < deadline:
            time.sleep(.05)
        with self.lock:
            try:
                if self.ser.isOpened():
                    self.keys_software_controller.end()
            except Exception:
                self._logger.exception('入力の解放に失敗しました')
            finally:
                self.ser.closeSerial()
            self.camera.destroy()
            self.save()
