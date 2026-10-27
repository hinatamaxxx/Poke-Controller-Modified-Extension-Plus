---
name: open
description: Poke-Controller（ポケコン）の操作画面を、Claude デスクトップアプリの内蔵ブラウザー（Codex なら Codex のブラウザー）で開く。本体が動いていなければ起動する。「ポケコンを開いて」「ポケコンの画面を見せて」「Switch の画面を出して」などで使う。
---

# ポケコンの操作画面を開く

操作画面の URL には接続用のトークンが入る。**URL を会話に書かず、ブラウザーのツールへ直接渡す**。

1. MCP の `list_sessions` を呼ぶ（本体が止まっていれば画面なしで起動する）。利用者が「2号機」などと言ったら `label` で選び、なければ最初のセッションを使う。
2. そのセッションの `id` で `get_web_url` を呼ぶ。
3. 返った `url` を開く。
   - Claude デスクトップアプリ: `mcp__Claude_Browser__preview_start` の `url` に渡す（読み込まれていなければ ToolSearch で先に読み込む）。
   - Codex: Codex のブラウザーのツールで開く。
   - どちらもないとき: 既定のブラウザーで開く（PowerShell の `Start-Process` に URL を渡す。出力に URL を出さない）。
4. 開いたことを一言で伝える。Claude の内蔵ブラウザーの欄が隠れていれば、Ctrl+Shift+B（Mac は Cmd+Shift+B）で出せると伝える。

MCP が使えないとき（このプラグインの MCP サーバーが起動しない）は、Poke-Controller が入っているかを確かめる。`%LOCALAPPDATA%\Programs\PokeController\PokeControllerMCP.exe` がなければ、利用者にインストールを案内する（README の「インストール」）。

## 開いたあと

- 画面が狭いと「映像＋下のタブ」の形になる（Claude とログも下のタブ）。上のタブが Switch 1 台ずつ。
- 実機につながっていると、画面のボタンは本当にゲームを操作する。操作するときは `operate` スキルの決まりに従う。
- 画面のテストのために、キー入力（矢印・Enter など）を窓やページに送らない。「キーボードで操作」がオンだと、そのまま Switch に届く。
- 確認のポップアップ（`confirm` / `alert` / `prompt`）は内蔵ブラウザーでは出ない。操作画面はこれらを使わない。
