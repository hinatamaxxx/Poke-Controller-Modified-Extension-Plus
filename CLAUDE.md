# Claude から操作するとき

Poke-Controller は画面を持たず、ブラウザの操作画面と MCP で使う。

1. MCP の `list_sessions` を呼ぶ（本体が動いていなければ自動で起動する）。セッションは Switch 1 台ずつ（画面のタブ）。利用者が「2号機で」などと言ったら `label` で選ぶ。MCP がないときは `PokeController.exe --background`（ソースなら `python app.py --background`）で起動し、`runtime/controller-*.json`（インストール版は `%LOCALAPPDATA%\PokeController\runtime`）の `web_url` を読む。
2. `get_web_url` の URL を `mcp__Claude_Browser__preview_start` に `url` として渡して開く。
3. 操作は要素を aria-label（「A」「十字キー上」「左スティック」など）で `find` してから押す。座標で押すとスクロールでずれる。スティックは JavaScript で要素の中心を求めてからドラッグするか、MCP の `tilt_stick` を使う。
4. 押した結果は映像で確かめる。カメラや COM は「接続」タブ、通知や更新は「設定」タブ。スクリプトがダイアログを出したら画面に表示されるので、入力して OK を押す。

利用者に伝える（画面の上部と「Claude」タブに表示される）:

- 作業を始めたら `set_status` で、目標（task）と「今ゲームの中でしていること」（doing）、必要なら進み具合（progress）を、ゲームの言葉で書く。例: task「色違いのヒトカゲを厳選」、doing「タマゴが孵るまで自転車で往復中」、progress「12/50」。状況が変わったら更新し、終わったら空にする。
- 区切りごとに `add_note` で、何をしたか・どうなったか・今どこまでか・次に何をするかを、あとから読む人向けに書く。例「ヒトカゲのタマゴを50個孵化。色違いは出ず。ボックス3まで埋まったので、次はボックス4から。」一致度や座標、ボタンの手順は、利用者が判断に使うときだけ書く。
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
- 記録の `clip` は直前 30 秒の録画。`get_recording_overview` で何が起きたかを見てから直す。
- `kind` が `crash` の記録は、その Switch のプロセスが落ちたもの。本体が自動で起動し直す（`switch_state` が ready に戻るのを待つ）。何度も落ちて `crashed` になったら、原因（記録の `detail`）を利用者に伝え、頼まれたら `restart_switch` で起動し直す。

注意:

- `web_url` のトークンは表示・共有しない。会話に貼らず、ツールへ直接渡す。
- 実機につながっている場合、ボタンやスクリプトはゲームを実際に操作する。ユーザーが頼んだ操作だけを行う。A ボタンなど、ソフトの起動・終了につながる操作は特に注意する。
- 細かいタイミングが必要な処理は、ボタンを1つずつ押さずに既存の Python スクリプトで実行する。
