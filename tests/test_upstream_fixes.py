"""フォーク元 0.2.0 から取り込んだ不具合の修正を、機器なしで確かめるテスト"""
from pathlib import Path
import contextlib
import io
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'SerialController')]


class TokenFileMixin:
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.token_path = str(Path(self.folder.name) / 'external_token.ini')


class MQTTTests(TokenFileMixin, unittest.TestCase):
    def make(self):
        import ExternalTools
        patcher = patch.object(ExternalTools.MQTTCommunications, 'MQTT_TOKEN_PATH', self.token_path)
        patcher.start()
        self.addCleanup(patcher.stop)
        with contextlib.redirect_stdout(io.StringIO()):
            return ExternalTools, ExternalTools.MQTTCommunications('tester')

    def test_client_uses_paho2_callback_api(self):
        ExternalTools, mqtt0 = self.make()
        import paho.mqtt.client as mqtt
        client = mqtt0._new_client()
        self.assertIsInstance(client, mqtt.Client)
        if hasattr(mqtt, 'CallbackAPIVersion'):
            self.assertEqual(client._callback_api_version, mqtt.CallbackAPIVersion.VERSION2)

    def test_transmit_connects_publishes_and_disconnects(self):
        ExternalTools, mqtt0 = self.make()
        mqtt0.pub_token = 'pub'
        fake = Mock()
        with patch.object(ExternalTools.mqtt, 'Client', return_value=fake) as client_class, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            mqtt0.transmit_message('room', 'hello')
        args = client_class.call_args.args
        if hasattr(ExternalTools.mqtt, 'CallbackAPIVersion'):
            self.assertEqual(args[0], ExternalTools.mqtt.CallbackAPIVersion.VERSION2)
        self.assertEqual(args[-1], 'tester')
        fake.publish.assert_called_once()
        self.assertTrue(fake.publish.call_args.args[1].endswith('hello'))
        fake.disconnect.assert_called_once_with()
        self.assertIn('[mqtt:send]:hello', out.getvalue())

    def test_transmit_without_token_does_not_fail(self):
        _, mqtt0 = self.make()
        mqtt0.pub_token = None
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertIsNone(mqtt0.transmit_message('room', 'hello'))
        self.assertIn('token error(readonly)', out.getvalue())
        self.assertNotIn('[mqtt:error]', out.getvalue())

    def test_error_message_shows_real_cause(self):
        ExternalTools, mqtt0 = self.make()
        mqtt0.pub_token = 'pub'
        fake = Mock()
        fake.connect.side_effect = ConnectionRefusedError('refused')
        with patch.object(ExternalTools.mqtt, 'Client', return_value=fake), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(mqtt0.transmit_message('room', 'hello'), '')
        self.assertIn('[mqtt:error]:ConnectionRefusedError', out.getvalue())
        self.assertNotIn('may not be installed', out.getvalue())

    def test_empty_token_file_is_not_bom(self):
        _, mqtt0 = self.make()
        empty = Path(self.folder.name) / 'empty.ini'
        empty.write_bytes(b'')
        self.assertFalse(mqtt0.is_utf8_file_with_bom(str(empty)))


class SocketTests(TokenFileMixin, unittest.TestCase):
    def test_change_port_is_used_for_connect(self):
        import ExternalTools
        with patch.object(ExternalTools.SocketCommunications, 'SOCKET_TOKEN_PATH', self.token_path):
            socket0 = ExternalTools.SocketCommunications()
        socket0.change_port('50007')
        self.assertEqual(socket0.PORT, 50007)
        self.assertEqual(socket0.port, '50007')
        fake = Mock()
        with patch.object(ExternalTools.socket, 'socket', return_value=fake), \
                contextlib.redirect_stdout(io.StringIO()):
            socket0.sock_connect()
        fake.connect.assert_called_once_with((socket0.IPADDR, 50007))


