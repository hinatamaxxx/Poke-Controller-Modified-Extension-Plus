"""Settings folders shared by the GUI modules. app.py points them to the installed locations first. MIT."""
import os
import sys

PROFILES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles")
LOGS = "log"

# The user's scripts, under the work folder: one folder per script with its images in 画像, and 共通/画像 for
# images several scripts use. The bundled samples stay in Commands/PythonCommands and Template.
SCRIPTS = "スクリプト"
SHARED = "共通"
IMAGES = "画像"
TEMPLATE = "./Template/"


def image_folders(module_name):
    """Folders a script's image (a relative name such as "egg.png") is looked for in, in order: the script's own
    画像 and folder, the 画像 of each folder above it inside スクリプト (images of one game), スクリプト/共通/画像,
    then Template, so scripts written for Template keep working."""
    root = os.path.realpath(SCRIPTS)
    folders = []
    folder = script_folder(module_name)
    if folder:
        folders += [os.path.join(folder, IMAGES), folder]
        folder = os.path.dirname(folder)
        while folder != root:
            folders.append(os.path.join(folder, IMAGES))
            folder = os.path.dirname(folder)
    return folders + [os.path.join(root, SHARED, IMAGES), TEMPLATE]


def script_folder(module_name):
    """The folder of a script in スクリプト ('' for the bundled ones and a .py directly in スクリプト)."""
    file = getattr(sys.modules.get(module_name), "__file__", None)
    if not file:
        return ""
    root, folder = os.path.realpath(SCRIPTS), os.path.dirname(os.path.realpath(file))
    return folder if folder != root and os.path.commonpath([root, folder]) == root else ""


def find_image(filename, module_name):
    for folder in image_folders(module_name):
        path = os.path.join(folder, filename)
        if os.path.isfile(path):
            return path
    # Not found: name the place it should be, so the error message says where to put it.
    own = script_folder(module_name)
    return os.path.join(own, IMAGES, filename) if own else os.path.join(TEMPLATE, filename)
