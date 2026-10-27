#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib
import sys

import Utility as util

from logging import getLogger, DEBUG, NullHandler

logger = getLogger(__name__)
logger.addHandler(NullHandler())
logger.setLevel(DEBUG)
logger.propagate = True


class CommandLoader:
    def __init__(self, base_path, base_class):
        self.path = base_path
        self.base_type = base_class
        self.modules = []

    def load(self):
        if not self.modules:  # load if empty
            self.modules = util.importAllModules(self.path)

        # return command class types
        return self.getCommandClasses()

    def reload(self):
        loaded_module_dic = {mod.__name__: mod for mod in self.modules}
        cur_module_names = util.getModuleNames(self.path)

        # Load only not loaded modules
        not_loaded_module_names = list(set(cur_module_names) - set(loaded_module_dic.keys()))
        if len(not_loaded_module_names) > 0:
            self.modules.extend(util.importAllModules(self.path, not_loaded_module_names))

        # Reload commands except deleted ones
        for mod_name in list(set(cur_module_names) & set(loaded_module_dic.keys())):
            try:
                importlib.reload(loaded_module_dic[mod_name])
            except Exception:
                # Keep the previous version loaded; one broken file must not stop the others from reloading.
                logger.exception("スクリプトを読み込めませんでした: %s", mod_name)
                print(f"読み込み失敗: {mod_name}（詳細は診断ログ）")

        # Unload deleted commands
        for mod_name in list(set(loaded_module_dic.keys()) - set(cur_module_names)):
            self.modules.remove(loaded_module_dic[mod_name])
            sys.modules.pop(loaded_module_dic[mod_name].__name__)  # Un-import module forcefully

        # return command class types
        return self.getCommandClasses()

    def getCommandClasses(self):
        classes = []
        for mod in self.modules:
            # extract module of having "NAME"
            class_list = [
                c
                for c in util.getClassesInModule(mod)
                if issubclass(c, self.base_type) and hasattr(c, "NAME") and c.NAME
            ]

            # make tags of directory name
            for c in class_list:
                # A class kept across reloads (its module failed to reload) must not get the suffix twice.
                if "_LOADER_NAME" not in c.__dict__:
                    c._LOADER_NAME, c._LOADER_TAGS = c.NAME, getattr(c, "TAGS", None)
                c.NAME = c._LOADER_NAME
                if c._LOADER_TAGS is None:
                    if "TAGS" in c.__dict__:
                        del c.TAGS
                else:
                    c.TAGS = c._LOADER_TAGS
                dir_name = "/".join(mod.__name__.split(".")[2:])
                dir_tags = ["@" + t for t in mod.__name__.split(".")[2:-1]]

                # add tags of directory name
                if hasattr(c, "TAGS"):
                    if isinstance(c.TAGS, list):
                        logger.debug(f"TAGS name add: {dir_tags}")
                        c.TAGS = c.TAGS + dir_tags
                    elif isinstance(c.TAGS, str):
                        logger.debug(f"TAGS name add: {dir_tags}")
                        c.TAGS = [c.TAGS] + dir_tags
                    else:
                        logger.debug(f"TAGS Type error: {mod.__name__} {c.NAME} {type(c.TAGS)}")
                else:
                    logger.debug(f"TAGS do not exist: {mod.__name__} {c.NAME}")
                    c.TAGS = dir_tags

                # rename NAME
                c.NAME = f"{c.NAME} ({dir_name})"
                classes.append(c)

        return classes
