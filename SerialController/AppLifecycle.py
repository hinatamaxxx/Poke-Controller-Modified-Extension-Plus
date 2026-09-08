"""MIT. Cooperatively stop producers before releasing their transport or UI."""
import logging
import time
from Commands.CommandBase import Command
from Commands.ProController import ProController


class Lifecycle:
    def __init__(self, app):
        self.app = app
        self.closing = False
        self.disconnecting = False
        self.started = 0
        self.reported = False
        self.seen_error = ''
        self.stopping_threads = []
        app.root.after(50, self.tick)

    def busy(self):
        app = self.app
        self.stopping_threads = [thread for thread in self.stopping_threads if thread.is_alive()]
        command = getattr(app, 'cur_command', None)
        threads = [getattr(command, 'thread', None), getattr(app, 'procon_thread', None)]
        return any(thread is not None and thread.is_alive() for thread in threads + self.stopping_threads)

    def stop_producers(self):
        app = self.app
        ProController.flag_procon = False
        Command.isPause = False
        if app.procon is not None:
            app.procon.flag_procon = False
        if app.keyboard is not None:
            self.stopping_threads.extend(app.keyboard.threads)
            app.keyboard.stop()
            app.keyboard = None
        app.is_use_keyboard.set(False)
        app.is_use_Pro_Controller.set(False)
        command = getattr(app, 'cur_command', None)
        if command is not None:
            if hasattr(command, 'alive'):
                command.alive = False
                for name in ('socket0', 'mqtt0'):
                    transport = getattr(command, name, None)
                    if transport is not None:
                        transport.alive = False
            elif getattr(command, 'isRunning', False):
                command.end(app.ser)

    def request(self, closing=False):
        if self.closing or self.disconnecting:
            if closing:
                self.closing, self.disconnecting = True, False
            return
        self.closing, self.disconnecting = closing, not closing
        self.started, self.reported = time.monotonic(), False
        self.keyboard_enabled = self.app.is_use_keyboard.get()
        self.stop_producers()
        print('スクリプトと入力処理の停止を待っています。')

    def tick(self):
        app = self.app
        error = app.ser.last_error
        if error and error != self.seen_error:
            self.seen_error = error
            print(error)
            self.request()
        if not error:
            self.seen_error = ''
        if self.closing or self.disconnecting:
            if self.busy():
                if time.monotonic() - self.started > 5 and not self.reported:
                    self.reported = True
                    print('停止待ちが続いています。スクリプトの外部通信や独自ループの終了を待っています。画面は操作できます。')
            else:
                # KeyPress follows the selected device's protocol.
                try:
                    if app.keyPress is not None and app.ser.isOpened():
                        app.keyPress.end()
                except Exception:
                    logging.getLogger(__name__).exception('入力の解放に失敗しました')
                finally:
                    try:
                        app.ser.closeSerial()
                    except Exception:
                        logging.getLogger(__name__).exception('シリアル接続の終了に失敗しました')
                app.keyPress = None
                if self.closing:
                    app.is_use_keyboard.set(self.keyboard_enabled)
                    app._finish_exit()
                    return
                self.disconnecting = False
                app.stopPlayPost()
                print('シリアル接続と入力処理を停止しました。')
        app.root.after(50, self.tick)
