"""Watching long-running scripts: notice when a script stops with an error, the picture freezes (the game or the
Switch hung), or the capture device / microcontroller is lost; save the screen, notify, and optionally restart. MIT.

An assistant can wait for these incidents over MCP and try to recover the game.
"""
import collections
import json
import os
import threading
import time

DEFAULTS = {'enabled': True, 'freeze_seconds': 120, 'notify': True, 'auto_restart': False, 'restart_limit': 3}
MESSAGES = {
    'error': 'スクリプトがエラーで止まりました',
    'frozen': '映像が{seconds}秒間変わっていません（ソフトかSwitchが止まった可能性があります）',
    'camera': 'キャプチャーボードの映像が途切れました',
    'serial': 'マイコン（COMポート）との接続が切れました',
    'finished': 'スクリプトが終了しました',
}
NOTIFIED = ('error', 'frozen', 'camera', 'serial')


class Watch:
    def __init__(self, core, profile_dir):
        self.core = core
        self.path = os.path.join(profile_dir, 'watch.json')
        self.settings = dict(DEFAULTS)
        try:
            with open(self.path, encoding='utf-8') as stream:
                saved = json.load(stream)
            self.settings.update({k: type(DEFAULTS[k])(v) for k, v in saved.items() if k in DEFAULTS})
        except (OSError, ValueError, TypeError):
            pass
        self.incidents = collections.deque(maxlen=50)
        from history import FrameHistory
        self.history = FrameHistory()  # the last seconds of video, saved with each incident
        self.next_id = 1
        self.restarts = 0
        self._was_running = False
        self._script = None  # (kind, name) of the running script
        self._expected_stop = False
        self._stops = 0  # counts stop requests, so a pending restart can tell the user stopped meanwhile
        self._next_check = 0
        self._thumb = None
        self._still_since = None
        self._frozen_reported = False
        self._camera_was_live = False

    # ---- settings ----
    def configure(self, values):
        for key, value in values.items():
            if key not in DEFAULTS:
                raise ValueError(f'Unknown watch setting: {key}')
            value = type(DEFAULTS[key])(value)
            if key == 'freeze_seconds' and value and not 30 <= value <= 3600:
                raise ValueError('freeze_seconds must be 0 (off) or 30-3600')
            if key == 'restart_limit' and not 0 <= value <= 100:
                raise ValueError('restart_limit must be 0-100')
            self.settings[key] = value
        from safe_settings import write_text
        write_text(self.path, json.dumps(self.settings, ensure_ascii=False, indent=1))

    # ---- hooks from Core ----
    def script_started(self, kind, name, restart=False):
        self._script = (kind, name)
        self._expected_stop = False
        self._was_running = True
        self._reset_freeze()
        if not restart:
            self.restarts = 0

    def expect_stop(self):
        self._expected_stop = True
        self._stops += 1

    def serial_lost(self, error):
        self.report('serial', str(error))

    # ---- called from Core.tick on the main loop (under core.lock) ----
    def tick(self):
        core = self.core
        if self._was_running and not core.running:
            self._was_running = False
            command = core.cur_command
            error = getattr(command, 'last_error', None)
            if self._expected_stop:
                pass
            elif error is not None:
                self.report('error', f'{type(error).__name__}: {error}', restart=True)
            elif not core.ser.last_error:
                self.report('finished')
        if self.history.due() and core.camera_live():
            self.history.add_frame(core.camera.image_bgr)
        if not self.settings['enabled'] or time.monotonic() < self._next_check:
            return
        self._next_check = time.monotonic() + 1
        live = core.camera_live()
        if self._camera_was_live and not live and core.running and not core.demo:
            self.report('camera')
        self._camera_was_live = live
        from Commands.CommandBase import Command
        if core.running and live and not Command.isPause and not core.dialogs.current():
            self._check_freeze()
        else:
            self._reset_freeze()

    def _reset_freeze(self):
        self._thumb, self._still_since, self._frozen_reported = None, None, False

    def _check_freeze(self):
        import cv2
        seconds = self.settings['freeze_seconds']
        frame = self.core.camera.image_bgr
        if not seconds or frame is None:
            return
        thumb = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (64, 36), interpolation=cv2.INTER_AREA).astype('int16')
        now = time.monotonic()
        if self._thumb is None or abs(thumb - self._thumb).mean() > 1.5:
            self._thumb, self._still_since, self._frozen_reported = thumb, now, False
        elif not self._frozen_reported and now - self._still_since >= seconds:
            self._frozen_reported = True
            self.report('frozen', restart=True)

    # ---- incidents ----
    def report(self, kind, detail='', restart=False):
        core = self.core
        script = self._script[1] if self._script else ''
        message = MESSAGES[kind].format(seconds=self.settings['freeze_seconds'])
        # IDs are millisecond times, so they keep increasing when the hub restarts this Switch's process.
        incident_id = max(self.next_id, int(time.time() * 1000))
        incident = {'id': incident_id, 'at': time.time(), 'kind': kind, 'message': message, 'detail': detail[:500],
                    'script': script, 'image': '', 'clip': '', 'restarted': False}
        self.next_id = incident_id + 1
        frame = core.camera.image_bgr if core.camera_live() else None
        if frame is not None and kind != 'finished':
            try:
                incident['image'] = self._save_image(frame, kind)
            except (OSError, ValueError) as exc:
                print(f'見張り: 画面を保存できませんでした: {exc}')
        if kind in NOTIFIED:
            try:
                incident['clip'] = self.history.save(core.recorder.root, f"{core.label}: {message}")
            except OSError as exc:
                print(f'見張り: 直前の映像を保存できませんでした: {exc}')
        self.incidents.append(incident)
        print(f'見張り: {message}' + (f'（{detail}）' if detail else ''))
        core.assist.record('watch', message + (f' — {script}' if script else ''))
        if kind in NOTIFIED and self.settings['enabled'] and self.settings['notify']:
            threading.Thread(target=self._notify, args=(incident, frame), daemon=True).start()
        if restart and self._can_restart():
            incident['restarted'] = True
            self.restarts += 1
            threading.Thread(target=self._restart, args=(kind, self._script), daemon=True).start()
        return incident

    def _can_restart(self):
        return (self.settings['enabled'] and self.settings['auto_restart'] and self._script is not None
                and self.restarts < self.settings['restart_limit'])

    @staticmethod
    def _save_image(frame, kind):
        import cv2
        import app_paths
        folder = os.path.join(app_paths.captures_dir(), 'incidents')
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}-{kind}.png")
        ok, encoded = cv2.imencode('.png', frame)
        if not ok:
            return ''
        with open(path, 'wb') as stream:
            stream.write(encoded.tobytes())
        return path

    def _notify(self, incident, frame):
        """Send to whatever the profile has set up: Discord (with the screen), LINE, and the Windows notification."""
        from product import NAME
        core = self.core
        text = f"{NAME} ({core.label})\n{incident['script'] or 'スクリプトなし'}: {incident['message']}"
        if incident['detail']:
            text += f"\n{incident['detail']}"
        settings = core.notification_settings()
        if settings['discord_webhook_set']:
            try:
                from DiscordNotify import Discord_Notify
                Discord_Notify().send_message(text, image=frame)
            except Exception as exc:
                print(f'Discordへの通知に失敗しました: {exc}')
        if settings['line_token_set']:
            try:
                from LineNotify import Line_Notify
                Line_Notify().send_message(text)
            except Exception as exc:
                print(f'LINEへの通知に失敗しました: {exc}')
        try:
            from plyer import notification
            notification.notify(title='Poke-Controller', message=text[-250:], timeout=10)
        except Exception:
            pass

    def _restart(self, kind, script):
        """Stop what is left of the script, wait for it to end, and start it again."""
        core = self.core
        self._expected_stop = True
        if kind == 'frozen':
            core.stop_script()
        stops = self._stops
        deadline = time.monotonic() + 15
        while core.script_alive() and time.monotonic() < deadline:
            time.sleep(.2)
        time.sleep(2)
        try:
            with core.lock:
                if (stops != self._stops or core.exit_requested or core.running or not self.settings['enabled']
                        or not self.settings['auto_restart']):
                    self._expected_stop = False
                    return  # the user stopped, started something else, or turned restarting off meanwhile
                core.start_script(*script, restart=True)
            print(f'見張り: {script[1]} を開始し直しました（{self.restarts}/{self.settings["restart_limit"]}回目）')
            core.assist.record('watch', f'{script[1]} を開始し直しました')
        except Exception as exc:
            self._expected_stop = False
            print(f'見張り: 開始し直せませんでした: {exc}')

    def since(self, after_id=0):
        return [dict(i) for i in self.incidents if i['id'] > int(after_id or 0)]

    def snapshot(self):
        still = (time.monotonic() - self._still_since) if self._still_since else 0
        return {'settings': dict(self.settings), 'incidents': [dict(i) for i in list(self.incidents)[-10:]],
                'restarts': self.restarts, 'still_seconds': round(still), 'last_id': self.next_id - 1,
                'script': list(self._script) if self._script and self.core.running else None}
