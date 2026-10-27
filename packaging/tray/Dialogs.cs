// 確認と進み具合の画面: 終了の確認、アンインストール（確認 → 進み具合 → 完了）、インストールの完了。
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;

namespace PokeControllerTray
{
    // 終了する前の確認。失われる機能と、もう一度起動する方法を伝える
    class ExitDialog : ModernDialog
    {
        public ExitDialog() : base(Program.Title, "Poke-Controller を終了しますか？")
        {
            AddText("本体も終了します。実行中のスクリプトは止まり、操作画面と Claude からの操作は使えなくなります。", true);
            AddText("もう一度使うときは、スタートメニューの「Poke-Controller」から起動します。Claude から使うと自動で起動します。");
            var cancel = AddButton("キャンセル", ButtonKind.Normal);
            var ok = AddButton("終了する", ButtonKind.Primary);
            cancel.DialogResult = DialogResult.Cancel;
            ok.DialogResult = DialogResult.OK;
            AcceptButton = cancel;   // 既定のボタンもキャンセル（Enter と、既定のボタンへのマウスの自動移動の先）
            CancelButton = cancel;
            TopMost = true;
            Shown += delegate { Activate(); cancel.Focus(); };
        }
    }

    // 段階の一覧。終わった段階に ✓、いま進めている段階に … を付ける
    class StepsLabel : Label
    {
        public StepsLabel(DialogPalette p, int width)
        {
            AutoSize = true;
            UseMnemonic = false;
            MaximumSize = new System.Drawing.Size(width, 0);
            ForeColor = p.Fore;
            Margin = new Padding(0, ModernDialog.Px(4), 0, ModernDialog.Px(12));
        }

        public void SetSteps(IList<string> steps, bool allDone)
        {
            var sb = new StringBuilder();
            for (int i = 0; i < steps.Count; i++)
            {
                bool current = !allDone && i == steps.Count - 1;
                sb.Append(current ? "…  " : "✓  ").Append(steps[i]);
                if (i < steps.Count - 1) sb.AppendLine();
            }
            Text = sb.ToString();
        }
    }

    // アンインストールの開始（「インストールされているアプリ」から PokeController.exe --uninstall で呼ばれる）。
    // インストール先は途中で消えるので、画面は一時フォルダーにコピーした exe で出す
    static class Uninstaller
    {
        public static int Start(bool quiet, bool keep)
        {
            string root = Program.Root.TrimEnd('\\');
            string temp = Path.Combine(Path.GetTempPath(), "PokeController-uninstall-" + DateTime.Now.Ticks);
            Directory.CreateDirectory(temp);
            File.Copy(Path.Combine(root, "uninstall.ps1"), Path.Combine(temp, "uninstall.ps1"));
            if (quiet)
            {
                var p = RunScript(temp, root, keep);
                p.WaitForExit();
                return p.ExitCode;
            }
            string copy = Path.Combine(temp, "PokeControllerUninstall.exe");
            File.Copy(Application.ExecutablePath, copy);
            Process.Start(new ProcessStartInfo(copy, "--uninstall-ui " + ServerHost.Quote(temp) + " --install-dir " + ServerHost.Quote(root) +
                (keep ? " --keep-settings" : "")) { UseShellExecute = false });
            return 0;
        }

        // uninstall.ps1 は段階ごとに progress.log へ追記し、最後に #done（失敗は #error 理由）を書く
        public static Process RunScript(string temp, string installDir, bool keep)
        {
            string arguments = "-NoProfile -ExecutionPolicy Bypass -File " + ServerHost.Quote(Path.Combine(temp, "uninstall.ps1")) +
                " -InstallDir " + ServerHost.Quote(installDir) + " -ProgressLog " + ServerHost.Quote(Path.Combine(temp, "progress.log")) +
                (keep ? " -KeepSettings" : "");
            return Process.Start(new ProcessStartInfo("powershell.exe", arguments) { UseShellExecute = false, CreateNoWindow = true });
        }
    }

    class UninstallFlow : ModernDialog
    {
        readonly string dir, installDir;
        readonly ModernCheckBox keep;
        readonly Timer timer = new Timer { Interval = 300 };
        StepsLabel stepsLabel;
        bool keepChosen;

