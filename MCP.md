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
| `stop_script` | 停止を要求 |
| `pause_script` | 一時停止 |
| `resume_script` | 再開 |

操作前に`list_sessions`でID、`list_scripts`で正確な名前を確認します。開始・停止の成功応答は要求の受理を表し、処理完了とは限りません。`get_logs`等で状態を確認してください。実行中の別スクリプトへの切り替えは拒否します。

接続は127.0.0.1のみ、トークン認証付きです。MCPから任意のコードを書き込んだり、設定ファイルや通知トークンを読み取るツールはありません。既存スクリプトの実行には実機操作など、そのスクリプト本来の作用があります。

`--demo`は人工の映像とボタン送信なしのPortableDemoを使う検証モードです。
