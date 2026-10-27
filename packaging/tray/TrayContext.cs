// 通知領域のアイコンとメニュー。本体の起動・状態の取得（2 秒ごと）・終了を受け持つ。
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;

namespace PokeControllerTray
{
    enum ServerState { Starting, Ready, Stopped, Quitting }

    partial class TrayContext : ApplicationContext
    {
        readonly NotifyIcon tray;
        readonly ContextMenu menu;
        readonly MenuItem miTitle, miState, miOpen, miRestart, miUpdate, miVersion, miUpdateNow, miAutoUpdate;
        readonly MenuItem miMore, miFolder, miRegister, miCopyCommand, miExit;
        readonly System.Windows.Forms.Timer pollTimer;
        readonly ServerHost host;
        readonly Icon icoNormal, icoStopped;

        ServerState state = ServerState.Starting;
        string webUrl;
        bool openWhenReady, polling, exiting;
        DateTime pollStarted;
        int pollGeneration;
        Dictionary<string, object> session;   // sessions の結果（1 件目）
        string version;
        // 「今すぐ確認して更新」の終わりは、update-state.json の last_check が変わったことで知る
        bool updating;
        double updateCheckBefore;
        DateTime updateStarted;

        public TrayContext(bool openWindow)
        {
            version = AppVersion();
            host = new ServerHost(Post);
            host.Ready += OnReady;
            host.Exited += OnServerExited;
            host.Exiting += OnServerExiting;

            int small = Math.Max(16, SystemInformation.SmallIconSize.Width);
            icoNormal = AppIcon.Make(small, false);
            icoStopped = AppIcon.Make(small, true);

            // Windows 標準（Win32）のメニュー。状態は行ごとに別の項目にする
            menu = new ContextMenu();
            miTitle = new MenuItem(Program.Title) { Enabled = false };
            miState = new MenuItem("") { Enabled = false };
            miOpen = new MenuItem("画面を開く", delegate { OpenWindow(); }) { DefaultItem = true };
            miRestart = new MenuItem("本体を起動し直す", delegate { StartServer(); });

            miVersion = new MenuItem("") { Enabled = false };
            miUpdateNow = new MenuItem("今すぐ確認して更新", delegate { UpdateNow(); });
            miAutoUpdate = new MenuItem("自動で更新する（毎日）", delegate { ToggleAutoUpdate(); });
            miUpdate = new MenuItem("アップデート");
            miUpdate.MenuItems.AddRange(new MenuItem[] { miVersion, new MenuItem("-"), miUpdateNow, miAutoUpdate });

            miFolder = new MenuItem("作業フォルダーを開く", delegate { Command("open_folder", "folder", "workspace"); });
            miRegister = new MenuItem("Claude Desktop に登録", delegate { RegisterClaudeDesktop(); });
            miCopyCommand = new MenuItem("Claude Code 用コマンドをコピー", delegate { CopyClaudeCodeCommand(); });
            miMore = new MenuItem("その他");
            miMore.MenuItems.AddRange(new MenuItem[] { miFolder, new MenuItem("-"), miRegister, miCopyCommand });

            miExit = new MenuItem("アプリを終了する", delegate { ConfirmExit(); });
            menu.MenuItems.AddRange(new MenuItem[] {
                miTitle, miState, new MenuItem("-"),
                miOpen, miRestart, miUpdate, miMore, new MenuItem("-"), miExit });
            menu.Popup += delegate { Theme.RefreshMenus(); UpdateVisuals(); Poll(); };

            tray = new NotifyIcon { Icon = icoNormal, Text = Program.Title, ContextMenu = menu };
            tray.MouseDoubleClick += delegate(object s, MouseEventArgs e) { if (e.Button == MouseButtons.Left) OpenWindow(); };
            tray.BalloonTipClicked += delegate { if (balloonAction != null && tray.BalloonTipText == balloonActionText) balloonAction(); };
            tray.Visible = true;
            InitMenuHover();
            InitSubmenuUp();
            SetHover(miVersion, delegate { string e = UpdateError(); return e == "" ? null : e; });
            SetHover(miRegister, delegate { return "Claude Desktop の設定に MCP サーバーとして追加します。\nClaude Desktop を再起動すると使えます。"; });
            SetHover(miCopyCommand, delegate { return "ターミナルに貼り付けて実行すると、Claude Code に登録されます。"; });

            pollTimer = new System.Windows.Forms.Timer { Interval = 2000 };
            pollTimer.Tick += delegate { Poll(); };
            pollTimer.Start();

            // 2 回目の起動から合図を受けたら画面を開く
            var showEvent = new EventWaitHandle(false, EventResetMode.AutoReset, Program.ShowWindowEvent);
            ThreadPool.RegisterWaitForSingleObject(showEvent, delegate { Post(delegate { OpenWindow(); }); }, null, -1, false);
            var quitEvent = new EventWaitHandle(false, EventResetMode.AutoReset, Program.QuitEvent);
            ThreadPool.RegisterWaitForSingleObject(quitEvent, delegate { Post(delegate { Quit(); }); }, null, -1, false);

            openWhenReady = openWindow;
            StartServer();
        }

