"""What this app adds to the fork origin's script runtime, applied when a worker starts. MIT.

SerialController/ is kept exactly as the fork origin (futo030/Poke-Controller-Modified-Extension) ships it, so its
updates can be taken in as they are. Everything this app needs on top is added here, by wrapping its functions:

- scripts: images are looked up next to the script first (Paths.find_image); a script that ends with an error tells
  the app (last_error, and the end callback is always called); stopping from the app never raises in the app's thread
- Discord: recording on the Switch itself before a notification (switch_capture), a follow-up after a notification
  (the app attaches the last 30 seconds of video), files, the name Pokecon, and no network check when created
- LINE: no network check when created, timeouts
- images with Japanese paths (the workspace is under ドキュメント) can be read
- serial writes time out instead of waiting forever on a lost port
"""
import threading
import time

_installed = False


class _Requests:
    """requests for the notifiers: no check when a notifier is created (it held up every script start), timeouts."""
    TIMEOUT = 15

    def __getattr__(self, name):
        import requests
        return getattr(requests, name)

    class _NotChecked:
        status_code = 0

        @staticmethod
        def json():
            return {}

    def get(self, *args, **kwargs):
        return self._NotChecked()  # the notifiers' check of a webhook / token: not done

    def post(self, *args, **kwargs):
        import requests
        kwargs.setdefault('timeout', self.TIMEOUT)
        return requests.post(*args, **kwargs)


def install():
    global _installed
    if _installed:
        return
    _installed = True
    _patch_notifiers()
    _patch_images()
    _patch_scripts()