        UninstallFlow(string dir, string installDir, bool keepDefault)
            : base("Poke-Controller のアンインストール", "Poke-Controller をアンインストールしますか？")
        {
            this.dir = dir;
            this.installDir = installDir;
            AddText("プログラム、スタートメニューの項目、専用の Python 環境、ログを削除します。", true);
            AddText("ドキュメントの PokeController フォルダー（スクリプト・画像・キャプチャ）は残します。");
            keep = AddCheck("設定とデータを残す", keepDefault);

            var cancel = AddButton("キャンセル", ButtonKind.Normal);
            var ok = AddButton("アンインストール", ButtonKind.Primary);
            cancel.Click += delegate { Close(); };
            ok.Click += delegate { Start(); };
            AcceptButton = cancel;
            CancelButton = cancel;
            TopMost = true;
            Shown += delegate { Activate(); cancel.Focus(); };   // 誤って Enter で消さないよう、最初はキャンセル
            FormClosing += delegate(object s, FormClosingEventArgs e) { if (timer.Enabled) e.Cancel = true; };   // 削除の途中では閉じない
            timer.Tick += delegate { Poll(); };
        }

        string ProgressFile { get { return Path.Combine(dir, "progress.log"); } }

        void Start()
        {
            keepChosen = keep.Checked;
            try { Uninstaller.RunScript(dir, installDir, keepChosen); }
            catch (Exception ex)
            {
                ShowFinished(new List<string>(), ex.Message);
                return;
            }
            ResetPage("アンインストールしています…");
            stepsLabel = new StepsLabel(P, Px(440));
            AddControl(stepsLabel);
            timer.Start();
        }

        void Poll()
        {
            string[] lines;
            try
            {
                if (!File.Exists(ProgressFile)) return;
                using (var fs = new FileStream(ProgressFile, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
                using (var r = new StreamReader(fs, Encoding.UTF8))
                    lines = r.ReadToEnd().Split(new[] { "\r\n", "\n" }, StringSplitOptions.RemoveEmptyEntries);
            }
            catch { return; }
            var steps = new List<string>();
            string error = null;
            bool done = false;
            foreach (var l in lines)
            {
                if (l == "#done") done = true;
                else if (l.StartsWith("#error")) error = l.Length > 7 ? l.Substring(7) : "";
                else steps.Add(l);
            }
            if (done || error != null) { timer.Stop(); ShowFinished(steps, error); return; }
            stepsLabel.SetSteps(steps, false);
        }

        void ShowFinished(List<string> steps, string error)
        {
            if (error == null)
            {
                ResetPage("アンインストールが完了しました");
                AddText(keepChosen ? "設定とデータ（%APPDATA%\\PokeController）は残しました。" : "設定とデータも削除しました。", true);
                AddText("ドキュメントの PokeController フォルダーは残っています。不要なら手動で削除してください。");
            }
            else
            {
                ResetPage("アンインストールを完了できませんでした");
                AddText(error, true);
            }
            var sl = new StepsLabel(P, Px(440));
            sl.SetSteps(steps, true);
            AddControl(sl);
            var close = AddButton("閉じる", ButtonKind.Primary);
            close.Click += delegate { Close(); };
            AcceptButton = close;
            CancelButton = close;
            close.Select();
        }

        public static int Run(string dir, string installDir, bool keepDefault)
        {
            using (var d = new UninstallFlow(dir, installDir, keepDefault)) d.ShowDialog();
            // 一時フォルダー（この exe を含む）は、このプロセスが終わってから消す
            try
            {
                Process.Start(new ProcessStartInfo("cmd.exe", "/c timeout /t 2 /nobreak >nul & rmdir /s /q " + ServerHost.Quote(dir))
                    { CreateNoWindow = true, UseShellExecute = false });
            }
            catch { }
            return 0;
        }
    }

    // インストールの完了（install.ps1 が最後に開く）
    class InstallFinishedDialog : ModernDialog
    {
        InstallFinishedDialog() : base(Program.Title, "インストールが完了しました")
        {
            AddText("スタートメニューの「Poke-Controller」から起動します。起動中は通知領域のアイコンから操作画面を開けます。", true);
            AddText("スクリプトや画像は、ドキュメントの PokeController フォルダーに置きます。");
            var launch = AddCheck("Poke-Controller を起動する", true);
            var done = AddButton("完了", ButtonKind.Primary);
            done.Click += delegate
            {
                if (launch.Checked)
                {
                    try { Process.Start(new ProcessStartInfo(Application.ExecutablePath) { UseShellExecute = false, WorkingDirectory = Program.Root }); } catch { }
                }
                Close();
            };
            AcceptButton = done;
            CancelButton = done;
            TopMost = true;
            Shown += delegate { Activate(); done.Focus(); };
        }

        public static int Run()
        {
            using (var d = new InstallFinishedDialog()) d.ShowDialog();
            return 0;
        }
    }
}
