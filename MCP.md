# MCP

Claude Code と Codex では、プラグインを入れると自動でつながります（[README](README.md#claude-codecodex-のプラグイン)）。ほかの MCP クライアントでは、`PokeControllerMCP.exe` を stdio サーバーとして登録します。

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

本体が動いていなければ、最初の呼び出しで画面なしのまま起動します。セッションは Switch 1 台ずつ（操作画面のタブ）で、`list_sessions` に並びます。複数の本体が動いているときは、すべて見つけて並べます。1つに限定したいときだけ `--endpoint <runtime\controller-PID.json>`、自動起動を止めたいときは `--no-autostart` を付けます。

| ツール | 機能 |
|---|---|
| `list_sessions` | Switch（タブ）ごとの ID・名前・状態（`switch_state`: ready / starting / restarting / crashed）。必要なら本体を起動 |
| `add_switch` / `close_switch` / `rename_switch` / `restart_switch` | Switch を増やす／閉じる（設定は残る。最初の台は閉じられない）／名前を変える／プロセスを起動し直す |
| `list_scripts` | Python / MCU スクリプトの名前 |
| `start_script` / `stop_script` / `pause_script` / `resume_script` | スクリプトの開始・停止・一時停止・再開 |
| `get_logs` | 上下のログと状態 |
| `get_capture` | 最新の映像（JPEG） |
| `press_buttons` | ボタンを同時に指定秒数（0.08〜5秒）押して離す |
| `tilt_stick` | アナログスティックを x/y（0〜255、128 が中央）に倒す |
| `get_web_url` | ブラウザの操作画面の URL |
| `run_sequence` / `cancel_sequence` | ボタン操作の手順（押す時間・待ち時間つき、最大200手順）を本体側で続けて実行／中止 |
| `list_templates` / `find_template` | Template フォルダーの画像の一覧／今の映像に映っているか（一致度と位置。映像に枠を表示） |
| `set_status` | 画面の上部に、目標・ゲーム内で今していること・進み具合を表示 |
| `add_note` / `get_assist` | 利用者向けのメモを残す／メモ・状況・Claude の操作の記録・連続操作の進み具合を読む |
| `get_dialogs` / `answer_dialog` | スクリプトが待っているダイアログを読む／答える |
| `list_devices` / `configure_devices` | キャプチャ機器と COM ポートの一覧／選択・接続 |
| `start_recording` / `stop_recording` / `list_recordings` | 映像（640×360、最大10fps・600秒）と、その間のボタン入力・画像の確認を録画 |
| `get_recording_overview` / `get_recording_frame` / `get_recording_inputs` | 録画の一覧画像（時刻つき）と入力の流れ／1コマ／入力の全記録 |
| `draft_script_from_recording` | 録画中の操作から、ループするスクリプトの下書きを作る（保存はしない） |
| `list_script_files` / `read_script` / `write_script` | 作業フォルダーの `スクリプト`（1 本ごとのフォルダー）と `Commands/PythonCommands` のスクリプトを一覧・読む・保存して再読み込み（上書き前に `Backups/scripts` へ控え） |
| `save_template` | 今の映像の一部を PNG で保存（`スクリプト/<フォルダー>/画像/…` でスクリプトの画像に、名前だけなら `Template` に） |
| `get_incidents` / `wait_for_incident` / `set_watch` | 見張りの記録（エラー、映像の停止、機器の切断、終了、Switch のプロセスの停止）を読む／次の記録を待つ（最大900秒）／見張りの設定。記録の `clip` は直前 30 秒の映像で、`get_recording_overview` で見られる |

`press_buttons` の名前: `A` `B` `X` `Y` `L` `R` `ZL` `ZR` `PLUS` `MINUS` `HOME` `CAPTURE` `LCLICK` `RCLICK`、十字キー `UP` `DOWN` `LEFT` `RIGHT`、スティック `LS_UP`・`RS_LEFT` など。スクリプト実行中と COM 未接続のときは手動入力を受け付けません。

開始・停止の成功は「受け付けた」という意味です。結果は `get_logs` と `get_capture` で確かめます。通知の設定などは操作画面で行います。Claude が行った操作は、操作画面の「Claude」タブに記録されます。

接続先は 127.0.0.1 のみで、トークンで認証します。`runtime\controller-PID.json` にはトークンが入るので共有しないでください。本体の終了時に削除し、強制終了などで残ったものは次の起動時に削除します。

`app.py --demo` は人工の映像を使い、ボタンを送らない確認用のモードです。
