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
FORMATS = ('Default', 'Qingpi', '3DS Controller(FW:-x.3)', '3DS Controller(FW:x.4-)')


class Var:
    """The get/set part of a tkinter variable."""

    def __init__(self, value=None):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


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
        import Settings
        import PokeConDialogue
        from Commands.CommandBase import Command
        from Commands.Keys import KeyPress
        from Commands.Sender import Sender
        from Camera import Camera
        from LineNotify import Line_Notify
        from DiscordNotify import Discord_Notify
        from ExternalTools import SocketCommunications, MQTTCommunications
        from product import NAME, VERSION
        self._logger = logging.getLogger(__name__)
        self.lock = threading.RLock()
        self.profile, self.demo = profile, demo
        self.label = label or profile  # the Switch's name, shown in notifications
        self.exit_requested = False
        Settings.GuiSettings.SETTING_PATH = os.path.join(profile_dir, 'settings.ini')
        Line_Notify.LINE_TOKEN_PATH = os.path.join(profile_dir, 'line_token.ini')
        Discord_Notify.DISCORD_SETTING_PATH = os.path.join(profile_dir, 'discord_token.ini')
        SocketCommunications.SOCKET_TOKEN_PATH = os.path.join(profile_dir, 'external_token.ini')
        MQTTCommunications.MQTT_TOKEN_PATH = os.path.join(profile_dir, 'external_token.ini')
        self.settings = Settings.GuiSettings()
        self.log1, self.log2 = LogArea(), LogArea()
        self.overlay, self.dialogs = Overlay(), Dialogs()
        Command.text_area_1, Command.text_area_2 = self.log1, self.log2
        Command.canvas = self.overlay
        Command.app_name = f'{NAME} ver.{VERSION}'
        Command.profilename = profile
        PokeConDialogue.DIALOGUE_PROVIDER = self.dialogs.ask
        self.console_mirror = console_mirror
        self.apply_options()
        self.camera = Camera(int(self.settings.fps.get() or 45))
        # Screenshots go to the chosen capture folder (settings: フォルダー).
        import app_paths
        import Camera as camera_module
        if app_paths.folder_choices().get('captures'):
            camera_module.CAPTURE_DIR = str(app_paths.CAPTURES)
            self.camera.capture_dir = str(app_paths.CAPTURES)
        self.camera_missing, self.next_camera_check = False, 0
        self.show_serial = Var(bool(self.settings.is_show_serial.get()))
        self.ser = Sender(self.show_serial)
        KeyPress.serial_data_format_name = self.settings.serial_data_format_name.get() or 'Default'
        self.keys_software_controller = KeyPress(self.ser)
        self.cur_command, self.running = None, False
        self.reported_error = ''
        from assist import Assist
        self.assist = Assist(self, profile_dir)
        from watch import Watch
        from recorder import Recorder
        self.watch = Watch(self, profile_dir)
        self.recorder = Recorder(self)
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
        Command.stdout_destination = str(s.stdout_destination or '1')
        Command.pos_dialogue_buttons = str(getattr(s, 'pos_dialogue_buttons', '2') or '2')
        sys.stdout = Console(self.log1 if Command.stdout_destination == '1' else self.log2, self.console_mirror)

    OPTIONS = {'show_realtime': 'is_show_realtime', 'show_value': 'is_show_value', 'show_guide': 'is_show_guide',
               'show_serial': 'is_show_serial', 'keyboard': 'is_use_keyboard',
               'win_start': 'is_win_notification_start', 'win_end': 'is_win_notification_end',
               'line_start': 'is_line_notification_start', 'line_end': 'is_line_notification_end',
               'discord_start': 'is_discord_notification_start', 'discord_end': 'is_discord_notification_end'}

    def options(self):
        return {key: bool(getattr(self.settings, name).get()) for key, name in self.OPTIONS.items()}

    def set_options(self, values):
        with self.lock:
            for key, value in values.items():
                if key not in self.OPTIONS or not isinstance(value, bool):
                    raise ValueError(f'Unknown option: {key}')
                getattr(self.settings, self.OPTIONS[key]).set(value)
            self.show_serial.set(bool(self.settings.is_show_serial.get()))
            self.ser._show_serial = self.show_serial.get()
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
                classes = self.py_classes if kind == 'python' else self.mcu_classes if kind == 'mcu' else None
                if classes is None or name not in [c.NAME for c in classes]:
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
            Discord_Notify().send_message(message)
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
            raise ValueError('Discord の Webhook URL が設定されていません（通知タブの送り先）')
        Discord_Notify().send_message(f'{NAME} ({self.label}) の画面', image=frame.copy())

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
    def load_scripts(self):
        import Utility as util
        from CommandLoader import CommandLoader
        from Commands import PythonCommandBase, McuCommandBase
        self.py_loader = CommandLoader(util.ospath('Commands/PythonCommands'), PythonCommandBase.PythonCommand)
        self.mcu_loader = CommandLoader(util.ospath('Commands/McuCommands'), McuCommandBase.McuCommand)
        self.py_classes = self.py_loader.load()
        self.mcu_classes = self.mcu_loader.load()

    def reload_scripts(self):
        with self.lock:
            if self.running:
                raise ValueError('Stop the running script before reloading')
            self.py_classes = self.py_loader.reload()
            self.mcu_classes = self.mcu_loader.reload()
            print('スクリプトを再読み込みしました。')

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
            self.py_loader.modules = [m for m in self.py_loader.modules if m.__name__ != module]
            sys.modules.pop(module, None)
            importlib.invalidate_caches()
            self.reload_scripts()
            result['names'] = [c.NAME for c in self.py_classes if c.__module__ == module]
            if not result['names']:
                try:
                    importlib.import_module(module)
                    result['error'] = 'NAME を持つ PythonCommand（または ImageProcPythonCommand）のクラスがありません。'
                except Exception:
                    lines = traceback.format_exc().splitlines(True)
                    first = next((n for n, line in enumerate(lines) if script_files.ROOT.replace(os.sep, '') in line.replace(os.sep, '').replace('/', '')), 0)
                    result['error'] = ''.join(lines[first:][-12:])
            return result

    def catalog(self):
        def describe(classes):
            return [{'name': c.NAME, 'tags': list(getattr(c, 'TAGS', []) or [])} for c in classes]
        return {'python': describe(self.py_classes), 'mcu': describe(self.mcu_classes)}

    def start_script(self, kind, name, restart=False):
        from Commands.CommandBase import Command
        from Commands import PythonCommandBase
        with self.lock:
            if self.running:
                raise ValueError('A script is already running')
            if kind not in ('python', 'mcu'):
                raise ValueError('Unknown script kind')
            classes = self.py_classes if kind == 'python' else self.mcu_classes
            cls = next((c for c in classes if c.NAME == name), None)
            if cls is None:
                raise ValueError('Script not found')
            if self.demo and cls.__module__ != 'Commands.PythonCommands.Samples.PortableDemo':
                raise ValueError('Demo mode only runs PortableDemo')
            if not self.serial_open():
                raise ValueError('COM port is not connected')
            if kind == 'python' and issubclass(cls, PythonCommandBase.ImageProcPythonCommand):
                try:
                    command = cls(self.camera, self.overlay)
                except TypeError:
                    command = cls(self.camera)
            else:
                command = cls()
            self.keys_software_controller.neutral()
            Command.isPause = False
            Command.cur_command_name = command.NAME
            self.cur_command, self.running = command, True
            print('開始 ' + command.NAME)
            command.start(self.ser, self._finished)
            self.watch.script_started(kind, name, restart)

    def _finished(self):
        self.running = False
        self.dialogs.cancel_all()

    def stop_script(self):
        from Commands.CommandBase import Command
        with self.lock:
            self.assist.cancel_sequence()
            if self.running and self.cur_command is not None:
                self.watch.expect_stop()
                print('停止 ' + self.cur_command.NAME)
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
            # The demo camera only produces a frame when read; the Tk preview used to do that.
            def pump():
                while not self.exit_requested:
                    self.camera.readFrame()
                    time.sleep(1 / 30)
            threading.Thread(target=pump, daemon=True).start()
            return
        if not path:
            self.camera.destroy()
            return
        self.camera.openCamera(0, device_path=path)

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
            if fmt not in FORMATS:
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
            self.keys_software_controller.init_hat()
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
                'command': Command.cur_command_name if self.running else '', 'demo': self.demo,
                'camera_live': self.camera_live(), 'camera': {'name': self.settings.camera_name, 'path': self.settings.camera_path,
                                                              'error': self.camera.error},
                'serial_open': self.serial_open(),
                'serial': {'port': self.serial_target(), 'baud': int(self.settings.baud_rate.get() or 9600),
                           'format': self.settings.serial_data_format_name.get() or 'Default', 'formats': list(FORMATS),
                           'error': self.ser.last_error},
                'held': [getattr(b, 'showName', None) or b.name for b in keys.holdButton],
                'options': self.options(), 'dialogs': self.dialogs.current(), 'keymap': self.keymap(),
                'choices': self.choices(), 'shortcuts': self.shortcuts(), 'notification': self.notification_settings(),
                'assist': self.assist.snapshot(), 'watch': self.watch.snapshot(), 'recording': self.recorder.state(),
                'log': self.log1.tail(), 'log2': self.log2.tail()}

    def close(self):
        """Stop the script, release the port and camera, and save settings."""
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