class KeysTests(unittest.TestCase):
    def make(self, data_format='Default'):
        from Commands import Keys
        sender = Mock()
        keys = Keys.KeyPress(sender)
        keys.serial_data_format_name = data_format
        return Keys, keys, sender

    def test_hold_button_and_hat_with_same_value(self):
        Keys, keys, sender = self.make()
        self.assertEqual(int(Keys.Button.B), int(Keys.Hat.RIGHT))
        keys.hold([Keys.Button.B, Keys.Hat.RIGHT])
        self.assertEqual(len(keys.holdButton), 2)
        self.assertEqual(sender.writeRow.call_args.args[0], format(int(Keys.Button.B) << 2, '#06x') + ' 2')
        keys.holdEnd(Keys.Button.B)
        self.assertEqual(keys.holdButton, [Keys.Hat.RIGHT])
        self.assertIs(type(keys.holdButton[0]), Keys.Hat)
        self.assertEqual(sender.writeRow.call_args.args[0], '0x0000 2')

    def test_hold_skips_already_held_and_sends_rest(self):
        Keys, keys, sender = self.make()
        keys.hold(Keys.Button.A)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            keys.hold([Keys.Button.A, Keys.Button.X])
        self.assertIn('already in holding state', out.getvalue())
        self.assertEqual(keys.holdButton, [Keys.Button.A, Keys.Button.X])
        expected = (int(Keys.Button.A) | int(Keys.Button.X)) << 2
        self.assertEqual(sender.writeRow.call_args.args[0], format(expected, '#06x') + ' 8')

    def test_hold_direction_already_held_does_not_crash(self):
        Keys, keys, _ = self.make()
        keys.hold(Keys.Direction.UP)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            keys.hold(Keys.Direction.UP)
        self.assertIn('already in holding state', out.getvalue())

    def test_hold_end_not_held_warns(self):
        Keys, keys, sender = self.make()
        keys.hold(Keys.Button.A)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            keys.holdEnd([Keys.Button.B])
        self.assertIn('not in holding state', out.getvalue())
        self.assertEqual(keys.holdButton, [Keys.Button.A])
        self.assertEqual(sender.writeRow.call_args.args[0], format(int(Keys.Button.A) << 2, '#06x') + ' 8')

    def test_input_does_not_modify_caller_list(self):
        Keys, keys, sender = self.make()
        keys.hold(Keys.Button.A)
        buttons = [Keys.Button.X]
        keys.input(buttons)
        self.assertEqual(buttons, [Keys.Button.X])
        keys.inputEnd(buttons)
        self.assertEqual(sender.writeRow.call_args.args[0], format(int(Keys.Button.A) << 2, '#06x') + ' 8')

    def test_press_while_holding_hat_keeps_hat(self):
        Keys, keys, sender = self.make()
        keys.hold(Keys.Hat.TOP)
        keys.input(Keys.Button.A)
        keys.inputEnd(Keys.Button.A)
        self.assertEqual(sender.writeRow.call_args.args[0], '0x0000 0')
        keys.holdEnd(Keys.Hat.TOP)
        self.assertEqual(sender.writeRow.call_args.args[0], '0x0000 8')

    def test_neutral_releases_everything(self):
        Keys, keys, sender = self.make()
        keys.hold([Keys.Button.A, Keys.Hat.TOP])
        keys.neutral()
        self.assertEqual(keys.holdButton, [])
        self.assertEqual(sender.writeRow.call_args.args[0], '0x0000 8')

    def test_input_end_releases_touch_when_passed(self):
        Keys, keys, sender = self.make('Qingpi')
        touch = Keys.Touchscreen(100, 50)
        keys.input(touch)
        self.assertEqual(keys.format.format['sx'], 100)
        keys.inputEnd(touch, unset_Touchscreen=False)
        self.assertEqual((keys.format.format['sx'], keys.format.format['sy']), (0, 0))

    def test_reverse_axis_change_detection(self):
        from Commands import Keys
        send = Keys.SendFormat()
        send.setAnyDirection([Keys.Direction.UP], y_reverse=True)
        send.L_stick_changed = False
        send.setAnyDirection([Keys.Direction.UP], y_reverse=True)
        self.assertFalse(send.L_stick_changed)
        send.setAnyDirection([Keys.Direction.UP])
        self.assertTrue(send.L_stick_changed)

    def test_logger_handlers_do_not_grow(self):
        from Commands import Keys
        before = len(Keys._logger.handlers)
        for _ in range(20):
            Keys.Direction(Keys.Stick.LEFT, 30)
            Keys.SendFormat()
            Keys.Touchscreen(1, 1)
        self.assertEqual(len(Keys._logger.handlers), before)


