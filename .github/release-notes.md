## Poke-Controller Modified Extension Plus

[Poke-Controller Modified Extension](https://github.com/futo030/Poke-Controller-Modified-Extension) をもとにした Windows 用のフォークです。ブラウザの操作画面と、Claude などの AI から使う MCP で、Nintendo Switch を自動操作します。

### 入れ方

PowerShell で次の1行を実行します（管理者権限・Python は不要）。

```powershell
irm https://raw.githubusercontent.com/hinatamaxxx/Poke-Controller-Modified-Extension-Plus/master/get.ps1 | iex
```

AI（Claude Code・Codex）に「https://github.com/hinatamaxxx/Poke-Controller-Modified-Extension-Plus を導入して。」と頼むこともできます。

### 添付ファイル

- `PokeController-win64.zip`: アプリ本体（インストーラーと自動更新が使います）
- `PokeController-win64.zip.sha256`: 照合用の SHA-256

変更点は [changelog.txt](https://github.com/hinatamaxxx/Poke-Controller-Modified-Extension-Plus/blob/master/changelog.txt) を見てください。

公式のものではありません。動作の保証やサポートはありません。
