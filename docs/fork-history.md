# フォーク元との違いと変更の記録

このリポジトリ（Poke-Controller Modified Extension Plus）が、フォーク元からどう変わったかの記録です。2026-10-27 時点の内容です。

- 比較の基準: フォーク元 `futo030/Poke-Controller-Modified-Extension` のコミット `3274e77`（ver. 0.1.9、2026-09-03）
- 比較の対象: このリポジトリの `2fda8a0`（master、0.3.0-alpha.1。PR #3 のマージ）

## 系譜

| 段 | リポジトリ | 備考 |
|---|---|---|
| 1 | [KawaSwitch/Poke-Controller](https://github.com/KawaSwitch/Poke-Controller) | 元の Poke-Controller |
| 2 | [Moi-poke/Poke-Controller-Modified](https://github.com/Moi-poke/Poke-Controller-Modified) | Modified |
| 3 | [futo030/Poke-Controller-Modified-Extension](https://github.com/futo030/Poke-Controller-Modified-Extension) | Modified Extension。0.1.9（`3274e77`）からフォーク |
| 4 | hinatamaxxx/Poke-Controller-Modified-Extension-Plus（非公開） | このリポジトリ |

フォーク元とは履歴がつながっています（`3274e77` がこのリポジトリの祖先）。フォーク後にフォーク元の変更は取り込んでいません。

## 数字で見る差分

基準: `3274e77`（フォーク元 0.1.9）と `2fda8a0`（このリポジトリ）。

### 全体

| 項目 | 値 |
|---|---|
| 変更されたファイル | 97（追加 59、削除 19、変更 19） |
| 行数（そのまま） | +8,804 / −7,608 |
| 行数（空白と改行コードの違いを無視、`-w --ignore-cr-at-eol`） | +8,235 / −7,039 |
| ファイル数 | 99 → 139 |

### フォーク元のファイル 99 個の行き先

| 状態 | 数 | 内容 |
|---|---|---|
| バイト単位で同一 | 61 | 下表のとおり。サンプルスクリプト、テンプレート画像、db、一部の基底クラス |
| 変更 | 19 | 空白・改行コードだけの変更はなし（すべて中身の変更） |
| 削除 | 19 | Tk の画面、DirectShowLib、起動・更新用 bat、既定のプロファイル |

Python ファイルだけで見ると、フォーク元の 64 ファイル・13,181 行のうち、同一 42 ファイル（3,341 行）、変更 14 ファイル（4,229 行）、削除 8 ファイル（5,611 行）です。このリポジトリの Python は 87 ファイル・約 11,100 行で、ほかに C#（トレイアプリ）約 2,200 行、PowerShell（インストーラー）約 340 行、HTML（操作画面）約 1,200 行があります。

### 領域ごと

| 領域 | 同一 | 変更 | 削除 |
|---|---|---|---|
| 基底クラス `SerialController/Commands/*.py` | `Keys.py` `McuCommandBase.py` `StickCommand.py` `UnitCommand.py` | `CommandBase.py`（+14/−16） `PythonCommandBase.py`（+18/−19） `Sender.py`（+48/−13） `ProController.py`（+64/−19） | なし |
| サンプル `Commands/PythonCommands` | 全 34 ファイル（Samples 18、RankGlitch 5、ImageProcessingOnly 7、bridge_functions 4） | なし（`Samples/PortableDemo.py` を追加） | なし |
| サンプル `Commands/McuCommands` | 全 4 ファイル | なし | なし |
| テンプレート画像 `Template/Samples` | 全 14 ファイル | なし | なし |
| `db` | `poke_form_name.csv` `pokedex.json` | なし | なし |
| 本体の共通モジュール | `CommandLoader.py` | `Camera.py`（+89/−33） `Settings.py`（+79/−41） `ImageProcessing.py`（+32/−13） `PokeConLogger.py`（+14/−59） `PokeConDialogue.py`（+11） `DiscordNotify.py` `LineNotify.py` `ExternalTools.py` `Utility.py` `Constant.py` | なし |
| Tk の画面 | なし | なし | `Window.py`（2,788 行） `GuiAssets.py`（1,022） `Menubar.py`（295） `KeyConfig.py`（389） `Keyboard.py`（251） `PokeConShowInfo.py`（274） `PokeConUpdateChecker.py`（125） `get_pokestatistics.py`（467） `assets/icons8-OpenDir-16.png` |
| その他 | `Images/disabled.png` `Controller_Log/sample.txt` | `README.md` `changelog.txt` `requirements.txt` `LICENSE`（著作権表示を1行追加） `.gitignore` | `DirectShowLib/`（4） `ExecutePokeConModified-Extension.bat` `UpdatePokeConModified-Extension.bat` `profiles/default/*.ini`（4） |

行数は空白と改行コードの違いを無視した値です。フォーク元の README と更新履歴は `README.upstream.md` と `changelog.upstream.txt` に残しています。

### 追加した主なファイル

| 種類 | ファイル |
|---|---|
| 画面のない本体 | `core.py`（770 行） `app.py` `app_paths.py` `bootstrap.py` `product.py` `safe_settings.py` `plus_preferences.py` `demo_camera.py` |
| 操作画面と API | `web/index.html`（1,225 行） `local_control.py`（498 行） `host_channel.py` |
| MCP | `controller_mcp.py` `controller_api.py` `plugin/` `MCP.md` `CLAUDE.md` |
| 更新 | `update_service.py` |
| Windows の機器 | `SerialController/WindowsDevices.py`（COM でカメラを列挙） `SerialController/UiDispatch.py` `SerialController/Paths.py` |
| 配布 | `packaging/`（トレイアプリ C# 11 ファイル、`install.ps1` `get.ps1` `uninstall.ps1` `build.py` `Launcher.cs`、WebView2 SDK の DLL） |
| テスト | `tests/`（unittest 9 ファイル、`integration.py`、`virtual_gamepad.py`） |
| 文書 | `README.upstream.md` `changelog.upstream.txt` `THIRD_PARTY_NOTICES.md` `.gitattributes` `requirements-lock.txt` |

## 機能ごとの変更

### 画面

- Tk の画面（`Window.py` `GuiAssets.py` `Menubar.py`）を削除しました。本体は画面を持たない Python のプロセス（`core.py` + `app.py`）になり、カメラ、シリアル、スクリプトの実行、ログ、操作画面の配信、MCP の接続先を受け持ちます。
- 操作画面は 1 枚の HTML（`web/index.html`）です。`local_control.py` が `127.0.0.1` だけで待ち受け、トークンで認証します。映像、コントローラー（スティックはドラッグ）、スクリプトの開始・停止・一時停止・再開、接続、設定、ログ、スクリプトのダイアログを扱います。
- 通知領域に常駐するトレイアプリ（`PokeController.exe`、C#/WinForms）を追加しました。本体を起動・監視し、操作画面を WebView2 の専用ウィンドウで開きます。メニューは「画面を開く」「作業フォルダーを開く」「本体を起動し直す」「アップデート」「アプリを終了する」などです。ログオン時の自動起動はしません。
- 画像認識の枠と文字（`Command.canvas` の `ImgRect` / `ImgText`）は、`core.py` の `Overlay` が映像に描き込みます。
- 同じアプリを複数起動すると、空いている設定枠（プロファイル）を自動で割り当てます（`app.py` の `acquire_profile`）。フォーク元の「起動用 bat とプロファイルを作る」機能の代わりです。

### スクリプトの互換層

- `CommandBase.Command` の `text_area_1` / `text_area_2` / `canvas` は、`core.py` の `LogArea` / `Overlay` に差し替えています。Tk のテキスト部品と同じメソッド（`insert` `delete` `config` `see` など）を持つので、スクリプトから見た使い方は同じです。ログは 2,000 行・20 万文字で古いものから消します。
- ダイアログ（`dialogue` `dialogue6widget` など）は `PokeConDialogue.show_dialogue` を通り、本体が `DIALOGUE_PROVIDER` を設定していればブラウザで聞き、なければ従来の Tk で開きます。
- `Settings.py` の `tk.IntVar` などは、同じ `get` / `set` を持つ `Var` に置き換えました。

### シリアル

- 書き込みをロックで直列化し、書き込みタイムアウト（0.25 秒）を設定しました。マイコンの受信待ちによるタイムアウトは切断として扱わず、その送信だけを捨てます。それ以外の書き込みエラーは切断として扱い、ポートを閉じます。
- ポート名で開くときにボーレートの指定が使われず 9600 になる問題、開いていないポートを閉じるとエラーになる問題を直しました。
- スクリプトの停止時・エラー時に必ず入力を離し（`keys.end()`）、後処理を 1 回だけ呼ぶよう `PythonCommandBase.do_safe` を整理しました。0.1 秒を超える `wait` は 20 ミリ秒ごとに停止要求を確認します。
- スクリプトのエラーはログ欄に「スクリプトがエラーで停止しました: 種類: 内容」と出します。読み込めないスクリプトがあっても、ほかのスクリプトは読み込みます（`Utility.importAllModules`）。

### カメラ

- カメラの列挙を DirectShowLib（pythonnet 経由）と windows-capture-device-list から、ctypes で Windows の COM を直接呼ぶ実装（`WindowsDevices.py`）に置き換えました。
- 選んだカメラを機器 ID（`camera_path`）で覚え、抜き差しや並び順の変化があっても同じ機器を開きます。OBS 仮想カメラのような機器 ID のないカメラも選べます。
- 映像の読み取りを専用スレッドに分けました。2 秒までの途切れでは切断せず、抜けたカメラを挿し直すと自動で再接続します。
- キャプチャ保存で、映像がないときや書き込みに失敗したときに成功と表示する問題を直しました。

### 画像認識

- `ImageProcessing.getImage` は、日本語を含むパスでも読めるよう `imdecode` で読みます。ファイルがない・読めない・画像でないときは、従来の `None` を返す動作ではなく、理由を書いた例外を出します。
- テンプレートマッチングの前に、画像の有無、テンプレートが比較対象より大きくないか、色形式、マスクの大きさを確認し、合わなければ理由を書いた例外を出します。

### 設定の保存

- 設定ファイル（`settings.ini` ほか）の書き込みをアトミックにし、直前の正しい内容を `.bak` に残します。読めないときは `.bak` から戻します（`safe_settings.py`）。
- 形式はフォーク元と同じ `settings.ini` です。追加した項目は `camera_path` `camera_name` `enlarge_preview` です。新規作成時の既定値は `camera_id = -1`（未選択）、`is_use_keyboard = False` に変えました。
- 保存先は、インストール版では設定（プロファイル）が `%APPDATA%\PokeController`、ログ・専用 Python・接続ファイルが `%LOCALAPPDATA%\PokeController`、スクリプトと画像が `ドキュメント\PokeController` です。ソースから動かすとき（`.git` があるとき）は従来どおり `SerialController` 以下です。
- ログは標準の `logging` で `controller-<PID>.log` に書き、4MB ×3 で回します。

### 配布・インストール・更新

- 0.2.0-alpha 系は Python とライブラリを同梱した portable ZIP でした。0.3.0-alpha.1 からはユーザーごとのインストール型（管理者権限不要）で、Python とライブラリは同梱しません。インストール時に、専用の仮想環境を作るか、公式の Python 3.12 を専用フォルダーに展開するか、既存の Python を使うかを選べます。配布物は約 4.5〜5MB です。
- ライブラリの版は `requirements-lock.txt` で固定しています（OpenCV 5.0.0.93、NumPy 2.5.3、paho-mqtt 2.1.0 など）。
- 自動更新は 1 日 1 回、このリポジトリの GitHub Releases を確認し、SHA-256 を照合してから入れ替えます。0.2.0-alpha.1 にあったアプリ内のライブラリ更新機能は 0.3.0-alpha.1 で廃止しました。
- レジストリはアンインストール情報（`HKCU\...\Uninstall\PokeController`）だけを書きます。

### MCP

- `PokeControllerMCP.exe`（`controller_mcp.py`）を stdio の MCP サーバーとして登録します。本体が動いていなければ画面なしで起動し、複数の本体があればすべて見つけます。
- ツールは `list_sessions` `list_scripts` `start_script` `stop_script` `pause_script` `resume_script` `get_logs` `get_capture` `press_buttons` `tilt_stick` `get_web_url` です（[MCP.md](../MCP.md)）。
- 本体との通信は名前付きパイプで、トークンで認証します。AdGuard の localhost フィルタリングなどで Python の loopback 通信が壊れる環境への対応です。

### 依存ライブラリ

| 変化 | ライブラリ |
|---|---|
| 削除 | pythonnet、windows-capture-device-list、DirectShowLib（DLL） |
| 追加 | mcp、PyAudio |
| 残したもの | opencv-python、pyserial、Pillow、pygubu、requests、pandas、numpy、scipy、paho-mqtt、GitPython、plyer、pygame、pynput（有志スクリプトが使うことがあるため） |

すべて版を固定しました。フォーク元は版を固定していません。

### テスト

フォーク元にはテストがありません。このリポジトリでは `tests/` に unittest（設定の保存と復元、切断の扱い、プロファイルの割り当て、MCP 登録、更新、互換性など）と、本体と MCP を実際に起動して確かめる `tests/integration.py` があります。`test_compatibility.py` は、テンプレート画像 14 個が `3274e77` とバイト単位で同じことを確かめます。

## 有志スクリプトとの互換性

### 同じもの

- 基底クラス `PythonCommand` / `ImageProcPythonCommand` / `McuCommand` と、そのメソッド名・引数（`press` `hold` `wait` `isContainTemplate` `dialogue6widget` など）。`McuCommandBase.py` `StickCommand.py` `UnitCommand.py` はバイト単位で同一です。`Keys.py` はフォーク元 0.2.0 の修正を取り込んだ分だけ違います（名前・引数・値は同じ）。
- 置き場所: `Commands/PythonCommands`、`Commands/McuCommands`、`Template/`。テンプレートのパスの指定方法（`./Template/` 起点）。
- ダイアログの関数と戻り値の形（ブラウザで表示します）。
- `settings.ini`、`line_token.ini`、`discord_token.ini`、`external_token.ini` の形式。
- 橋渡し関数（bridge_functions）は `3274e77` のものを改行コードも含めて変更せずに同梱しています。
- 通知（Windows、LINE、Discord）、Socket・MQTT の関数。データ形式は Default / Qingpi / 3DS Controller（2 種）です。

### 変わったもの

- 画像ファイルがない・壊れているときの `getImage` は、`None` を返さず例外を出します。テンプレートマッチングも、サイズや形式が合わないと例外を出します。`None` を受けて分岐していたスクリプトは止まります。
- `print` の出力とログ欄はブラウザの操作画面に出ます。認識の枠は映像に描き込みます。
- 長い `wait` が停止要求ですぐ止まります（止めないときの待ち時間は同じ）。
- LINE / Discord の通知設定の読み込み時に、ネットワークでの確認をしなくなりました。
- スクリプトから `tkinter` を直接使うもの（サンプルでは `RecPlay.py` の `filedialog`、`isContainTemplate_sample.py` と `isContainedImage_sample.py` の `messagebox`）は、操作画面には出ません。Tk を含む Python なら別ウィンドウで開く可能性がありますが、確かめていません。

### なくなったもの

- PC のキーボードによる全体での操作（pynput で常に受け付ける方式）と、PC につないだゲームパッドの中継・操作記録（Use Pro Controller / Record Pro Controller）。`ProController.py` はファイルとして残っていますが、本体からは使いません。キーボード操作は、操作画面にフォーカスがある間だけ、`settings.ini` の `KeyMap-*` に従って受け付けます。
- Pokemon Home 連携（`get_pokestatistics.py`。`settings.ini` の `Pokemon Home` の節は残しています）。
- Tk のメニュー: 質問テンプレート、Version 確認、Poke-Controller Guide、LINE Token / Discord の確認、画面サイズのリセット、bat とプロファイルの生成、git による更新（`PokeConUpdateChecker.py`、`UpdatePokeConModified-Extension.bat`）。
- プレビュー上のマウスでスティックを操作する機能（Use LStick Mouse / RStick Mouse）。操作画面のスティックはドラッグで操作します。

## フォーク元のその後

`git fetch upstream` の結果（2026-10-27）、`3274e77` 以降のフォーク元のコミットは次の 2 つです。

| コミット | 日付 | 内容 |
|---|---|---|
| `8cb238d` | 2026-10-12 | ver. 0.2.0 |
| `cc49f82` | 2026-10-12 | PR #27 のマージ（タグ `v0.2.0`、GitHub の Latest リリース） |

このリポジトリの基準は 0.1.9、フォーク元の最新は 0.2.0 です。0.2.0 は 289 ファイル（+64,763 / −45,951）の大きな変更で、Tk の画面の再構成、`services/` への処理の分離、FastAPI による Web ブラウザ版（試作）、uv による環境の用意、テストと CI、音声、ウィンドウの取り込み、データ形式 NX・DS FT の追加などを含みます。共通モジュールの `Commands/*.py` `ImageProcessing.py` `PokeConDialogue.py` `ExternalTools.py` も大きく変わっています（空白を無視して +2,455 / −1,140）。

### 0.2.0 から取り込んだ修正（0.3.0-alpha.1）

共通のモジュールに関わる不具合の修正を、ファイルごとではなく修正ごとに移しました。確かめるテストは `tests/test_upstream_fixes.py` です。

| 修正 | ファイル |
|---|---|
| MQTT を paho-mqtt 2.x で使えるようにした（`CallbackAPIVersion.VERSION2` を渡す。1.x でも動く）。通信に失敗したとき、原因に関わらず「paho-mqtt が入っていない」と出ていたのを、例外の内容を出すよう変更。トークンのない `transmit_message` が例外になる問題、`receive_message2` の表示が `[socket:wait]` だった問題 | `ExternalTools.py` |
| Socket 通信で `change_port` の値が接続に使われない問題 | `ExternalTools.py` |
| 空の `external_token.ini` で BOM の判定が例外になる問題（加えて、`[SOCKET]` `[MQTT]` が無いときは初期値を使い、スクリプトを開始できるようにした） | `ExternalTools.py` |
| `hold` で Button.B と Hat.RIGHT のように値が同じ入力を同時に長押しできない問題。押したままの入力があるとき `input` が呼び出し元のリストを書き換える問題。ホールド済みの入力があると残りを送らない問題。ホールドしていない入力の `holdEnd` がエラーで止まる問題（警告にした）。`inputEnd(..., unset_Touchscreen=False)` でタッチが離れない問題。`setAnyDirection` の `x_reverse` / `y_reverse` で変化の判定が逆になる問題 | `Commands/Keys.py` |
| `isContainTemplate_max` にマスク画像のリストを渡すと -1 が返る問題、GPU でのマッチングのエラー、`saveImage` の失敗を成功と表示する問題・ファイル名なしでエラーになる問題 | `ImageProcessing.py` |
| `isContainedImage` で `crop_template` を省略すると、見つかったときにエラーになる問題 | `Commands/PythonCommandBase.py` |
| `camera.saveCapture` で `img` を渡しても `crop` がないとカメラの画像を保存する問題 | `Camera.py` |
| Mcu コマンドなどでダイアログをキャンセルするとエラーになる問題（`Command.finish` を追加） | `Commands/CommandBase.py` |
| 画像認識やコマンドの開始のたびにログのハンドラが増え続ける問題 | `Keys.py` `ImageProcessing.py` `PythonCommandBase.py` `Camera.py` `LineNotify.py` `DiscordNotify.py` |
| LINE / Discord の確認の結果の表示（`str()`）がエラーになる問題、送信の後に `getRateLimit` がエラーになる問題、LINE の ImageLimit に Limit の値を出していた問題。Discord の設定で `username` / `avatar_url` が欠けていると開始できない問題 | `LineNotify.py` `DiscordNotify.py` |
| ログのファイルに通信先の URL（Discord の Webhook の URL を含む）が書かれる問題（urllib3 の DEBUG ログを止めた） | `PokeConLogger.py` |

このフォーク自身の問題で、取り込みの確認中に見つけて直したもの: スクリプトの中で `self.finish()` を呼んでも止まらず、ダイアログをキャンセルしても後の処理が続いていた（0.2.0-alpha.8 で停止の要求を別スレッドから出せるようにしたときの副作用）。スクリプトのスレッドから呼んだときは、元の Modified 版と同じく `StopThread` で終えるよう戻した。正常に終わったときの「finished successfully」と終了の通知も、これで再び出る。

取り込まなかったもの:

| フォーク元 0.2.0 の変更 | 理由 |
|---|---|
| `Sender.show_input` の表示の修正 | このリポジトリでは呼ばれない（Tk 版のキーボード操作の記録用で、`is_show=True` で送る箇所がない） |
| `StickCommand` / `UnitCommand` の修正 | このリポジトリでは使っていない |
| `getImage` で読めないファイルを知らせる修正 | このリポジトリの `getImage` は、読めないときに理由つきの例外を出す形に作り替え済み |
| ポート名で開くとボーレートが 9600 になる問題、未接続のポートを閉じるとエラーになる問題、COM 番号のないポートで一覧が取れない問題、log フォルダがないとログを始められない問題、長い待機の途中で止まらない問題 | 同等の対応あり |
| Mac / Linux のキャプチャデバイス・キー入力の修正 | このリポジトリは Windows 専用 |
| 別スレッドから GUI を操作して不安定になる問題、キーコンフィグ、メニュー、ダイアログの Cancel など画面の修正 | Tk の画面がない |
| 新しいスクリプト API（`getInterframeDiff`、Switch へのキーボード入力、`holdChange`、`discord_text` / `discord_image` の `name` 引数、Discord の通知先の複数登録）、bridge_functions ver.0.0.3、データ形式 NX・DS FT、音声、一時停止の位置表示など | 不具合の修正ではなく機能の追加。これらを使う新しい有志スクリプトは、このリポジトリでは動かない |

フォーク元 0.2.0 では `CommandBase.py` などが画面から切り離されて大きく書き換わっているため、今後も、ファイルごと置き換えるのではなく、修正ごとに移します。

## このフォークの版ごとの履歴

詳細は [changelog.txt](../changelog.txt) にあります。コミットとの対応は次のとおりです。

| 版 | コミット | 日付 | 概要 |
|---|---|---|---|
| 0.2.0-alpha.8 | `8d760d9`（タグ `v0.2.0-alpha.8`） | 2026-09-08 | 0.1.9 をもとにした Windows 用 portable ZIP の最初の公開。MCP、設定の安全な保存、画像認識のエラー表示、入力解除、カメラ列挙の置き換え |
| 0.2.0-alpha.9 | `f78c0d4`（タグ `v0.2.0-alpha.9`） | 2026-09-09 | カメラの選択を機器 ID で覚える |
| 0.2.0-alpha.1 | `de49cf9`〜`6e73ef8`（タグ `v0.2.0-alpha.1`、GitHub の Pre-release） | 2026-09-09 | 版番号を「初期アルファ版」として alpha.1 に振り直し。ライブラリ更新機能、設定画面の配置、日本語化、複数起動の設定枠 |
| 0.2.0-alpha.2 | `cee5d24`〜`dd10266`（タグなし） | 2026-10-27 | ブラウザの操作画面、MCP の `press_buttons` / `get_web_url`、切断・カメラ・MCP 登録の不具合修正 |
| 0.3.0-alpha.1 | `1210a64`（PR #3、`2fda8a0` でマージ。タグなし） | 2026-10-27 | Tk の画面を削除し、画面のない本体・ブラウザの操作画面・トレイアプリ・インストーラー・自動更新に作り替え |

版番号は alpha.8 → alpha.9 → alpha.1 と一度戻っています。タグと GitHub のリリースがあるのは `v0.2.0-alpha.1` までです。

## 調べ方

このリポジトリのクローンで次を実行すると、上の数字を再現できます（Git Bash）。

```bash
git fetch origin
git remote add upstream https://github.com/futo030/Poke-Controller-Modified-Extension.git
git remote set-url --push upstream DISABLED   # 取得だけに使う
git fetch upstream --tags

B=3274e77; M=2fda8a0
git diff --shortstat $B $M                          # 全体
git diff --shortstat -w --ignore-cr-at-eol $B $M    # 空白・改行コードを無視
git diff --name-status $B $M | cut -f1 | sort | uniq -c
git diff --numstat -w --ignore-cr-at-eol $B $M -- SerialController

# フォーク元のファイルごとに 同一 / 変更 / 削除 を判定
export MSYS_NO_PATHCONV=1   # Git Bash が "rev:path" を書き換えないようにする
git ls-tree -r $B | while read mode type sha path; do
  n=$(git rev-parse -q --verify "$M:$path")
  if [ -z "$n" ]; then echo "削除 $path"; elif [ "$n" = "$sha" ]; then echo "同一 $path"; else echo "変更 $path"; fi
done

# フォーク元のその後
git log --format='%h %ci %s' $B..upstream/master
git diff --shortstat $B upstream/master
git diff $B upstream/master -- changelog.txt

# このフォークの履歴
git log --format='%h %ci %s' --no-merges $B..$M
```

パスが長いファイルで `Filename too long` が出るときは `git -c core.longpaths=true` を付けます。
