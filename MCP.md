# MCP

`PokeControllerMCP.exe` を MCP クライアントの stdio サーバーとして登録します（[README](README.md#mcp-の登録)）。本体が動いていなければ、最初の呼び出しで画面なしのまま起動します。複数の本体が動いているときは、すべて見つけて `list_sessions` に並べます。1つに限定したいときだけ `--endpoint <runtime\controller-PID.json>`、自動起動を止めたいときは `--no-autostart` を付けます。

| ツール | 機能 |
|---|---|
| `list_sessions` | 起動中の本体と状態（必要なら本体を起動） |
| `list_scripts` | Python / MCU スクリプトの名前 |
| `start_script` / `stop_script` / `pause_script` / `resume_script` | スクリプトの開始・停止・一時停止・再開 |
| `get_logs` | 上下のログと状態 |
| `get_capture` | 最新の映像（JPEG） |
| `press_buttons` | ボタンを同時に指定秒数（0.08〜5秒）押して離す |
| `tilt_stick` | アナログスティックを x/y（0〜255、128 が中央）に倒す |
| `get_web_url` | ブラウザの操作画面の URL |

`press_buttons` の名前: `A` `B` `X` `Y` `L` `R` `ZL` `ZR` `PLUS` `MINUS` `HOME` `CAPTURE` `LCLICK` `RCLICK`、十字キー `UP` `DOWN` `LEFT` `RIGHT`、スティック `LS_UP`・`RS_LEFT` など。スクリプト実行中と COM 未接続のときは手動入力を受け付けません。

開始・停止の成功は「受け付けた」という意味です。結果は `get_logs` と `get_capture` で確かめます。カメラ・COM ポートの選択、通知の設定、スクリプトのダイアログへの回答は操作画面で行います。

接続先は 127.0.0.1 のみで、トークンで認証します。`runtime\controller-PID.json` にはトークンが入るので共有しないでください。本体の終了時に削除し、強制終了などで残ったものは次の起動時に削除します。

`app.py --demo` は人工の映像を使い、ボタンを送らない確認用のモードです。
