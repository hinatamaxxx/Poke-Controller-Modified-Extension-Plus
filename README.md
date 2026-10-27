# Poke-Controller Modified Extension Plus

[Poke-Controller Modified Extension](https://github.com/futo030/Poke-Controller-Modified-Extension) 0.1.9 をもとにした Windows 用のフォークです。Tk の画面をなくし、ブラウザで操作する形にしました。Claude などの AI から MCP とブラウザで扱うことを主な用途にしています。有志が公開しているスクリプトは、元と同じ置き方・書き方で使えます。

フォーク元との違いの詳細は [docs/fork-history.md](docs/fork-history.md) にまとめています。

## この公開について

動作・スクリプト互換性・不具合の修正を保証しません。利用による損害などについて責任は負いません。継続的な更新・サポートの予定もありません。了承のうえ、各ライブラリのライセンス条件の範囲で、自己責任で使ってください。必要な変更は、フォークして AI などでご自身の環境に合わせることをおすすめします。

## 構成

| | |
|---|---|
| トレイアプリ | `PokeController.exe`。通知領域に常駐し、本体を起動・監視する。操作画面を専用のウィンドウで開く |
| 本体 | 画面を持たない Python のプロセス。操作画面と MCP の窓口になる司令塔と、Switch 1 台ごとの作業プロセス（カメラ、シリアル、スクリプトの実行）に分かれる |
| 操作画面 | 専用ウィンドウ（WebView2）またはブラウザ（`http://127.0.0.1`、トークン付き）。映像、コントローラー、スクリプト、接続、設定、ログ、スクリプトのダイアログ |
| MCP | `PokeControllerMCP.exe`。トレイアプリが動いていなければ裏で起動する |

## インストール

PowerShell で次の1行を実行します。管理者権限は要りません。

```powershell
irm https://github.com/hinatamaxxx/Poke-Controller-Modified-Extension-Plus/releases/latest/download/get.ps1 | iex
```

Python の扱いはインストール時に選べます（`get.ps1` と `install.ps1` の引数）。

| 指定 | 内容 |
|---|---|
| なし（おすすめ） | python.org 版の Python 3.12 があれば、それをもとに専用の仮想環境を作る。なければ公式の Python 3.12 を専用フォルダーに展開する（システムには登録しない）。どちらも既存の Python 環境には触らない |
| `-Python Existing [-PythonPath <python.exe>]` | 指定した Python にライブラリを入れて使う |
| `-Python Manual -PythonPath <python.exe>` | 指定した Python をそのまま使う。ライブラリは自分で用意する |

ライブラリは元のポケコンと同じ組み合わせ（`requirements-lock.txt`）を PyPI から入れます。Microsoft Store 版の Python はカメラの許可が別に必要になるため、おすすめの方法では使いません。

ほかの引数: `-DesktopShortcut`（デスクトップにも置く）。Claude Code・Codex から使うときは、あわせてプラグインを入れます（[Claude Code・Codex のプラグイン](#claude-codecodex-のプラグイン)）。ソースから入れる場合は `python packaging\build.py` の後、`dist\PokeController\install.ps1` を実行します。

署名していないため、SmartScreen の警告が出たら「詳細情報」→「実行」で進めます。

## 使い方

- スタートメニューの「Poke-Controller」で操作画面のウィンドウを開きます。通知領域のアイコンのダブルクリックでも開けます。ウィンドウを閉じても本体は動き続けます。終了は通知領域のメニューの「アプリを終了する」か、操作画面の「設定 → アプリを終了」で行います。
- ログオン時の自動起動はしません。本体は起動している間、設定したカメラと COM ポートを使い続けるため、使うときだけ起動します（Claude からは MCP が自動で起動します）。
- Claude から使うときは、アプリを開いておく必要はありません。MCP が本体を裏で起動します。`get_web_url` の URL を Claude の内蔵ブラウザで開くと、映像を見ながら操作できます。

### Claude Code・Codex のプラグイン

Claude Code と Codex には、ポケコンをまとめて使えるようにするプラグインがあります。入れると、MCP の道具（映像・ボタン・スクリプトなど 40 個）と、使い方のスキル（`open` 操作画面を開く、`operate` 操作の決まり、`script` スクリプトを作る、`migrate` 古いポケコンのスクリプトを移す）が入ります。先にアプリ本体をインストールしてください。

Claude Code:

```bash
claude plugin marketplace add hinatamaxxx/Poke-Controller-Modified-Extension-Plus
```

```bash
claude plugin install poke-controller@poke-controller --scope user
```

Codex:

```bash
codex plugin marketplace add hinatamaxxx/Poke-Controller-Modified-Extension-Plus
```

```bash
codex plugin add poke-controller@poke-controller
```

入れたあと、新しいセッションで「ポケコンを開いて」と頼むと、操作画面が開きます。アプリを標準以外の場所に置いているときは、環境変数 `POKECONTROLLER_MCP` に `PokeControllerMCP.exe` のパスを設定します。

プラグインを使わない MCP クライアント（Claude Desktop のチャットなど）では、`PokeControllerMCP.exe` を stdio サーバーとして登録します（[MCP.md](MCP.md)）。

### ゲームコントローラーとキーボード

PC につないだゲームコントローラー（Pro コントローラー、Xbox 系など、ブラウザーが標準の配置として認識するもの）で、そのまま Switch を操作できます。ボタンは配置どおり（下が B、右が A、左が Y、上が X）で、スティックはアナログのまま送ります。つながっている間は、上のバーに 🎮 が出ます。最初にボタンを 1 つ押すと認識されます。キーボードでの操作は最初からオンで、キーの割り当ては設定の「キー設定」で変えられます。どちらも、スクリプトの実行中と COM ポートが未接続のときは効きません。

### メニューと設定

左上の「☰」に、設定・ヘルプ・アプリの終了があります。スクリーンショットと画面を Discord に送るボタンは、下のタブの右端にあります。設定（Ctrl+,）は画面に重なるウィンドウで開き、左の一覧で項目を選びます（Discord 連携、見張り、キー設定、ログ、フォルダー、更新、このアプリについて）。「フォルダー」では、作業フォルダーとスクリーンショット・録画の保存先を変えられます。設定は全 Switch 共通で、どのタブで変えても全台に反映されます。Windows と Discord の通知と、Discord の Webhook は「Discord 連携」で設定します。スクリプトの Discord 通知（`self.discord_text` など）も、この Webhook に届きます。「Switch 本体でも録画する」をオンにすると、通知の直前にキャプチャーボタンを長押しして直前およそ 30 秒を Switch に保存し、「直前30秒の映像を添付する」をオンにすると、アプリが覚えている直前の映像を動画で送ります（色違いが出た瞬間を残せます）。カメラと COM ポートは Switch ごとです。

アプリの窓では、上のバーがタイトルバーを兼ねます。空いた所をドラッグすると窓が動き、ダブルクリックで最大化します。

Claude Code（デスクトップアプリ）では「ポケコンを開いて」と頼むと、MCP の `get_web_url` で操作画面を Claude の内蔵ブラウザーに開きます。

### 複数の Switch

操作画面の上のタブが Switch 1 台ずつです。「＋」で増やし、Switch ごとにカメラと COM ポート（マイコン）を「機器接続」で選びます。ほかのタブで使っている機器には「（Switch 1 で使用中）」と出ます。タブ名はダブルクリック（または F2）で変えられ、通知にもこの名前が入ります。新しい Switch は、一番左の Switch の設定を引き継ぎます。タブは × で閉じられます（最後の 1 台は除く）。閉じたタブの設定は残り、「＋」を押すとまた開きます（閉じた台があるときに新しい台を足すには、「＋」を右クリック）。

Switch ごとに別のプロセスで動くので、1 台が落ちたり固まったりしても、ほかの台は動き続けます（Chrome のタブと同じ考え方）。落ちた台は自動で起動し直し、見張りの自動再開が有効ならスクリプトも再開します。そのとき、直前 30 秒の映像を録画として残し、Discord などに知らせます。10 分の間に 4 回落ちたときは、自動の再起動をやめ、タブに「再起動」ボタンを出します。

Claude も同じ一覧（`list_sessions`）で台を選び、`add_switch` などで台を増やしたり閉じたりできます。

### Claude にスクリプトを作ってもらう

やりたいことを言葉で伝えると、Claude が実機で 1 回ずつ操作して確かめ、うまくいったら、その操作（押した長さ、間隔、画面の確認）からループするスクリプトを作ります。例:「ヒトカゲの色違いが出るまで、ソフトの再起動と話しかけを繰り返して」。作ったスクリプトは作業フォルダーの `スクリプト` に保存され、ほかのスクリプトと同じように使えます。録画はカメラタブの「録画」からも撮れ、Claude に見せて作ってもらうこともできます。

### 長時間の実行の見張り

スクリプトの実行中に、エラーで止まった、映像が一定時間変わらない（ソフトや Switch が止まった）、キャプチャーボードやマイコンが外れた、を見つけると、画面を `Captures\incidents` に、直前 30 秒の映像を `Captures\recordings` に保存し、通知タブで設定した Discord（画面つき）・LINE と Windows の通知に知らせます。通知タブで、スクリプトを自動で開始し直す設定もできます。Claude に見張りを頼むと、知らせを受けて画面を確認し、ソフトの再起動などで復旧を試みます。

## ファイルの場所

| 種類 | 場所 |
|---|---|
| プログラム | `%LOCALAPPDATA%\Programs\PokeController` |
| スクリプト・テンプレート画像・キャプチャ（作業フォルダー） | `ドキュメント\PokeController`（中は元の `SerialController` と同じ構成） |
| 設定（プロファイル、通知トークン、自動更新） | `%APPDATA%\PokeController` |
| 専用の Python、ログ、接続ファイル | `%LOCALAPPDATA%\PokeController`（Switch ごとのログは `log\worker-<設定名>.log`） |
| Switch の一覧 | 最初の Switch の設定フォルダーの `switches.json`。2 台目からの設定は `default-2` のような名前のフォルダー |

同梱のサンプルは初回起動時に作業フォルダーの `Commands\PythonCommands` と `Template` へコピーし、利用者が変更したファイルは上書きしません。

### スクリプトと画像の置き方

自分のスクリプトは、作業フォルダーの `スクリプト` に **1 本ずつフォルダーを作って**、使う画像と一緒に置きます。入れるのも消すのもフォルダーごとで済み、ほかのスクリプトの画像と混ざりません。

```
スクリプト  BDSP    画像\              ← BDSP のスクリプトが共通で使う画像
    エンテイ      エンテイ.py
      画像\            ← このスクリプトだけが使う画像
  共通    画像\              ← ゲームをまたいで使う画像
```

- `isContainTemplate('yuke.png')` のように名前だけ書くと、スクリプトの `画像` → 上のフォルダーの `画像`（例: `BDSP\画像`）→ `共通\画像` → `Template` の順に探します。見つからないときのエラーには、そのスクリプトの `画像` の場所が出ます。
- 一覧では、スクリプトのフォルダーの 1 つ上（例: `BDSP`）でまとまります。スクリプトタブの「フォルダー」で、選んでいるスクリプトのフォルダーを開けます。
- 回数の記録など、スクリプトが自分で保存するファイルは `Path(__file__).parent` を基準にすると、スクリプトのフォルダーに入ります。
- 複数のスクリプトで使う関数は `共通` に置き、`from スクリプト.共通 import 名前` で読み込めます。
- これまでどおり `Commands\PythonCommands` と `Template` に置いたスクリプトもそのまま動きます。古いポケコンのスクリプトを移すときは、Claude に古いフォルダーの場所を伝えて「スクリプトを移植して」と頼めます（プラグインの `migrate` の手順）。

変更するレジストリは、「インストールされているアプリ」に表示するための `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\PokeController` だけです。ほかに作るものは、スタートメニューの `Poke-Controller.lnk`、専用ウィンドウのデータ（`%LOCALAPPDATA%\PokeController\WebView2`）です。

## 更新とアンインストール

- 自動更新は既定でオンです（1日1回、GitHub Releases の最新版を SHA-256 で照合してから入れ替え）。更新は次の起動から反映されます。操作画面の「設定」から切り替えと手動確認ができます。
- アンインストールは「設定 → アプリ → インストールされているアプリ」から行います。既定では設定も削除し、「設定とデータを残す」を選ぶと残します。作業フォルダー（ドキュメント）は消しません。

## 大きさ

配布物は約 5MB（アプリのコード、サンプル画像、WebView2 の部品）です。Python とライブラリは同梱せず、インストール時に用意します。ライブラリ（OpenCV、SciPy、pandas など、元のポケコンと同じもの）は約 500MB で、専用の環境に入ります。

## 開発

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.venv\Scripts\python.exe -m unittest discover -s tests
.venv\Scripts\python.exe tests\integration.py
.venv\Scripts\python.exe app.py --demo
```

ソースから実行するとき（`.git` があるとき）は、設定やログを従来どおり `SerialController` 以下に置きます。`--demo` は人工の映像を使い、ボタンを送りません。

## ライセンス

本体と追加コードは [MIT](LICENSE) です。橋渡し関数は独自ライセンス、ゲーム画像は本体の MIT の対象外です。ライブラリは同梱せず、インストール時に PyPI から取得するため、それぞれのライセンスに従います。[第三者ライセンスと変更内容](THIRD_PARTY_NOTICES.md)を参照してください。

フウ氏（@dragonite303）の橋渡し関数を、フォーク元と同じ内容で同梱しています。[同関数の利用条件](SerialController/Commands/PythonCommands/bridge_functions/License.txt)を確認してください。

本プロジェクトは、[KawaSwitch/Poke-Controller](https://github.com/KawaSwitch/Poke-Controller)、[Moi-poke/Poke-Controller-Modified](https://github.com/Moi-poke/Poke-Controller-Modified)、[futo030/Poke-Controller-Modified-Extension](https://github.com/futo030/Poke-Controller-Modified-Extension) に基づいています。
