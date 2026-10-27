# Claude から操作するとき

Poke-Controller は画面を持たず、ブラウザの操作画面と MCP で使う。

1. MCP の `list_sessions` を呼ぶ（本体が動いていなければ自動で起動する）。MCP がないときは `PokeController.exe --background`（ソースなら `python app.py --background`）で起動し、`runtime/controller-*.json`（インストール版は `%LOCALAPPDATA%\PokeController\runtime`）の `web_url` を読む。
2. `get_web_url` の URL を `mcp__Claude_Browser__preview_start` に `url` として渡して開く。
3. 操作は要素を aria-label（「A」「十字キー上」「左スティック」など）で `find` してから押す。座標で押すとスクロールでずれる。スティックは JavaScript で要素の中心を求めてからドラッグするか、MCP の `tilt_stick` を使う。
4. 押した結果は映像で確かめる。カメラや COM は「接続」タブ、通知や更新は「設定」タブ。スクリプトがダイアログを出したら画面に表示されるので、入力して OK を押す。

注意:

- `web_url` のトークンは表示・共有しない。会話に貼らず、ツールへ直接渡す。
- 実機につながっている場合、ボタンやスクリプトはゲームを実際に操作する。ユーザーが頼んだ操作だけを行う。A ボタンなど、ソフトの起動・終了につながる操作は特に注意する。
- 細かいタイミングが必要な処理は、ボタンを1つずつ押さずに既存の Python スクリプトで実行する。