        static string AppVersion()
        {
            var attr = (AssemblyInformationalVersionAttribute)Attribute.GetCustomAttribute(
                typeof(TrayContext).Assembly, typeof(AssemblyInformationalVersionAttribute));
            return attr != null ? attr.InformationalVersion : "";
        }

        // ---------- 本体 ----------

        void StartServer()
        {
            if (host.Alive || exiting) return;
            session = null;
            webUrl = null;
            state = ServerState.Starting;
            string error;
            if (!host.Start(out error))
            {
                state = ServerState.Stopped;
                ShowBalloon(10000, Program.Title, error, ToolTipIcon.Error, null, 1);
            }
            UpdateVisuals();
        }

        void OnReady(Dictionary<string, object> message)
        {
            webUrl = Str(message, "web_url");
            state = ServerState.Ready;
            UpdateVisuals();
            Poll();
            if (openWhenReady) { openWhenReady = false; OpenWindow(); }
            else if (webUrl != null) AppWindow.Retarget(webUrl);
        }

        // 本体が終了処理を終えた（{"event":"exit"}）。プロセスが消えるまでの間も、もう要求には答えない
        void OnServerExiting()
        {
            if (state == ServerState.Quitting) return;
            webUrl = null;
            state = ServerState.Stopped;
            openWhenReady = false;
            UpdateVisuals();
        }

        void OnServerExited(int code)
        {
            webUrl = null;
            session = null;
            polling = false;
            if (state == ServerState.Quitting) { FinishExit(); return; }
            // 操作画面の「アプリを終了」などで本体が自分で終わった（終了コード 0）ときは、トレイも終わる
            if (code == 0) { FinishExit(); return; }
            state = ServerState.Stopped;
            openWhenReady = false;
            AppWindow.CloseWindow();
            UpdateVisuals();
            ShowBalloon(10000, Program.Title, "Poke-Controller の本体が停止しました", ToolTipIcon.Warning, delegate { StartServer(); }, 1);
        }

        void Poll()
        {
            if (state != ServerState.Ready) return;
            // 返事が失われても状態の更新が止まらないよう、15 秒で待つのをやめる（遅れて届いた古い返事は使わない）
            if (polling && (DateTime.Now - pollStarted).TotalSeconds < 15) return;
            polling = true;
            pollStarted = DateTime.Now;
            int generation = ++pollGeneration;
            host.Request("sessions", null, delegate(bool ok, object result, string error)
            {
                if (generation != pollGeneration) return;
                polling = false;
                var list = result as object[];
                if (ok && list != null && list.Length > 0) session = list[0] as Dictionary<string, object>;
                UpdateVisuals();
                CheckUpdateFinished();
            });
        }

        void Command(string action, string key, object value)
        {
            var values = new Dictionary<string, object>();
            if (key != null) values[key] = value;
            host.Command(action, values, delegate(bool ok, object result, string error)
            {
                if (!ok) ShowBalloon(5000, Program.Title, error ?? "操作できませんでした", ToolTipIcon.Warning);
                Poll();
            });
        }

        // ---------- 表示 ----------

        static string Str(Dictionary<string, object> d, string key)
        {
            object v;
            return d != null && d.TryGetValue(key, out v) && v != null ? Convert.ToString(v, System.Globalization.CultureInfo.InvariantCulture) : null;
        }

        static bool Flag(Dictionary<string, object> d, string key)
        {
            object v;
            return d != null && d.TryGetValue(key, out v) && v is bool && (bool)v;
        }

        static double Num(Dictionary<string, object> d, string key)
        {
            object v;
            try { return d != null && d.TryGetValue(key, out v) && v != null ? Convert.ToDouble(v, System.Globalization.CultureInfo.InvariantCulture) : 0; }
            catch { return 0; }
        }

