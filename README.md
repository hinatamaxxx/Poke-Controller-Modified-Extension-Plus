# Poke-Controller Modified Extension Plus

[Poke-Controller Modified Extension](https://github.com/futo030/Poke-Controller-Modified-Extension) 0.2.0 をもとにした Windows 用のフォークです。Tk の画面をなくし、ブラウザで操作する形にしました。Claude などの AI から MCP とブラウザで扱うことを主な用途にしています。有志が公開しているスクリプトは、元と同じ置き方・書き方で使えます。

フォーク元との違いの詳細は [docs/fork-history.md](docs/fork-history.md) にまとめています。

## この公開について

動作・スクリプト互換性・不具合の修正を保証しません。利用による損害などについて責任は負いません。継続的な更新・サポートの予定もありません。了承のうえ、各ライブラリのライセンス条件の範囲で、自己責任で使ってください。必要な変更は、フォークして AI などでご自身の環境に合わせることをおすすめします。

## 構成

| | |
|---|---|
| トレイアプリ | `PokeController.exe`。通知領域に常駐し、本体を起動・監視する。操作画面を専用のウィンドウで開く |
| 本体 | 画面を持たない Python のプロセス。操作画面と MCP の窓口になる司令塔と、Switch 1 台ごとの作業プロセス（カメラ、シリアル、スクリプトの実行）に分かれる |
| 操作画面 | 専用ウィンドウ（WebView2）またはブラウザ（`http://127.0.0.1`、トークン付き）。映像、コントローラー、スクリプト、接続、設定、ログ、スクリプトのダイアログ、スクリプトが自分で出す窓（tkinter・cv2.imshow など。スクリプトを書き換えずに操作画面の中に表示して操作でき、「デスクトップに出す」で元の窓に戻せる） |
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
- スクリプトタブの「実行リスト」で、スクリプトを並べて続けて動かせます（行ごとの回数と制限時間、間の待ち時間、エラーのときに中止するか次へ進むか、全体の繰り返し）。保存すると一覧に「名前 (実行リスト)」として並び、ふつうのスクリプトと同じように開始・停止できます。「予約」では、時刻での開始と、時刻または開始から何分後の停止を予約できます（フォーク元 0.2.0 の機能）。予約の時刻に PC がスリープしていると、予約どおりには動きません。
- PC がスリープなどで止まっていたら、戻ったときに実行中のスクリプトを止めます（その間も Switch は動いているため）。

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

PC につないだゲームコントローラー（Pro コントローラー、Xbox 系など、ブラウザーが標準の配置として認識するもの）で、そのまま Switch を操作できます。ボタンは配置どおり（下が B、右が A、左が Y、上が X）で、スティックはアナログのまま送ります。つながっている間は、上のバーに 🎮 が出ます。最初にボタンを 1 つ押すと認識されます。キーボードでの操作は最初からオンで、キーの割り当ては設定の「キー設定」で変えられます。「コントローラー」タブの画面のコントローラーの下で、色（フォーク元の Joy-Con の色と Switch 2）と「スティックは押し込みだけ」（スティックを倒さず、押している間だけ押し込み）を選べます。どちらも、スクリプトの実行中と COM ポートが未接続のときは効きません。

その下の欄から、Switch のキーボード（ニックネームや検索の文字入力の画面）に文字を打てます。Switch で文字入力の画面を開いてから、欄に書いて「送信」を押します。半角英数・記号・ひらがな・カタカナを打て、入力モードは自動で切り替わります。⌫ で 1 文字消す、Enter で改行、OK で確定（+）です。マイコンが USB キーボードとして打つので、Data Format がキーボードに対応している（Default / NX）ときだけ表示されます。

### メニューと設定

「機器接続」タブの「音声」で、キャプチャーボードの音を PC で鳴らせます（「音声」の横の「音声を鳴らす」をオン）。入力は、その Switch のカメラと同じ機器が最初に選ばれます。メーターで音が来ているかを確かめられます。

カメラタブの「目隠し」で、映像の一部（名前やフレンドコードなど）を塗りつぶして表示できます。「＋ 四角」か「＋ 楕円」を押して映像の上をドラッグします。カメラの画像そのものは変えないので、スクリプトの画像認識には影響しません。保存するスクリーンショットにも入れるかは選べます。

左上の「☰」に、設定・ヘルプ・アプリの終了があります。スクリーンショットと画面を Discord に送るボタンは、下のタブの右端にあります。設定（Ctrl+,）は画面に重なるウィンドウで開き、左の一覧で項目を選びます（Discord 連携、見張り、キー設定、ログ、フォルダー、更新、このアプリについて）。「フォルダー」では、作業フォルダーとスクリーンショット・録画の保存先を変えられます。設定は全 Switch 共通で、どのタブで変えても全台に反映されます。Windows と Discord の通知と、Discord の Webhook は「Discord 連携」で設定します。スクリプトの Discord 通知（`self.discord_text` など）も、この Webhook に届きます。その下の「スクリプトの送り先」で名前つきの送り先を足すと、スクリプトから `self.discord_text('…', name='名前')` のように選んで送れます（フォーク元 0.2.0 の機能。名前が見つからないときは、上の Webhook に届きます）。「Switch 本体でも録画する」をオンにすると、通知の直前にキャプチャーボタンを長押しして直前およそ 30 秒を Switch に保存し、「直前30秒の映像を添付する」をオンにすると、アプリが覚えている直前の映像を動画で送ります（色違いが出た瞬間を残せます）。カメラと COM ポートは Switch ごとです。

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
スクリプト\
  BDSP\
    画像\                ← BDSP のスクリプトが共通で使う画像
    固定シンボル\        ← 数が多いときは分類のフォルダーを挟んでよい
      エンテイ\
        エンテイ.py
        エンテイ.count   ← スクリプトが書く記録もここに
        画像\            ← このスクリプトだけが使う画像
  共通\
    画像\                ← ゲームをまたいで使う画像
```

一覧では自分のスクリプトが先に並び、アプリに付いてくるサンプルは「サンプル / …」として後ろにまとまります。

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

### フォーク元との関係

- `SerialController/` は、フォーク元（futo030/Poke-Controller-Modified-Extension）が配布しているものと同じ中身です。手を加えていません。例外は、ここで足したファイル（`Paths.py`、`WindowsDevices.py`、`UiDispatch.py`、サンプルの `PortableDemo.py`）だけです。
- このアプリで足した動きは、外側のファイルにまとめています。

| ファイル | 中身 |
|---|---|
| `plus_runtime.py` | スクリプトの画像を探す順、エラーでの停止を知らせる、Switch 本体の録画、Discord の後続の送信、日本語のパスの画像、シリアルの書き込みの時間切れ |
| `plus_settings.py` | 画面のない設定。このアプリの設定は `[PokeControllerPlus]` に置く |
| `plus_camera.py` | 機器のパスでカメラを選ぶ、ほかのアプリと取り合わない、デモの映像 |
| `plus_logger.py` | ログファイル |
| `plus_audio.py` | 音声の入力が Windows の標準の方式で開けないときに、同じ機器を別の方式（WDM-KS など）で開く。開くのが固まっても待ち続けない。「既定の再生デバイス」は Windows の今の既定を使い、変わったら知らせを受けて鳴らし直す |

- `plus_runtime.py` は、起動したときにフォーク元の関数を包んで差し込みます。
- 本体の `core.py` は、フォーク元の `services/app_core.py`（AppCore）の部品を少しずつ使う形に寄せています。今使っているもの: スクリプトの一覧と作成（`CommandService`）、シリアルの接続・ポートの並び・形式で決まるボーレート（`SerialService`）、実行リスト、予約、スリープの検知、キーボード入力、目隠し（`Mask`）、音声（`AudioService`）、Discord の送り先。
- カメラと画面の状態は、このアプリのものを使い続けます。カメラは機器のパスで選び、ほかのアプリと取り合わない（`plus_camera.py`）点がフォーク元の番号での選び方より優れており、画面の状態はブラウザーの画面に合わせた形だからです。
- フォーク元の起動用の bat、`bootstrap/`、`pyproject.toml` などは、取り込みを楽にするためにリポジトリには残しています。インストールには含めません。

フォーク元の更新を取り込む手順:

```powershell
git fetch upstream
git merge upstream/master          # SerialController/ はフォーク元の内容をそのまま採る
.venv\Scripts\python.exe -m unittest discover -s tests    # test_portable が、SerialController がフォーク元のままかも確かめる
```

## ライセンス

本体と追加コードは [MIT](LICENSE) です。橋渡し関数は独自ライセンス、ゲーム画像は本体の MIT の対象外です。ライブラリは同梱せず、インストール時に PyPI から取得するため、それぞれのライセンスに従います。[第三者ライセンスと変更内容](THIRD_PARTY_NOTICES.md)を参照してください。

フウ氏（@dragonite303）の橋渡し関数を、フォーク元と同じ内容で同梱しています。[同関数の利用条件](SerialController/Commands/PythonCommands/bridge_functions/License.txt)を確認してください。

本プロジェクトは、[KawaSwitch/Poke-Controller](https://github.com/KawaSwitch/Poke-Controller)、[Moi-poke/Poke-Controller-Modified](https://github.com/Moi-poke/Poke-Controller-Modified)、[futo030/Poke-Controller-Modified-Extension](https://github.com/futo030/Poke-Controller-Modified-Extension) に基づいています。
