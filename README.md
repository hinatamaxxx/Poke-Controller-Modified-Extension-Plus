# Poke-Controller Modified Extension Plus

[Poke-Controller Modified Extension](https://github.com/futo030/Poke-Controller-Modified-Extension) 0.1.9をベースにした、Windows用のフォークです。元のTk画面とPythonスクリプト実行方式を維持し、Pythonのインストールが不要な配布とMCP対応を追加しています。

## この公開について

ポケコンについて詳しいわけではありませんが、個人的に使っていて気になった部分を、Codexを使って修正しました。「とりあえず動けばよい」という方向けに、Pythonやライブラリを自分で導入しなくても起動できるアルファ版を置いています。

動作・スクリプト互換性・不具合の修正を保証しません。利用による損害などについて責任は負いません。また、今後継続的に更新・サポートする予定はありません。これらを了承のうえ、各同梱物のライセンス条件の範囲で、自己責任で利用してください。

必要な機能や不具合があれば、このリポジトリをフォークし、CodexやClaudeなどを使って、ご自身の環境に合わせて修正することをおすすめします。AIによる変更も、実際に使う前にご自身で確認してください。

## フォーク元との差分

比較対象は[futo030/Poke-Controller-Modified-Extension 0.1.9](https://github.com/futo030/Poke-Controller-Modified-Extension/tree/3274e77)です。

| 項目 | このフォークでの変更 |
|---|---|
| 配布 | Pythonと依存ライブラリを同梱したWindows用portable ZIPを提供。解凍してexeから起動できます。 |
| MCP | スクリプトの開始・停止・一時停止・再開、映像・ログ取得に対応。初期状態はOFFです。 |
| 設定保存 | 書き込み途中の破損を防ぐ保存方式、前回分のバックアップ、破損時の復元を追加。通常設定とキー設定が互いの変更を上書きする問題を修正。 |
| 映像表示 | 設定タブとコントローラーの見切れを修正。大きな表示サイズでもモニター内に収め、解像度変更時のウィンドウ・操作欄・ログ欄の配置を固定。確認ダイアログを削除。 |
| 画像認識 | 画像不足・破損・範囲やサイズの不一致を具体的に表示。日本語の画像パスに対応。 |
| ライブラリ更新 | 一括選択・個別選択、確認結果と更新状況の表示、更新不要の判定、配布時の状態への復帰に対応。更新は再起動後に反映。 |
| 停止・入力 | スクリプト停止時やUSB切断時の入力解除、キーボード入力処理、右スティックの変化判定を改善。 |
| キャプチャ・ログ | 映像取得を別スレッドで処理し、画面ログの保持件数に上限を設定。 |
| 接続・起動 | 指定COMポート名でのボーレート適用、カメラ無効時の処理、スクリプトの読み込み失敗時の処理を修正。通知設定を読むだけでは外部通信しないよう変更。 |
| 依存部品 | カメラ列挙をDirectShowLib・pythonnet・windows-capture-device-listからWindows標準のCOM APIへ変更。機器名と映像の対応を機器IDで管理。ログ装飾を標準loggingへ、フォルダー画像ボタンを文字ボタンへ変更。 |

元の画面とPythonスクリプト方式をベースにしています。元アプリの機能・操作方法は[フォーク元のREADME](README.upstream.md)を参照してください。

## 起動

1. [Releases](https://github.com/hinatamaxxx/Poke-Controller-Modified-Extension-Plus/releases)から`PokeController-portable-win64.zip`をダウンロードします。
2. ZIP全体を書き込み可能なフォルダーへ解凍します。Python・追加ライブラリの手動導入は不要です。
3. 解凍したフォルダー内の`PokeController.exe`を起動します。exeだけを移動しないでください。
4. カメラとCOMポートを選んで接続します。初回はどちらも無効です。

Windows 10/11 x64向けです。Python、.NET SDK、Gitのインストールは不要です。Windows付属の.NET Framework 4を使用します。

フォルダー一式で動作するportable版です。

カメラ名を選ぶと接続が切り替わります。同名の機器は名前の後ろの識別表示で区別できます。カメラ一覧を開くと接続機器を再確認します。選択した機器が外れている場合は「未接続」と表示します。番号しか保存していない旧設定を使う場合は、初回にカメラ名を選び直してください。

別の設定で同時起動する場合は`PokeController.exe --profile 名前`を使用します。同じプロファイルの二重起動は防止しています。元のメニューからプロファイル別の起動BATも作れます。

設定は`SerialController/profiles`、追加スクリプトは`SerialController/Commands/PythonCommands`、画像認識用の画像は`SerialController/Template`、キャプチャは`SerialController/Captures`に保存します。更新時は新しいZIPを別フォルダーへ展開し、自分の設定・スクリプト・画像を移してください。

## MCP

MCPは初期状態でOFFです。「メニュー → 設定 → MCP」またはMCPメニューからONにし、MCPクライアントに`PokeControllerMCP.exe`を登録してください。[接続方法とツール一覧](MCP.md)。MCPも同梱Pythonで動作します。設定はプロファイルごとに保存されます。`--mcp` / `--no-mcp`はその起動だけの指定です。

## 設定と更新

Show Sizeは映像の表示サイズです。起動時にモニターへ収まる表示領域を確保し、解像度を変更してもウィンドウ・操作欄・ログ欄の位置とサイズを維持します。大きな映像は縦横比を保って領域内へ縮小し、小さな映像では余白が残ります。確認ダイアログは表示せず、その場で映像を更新します。保存される指定値とキャプチャ・画像認識の解像度は変更しません。

「メニュー → 設定」でMCP、アプリの更新、同梱ライブラリを確認できます。「ヘルプ → アップデート確認」からも更新画面を開けます。

- アプリの更新は「更新を確認」から確認できます。公開リリースの確認にはGitHubトークンは不要です。
- 同梱ライブラリ画面は初期状態で全項目にチェックが入っています。「チェックした部品を更新」で一括更新でき、チェックを外すと個別更新になります。外した部品のバージョンは維持します。依存関係が両立しなければ適用せずエラーを表示します。FFmpegはOpenCV付属なので`opencv-python`と一緒に更新します。Python本体の更新機能はありません。
- ライブラリは別の実行環境へコピーして更新・基本検証し、次回起動から使用します。全ウィンドウとMCPを終了して同じexeを起動し直してください。最新版での全スクリプトの動作は保証できません。「配布時のライブラリに戻す」で元に戻せます。起動できないときはexeに`--reset-libraries`を付けて実行し、その後通常起動してください。更新には通信と追加ディスク容量が必要です。失敗の詳細は`.runtime-updates`内の`update.log`に残ります。
- 新しい配布版がある場合は「配布ページを開く」からダウンロードしてください。検証版を更新確認の対象にする設定もあります。
- 更新は手動です。全ウィンドウを終了して新しいZIPを別フォルダーへ展開し、`SerialController/profiles`、`Commands/PythonCommands`内の自分で追加・変更したスクリプト、`Template`内の独自画像をコピーしてください。必要なら`Captures`と`Controller_Log`もコピーします。いずれも`SerialController`以下です。標準スクリプト全体を旧版で上書きすると修正が戻るため、自分の変更分を移してください。
- 同じフォルダーへの上書き更新も可能です。全ウィンドウを終了し、設定と独自ファイルのバックアップを取ってからZIPの内容を上書きしてください。旧版で不要になったファイルは残るため、別フォルダーへの展開を推奨します。exeだけの置換では更新できません。
- アプリのフォルダーを移動した場合は、MCPクライアントの登録パスも変更してください。

通常の設定とMCPなどの追加設定は、一時ファイルへの書き込み完了後に置き換えます。変更前の内容を同じ場所の`.bak`へ保存し、同じ内容の再保存ではバックアップを更新しません。読み込み時に破損が見つかり正常なバックアップがあれば、破損ファイルを`.corrupt-*`へ残して復元します。復元できない場合はファイルを上書きせずエラーを表示します。キー設定と通常設定は保存前に最新内容を読み込み、互いの変更を保ちます。

## 動作上の制約

実機への操作送信と全スクリプトの動作は未検証です。スクリプトが対象とするポケコンの種類・バージョン、追加ライブラリ、テンプレート画像によっては調整が必要です。画像認識用の画像は、キャプチャ解像度とゲームの表示設定に合わせて用意してください。

独自スクリプトの無限ループやタイムアウトのない外部処理では、停止・終了を待ち続ける場合があります。Mac/Linuxには対応していません。

## 開発・ビルド

開発時のみPython 3.12 x64が必要です。

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe tests\integration.py
.venv\Scripts\python.exe packaging\build.py
.venv\Scripts\python.exe tests\integration.py --package C:\絶対パス\dist\PokeController
```

ビルドはGitで管理されているファイルのみを収集します。変更をコミットしてから実行してください。出力先が既にある場合は`--output-name PokeController-alpha8`などで新しいフォルダー名を指定できます。起動中のアプリのフォルダーは移動しないでください。ZIPは`release`に出力します。

## ライセンス

本体と今回の追加コードは[MIT](LICENSE)ですが、橋渡し関数は独自ライセンス、pygame・pynput・FFmpeg等はそれぞれのライセンスです。ゲーム画像も本体のMITの対象ではありません。配布物全体がMITではありません。[第三者ライセンスと変更内容](THIRD_PARTY_NOTICES.md)を参照してください。依存元のライセンスと、一部ライブラリの対応するソースアーカイブを同梱します。

フウ氏（@dragonite303）の橋渡し関数を、フォーク元と同じ内容で引用・同梱しています。[同関数の利用条件](SerialController/Commands/PythonCommands/bridge_functions/License.txt)を確認してください。

本プロジェクトは、[KawaSwitch/Poke-Controller](https://github.com/KawaSwitch/Poke-Controller)、[Moi-poke/Poke-Controller-Modified](https://github.com/Moi-poke/Poke-Controller-Modified)、[futo030/Poke-Controller-Modified-Extension](https://github.com/futo030/Poke-Controller-Modified-Extension)に基づいています。