        Dictionary<string, object> AppInfo { get { object v; return session != null && session.TryGetValue("app", out v) ? v as Dictionary<string, object> : null; } }
        Dictionary<string, object> UpdateInfo { get { object v; var a = AppInfo; return a != null && a.TryGetValue("update", out v) ? v as Dictionary<string, object> : null; } }

        string UpdateError() { return Str(UpdateInfo, "last_error") ?? ""; }

        // ディスク上の版（更新が入ると、次の起動から新しい版になる）
        static string InstalledVersion()
        {
            try
            {
                var m = Regex.Match(File.ReadAllText(Path.Combine(Program.Root, "product.py")), "VERSION = '([^']+)'");
                return m.Success ? m.Groups[1].Value : null;
            }
            catch { return null; }
        }

        string StateText()
        {
            switch (state)
            {
                case ServerState.Starting: return "本体を起動しています…";
                case ServerState.Stopped: return "本体が停止しています";
                case ServerState.Quitting: return "終了しています…";
            }
            if (Flag(session, "running"))
                return (Flag(session, "paused") ? "一時停止中: " : "実行中: ") + Str(session, "command");
            return "待機中";
        }

        void UpdateVisuals()
        {
            string running = Str(AppInfo, "version");
            if (!string.IsNullOrEmpty(running)) version = running;
            string title = Program.Title + (version == "" ? "" : " v" + version);
            bool ready = state == ServerState.Ready;
            miTitle.Text = title;
            miState.Text = StateText();
            miRestart.Visible = state == ServerState.Stopped;
            miUpdate.Enabled = ready;
            miFolder.Enabled = ready;

            string installed = InstalledVersion();
            string suffix = "";
            if (installed != null && version != "" && installed != version) suffix = "（次の起動で v" + installed + "）";
            else if (UpdateError() != "") suffix = "（確認できませんでした）";
            else if (Num(UpdateInfo, "last_check") > 0) suffix = "（最新です）";
            miVersion.Text = title + suffix;
            miAutoUpdate.Checked = Flag(AppInfo, "auto_update");
            miUpdateNow.Text = updating ? "更新しています…" : "今すぐ確認して更新";
            miUpdateNow.Enabled = !updating;

            Icon icon = state == ServerState.Stopped ? icoStopped : icoNormal;
            if (tray.Icon != icon) tray.Icon = icon;
            // ツールチップは標準の表示（63 文字まで）。名前と版、状態
            string tip = title + "\n" + StateText();
            if (tip.Length > 63) tip = tip.Substring(0, 62) + "…";
            if (tray.Text != tip) tray.Text = tip;
        }

        // ---------- 操作 ----------

        void OpenWindow()
        {
            if (exiting) return;
            if (state == ServerState.Ready && webUrl != null) { AppWindow.ShowPage(webUrl, Shell); return; }
            openWhenReady = true;   // 起動が終わったら開く
            if (state == ServerState.Stopped) StartServer();
        }

        void UpdateNow()
        {
            if (state != ServerState.Ready || updating) return;
            updating = true;
            updateStarted = DateTime.Now;
            updateCheckBefore = Num(UpdateInfo, "last_check");
            UpdateVisuals();
            host.Command("update_now", null, delegate(bool ok, object result, string error)
            {
                if (!ok) { updating = false; UpdateVisuals(); ShowBalloon(5000, Program.Title, error ?? "更新を始められませんでした", ToolTipIcon.Warning); }
            });
        }

        void CheckUpdateFinished()
        {
            if (!updating) return;
            double now = Num(UpdateInfo, "last_check");
            if (now == updateCheckBefore)
            {
                if ((DateTime.Now - updateStarted).TotalMinutes > 30) { updating = false; UpdateVisuals(); }
                return;
            }
            updating = false;
            UpdateVisuals();
            string installed = InstalledVersion();
            string error = UpdateError();
            string portableMessage = Str(UpdateInfo, "result") == "portable" ? Str(UpdateInfo, "message") : null;
            string message = error != "" ? "更新できませんでした。" + error
                : !string.IsNullOrEmpty(portableMessage) ? portableMessage   // ソースから使っているときは確認だけ
                : installed != null && installed != version ? "v" + installed + " を入れました。次に起動したときから新しい版になります。"
                : "最新の版です。";
            ShowBalloon(8000, Program.Title, message.Length > 250 ? message.Substring(0, 250) : message, ToolTipIcon.Info);
        }

        void ToggleAutoUpdate()
        {
            if (state != ServerState.Ready) return;
            Command("app_options", "auto_update", !Flag(AppInfo, "auto_update"));
        }