# ---- Discord / LINE ----
def _patch_notifiers():
    import DiscordNotify
    import LineNotify
    DiscordNotify.requests = _Requests()
    LineNotify.requests = _Requests()
    Discord = DiscordNotify.Discord_Notify
    original_init, original_send = Discord.__init__, Discord.send_message

    def __init__(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.default_username = 'Pokecon'
        # A webhook without a URL is no destination (nothing is sent and the Switch does not record for it).
        self.webhook_keys = [key for key in self.webhook_keys if str(self.webhook_url_dict.get(key, '')).strip()]

    def send_message(self, notification_message=None, image=None, keys='DISCORD_WEBHOOK', follow_up=True):
        """The fork origin's send_message; after a notification, after_send(notifier, keys) may add to it."""
        sent = original_send(self, notification_message, image, keys)
        hook = type(self).after_send
        if sent and follow_up and hook is not None:
            try:
                hook(self, keys)
            except Exception as exc:
                print(f'Discord: {exc}')
        return sent

    def send_file(self, keys, filename, data):
        """Send a file (e.g. a video) to the webhooks named by keys."""
        import json
        targets = self.webhook_keys if keys == 'ALL' else [keys] if isinstance(keys, str) else list(keys)
        sent = True
        for key in targets:
            if key not in self.webhook_url_dict:
                continue
            content = {'username': self.username_dict.get(key) or self.default_username}
            if self.avatar_url_dict.get(key):
                content['avatar_url'] = self.avatar_url_dict[key]
            files = {'payload_json': (None, json.dumps(content)), 'file': (filename, data)}
            try:
                response = DiscordNotify.requests.post(self.webhook_url_dict[key], files=files, timeout=60)
                ok = response.status_code in (200, 204)
            except Exception:
                ok = False
            print(f'[{key}]{filename}を送信しました。' if ok else f'[{key}]{filename}を送信できませんでした。')
            sent = sent and ok
        return sent

    Discord.__init__ = __init__
    Discord.send_message = send_message
    Discord.send_file = send_file
    Discord.after_send = None  # set by the app: called after each notification (attach the video)


# ---- images ----
def _imread(path, mode='color'):
    """cv2.imread that also reads paths with Japanese (non-ASCII) names."""
    import cv2
    import numpy as np
    flag = cv2.IMREAD_GRAYSCALE if mode in ('gray', 'binary') else cv2.IMREAD_COLOR
    try:
        return cv2.imdecode(np.fromfile(path, dtype=np.uint8), flag)
    except (OSError, ValueError):
        return None


def _patch_images():
    import ImageProcessing
    from Commands import PythonCommandBase
    original = ImageProcessing.getImage

    def getImage(path, mode='color'):
        if path and not str(path).isascii():
            image = _imread(path, mode)
            if image is not None:
                return image
        return original(path, mode)
    ImageProcessing.getImage = getImage
    PythonCommandBase.getImage = getImage  # imported there by name


# ---- scripts ----
def _patch_scripts():
    from Commands import PythonCommandBase
    import Paths
    PythonCommand = PythonCommandBase.PythonCommand
    ImageProc = PythonCommandBase.ImageProcPythonCommand
    StopThread = PythonCommandBase.StopThread
    DEFAULT_KEYS = getattr(PythonCommandBase, 'DEFAULT_DISCORD_WEBHOOK', 'DISCORD_WEBHOOK')

    # Recording on the Switch itself: hold the capture button (shorter is a screenshot), as Pokémon Automation does.
    PythonCommand.SWITCH_CAPTURE_SECONDS = 2.0
    # The Switch keeps about the last 30 seconds, so notifications closer together than that do not record again.
    PythonCommand.SWITCH_CAPTURE_INTERVAL = 30.0
    PythonCommand._last_switch_capture = None
    PythonCommand.isDiscordSwitchCapture = False  # the app's setting (Discord 連携)
    PythonCommand.last_error = None
    PythonCommand.finished_itself = False

    original_start = PythonCommand.start

    def start(self, ser, postProcess):
        self.last_error = None
        self.finished_itself = False
        if self.thread is not None and not self.thread.is_alive():
            self.thread = None  # started again after it ended
        original_start(self, ser, postProcess)
    PythonCommand.start = start

    original_do_safe = PythonCommand.do_safe

    def do_safe(self, ser):
        """The fork origin's do_safe; whatever way the script ends, the app hears of it (postProcess)."""
        try:
            original_do_safe(self, ser)
        finally:
            self.alive = False
            callback, self.postProcess = self.postProcess, None
            if callback is not None:
                callback()
    PythonCommand.do_safe = do_safe

    original_run = PythonCommand._do_with_start_notification

    def _do_with_start_notification(self):
        try:
            original_run(self)
        except StopThread:
            raise
        except Exception as exc:
            self.last_error = exc  # read by the app's watcher
            self.print_t(f'スクリプトがエラーで停止しました: {type(exc).__name__}: {exc}')
            raise
    PythonCommand._do_with_start_notification = _do_with_start_notification

    original_stop = PythonCommand.sendStopRequest

    def sendStopRequest(self):
        """From the app (not the script's thread): only ask the script to stop. Never raise here."""
        thread = self.thread
        if thread is not None and threading.current_thread() is not thread:
            if self.alive:
                self.alive = False
                print('-- sent a stop request. --')
                self._logger.info('Sending stop request')
            if self.socket0.flag_socket:
                self.socket_disconnect()
            return
        original_stop(self)
    PythonCommand.sendStopRequest = sendStopRequest

    original_finish = PythonCommand.finish

    def finish(self):
        if self.thread is None or threading.current_thread() is self.thread:
            self.finished_itself = True  # it ended by itself (e.g. a shiny was found): the end notification records
        original_finish(self)
    PythonCommand.finish = finish

    def switch_capture(self, force=False):
        """
        Switch 本体で録画する。キャプチャーボタンを長押しすると、直前およそ 30 秒が本体に保存される(録画できるソフトのみ)。
        スクリプトのスレッドで、ホールド中の入力を保ったまま押す。30 秒以内に録画したばかりなら押さない(force で押す)。
        """
        if self.keys is None:
            return False
        now = time.monotonic()
        last = PythonCommand._last_switch_capture
        if not force and last is not None and now - last < self.SWITCH_CAPTURE_INTERVAL:
            return False
        PythonCommand._last_switch_capture = now
        from Commands.Keys import Button
        self.keys.hold(Button.CAPTURE)
        try:
            time.sleep(self.SWITCH_CAPTURE_SECONDS)
        finally:
            self.keys.holdEnd(Button.CAPTURE)
        print('Switch 本体で直前の映像を録画しました。')
        self._logger.info('Switch capture (video)')
        return True
    PythonCommand.switch_capture = switch_capture

    def _switch_capture_before_discord(self, switch_capture, keys):
        """Before a Discord notification: record on the Switch when asked (None: the app's setting)."""
        if getattr(self, '_capture_decided', False):
            return
        if switch_capture is None:
            switch_capture = self.isDiscordSwitchCapture
        if switch_capture and keys is not None:
            try:
                self.switch_capture()
            except Exception as exc:
                self._logger.error(f'Switch capture failed: {exc}')
    PythonCommand._switch_capture_before_discord = _switch_capture_before_discord

    original_notify = PythonCommand._discordNotify

    def _discordNotify(self, content):
        """Start / end notifications: record on the Switch only when the script ended by itself."""
        if self.isDiscordSwitchCapture and self.finished_itself:
            self._switch_capture_before_discord(True, self._discordKeys(0, DEFAULT_KEYS, None))
        self._capture_decided = True
        try:
            return original_notify(self, content)
        finally:
            self._capture_decided = False
    PythonCommand._discordNotify = _discordNotify

    original_text = PythonCommand.discord_text

    def discord_text(self, content='', index=0, keys=DEFAULT_KEYS, name=None, switch_capture=None):
        self._switch_capture_before_discord(switch_capture, self._discordKeys(index, keys, name))
        return original_text(self, content, index, keys, name)
    PythonCommand.discord_text = discord_text

    original_image = ImageProc.discord_image

    def discord_image(self, content='', index=0, crop_fmt='', crop=[], keys=DEFAULT_KEYS, name=None,
                      switch_capture=None):
        target = name if isinstance(crop_fmt, str) and crop_fmt not in PythonCommandBase.CROP_FORMAT_NAMES else None
        self._switch_capture_before_discord(switch_capture, self._discordKeys(index, keys, target or name))
        return original_image(self, content, index, crop_fmt, crop, keys, name)
    ImageProc.discord_image = discord_image

    original_filespec = ImageProc.get_filespec

    def get_filespec(self, filename, mode='t'):
        """Images: the script's own 画像 first, then shared images, then Template (Paths.image_folders)."""
        if mode == 't' and filename and not __import__('os').path.isabs(filename) \
                and self.template_path_name in (Paths.TEMPLATE, './Template/'):
            return Paths.find_image(filename, type(self).__module__)
        return original_filespec(self, filename, mode)
    ImageProc.get_filespec = get_filespec


# ---- serial ----
def make_sender(show_serial):
    """The fork origin's Sender, with writes that give up after a short time on a lost port."""
    from Commands.Sender import Sender

    class PlusSender(Sender):
        WRITE_TIMEOUT = .25

        def __init__(self, show):
            super().__init__(bool(show))
            self.last_error = ''
            self.on_send_failures = self._lost

        def _lost(self, count, error):
            self.last_error = f'シリアルに送れません（{count} 回続けて失敗）: {error}'

        def _openSerial(self, portNum, portName='', baudrate=9600):
            opened = super()._openSerial(portNum, portName, baudrate)
            if opened and self.ser is not None:
                self.last_error = ''
                try:
                    self.ser.write_timeout = self.WRITE_TIMEOUT
                except Exception:
                    pass
            return opened

        def _sendSucceeded(self):
            super()._sendSucceeded()
            self.last_error = ''

    return PlusSender(show_serial)


def install_demo_sender(sender):
    """The demo has no controller: nothing is written anywhere."""
    for name in ('openSerial',):
        setattr(sender, name, lambda *args, **kwargs: False)
    for name in ('writeRow', 'writeList', 'writeRow_wo_perf_counter', '_writeRow', '_writeList', '_writeRow_wo_perf_counter'):
        setattr(sender, name, lambda *args, **kwargs: None)
