# Poke-Controller Modified Extension Plus

[Poke-Controller Modified Extension](https://github.com/futo030/Poke-Controller-Modified-Extension) 0.1.9 をもとにした Windows 用のフォークです。Tk の画面をなくし、ブラウザで操作する形にしました。Claude などの AI から MCP とブラウザで扱うことを主な用途にしています。有志が公開しているスクリプトは、元と同じ置き方・書き方で使えます。

## この公開について

動作・スクリプト互換性・不具合の修正を保証しません。利用による損害などについて責任は負いません。継続的な更新・サポートの予定もありません。了承のうえ、各ライブラリのライセンス条件の範囲で、自己責任で使ってください。必要な変更は、フォークして AI などでご自身の環境に合わせることをおすすめします。

## 構成

| | |
|---|---|
| トレイアプリ | `PokeController.exe`。通知領域に常駐し、本体を起動・監視する。操作画面を専用のウィンドウで開く |
| 本体 | 画面を持たない Python のプロセス。カメラ、シリアル、スクリプトの実行、操作画面、MCP の接続先を受け持つ |
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

ほかの引数: `-DesktopShortcut`（デスクトップにも置く）、`-RegisterClaudeDesktop`（Claude Desktop の MCP 設定に登録）。ソースから入れる場合は `python packaging\build.py` の後、`dist\PokeController\install.ps1` を実行します。

署名していないため、SmartScreen の警告が出たら「詳細情報」→「実行」で進めます。

## 使い方

- スタートメニューの「Poke-Controller」で操作画面のウィンドウを開きます。通知領域のアイコンのダブルクリックでも開けます。ウィンドウを閉じても本体は動き続けます。終了は通知領域のメニューの「アプリを終了する」か、操作画面の「設定 → アプリを終了」で行います。
- ログオン時の自動起動はしません。本体は起動している間、設定したカメラと COM ポートを使い続けるため、使うときだけ起動します（Claude からは MCP が自動で起動します）。
- Claude から使うときは、アプリを開いておく必要はありません。MCP が本体を裏で起動します。`get_web_url` の URL を Claude の内蔵ブラウザで開くと、映像を見ながら操作できます。

### MCP の登録

Claude Desktop: インストール時に `-RegisterClaudeDesktop` を付けるか、設定ファイルに次を追記します。Claude Code: `claude mcp add --scope user poke-controller -- "%LOCALAPPDATA%\Programs\PokeController\PokeControllerMCP.exe"`。

```json
{
  "mcpServers": {
    "poke-controller": {
      "command": "C:\\Users\\<ユーザー名>\\AppData\\Local\\Programs\\PokeController\\PokeControllerMCP.exe",
      "args": []
    }
  }
}
```

ツールの一覧は [MCP.md](MCP.md)、Claude 向けの手順は [CLAUDE.md](CLAUDE.md) にあります。

## ファイルの場所

| 種類 | 場所 |
|---|---|
| プログラム | `%LOCALAPPDATA%\Programs\PokeController` |
| スクリプト・テンプレート画像・キャプチャ（作業フォルダー） | `ドキュメント\PokeController`（中は元の `SerialController` と同じ構成） |
| 設定（プロファイル、通知トークン、自動更新） | `%APPDATA%\PokeController` |
| 専用の Python、ログ、接続ファイル | `%LOCALAPPDATA%\PokeController` |

有志のスクリプトは作業フォルダーの `Commands\PythonCommands`、画像は `Template` に置きます。同梱のサンプルは初回起動時に作業フォルダーへコピーし、利用者が変更したファイルは上書きしません。

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
