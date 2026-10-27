# MCP接続

MCPは初期状態でOFFです。「メニュー → 設定 → MCP」またはMCPメニューからONにでき、プロファイルごとに保存します。コマンドラインの`PokeController.exe --mcp` / `--no-mcp`は、その起動だけ設定より優先します。

MCPクライアントのstdioサーバー設定に、展開先のexeの絶対パスを指定します。

```json
{
  "command": "C:\\Apps\\PokeController\\PokeControllerMCP.exe",
  "args": []
}
```

有効なアプリが一つの場合は自動選択します。複数起動時は`runtime/controller-PID.json`の対象ファイルを指定します。

```json
{
  "command": "C:\\Apps\\PokeController\\PokeControllerMCP.exe",
  "args": ["--endpoint", "C:\\Apps\\PokeController\\runtime\\controller-1234.json"]
}
```

このファイルにはローカル接続用のトークンが含まれます。公開・共有しないでください。アプリ終了時に削除されます。次の起動では新しいファイルが作られます。exeを手動でダブルクリックする必要はなく、MCPクライアントから起動します。

| ツール | 機能 |
|---|---|
| `list_sessions` | 起動中の対象と実行状態を取得 |
| `list_scripts` | 対象のPython/MCUスクリプト名を取得 |
| `get_logs` | 上下のログと実行状態を取得 |
| `get_capture` | 最新のカメラ画像をJPEGで取得 |
| `start_script` | 一覧から選んだスクリプトを開始 |
| `press_buttons` | ボタンを同時に指定秒数（0.08〜5秒）押して離す |
| `get_web_url` | ブラウザ操作画面のURLを取得 |
| `stop_script` | 停止を要求 |
| `pause_script` | 一時停止 |
| `resume_script` | 再開 |

操作前に`list_sessions`でID、`list_scripts`で正確な名前を確認します。開始・停止の成功応答は要求の受理を表し、処理完了とは限りません。`get_logs`等で状態を確認してください。実行中の別スクリプトへの切り替えは拒否します。

接続は127.0.0.1のみ、トークン認証付きです。MCPから任意のコードを書き込んだり、設定ファイルや通知トークンを読み取るツールはありません。既存スクリプトの実行には実機操作など、そのスクリプト本来の作用があります。

`press_buttons`のボタン名は`A` `B` `X` `Y` `L` `R` `ZL` `ZR` `PLUS` `MINUS` `HOME` `CAPTURE` `LCLICK` `RCLICK`、十字キーは`UP` `DOWN` `LEFT` `RIGHT`、スティックは`LS_UP`・`RS_LEFT`などです。スクリプト実行中とCOMポート未接続のときは拒否します。押した結果は`get_capture`で確認してください。

## ブラウザ操作画面

MCPをONにすると、同じ127.0.0.1の接続先でブラウザ用の画面も開けます。URLはアプリの「MCP → ブラウザで開く」、MCPの`get_web_url`、または`runtime/controller-PID.json`の`web_url`で確認できます。

画面でできること:

- 映像のライブ表示（MJPEG）
- コントローラーのボタン。押している間だけ入力します。「押しっぱなしモード」ではクリックごとに押す/離すを切り替えます。「全ボタンを離す」で全解除します。
- スクリプトの絞り込み・開始・停止・一時停止・再開
- 上下のログ表示

ClaudeデスクトップアプリのBrowserペインで開くと、Claudeが映像を見ながらボタンやスクリプトを操作できます。トークン付きURLを開くとCookieに移り、以後は`http://127.0.0.1:PORT/`で開けます。ほかのHost名からの接続と、他サイトからの操作要求は拒否します。

`--demo`は人工の映像とボタン送信なしのPortableDemoを使う検証モードです。