class ImageProcessingTests(unittest.TestCase):
    def test_template_max_accepts_mask_list(self):
        import numpy as np
        from ImageProcessing import ImageProcessing
        image = np.zeros((40, 40, 3), np.uint8)
        image[10:20, 10:20] = 255
        template = image[5:25, 5:25].copy()
        mask = np.full((20, 20), 255, np.uint8)
        index, values, *_ = ImageProcessing().isContainTemplate_max(
            image, [template, template], mask_image_list=[mask, mask])
        self.assertNotEqual(index, -1)
        self.assertEqual(len(values), 2)

    def test_save_image_reports_failure(self):
        import numpy as np
        from ImageProcessing import ImageProcessing
        processor = ImageProcessing()
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()) as out:
            with patch.object(ImageProcessing, 'imwrite', return_value=False):
                processor.saveImage(np.zeros((4, 4, 3), np.uint8), filename=str(Path(folder) / 'a.png'))
            processor.saveImage(np.zeros((4, 4, 3), np.uint8), filename=None)
        self.assertIn('Capture Failed', out.getvalue())
        self.assertNotIn('capture succeeded', out.getvalue())

    def test_logger_handlers_do_not_grow(self):
        import ImageProcessing as module
        before = len(module._logger.handlers)
        for _ in range(10):
            module.ImageProcessing()
        self.assertEqual(len(module._logger.handlers), before)


