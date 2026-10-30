# AI エージェント向けの手順（Claude Code・Codex）

Poke-Controller Modified Extension Plus（ポケコン）は、Nintendo Switch を PC から自動操作する Windows 用のアプリです。画面を持たない本体と、ブラウザーの操作画面、MCP で使います。

利用者が「このリポジトリを導入して」と頼んだら、「導入」の手順を最後まで進めます。

## 導入

### 1. 前提を確かめる

- Windows 10 / 11（64 ビット）であること。
- 管理者権限・Python・git は要りません。Python とライブラリは、インストーラーが uv でアプリ専用に用意します。
- すでに入っているかは `%LOCALAPPDATA%\Programs\PokeController\PokeController.exe` の有無で分かります。入っていれば、2 は省略してよい（入れ直すと最新版に更新される）。

### 2. アプリを入れる

PowerShell で実行します（ユーザーごとのインストール。UAC は出ません）。

```powershell
irm https://raw.githubusercontent.com/hinatamaxxx/Poke-Controller-Modified-Extension-Plus/master/get.ps1 | iex
```

- 最新のリリースを SHA-256 で照合してから入れます。初回は Python とライブラリ（約 600MB）を取得するので、数分かかります。
- 最後に「インストールが完了しました」の画面が出ます。利用者が閉じるまで待たず、次へ進んでよい。
- 失敗したら、表示された理由を利用者に伝えます。ネットワークの検査をするウイルス対策ソフトがあると失敗することがあります。

確認: スタートメニューに「Poke-Controller」があり、`%LOCALAPPDATA%\Programs\PokeController\PokeControllerMCP.exe` があること。

### 3. プラグインを入れる

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

プラグインは MCP の道具（映像・ボタン・スクリプトなど）とスキル（`open`、`operate`、`script`、`migrate`）を入れます。使えるようになるのは、新しいセッションからです。利用者に「新しいセッションで『ポケコンを開いて』と頼んでください」と伝えます。

### 4. 機器をつなぐ（利用者と一緒に）

- キャプチャーボード（カメラ）と、Switch につないだマイコン（COM ポート）は、操作画面の「機器接続」タブで選びます。どれを選ぶかは利用者に確かめます。
- 古いポケコンのスクリプトがある場合は、利用者がフォルダーの場所を言えば、プラグインの `migrate` の手順で移せます。

### アンインストール

「設定 → アプリ → インストールされているアプリ」の「Poke-Controller」から行います。プラグインは `claude plugin uninstall poke-controller@poke-controller` で外します。

## AI が守ること

- 実機につながっているとき、ボタンやスクリプトはゲームを実際に操作します。利用者が頼んだ操作だけを行います。A ボタンなど、ソフトの起動・終了につながる操作は特に注意します。
- 操作画面の URL（`web_url`）のトークンは、表示も共有もしません。会話に貼らず、ツールへ直接渡します。
- Discord の Webhook などの秘密の値を、会話やリポジトリに出しません。
- Windows の設定やセキュリティの設定は変えません。必要なら利用者に頼みます。

## 操作するとき

Poke-Controller は画面を持たず、ブラウザーの操作画面と MCP で使う。

1. MCP の `list_sessions` を呼ぶ（本体が動いていなければ自動で起動する）。セッションは Switch 1 台ずつ（画面のタブ）。利用者が「2号機で」などと言ったら `label` で選ぶ。MCP がないときは `PokeController.exe --background`（ソースなら `python app.py --background`）で起動し、`runtime/controller-*.json`（インストール版は `%LOCALAPPDATA%\PokeController\runtime`）の `web_url` を読む。
2. `get_web_url` の URL を、内蔵ブラウザー（Claude なら `mcp__Claude_Browser__preview_start` の `url`）で開く。利用者が「ポケコンを開いて」と頼んだときも同じ。
3. 操作は要素を aria-label（「A」「十字キー上」「左スティック」など）で探してから押す。座標で押すとスクロールでずれる。スティックは JavaScript で要素の中心を求めてからドラッグするか、MCP の `tilt_stick` を使う。
4. 押した結果は映像で確かめる。カメラや COM は「機器接続」タブ、通知や更新は「設定」。スクリプトがダイアログを出したら画面に表示されるので、入力して OK を押す。

利用者に伝える（画面の上部と「Claude」タブに表示される）:

- 作業を始めたら `set_status` で、目標（task）と「今ゲームの中でしていること」（doing）、必要なら進み具合（progress）を、ゲームの言葉で書く。例: task「色違いのヒトカゲを厳選」、doing「タマゴが孵るまで自転車で往復中」、progress「12/50」。状況が変わったら更新し、終わったら空にする。
- 区切りごとに `add_note` で、何をしたか・どうなったか・今どこまでか・次に何をするかを、あとから読む人向けに書く。一致度や座標、ボタンの手順は、利用者が判断に使うときだけ書く。
- 利用者のメモも `get_assist` で読み、作業の前提にする。

スクリプトを作るとき（利用者が、やりたいことを言葉で説明したとき）:

1. 目的と、終わりの条件（例: 色違いが出たら止める）を利用者に確かめる。
2. `start_recording` で録画を始め、`press_buttons` や `run_sequence` で 1 手ずつ実際に操作する。画面が変わるたびに `get_capture` で確かめ、待つべき画面は `save_template` で切り出して `find_template` で照合する（照合も録画に残る）。
3. 1 回分が通ったら `stop_recording`。`get_recording_overview` で流れを見直し、利用者のやりたいことと合っているか、画面の写真を添えて確認する。
4. `draft_script_from_recording` で下書きを作る。待ち時間には考えていた時間も含まれるので、画面の照合（`isContainTemplate` を待つループ）に置き換え、終わりの条件、回数の表示、見つけたときの通知（`self.discord_image` など）を足して、`write_script`（`Claude/` の下などに保存）。読み込みエラーが返ったら直す。
5. `start_script` で動かし、1 周を映像で確かめてから利用者に任せる。既存のスクリプト（`list_script_files` / `read_script`）の書き方に合わせる。

長時間の実行を見張るとき（利用者が頼んだときだけ）:

- `wait_for_incident` で待ち（`last_id` を次の `after` に渡す）、知らせが来たら `get_capture` で画面を確かめる。
- エラーの画面なら閉じる、ソフトが止まっていれば HOME からソフトを終了して起動し直す、など、ゲームを元の状態に戻してから `start_script` で再開する。戻せないときは止めたまま、何が起きたかを `add_note` に残す。Discord などへの通知は本体が送る。
- 映像が止まっても、本当に止まっているとは限らない（長い演出など）。画面を見て判断する。
- `kind` が `crash` の記録は、その Switch のプロセスが落ちたもの。本体が自動で起動し直す。何度も落ちて `crashed` になったら、原因（記録の `detail`）を利用者に伝え、頼まれたら `restart_switch` で起動し直す。

細かいタイミングが必要な処理は、ボタンを1つずつ押さずに既存の Python スクリプトで実行する。

## 開発するとき

README の「開発」と「フォーク元との関係」を読む。`SerialController/` はフォーク元と同じ中身に保ち、このアプリの変更は外側（`core.py`、`plus_*.py` など）に入れる。