        void CopyClaudeCodeCommand()
        {
            string exe = Path.Combine(Program.Root, "PokeControllerMCP.exe");
            string text = "claude mcp add --scope user poke-controller -- " + (exe.IndexOf(' ') >= 0 ? "\"" + exe + "\"" : exe);
            try
            {
                Clipboard.SetText(text);
                ShowBalloon(4000, Program.Title, "Claude Code 用のコマンドをコピーしました", ToolTipIcon.Info);
            }
            catch (Exception ex) { MessageBox.Show(ex.Message, Program.Title, MessageBoxButtons.OK, MessageBoxIcon.Error); }
        }

        // mcp_setup.py（設定ファイルを .bak を残して書き換える）を、記録した Python で実行する
        void RegisterClaudeDesktop()
        {
            string python = ServerHost.FindPython();
            if (python == null) { MessageBox.Show("Python の実行環境が見つかりません。", Program.Title, MessageBoxButtons.OK, MessageBoxIcon.Error); return; }
            const string code = "import sys; sys.path.insert(0, sys.argv[1]); import mcp_setup; " +
                "paths = mcp_setup.desktop_configs(); [mcp_setup.register_desktop(p, sys.argv[1]) for p in paths]; print(len(paths))";
            var psi = ServerHost.PythonStartInfo(python, "-c " + ServerHost.Quote(code) + " " + ServerHost.Quote(Program.Root.TrimEnd('\\')));
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            ThreadPool.QueueUserWorkItem(delegate
            {
                string output = "", errors = "";
                int exit = -1;
                try
                {
                    using (var p = Process.Start(psi))
                    {
                        var err = p.StandardError.ReadToEndAsync();
                        output = p.StandardOutput.ReadToEnd().Trim();
                        errors = err.Result.Trim();
                        p.WaitForExit();
                        exit = p.ExitCode;
                    }
                }
                catch (Exception ex) { errors = ex.Message; }
                Post(delegate
                {
                    if (exit != 0)
                    {
                        string[] lines = errors.Split('\n');
                        MessageBox.Show("Claude Desktop に登録できませんでした。\n" + lines[lines.Length - 1].Trim(), Program.Title, MessageBoxButtons.OK, MessageBoxIcon.Error);
                    }
                    else if (output == "0")
                        MessageBox.Show("Claude Desktop の設定ファイルが見つかりません。Claude Desktop を一度起動してから、もう一度試してください。", Program.Title, MessageBoxButtons.OK, MessageBoxIcon.Information);
                    else
                        ShowBalloon(5000, Program.Title, "Claude Desktop に登録しました。Claude Desktop を再起動すると使えます。", ToolTipIcon.Info);
                });
            });
        }

        void ConfirmExit()
        {
            if (exiting) return;
            using (var d = new ExitDialog())
            {
                if (d.ShowDialog() != DialogResult.OK) return;
            }
            Quit();
        }

        // 標準入力を閉じて本体に終了を頼み、終わるのを待つ（最大 10 秒。過ぎたら止める）
        void Quit()
        {
            if (exiting || state == ServerState.Quitting) return;
            AppWindow.CloseWindow();
            if (!host.Alive) { FinishExit(); return; }
            state = ServerState.Quitting;
            UpdateVisuals();
            host.RequestStop();
            var timeout = new System.Windows.Forms.Timer { Interval = 10000 };
            timeout.Tick += delegate { timeout.Stop(); host.Kill(); };
            timeout.Start();
        }

        void FinishExit()
        {
            if (exiting) return;
            exiting = true;
            pollTimer.Stop();
            AppWindow.CloseWindow();
            tray.Visible = false;
            ExitThread();
        }

        static void Shell(string target)
        {
            try { Process.Start(new ProcessStartInfo(target) { UseShellExecute = true }); }
            catch (Exception ex) { MessageBox.Show(ex.Message, Program.Title, MessageBoxButtons.OK, MessageBoxIcon.Error); }
        }

        // UI スレッドへ処理を戻す。メニューはコントロールではないため、専用の非表示コントロールを使う
        readonly Control invoker = CreateInvoker();

        static Control CreateInvoker()
        {
            var c = new Control();
            var h = c.Handle;
            return c;
        }

        void Post(MethodInvoker action)
        {
            try { invoker.BeginInvoke(action); } catch { }
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                host.RequestStop();   // 万一の終わり方でも、本体を残さない
                tray.Dispose();
                menu.Dispose();
            }
            base.Dispose(disposing);
        }
    }
}