class CameraTests(unittest.TestCase):
    def test_save_capture_uses_given_image_without_crop(self):
        import numpy as np
        import Camera
        camera = Camera.Camera()
        camera.image_bgr = np.zeros((8, 8, 3), np.uint8)
        given = np.full((4, 6, 3), 200, np.uint8)
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            target = str(Path(folder) / 'shot')
            camera.saveCapture(filename=target, img=given)
            import cv2
            saved = cv2.imdecode(np.fromfile(target + '.png', np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(saved.shape, given.shape)
        self.assertEqual(int(saved[0, 0, 0]), 200)


class CommandTests(unittest.TestCase):
    def test_mcu_command_has_finish(self):
        from Commands.McuCommandBase import McuCommand
        command = McuCommand('sync')
        self.assertIsNone(command.finish())


class NotifyTests(unittest.TestCase):
    def test_discord_rate_limit_after_send_does_not_fail(self):
        import DiscordNotify
        notify = DiscordNotify.Discord_Notify.__new__(DiscordNotify.Discord_Notify)
        notify._logger = DiscordNotify._logger
        notify.webhook_keys = ['DISCORD_WEBHOOK']
        notify.status = [204]
        for response in ([], Mock(spec=['headers'])):
            notify.res = response
            with contextlib.redirect_stdout(io.StringIO()):
                notify.getRateLimit()
        self.assertEqual(str(notify), 'DISCORD API Check: not confirmed.')

    def test_line_rate_limit_without_check_does_not_fail(self):
        import LineNotify
        notify = LineNotify.Line_Notify.__new__(LineNotify.Line_Notify)
        notify._logger = LineNotify._logger
        notify.token_num = 1
        notify.token_list = {'token': 'x'}
        notify.res = []
        notify.status = [500]
        with contextlib.redirect_stdout(io.StringIO()):
            notify.getRateLimit()
        self.assertEqual(str(notify), 'LINE Token Check: not confirmed.')


class FinishTests(unittest.TestCase):
    def make(self):
        from Commands import PythonCommandBase as module
        command = module.PythonCommand.__new__(module.PythonCommand)
        command._logger = module._logger
        command.alive = True
        command.socket0 = Mock(flag_socket=False)
        command.mqtt0 = Mock()
        command.keys = Mock()
        command.thread = None
        return module, command

    def test_finish_in_script_thread_stops_script(self):
        import threading
        module, command = self.make()
        result = []

        def run():
            try:
                command.finish()
                result.append('continued')
            except module.StopThread:
                result.append('stopped')

        command.thread = threading.Thread(target=run)
        with contextlib.redirect_stdout(io.StringIO()):
            command.thread.start()
            command.thread.join(5)
        self.assertEqual(result, ['stopped'])
        self.assertFalse(command.alive)

    def test_finish_from_other_thread_only_requests_stop(self):
        import threading
        _, command = self.make()
        command.thread = threading.Thread(target=lambda: None)
        with contextlib.redirect_stdout(io.StringIO()):
            command.finish()
        self.assertFalse(command.alive)

    def test_dialogue_cancel_stops_script(self):
        module, command = self.make()
        command.pos_dialogue_buttons = 0
        with patch('Commands.CommandBase.show_dialogue', return_value=None),                 contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(module.StopThread):
                command.dialogue('title', ['a'])


class SettingsFileTests(TokenFileMixin, unittest.TestCase):
    def test_empty_external_token_file_uses_defaults(self):
        import ExternalTools
        Path(self.token_path).write_bytes(b'')
        with patch.object(ExternalTools.SocketCommunications, 'SOCKET_TOKEN_PATH', self.token_path),                 patch.object(ExternalTools.MQTTCommunications, 'MQTT_TOKEN_PATH', self.token_path),                 contextlib.redirect_stdout(io.StringIO()):
            socket0 = ExternalTools.SocketCommunications()
            mqtt0 = ExternalTools.MQTTCommunications('')
        self.assertEqual((socket0.IPADDR, socket0.PORT), ('127.0.0.1', 49152))
        self.assertIsNone(mqtt0.pub_token)

    def test_discord_webhook_without_username(self):
        import DiscordNotify
        Path(self.token_path).write_text('[DISCORD_WEBHOOK]\nwebhook_url = https://example.invalid/x\n'
                                         '[DISCORD_WEBHOOK2]\nusername = only\n', encoding='utf-8')
        with patch.object(DiscordNotify.Discord_Notify, 'DISCORD_SETTING_PATH', self.token_path):
            notify = DiscordNotify.Discord_Notify()
        self.assertEqual(notify.webhook_keys, ['DISCORD_WEBHOOK'])
        self.assertEqual(notify.username_dict, {'DISCORD_WEBHOOK': ''})


class LoggerTests(unittest.TestCase):
    def test_urllib3_debug_is_not_logged(self):
        import logging
        import PokeConLogger
        root = logging.getLogger()
        saved = (root.handlers[:], root.level, getattr(root, '_poke_configured', False))
        urllib3_logger = logging.getLogger('urllib3')
        saved_level = urllib3_logger.level
        try:
            with tempfile.TemporaryDirectory() as folder, patch.object(PokeConLogger.Paths, 'LOGS', folder):
                root._poke_configured = False
                PokeConLogger.root_logger()
                self.assertFalse(urllib3_logger.isEnabledFor(logging.DEBUG))
                for handler in root.handlers[:]:
                    if handler not in saved[0]:
                        root.removeHandler(handler)
                        handler.close()
        finally:
            root.setLevel(saved[1])
            root._poke_configured = saved[2]
            urllib3_logger.setLevel(saved_level)


if __name__ == '__main__':
    unittest.main()
