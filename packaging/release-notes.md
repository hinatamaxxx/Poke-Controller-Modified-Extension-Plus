# Poke-Controller Modified Extension Plus 0.2.0-alpha.8

ポケコンについて詳しいわけではありませんが、個人的に気になったところをCodexで修正したものです。「とりあえず動けばよい」という方に向けて、Pythonやライブラリを自分で導入しなくても起動できる版を公開します。

動作・互換性・不具合の修正を保証しません。利用による損害などについて責任は負いません。今後継続的に更新・サポートする予定もありません。各同梱物のライセンス条件を守り、自己責任で利用してください。

必要な機能やバグ修正があれば、フォークしてCodexやClaudeなどで自分の環境に合わせて直すことをおすすめします。変更後の動作もご自身で確認してください。

## ダウンロード

- **PokeController-portable-win64.zip**：手動展開するportable版。全体を展開して`PokeController.exe`を起動します。ZIP内の小さなexeだけでは動きません。
- `.sha256`：各配布ファイルのSHA-256。

Windows 10/11 x64向けです。Python・.NET SDK・Gitの事前インストールは不要です。Windows付属の.NET Frameworkと同梱Pythonを使用します。初回は書き込み可能な場所に置いてください。未署名のアルファ版です。

## フォーク元と引き継いだ機能

[futo030/Poke-Controller-Modified-Extension](https://github.com/futo030/Poke-Controller-Modified-Extension) 0.1.9がベースです。その元は[KawaSwitch/Poke-Controller](https://github.com/KawaSwitch/Poke-Controller)、[Moi-poke/Poke-Controller-Modified](https://github.com/Moi-poke/Poke-Controller-Modified)です。

元の画面とスクリプト方式、2つのログ欄、プロファイル、スクリプトの一時停止・絞り込み・ショートカット、ソフトウェアコントローラー、画像認識の範囲表示、ゲームパッド入力、3DS向け通信形式、MQTT・Socket通信などを引き継いでいます。詳細はリポジトリのREADME.upstream.mdに残しています。

## 今回の主な変更

- Pythonと依存ライブラリを同梱したportable ZIP。解凍してexeを起動するだけで使えます。
- MCPを追加。初期状態はOFFで、プロファイルごとに保存します。MCPクライアントには展開先のPokeControllerMCP.exeを登録します。
- 設定保存の一時ファイル・前回バックアップ・破損時の復元を追加。キー設定の上書き問題も修正。
- 1080p指定時の画面外へのはみ出しと、低解像度への変更時のレイアウト変化を修正。解像度変更の確認ダイアログと途中の再配置を削除。
- 画像不足・破損・範囲・サイズ不一致を具体的に表示。日本語の画像パスに対応。
- ライブラリは初期状態で全選択。一括更新でき、チェックを外して個別更新も可能。別環境で更新し、全ウィンドウとMCPの再起動後に反映。配布時への復帰も可能。
- アプリ本体は更新確認と配布ページへの案内を残し、手動更新・設定や独自スクリプトのコピー方式に整理。
- 停止処理と入力解除、USB切断時の停止、非同期キャプチャ、画面ログの件数制限、ボーレート適用、右スティック判定などを改善。
- DirectShowLibとpythonnetを除外し、Windows COMによるカメラ列挙へ置換。pygame・pynput・OpenCVのFFmpegは維持。

実機への操作送信と全スクリプトの互換性は未検証です。旧版独自の関数や追加ライブラリを使うスクリプトは調整が必要な場合があります。Mac/Linux対応は行っていません。

## ライセンス

本体・追加コードはMITですが、配布物全体がMITという意味ではありません。フウ氏（@dragonite303）の橋渡し関数を無変更で引用・同梱しています。同関数は個人・非商用などの独自条件です。ゲーム画像、pygame・pynput・FFmpegなどもそれぞれの権利・ライセンスに従ってください。THIRD_PARTY_NOTICES.mdと同梱のlicensesを参照してください。
