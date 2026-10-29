#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import configparser
import requests
import json
import cv2
import io
import os
import Paths
import numpy as np
from PIL import Image
from logging import getLogger, DEBUG, NullHandler

# ロガーの設定は 1 回だけ行う(作るたびに addHandler すると、ハンドラが増え続ける。フォーク元 0.2.0 の修正)
_logger = getLogger(__name__)
_logger.addHandler(NullHandler())
_logger.setLevel(DEBUG)
_logger.propagate = True


def convert_bgr_to_bytes(image_bgr):
    """
    BGRの画像をbyte形式に変換する
    """
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(image_rgb)
    png = io.BytesIO()  # 空のio.BytesIOオブジェクトを用意
    image.save(png, format="png")  # 空のio.BytesIOオブジェクトにpngファイルとして書き込み
    b_frame = png.getvalue()  # io.BytesIOオブジェクトをbytes形式で読みとり
    return b_frame


class Discord_Notify:
    DISCORD_SETTING_PATH = os.path.join(Paths.PROFILES, "default", "discord_token.ini")

    def __init__(self, webhook_url="webhook_url", username="username", avatar_url="", token_name="token"):
        self._logger = _logger

        # The name a message is posted under when the settings leave it empty.
        self.default_username = "Pokecon"

        self.res = None
        self.setting_file = configparser.ConfigParser(comment_prefixes="#", allow_no_value=True, interpolation=None)
        self.open_file_with_utf8()

        self.section_list = list(self.setting_file.keys())
        # webhook_url の無いセクションは通知先にしない。username / avatar_url は省略できる
        # (以前は、どれかが欠けていると KeyError で、スクリプトを開始できなかった。フォーク元 0.2.0 の修正)
        self.webhook_keys = [
            key
            for key in self.section_list
            if "DISCORD_WEBHOOK" in key and self.setting_file.has_option(key, "webhook_url")
        ]
        self.webhook_url_dict = {key: self.setting_file[key]["webhook_url"] for key in self.webhook_keys}
        self.username_dict = {key: self.setting_file.get(key, "username", fallback="") for key in self.webhook_keys}
        self.avatar_url_dict = {key: self.setting_file.get(key, "avatar_url", fallback="") for key in self.webhook_keys}

        self.res, self.status, self.chk_webhook_json = [], [], []

    def open_file_with_utf8(self):
        """
        utf-8 のファイルを BOM ありかどうかを自動判定して読み込む
        (ファイルがない場合は空のファイルを作成する)
        """
        if os.path.isfile(self.DISCORD_SETTING_PATH):
            is_with_bom = self.is_utf8_file_with_bom(self.DISCORD_SETTING_PATH)

            encoding = "utf-8-sig" if is_with_bom else "utf-8"

            self._logger.debug("Load token file")
            self.setting_file.read(self.DISCORD_SETTING_PATH, encoding)
        else:
            dirname = os.path.dirname(self.DISCORD_SETTING_PATH)
            if not os.path.isdir(dirname):
                os.makedirs(dirname)
                self._logger.debug(f"mkdir: '{dirname}'")
            self.setting_file["DISCORD_WEBHOOK"] = {
                "webhook_url": "",
                "username": "",
                "avatar_url": "",
            }
            with open(self.DISCORD_SETTING_PATH, "w", encoding="utf-8") as file:
                self.setting_file.write(file)
            os.chmod(path=self.DISCORD_SETTING_PATH, mode=0o777)
            self._logger.debug("Generate token file")

    def is_utf8_file_with_bom(self, filename):
        """
        utf-8 ファイルが BOM ありかどうかを判定する
        """
        with open(filename, "rb") as stream:
            return stream.read(3) == b"\xef\xbb\xbf"

    def __str__(self):
        if not self.status:
            return "Notification settings loaded (not checked online)."
        for stat in self.status:
            if stat == 401:
                self._logger.error("Invalid url")
                return "DISCORD API Check FAILED."
            elif stat == 200:
                self._logger.info("Valid url")
                return "DISCORD API Check OK!"
        # 401 / 200 以外だけのときに None を返して str() がエラーになっていた(フォーク元 0.2.0 の修正)
        self._logger.warning(f"Webhook check was not confirmed: {self.status}")
        return "DISCORD API Check: not confirmed."

    # アプリが設定する: 通知を送ったあとに呼ばれる(直前の映像の添付など)。引数は (この通知, 送れた送り先の一覧)
    after_send = None

    def resolve_keys(self, keys="DISCORD_WEBHOOK"):
        """
        送り先の一覧を返す。設定に無い送り先(DISCORD_WEBHOOK2 など)は、設定画面の Webhook (DISCORD_WEBHOOK) に送る
        (スクリプトに書かれた送り先が無くても、通知が届くようにする)
        """
        if keys == "ALL":
            keys = list(self.webhook_keys)
        elif isinstance(keys, str):
            keys = [keys]
        elif not isinstance(keys, (list, tuple)):
            print("keysのフォーマットが間違っています")
            self._logger.error('Using the wrong "keys" format')
            keys = ["DISCORD_WEBHOOK"]
        resolved = []
        for key in keys:
            if key not in self.webhook_url_dict or not str(self.webhook_url_dict[key]).strip():
                key = "DISCORD_WEBHOOK"
            if key in self.webhook_url_dict and str(self.webhook_url_dict[key]).strip() and key not in resolved:
                resolved.append(key)
        return resolved

    def _content(self, key, notification_message):
        content = {"username": self.username_dict.get(key) or self.default_username}
        if self.avatar_url_dict.get(key):
            content["avatar_url"] = self.avatar_url_dict[key]
        content["content"] = notification_message or ""
        return content

    def send_message(self, notification_message=None, image=None, keys="DISCORD_WEBHOOK", follow_up=True):
        """
        DISCORDにテキスト/画像を通知する
        imageが設定されていなければテキストのみ、設定されていればテキストと画像を通知する
        imageはBGRを想定する
        follow_up が真なら、送ったあとにアプリの after_send を呼ぶ(テスト通知では呼ばない)
        """
        # 画像の有無判定
        flag_image = isinstance(image, np.ndarray)
        if notification_message:
            send_data_type, send_data_type_eng = ("テキスト・画像", "Text & Image") if flag_image else ("テキスト", "Text")
        else:
            send_data_type, send_data_type_eng = ("画像", "Image") if flag_image else ("(empty)", "empty")

        resolved = self.resolve_keys(keys)
        if not resolved:
            print("Discord の Webhook URL が設定されていません（設定の「Discord 連携」）。")
            self._logger.error("No Discord webhook is set")
        sent = []
        for key in resolved:
            try:
                files = {"payload_json": (None, json.dumps(self._content(key, notification_message)))}
                if flag_image:
                    files["media"] = ("pokecon_image.png", convert_bgr_to_bytes(image))

                self.res = requests.post(self.webhook_url_dict[key], files=files, timeout=(5, 10))

                if self.res.status_code in [200, 204]:
                    print(f"[{key}]{send_data_type}を送信しました。")
                    self._logger.info(f"Send {send_data_type_eng}")
                    sent.append(key)
                else:
                    print(f"[{key}]{send_data_type}の送信に失敗しました。({self.res.status_code})")
                    self._logger.error(f"Failed to send {send_data_type_eng}")
            except Exception as exc:
                print(f"[{key}]{send_data_type}を送れませんでした。webhook urlを確認してください。({exc})")
                self._logger.error(f"Failed to send {send_data_type_eng}: {exc}")
        hook = Discord_Notify.after_send
        if sent and follow_up and hook is not None:
            try:
                hook(self, sent)
            except Exception as exc:
                self._logger.error(f"after_send failed: {exc}")
        return sent

    def send_file(self, keys, filename, data, notification_message=""):
        """ファイル(直前の映像など)を送る。送れた送り先の一覧を返す"""
        sent = []
        for key in self.resolve_keys(keys):
            try:
                files = {
                    "payload_json": (None, json.dumps(self._content(key, notification_message))),
                    "file": (filename, data),
                }
                res = requests.post(self.webhook_url_dict[key], files=files, timeout=(5, 60))
                if res.status_code in [200, 204]:
                    print(f"[{key}]{filename}を送信しました。")
                    sent.append(key)
                else:
                    print(f"[{key}]{filename}の送信に失敗しました。({res.status_code})")
                    self._logger.error(f"Failed to send {filename}: {res.status_code}")
            except Exception as exc:
                print(f"[{key}]{filename}を送れませんでした: {exc}")
                self._logger.error(f"Failed to send {filename}: {exc}")
        return sent

    def getRateLimit(self):
        try:
            for i, name in enumerate(self.webhook_keys):
                print(f"For: {name}")
                print("X-RateLimit-Limit: " + self.res[i].headers["X-RateLimit-Limit"])
                print("X-RateLimit-Remaining: " + self.res[i].headers["X-RateLimit-Remaining"])
                import datetime

                dt = datetime.datetime.fromtimestamp(
                    int(self.res[i].headers["X-RateLimit-Reset"]), datetime.timezone(datetime.timedelta(hours=9))
                )
                print("Reset time:", dt, "\n")

                self._logger.info(f"DISCORD API - Limit: {self.res[i].headers['X-RateLimit-Limit']}")
                self._logger.info(f"DISCORD API - Remaining: {self.res[i].headers['X-RateLimit-Remaining']}")
                self._logger.info(f"Reset time: {dt}")
        # send_message の後は self.res が 1 つの応答になり、確認の応答が無いときは空のリストなので、
        # TypeError / IndexError でも止めない(フォーク元 0.2.0 の修正)
        except (AttributeError, TypeError, IndexError) as e:
            self._logger.error(e)
            pass
        except KeyError as e:
            self._logger.error(e)
            pass


if __name__ == "__main__":
    """
    status  HTTPステータスコードに準拠した値
       200  成功時
       401  アクセストークンが無効
    """
    # import cv2
    # cap = cv2.VideoCapture(0)
    # cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    # cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    # ret, frame = cap.read()

    DISCORD = Discord_Notify()
    DISCORD.getRateLimit()
    # DISCORD.send_message(notification_message="test")
    # DISCORD.send_message(notification_message="test", image=frame)
