# Third-party notices

The controller base is Poke-Controller Modified Extension 0.1.9, derived from Poke-Controller and Poke-Controller Modified. Retain the complete root LICENSE including @progmem, KawaSwitch, Moi-poke and Futo030. Additions in this fork are MIT licensed. This does not relicense the helper, dependencies or game assets.

## Included in the release

- PokeCon橋渡し関数, authored by フウ (@dragonite303), copyright 2025, bundled unchanged from upstream commit 3274e77 with its sample, README and License.txt. Its own license permits personal use and unmodified redistribution, restricts commercial use, and specifies conditions for distributing modifications. See `SerialController/Commands/PythonCommands/bridge_functions/License.txt`. This component is NOT MIT licensed.
- Microsoft Edge WebView2 SDK 1.0.4258.31 (`Microsoft.Web.WebView2.Core.dll`, `Microsoft.Web.WebView2.WinForms.dll`, `WebView2Loader.dll`), redistributed unchanged for the tray app window under its BSD-style license. See `WebView2-LICENSE.txt` and `WebView2-NOTICE.txt` (sources in `packaging/webview2`).
- Upstream game screenshot templates. Game imagery retains its respective rights and is NOT covered by the root MIT license.

## Installed at setup, not distributed

Python and the libraries in `requirements-lock.txt` (OpenCV with its FFmpeg plugin, NumPy, SciPy, pandas, pygame, pynput, Pillow, pyserial, sounddevice (with PortAudio), the MCP SDK and their dependencies) are downloaded by the installer from python.org and PyPI into the user's environment. Each keeps its own license, available in its installed package.

## Changes from Modified Extension 0.1.9

The Tk interface is replaced by a window-less process with a browser UI. Script base classes, dialogues, template paths and settings files keep their original interfaces. Windows camera enumeration uses our COM implementation instead of DirectShowLib, pythonnet and windows-capture-device-list, and logging uses Python's standard logging module.
