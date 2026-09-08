# Third-party notices

The controller base is Poke-Controller Modified Extension 0.1.9, derived from Poke-Controller and Poke-Controller Modified. Retain the complete root LICENSE including @progmem, KawaSwitch, Moi-poke and Futo030. Additions in this fork are MIT licensed. This does not relicense the helper, dependencies, game assets.

## Bundled components

PokeCon橋渡し関数, authored by フウ (@dragonite303), copyright 2025, is quoted and bundled unchanged from upstream commit 3274e77, together with its sample, README and License.txt. Its own license permits personal use and unmodified redistribution, restricts commercial use, and specifies conditions for distributing modifications. Read `SerialController/Commands/PythonCommands/bridge_functions/License.txt`. This component is NOT MIT licensed.

The distribution includes pynput, pygame, OpenCV's FFmpeg plugin and upstream game screenshot templates. Game imagery retains its respective rights and is NOT covered by the root MIT license.

Compared with Modified Extension 0.1.9, Windows camera enumeration uses our COM implementation instead of DirectShowLib, pythonnet and windows-capture-device-list. Log decoration uses Python's standard logging module, and the folder button uses text instead of an image.

## Runtime inventory

`licenses/dependencies.json` records the versions in the actual build. Individual complete notices are copied into `licenses/` and also remain beside their packages under `runtime-python/Lib/site-packages`. CPython, its native components and Tcl/Tk retain their original notices under `runtime-python` and `licenses/Python-LICENSE.txt`.

- Python: PSF and bundled component notices; https://docs.python.org/3.12/license.html
- OpenCV: Apache 2.0 and native third-party notices. The distribution includes the unmodified Windows FFmpeg plugin; its LGPL 2.1 text is in cv2/LICENSE-3RD-PARTY.txt. Source/build recipes: https://github.com/opencv/opencv-python ; Windows FFmpeg sources/scripts: https://github.com/opencv/opencv_3rdparty/tree/ffmpeg . Available codecs depend on the plugin's build.
- pygame 2.6.1: LGPL 2.1. Its matching source archive is included in `licenses/sources/pygame-2.6.1.tar.gz`. README, full LGPL text and native dependency notices are separately copied into `licenses/pygame`. SDL2 is zlib licensed; SDL image/mixer/ttf and codec/font libraries retain their own notices. The full Windows wheel is retained. Build recipes are in the source archive's buildconfig directory. https://www.pygame.org/docs/ .
- pynput 1.8.1: LGPL 3. Its unmodified source archive is included in `licenses/sources/pynput-1.8.1.tar.gz` and its full COPYING.LGPL notice is preserved. https://github.com/moses-palmer/pynput .
- certifi: MPL 2.0. Its unmodified source archive is included in `licenses/sources` along with its license. Its source and certificate bundle also remain accessible in the runtime.
- paho-mqtt is used under its BSD 3-Clause option, not the alternative EPL option.
- MCP SDK: MIT. The complete Python dependency tree and source notices are preserved, including cryptography/OpenSSL, PyWin32, NumPy/SciPy native components and Pillow components.

All source archives in `licenses/sources` correspond to the versions listed in requirements-lock.txt. Libraries and DLLs remain separately stored under `runtime-python`; the application does not check signatures to prevent replacing or debugging modified libraries. Preserve applicable notices and source availability obligations when redistributing. Licenses mentioning unused components can remain in upstream wheel notices; their presence does not imply the corresponding DLL is shipped.

The bridge helper has separate personal/noncommercial conditions. The root MIT license does not apply to the complete distribution. User-installed library updates may have different versions and notices; the bundled inventory describes the original release only.
