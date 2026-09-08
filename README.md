# Poke-Controller Modified Extension Plus

[Poke-Controller Modified Extension](https://github.com/futo030/Poke-Controller-Modified-Extension) 0.1.9をベースにした、Windows用のフォークです。元のTk画面とPythonスクリプト実行方式を維持し、Pythonのインストールが不要な配布とMCP対応を追加しています。

## この公開について

ポケコンについて詳しいわけではありませんが、個人的に使っていて気になった部分を、Codexを使って修正しました。「とりあえず動けばよい」という方向けに、Pythonやライブラリを自分で導入しなくても起動できるアルファ版を置いています。

動作・スクリプト互換性・不具合の修正を保証しません。利用による損害などについて責任は負いません。また、今後継続的に更新・サポートする予定はありません。これらを了承のうえ、各同梱物のライセンス条件の範囲で、自己責任で利用してください。

必要な機能や不具合があれば、このリポジトリをフォークし、CodexやClaudeなどを使って、ご自身の環境に合わせて修正することをおすすめします。AIによる変更も、実際に使う前にご自身で確認してください。

## フォーク元から引き継いだ機能

元のアプリは[KawaSwitch氏のPoke-Controller](https://github.com/KawaSwitch/Poke-Controller)、[Moi-poke氏のModified](https://github.com/Moi-poke/Poke-Controller-Modified)を経て、[futo030氏のModified Extension](https://github.com/futo030/Poke-Controller-Modified-Extension)へ拡張されています。

Extensionの2つのログ欄、プロファイル、スクリプトの絞り込み・ショートカット・一時停止、ソフトウェアコントローラー、画像認識の範囲表示、ゲームパッド入力、3DS向け通信形式、MQTT・Socket通信などを引き継いでいます。これらを今回新しく作ったものとして扱っていません。詳細と元の改善点は[元版README](README.upstream.md)に残しています。

## 起動

1. [Releases](https://github.com/hinatamaxxx/Poke-Controller-Modified-Extension-Plus/releases)から`PokeController-portable-win64.zip`をダウンロードします。
2. ZIP全体を書き込み可能なフォルダーへ解凍します。Python・追加ライブラリの手動導入は不要です。
3. 解凍したフォルダー内の`PokeController.exe`を起動します。exeだけを移動しないでください。
4. カメラとCOMポートを選んで接続します。初回はどちらも無効です。

Windows 10/11 x64向けです。Python、.NET SDK、Gitのインストールは不要です。小さな起動用exeはWindows付属の.NET Framework 4を使用し、Python本体とライブラリは`runtime-python`に同梱しています。

インストーラーや自己展開exeは使用しません。フォルダー一式で動作するportable版です。MCPには同じフォルダー内の`PokeControllerMCP.exe`を登録します。

別の設定で同時起動する場合は`PokeController.exe --profile 名前`を使用します。同じプロファイルの二重起動は防止しています。元のメニューからプロファイル別の起動BATも作れます。

設定は`SerialController/profiles`、追加スクリプトは`SerialController/Commands/PythonCommands`、画像認識用の画像は`SerialController/Template`、キャプチャは`SerialController/Captures`に保存します。更新時は新しいZIPを別フォルダーへ展開し、自分の設定・スクリプト・画像を移してください。

## MCP

MCPは初期状態でOFFです。「メニュー → 設定 → MCP」またはMCPメニューからONにし、MCPクライアントに`PokeControllerMCP.exe`を登録してください。[接続方法とツール一覧](MCP.md)。MCPも同梱Pythonで動作します。設定はプロファイルごとに保存されます。`--mcp` / `--no-mcp`はその起動だけの指定です。

## 設定と更新

Show Sizeは映像の表示サイズです。起動時にモニターへ収まる表示領域を確保し、解像度を変更してもウィンドウ・操作欄・ログ欄の位置とサイズを維持します。大きな映像は縦横比を保って領域内へ縮小し、小さな映像では余白が残ります。確認ダイアログは表示せず、その場で映像を更新します。保存される指定値とキャプチャ・画像認識の解像度は変更しません。

「メニュー → 設定」でMCP、アプリの更新、同梱ライブラリを確認できます。「ヘルプ → アップデート確認」からも更新画面を開けます。

- 更新確認は手動です。非公開リポジトリでは、そのリポジトリのContents読み取り権限を持つGitHubトークンを入力してください。トークンはファイルに保存しません。
- 同梱ライブラリ画面は初期状態で全項目にチェックが入っています。「チェックした部品を更新」で一括更新でき、チェックを外すと個別更新になります。外した部品のバージョンは維持します。依存関係が両立しなければ適用せずエラーを表示します。FFmpegはOpenCV付属なので`opencv-python`と一緒に更新します。Python本体の更新機能はありません。
- ライブラリは別の実行環境へコピーして更新・基本検証し、次回起動から使用します。全ウィンドウとMCPを終了して同じexeを起動し直してください。最新版での全スクリプトの動作は保証できません。「配布時のライブラリに戻す」で元に戻せます。起動できないときはexeに`--reset-libraries`を付けて実行し、その後通常起動してください。更新には通信と追加ディスク容量が必要です。失敗の詳細は`.runtime-updates`内の`update.log`に残ります。
- 更新対象は新しいバージョンの非下書きリリースで、`PokeController-portable-win64.zip`が必要です。検証版も設定で対象にできます。「配布ページを開く」からブラウザーでダウンロードしてください。
- 更新は手動です。全ウィンドウを終了して新しいZIPを別フォルダーへ展開し、`SerialController/profiles`、`Commands/PythonCommands`内の自分で追加・変更したスクリプト、`Template`内の独自画像をコピーしてください。必要なら`Captures`と`Controller_Log`もコピーします。いずれも`SerialController`以下です。標準スクリプト全体を旧版で上書きすると修正が戻るため、自分の変更分を移してください。
- 同じフォルダーへの上書き更新も可能です。全ウィンドウを終了し、設定と独自ファイルのバックアップを取ってからZIPの内容を上書きしてください。旧版で不要になったファイルは残るため、別フォルダーへの展開を推奨します。exeだけの置換では更新できません。
- アプリは更新版の自動展開・データ移行・切り替えを行いません。exeファイル名は既存MCP設定との互換性のため変更していません。移動した場合はMCPクライアントの登録パスも変更してください。

通常の設定とMCPなどの追加設定は、一時ファイルへの書き込み完了後に置き換えます。変更前の内容を同じ場所の`.bak`へ保存し、同じ内容の再保存ではバックアップを更新しません。読み込み時に破損が見つかり正常なバックアップがあれば、破損ファイルを`.corrupt-*`へ残して復元します。復元できない場合はファイルを上書きせずエラーを表示します。キー設定と通常設定は保存前に最新内容を読み込み、互いの変更を保ちます。

## この版の変更と制約

- DirectShowLib、pythonnet、windows-capture-device-listを廃止し、Windows COMによるカメラ列挙へ置換。
- 元版と同じpynput・pygameへ復帰しました。独自の代替ライブラリは削除し、既存スクリプトから元のライブラリのAPIを利用できます。
- 橋渡し関数・サンプルスクリプトは上流0.1.9のファイルを無変更で復元しました。フウ氏の作成物を引用・同梱しています。[個人・非商用などの元の利用条件](SerialController/Commands/PythonCommands/bridge_functions/License.txt)が適用され、MITではありません。
- 出典のライセンスを明確にできないログ装飾コードを標準loggingへ置換。Icons8の画像は文字ボタンへ置換。
- 上流のサンプル画像を元のファイル名・配置で復元しています。画像内のゲーム著作物は本体のMITライセンスの対象ではありません。解像度・ゲームの表示設定が違う場合は自分で画像を用意してください。
- OpenCV付属のFFmpegプラグインも復元し、対応する動画ファイルの読み書きを利用できます。
- 通知設定の読み込み時に外部サービスへ接続しません。通知の実送信は従来の操作で行います。既存のLINE関連UIは残していますが、サービスの稼働を保証するものではありません。
- 指定ポート名で接続する際のボーレート、右スティックの変化判定、カメラ無効時の処理、スクリプトの個別読み込み失敗を修正。

0.2.0-alpha.8は個人用の修正をまとめた公開アルファ版です。協調停止、切断時の入力停止、デバイス別ゲームパッド入力、非同期キャプチャ、画面ログの件数制限を維持しています。pynputのコールバックから送信処理を分離し、キーを押したまま停止した際の入力解除も行います。独自スクリプトの無限ループやタイムアウトのない外部処理は強制終了せず、終了待ちを表示します。実機への操作送信と全スクリプトの動作は未検証です。Mac/Linux向けのアプリ全体の対応は行っていません。

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

フォークのGit履歴には元のファイルと元のライセンスが残ります。過去の制限付きファイルをMITへ変更したものではありません。元版の説明は[README.upstream.md](README.upstream.md)に保存しています。配布版の起動・更新方法はこのREADMEを優先してください。
