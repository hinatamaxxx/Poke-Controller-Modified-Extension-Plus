#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import configparser
import os
import Paths
import tkinter as tk
from pathlib import Path
from safe_settings import read_config, write_config
from logging import getLogger  # , DEBUG, NullHandler


class Var:
    """Minimal stand-in for tkinter variables so settings work without a window."""

    def __init__(self, value=None):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


class GuiSettings:
    SETTING_PATH = os.path.join(Paths.PROFILES, "default", "settings.ini")

    def __init__(self):
        self._logger = getLogger(__name__)
        self.setting = configparser.ConfigParser()
        self.setting.optionxform = str
        # print("isExistConfig =", os.path.exists(self.SETTING_PATH))

        if not os.path.exists(self.SETTING_PATH) and not Path(self.SETTING_PATH + '.bak').exists():
            self._logger.debug("Setting file does not exists.")
            self.generate()
            self.load()
            self._logger.debug("Settings file has been generated.")
        else:
            self._logger.debug("Setting file exists.")
            self.load()
            self._logger.debug("Settings file has been loaded.")

        # default
        self.camera_id = Var(value=self.setting["General Setting"].getint("camera_id"))
        self.camera_path = self.setting['General Setting'].get('camera_path', '')
        self.camera_name = self.setting['General Setting'].get('camera_name', '')
        self.com_port = Var(value=self.setting["General Setting"].getint("com_port"))
        self.com_port_name = Var(value=self.setting["General Setting"].get("com_port_name"))
        self.baud_rate = Var(value=self.setting["General Setting"].getint("baud_rate"))
        self.fps = Var(value=self.setting["General Setting"]["fps"])
        self.show_size = Var(value=self.setting["General Setting"].get("show_size"))
        self.is_show_realtime = Var(value=self.setting["General Setting"].getboolean("is_show_realtime"))
        self.is_show_value = Var(value=self.setting["General Setting"].getboolean("is_show_value"))
        self.is_show_guide = Var(value=self.setting["General Setting"].getboolean("is_show_guide"))
        self.enlarge_preview = Var(value=self.setting["General Setting"].getboolean("enlarge_preview", fallback=False))
        self.is_show_serial = Var(value=self.setting["General Setting"].getboolean("is_show_serial"))
        self.is_use_keyboard = Var(value=self.setting["General Setting"].getboolean("is_use_keyboard"))
        try:
            self.serial_data_format_name = Var(
                value=self.setting["General Setting"]["serial_data_format_name"]
            )
        except Exception:
            self.serial_data_format_name = Var(value="Default")
        try:
            self.touchscreen_start_x = int(self.setting["General Setting"]["touchscreen_start_x"])
        except Exception:
            self.touchscreen_start_x = 1
        try:
            self.touchscreen_start_y = int(self.setting["General Setting"]["touchscreen_start_y"])
        except Exception:
            self.touchscreen_start_y = 1
        try:
            self.touchscreen_end_x = int(self.setting["General Setting"]["touchscreen_end_x"])
        except Exception:
            self.touchscreen_end_x = 320
        try:
            self.touchscreen_end_y = int(self.setting["General Setting"]["touchscreen_end_y"])
        except Exception:
            self.touchscreen_end_y = 240
        # Pokemon Home用の設定
        self.season = Var(value=self.setting["Pokemon Home"].get("Season"))
        self.is_SingleBattle = Var(value=self.setting["Pokemon Home"].get("Single or Double"))
        # Shortcut用の設定
        self.command_class_dict = {}
        self.command_name_dict = {}
        for i in range(1, 11):  # Update直後のError回避策
            try:
                self.command_class_dict[str(i)] = self.setting["Shortcut"][f"command_class_{i}"]
                self.command_name_dict[str(i)] = Var(value=self.setting["Shortcut"][f"command_name_{i}"])
            except Exception:
                self.command_class_dict[str(i)] = "None"
                self.command_name_dict[str(i)] = Var(value="(empty)")
        # Notification用の設定
        try:
            self.is_win_notification_start = Var(
                value=self.setting["Notification"].getboolean("is_win_notification_start")
            )
        except Exception:
            self.is_win_notification_start = Var(value=False)
        try:
            self.is_win_notification_end = Var(
                value=self.setting["Notification"].getboolean("is_win_notification_end")
            )
        except Exception:
            self.is_win_notification_end = Var(value=False)
        try:
            self.is_line_notification_start = Var(
                value=self.setting["Notification"].getboolean("is_line_notification_start")
            )
        except Exception:
            self.is_line_notification_start = Var(value=False)
        try:
            self.is_line_notification_end = Var(
                value=self.setting["Notification"].getboolean("is_line_notification_end")
            )
        except Exception:
            self.is_line_notification_end = Var(value=False)
        try:
            self.is_discord_notification_start = Var(
                value=self.setting["Notification"].getboolean("is_discord_notification_start")
            )
        except Exception:
            self.is_discord_notification_start = Var(value=False)
        try:
            self.is_discord_notification_end = Var(
                value=self.setting["Notification"].getboolean("is_discord_notification_end")
            )
        except Exception:
            self.is_discord_notification_end = Var(value=False)
        # Discord に通知するとき: Switch 本体の録画(キャプチャーボタン長押し)と、アプリの直前の映像の添付
        for name in ("is_discord_switch_capture", "is_discord_clip"):
            try:
                setattr(self, name, Var(value=bool(self.setting["Notification"].getboolean(name, fallback=False))))
            except Exception:
                setattr(self, name, Var(value=False))
        # Output Area用の設定
        self.area_size = self.setting["Output"]["area_size"]
        self.stdout_destination = self.setting["Output"]["stdout_destination"]
        try:
            self.right_frame_widget_mode = self.setting["Output"]["widget_mode"]
        except Exception:
            self.right_frame_widget_mode = "ALL (default)"
        try:
            self.pos_software_controller = self.setting["Output"]["software_controller_position"]
        except Exception:
            self.pos_software_controller = "2"
        try:
            self.pos_dialogue_buttons = self.setting["Output"]["dialogue_buttons_position"]
        except Exception:
            self.pos_dialogue_buttons = "2"

    def load(self):
        def validate(config):
            for section in ('General Setting', 'Pokemon Home', 'Output', 'KeyMap-Button', 'KeyMap-Direction', 'KeyMap-Hat'):
                if section not in config:
                    raise ValueError('Missing section')
            general = config['General Setting']
            general.getboolean('enlarge_preview', fallback=False)
            for key in ('camera_id', 'com_port', 'baud_rate'):
                int(general[key])
            for key in ('fps', 'show_size', 'com_port_name'):
                general[key]
            for key in ('is_show_realtime', 'is_show_value', 'is_show_guide', 'is_show_serial', 'is_use_keyboard'):
                if key not in general:
                    raise ValueError('Missing setting')
                general.getboolean(key)
            for key in ('area_size', 'stdout_destination'):
                config['Output'][key]
        self.setting = read_config(self.SETTING_PATH, validate)

    def generate(self):
        # logger.info('Create Default setting file.')
        # default
        self.setting["General Setting"] = {
            "camera_id": -1,
            "com_port": 0,
            "com_port_name": "",
            "baud_rate": 9600,
            "fps": 45,
            "show_size": "640x360",
            "is_show_realtime": True,
            "is_show_value": False,
            "is_show_guide": False,
            "is_show_serial": False,
            "is_use_keyboard": True,
            "serial_data_format_name": "Default",
            "touchscreen_start_x": 1,
            "touchscreen_start_y": 1,
            "touchscreen_end_x": 320,
            "touchscreen_end_y": 240,
        }
        # pokemon home用の設定
        self.setting["Pokemon Home"] = {
            "Season": 1,
            "Single or Double": "シングル",
        }
        # keyconfig
        self.setting["KeyMap-Button"] = {
            "Button.Y": "y",
            "Button.B": "b",
            "Button.X": "x",
            "Button.A": "a",
            "Button.L": "l",
            "Button.R": "r",
            "Button.ZL": "k",
            "Button.ZR": "e",
            "Button.MINUS": "m",
            "Button.PLUS": "p",
            "Button.LCLICK": "q",
            "Button.RCLICK": "w",
            "Button.HOME": "h",
            "Button.CAPTURE": "c",
        }
        self.setting["KeyMap-Direction"] = {
            # The arrow keys play the D-pad (KeyMap-Hat); the left stick is unassigned until chosen in the key settings.
            "Direction.UP": "20100",
            "Direction.RIGHT": "20101",
            "Direction.DOWN": "20110",
            "Direction.LEFT": "20111",
            "Direction.UP_RIGHT": "20001",
            "Direction.DOWN_RIGHT": "20002",
            "Direction.DOWN_LEFT": "20010",
            "Direction.UP_LEFT": "20011",
        }
        self.setting["KeyMap-Hat"] = {
            "Hat.TOP": "Key.up",
            "Hat.TOP_RIGHT": "10001",
            "Hat.RIGHT": "Key.right",
            "Hat.BTM_RIGHT": "10011",
            "Hat.BTM": "Key.down",
            "Hat.BTM_LEFT": "10101",
            "Hat.LEFT": "Key.left",
            "Hat.TOP_LEFT": "10111",
            "Hat.CENTER": "11000",
        }
        self.setting["Shortcut"] = {
            "command_class_1": "None",
            "command_name_1": "(empty)",
            "command_class_2": "None",
            "command_name_2": "(empty)",
            "command_class_3": "None",
            "command_name_3": "(empty)",
            "command_class_4": "None",
            "command_name_4": "(empty)",
            "command_class_5": "None",
            "command_name_5": "(empty)",
            "command_class_6": "None",
            "command_name_6": "(empty)",
            "command_class_7": "None",
            "command_name_7": "(empty)",
            "command_class_8": "None",
            "command_name_8": "(empty)",
            "command_class_9": "None",
            "command_name_9": "(empty)",
            "command_class_10": "None",
            "command_name_10": "(empty)",
        }
        self.setting["Notification"] = {
            "is_win_notification_start": False,
            "is_win_notification_end": False,
            "is_line_notification_start": False,
            "is_line_notification_end": False,
            "is_discord_notification_start": False,
            "is_discord_notification_end": False,
            "is_discord_switch_capture": False,
            "is_discord_clip": False,
        }
        self.setting["Output"] = {
            "area_size": "20",
            "stdout_destination": "1",
            "widget_mode": "ALL (default)",
            "software_controller_position": "2",
            "dialogue_buttons_position": "2",
        }
        write_config(self.SETTING_PATH, self.setting)

    def save(self, path=None):
        # Some preparations are needed because tkinter related objects are not serializable.
        # Preserve key mappings changed by a separate settings window.
        try:
            self.load()
        except (OSError, ValueError):
            pass  # unreadable file without a valid backup: keep the in-memory settings

        self.setting["General Setting"] = {
            "camera_id": self.camera_id.get(),
            "camera_path": self.camera_path,
            "camera_name": self.camera_name,
            "com_port": self.com_port.get(),
            "com_port_name": self.com_port_name.get(),
            "baud_rate": self.baud_rate.get(),
            "fps": self.fps.get(),
            "show_size": self.show_size.get(),
            "is_show_realtime": self.is_show_realtime.get(),
            "is_show_value": self.is_show_value.get(),
            "is_show_guide": self.is_show_guide.get(),
            "enlarge_preview": self.enlarge_preview.get(),
            "is_show_serial": self.is_show_serial.get(),
            "is_use_keyboard": self.is_use_keyboard.get(),
            "serial_data_format_name": self.serial_data_format_name.get(),
            "touchscreen_start_x": self.touchscreen_start_x,
            "touchscreen_start_y": self.touchscreen_start_y,
            "touchscreen_end_x": self.touchscreen_end_x,
            "touchscreen_end_y": self.touchscreen_end_y,
        }
        # pokemon home用の設定
        self.setting["Pokemon Home"] = {
            "Season": self.season.get(),
            "Single or Double": self.is_SingleBattle.get(),
        }

        # ショートカット用の設定
        self.setting["Shortcut"] = {
            "command_class_1": self.command_class_dict["1"],
            "command_name_1": self.command_name_dict["1"].get(),
            "command_class_2": self.command_class_dict["2"],
            "command_name_2": self.command_name_dict["2"].get(),
            "command_class_3": self.command_class_dict["3"],
            "command_name_3": self.command_name_dict["3"].get(),
            "command_class_4": self.command_class_dict["4"],
            "command_name_4": self.command_name_dict["4"].get(),
            "command_class_5": self.command_class_dict["5"],
            "command_name_5": self.command_name_dict["5"].get(),
            "command_class_6": self.command_class_dict["6"],
            "command_name_6": self.command_name_dict["6"].get(),
            "command_class_7": self.command_class_dict["7"],
            "command_name_7": self.command_name_dict["7"].get(),
            "command_class_8": self.command_class_dict["8"],
            "command_name_8": self.command_name_dict["8"].get(),
            "command_class_9": self.command_class_dict["9"],
            "command_name_9": self.command_name_dict["9"].get(),
            "command_class_10": self.command_class_dict["10"],
            "command_name_10": self.command_name_dict["10"].get(),
        }

        self.setting["Notification"] = {
            "is_win_notification_start": self.is_win_notification_start.get(),
            "is_win_notification_end": self.is_win_notification_end.get(),
            "is_line_notification_start": self.is_line_notification_start.get(),
            "is_line_notification_end": self.is_line_notification_end.get(),
            "is_discord_notification_start": self.is_discord_notification_start.get(),
            "is_discord_notification_end": self.is_discord_notification_end.get(),
            "is_discord_switch_capture": self.is_discord_switch_capture.get(),
            "is_discord_clip": self.is_discord_clip.get(),
        }

        self.setting["Output"] = {
            "area_size": self.area_size,
            "stdout_destination": self.stdout_destination,
            "widget_mode": self.right_frame_widget_mode,
            "software_controller_position": self.pos_software_controller,
            "dialogue_buttons_position": self.pos_dialogue_buttons,
        }

        write_config(path or self.SETTING_PATH, self.setting)
        self._logger.debug("Settings file has been saved.")
