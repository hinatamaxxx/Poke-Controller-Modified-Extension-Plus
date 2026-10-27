// 操作画面（本体のブラウザ用の画面）を表示する専用ウィンドウ（WebView2）。
// ブラウザーらしい部品（ツールバー、Edge の右クリックメニュー、開発者ツール、拡大、パスワード保存）は出さず、
// Windows のライト/ダーク設定に追従する。WebView2 のデータは %LOCALAPPDATA%\PokeController\WebView2 に置く。
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
using Microsoft.Win32;

namespace PokeControllerTray
{
    class AppWindow : Form
    {
        static AppWindow current;

        static readonly string DataDir = Program.LocalDir;
        static readonly string BoundsFile = Path.Combine(DataDir, "window.txt");

        readonly WebView2 web;
        readonly Action<string> openExternal;
        readonly UserPreferenceChangedEventHandler themeHandler;
        string pendingUrl;
        Uri home;
        bool ready;

        public static bool IsOpen { get { return current != null && !current.IsDisposed; } }

        // 画面を開く。開いていれば前面に出す（URL が変わったときだけ移動する）。
        // WebView2 のランタイムがなければ openExternal（既定のブラウザー）で開く
        public static void ShowPage(string url, Action<string> openExternal)
        {
            if (IsOpen)
            {
                if (current.pendingUrl != url) current.Navigate(url);
                if (current.WindowState == FormWindowState.Minimized) current.WindowState = FormWindowState.Normal;
                current.Activate();
                return;
            }
            string runtime = null;
            try { runtime = CoreWebView2Environment.GetAvailableBrowserVersionString(); } catch { }
            if (string.IsNullOrEmpty(runtime)) { openExternal(url); return; }
            current = new AppWindow(url, openExternal);
            current.Show();
            current.Activate();
        }

        // 本体が新しい URL で起動し直したとき、開いている画面を移す
        public static void Retarget(string url)
        {
            if (IsOpen && current.pendingUrl != url) current.Navigate(url);
        }

        public static void CloseWindow()
        {
            if (IsOpen) current.Close();
        }

        AppWindow(string url, Action<string> openExternal)
        {
            this.openExternal = openExternal;
            pendingUrl = url;
            home = new Uri(url);

            Text = Program.Title;
            AutoScaleMode = AutoScaleMode.Dpi;
            Icon = Theme.TitleBarIcon();
            StartPosition = FormStartPosition.Manual;
            MinimumSize = new Size(640, 480);
            RestoreSavedBounds();

            web = new WebView2 { Dock = DockStyle.Fill };
            Controls.Add(web);
            // 最初から独自のタイトルバーで開く（読み込んでから切り替えると、上部が動いて見える）
            framed = true;
            UpdateFramePadding();
            ApplyTheme();

            themeHandler = delegate(object s, UserPreferenceChangedEventArgs e)
            {
                if (e.Category == UserPreferenceCategory.General) BeginInvoke((MethodInvoker)ApplyTheme);
            };
            SystemEvents.UserPreferenceChanged += themeHandler;

            HandleCreated += delegate { Theme.ApplyTitleBar(this); };
            FormClosing += delegate { SaveBounds(); };
            FormClosed += delegate
            {
                SystemEvents.UserPreferenceChanged -= themeHandler;
                if (current == this) current = null;
            };
            Shown += async delegate
            {
                // 初期化の途中でウィンドウを閉じても、例外でアプリを落とさない
                try { await InitAsync(); }
                catch (Exception) { if (!IsDisposed) throw; }
            };
        }

        void ApplyTheme()
        {
            bool dark = Theme.IsDark;
            // 独自のタイトルバーのときは、上端の帯を画面の上のバー（CSS の --strip）と同じ色にする
            if (framed) BackColor = dark ? Color.FromArgb(0x0E, 0x10, 0x13) : Color.FromArgb(0xDD, 0xE1, 0xE6);
            else BackColor = dark ? Theme.DarkBack : Color.White;
            web.DefaultBackgroundColor = BackColor;   // 読み込み中に白く光らないように
            if (web.CoreWebView2 != null)
                web.CoreWebView2.Profile.PreferredColorScheme = dark ? CoreWebView2PreferredColorScheme.Dark : CoreWebView2PreferredColorScheme.Light;
            Theme.ApplyTitleBar(this);
        }

        async Task InitAsync()
        {
            try
            {
                Directory.CreateDirectory(DataDir);
                var env = await CoreWebView2Environment.CreateAsync(null, Path.Combine(DataDir, "WebView2"));
                if (IsDisposed) return;   // 待っている間に閉じられた
                await web.EnsureCoreWebView2Async(env);
                if (IsDisposed || web.IsDisposed || web.CoreWebView2 == null) return;
            }
            catch (Exception)
            {
                if (IsDisposed || Disposing) return;   // 閉じたことで失敗した。ブラウザーでは開かない
                // WebView2 を起動できない場合は既定のブラウザーで開く
                string url = pendingUrl;
                Close();
                openExternal(url);
                return;
            }

            var core = web.CoreWebView2;
            var st = core.Settings;
            st.AreDevToolsEnabled = false;
            st.IsStatusBarEnabled = false;
            st.IsZoomControlEnabled = false;
            st.IsPinchZoomEnabled = false;
            st.IsSwipeNavigationEnabled = false;
            st.IsPasswordAutosaveEnabled = false;
            st.IsGeneralAutofillEnabled = false;
            st.AreBrowserAcceleratorKeysEnabled = false;   // Ctrl+P・Ctrl+F などを無効に（編集キーとページのキー入力は届く）
            // 画面の上のバーをタイトルバーにする（CSS の app-region: drag で移動・ダブルクリックで最大化）
            try { st.IsNonClientRegionSupportEnabled = true; canFrame = true; } catch (Exception) { canFrame = false; }
            if (!canFrame) SetFramed(false);
            ApplyTheme();
            // 拡大率は 1.0 に固定する（画面はウィンドウの大きさに合わせて組まれる）
            web.ZoomFactor = 1.0;
            web.ZoomFactorChanged += delegate { if (web.ZoomFactor != 1.0) web.ZoomFactor = 1.0; };

            // 右クリックメニューは、文字の選択・入力の操作だけにする
            core.ContextMenuRequested += delegate(object s, CoreWebView2ContextMenuRequestedEventArgs e)
            {
                var keep = new HashSet<string> { "copy", "cut", "paste", "selectAll", "undo", "redo" };
                var items = e.MenuItems;
                for (int i = items.Count - 1; i >= 0; i--)
                    if (!keep.Contains(items[i].Name)) items.RemoveAt(i);
                if (items.Count == 0) e.Handled = true;
            };
            // 操作画面以外へのリンクや新しいウィンドウは、既定のブラウザーで開く
            core.NewWindowRequested += delegate(object s, CoreWebView2NewWindowRequestedEventArgs e)
            {
                e.Handled = true;
                openExternal(e.Uri);
            };
            core.NavigationStarting += delegate(object s, CoreWebView2NavigationStartingEventArgs e)
            {
                Uri u;
                if (!Uri.TryCreate(e.Uri, UriKind.Absolute, out u)) return;
                if (u.Scheme == "about" || u.Scheme == "data") return;
                if (!IsApp(u)) { e.Cancel = true; openExternal(e.Uri); }
            };

            // 画面が読み込めたら、画面がタイトルバーを描く。読み込めなければ標準のタイトルバーに戻す（閉じられなくならないように）
            core.WebMessageReceived += delegate(object s, CoreWebView2WebMessageReceivedEventArgs e)
            {
                Uri source;
                if (!Uri.TryCreate(e.Source, UriKind.Absolute, out source) || !IsApp(source)) return;
                string message;
                try { message = e.TryGetWebMessageAsString(); } catch (ArgumentException) { return; }
                switch (message)
                {
                    case "frame": SetFramed(canFrame); break;
                    case "minimize": WindowState = FormWindowState.Minimized; break;
                    case "maximize": WindowState = WindowState == FormWindowState.Maximized ? FormWindowState.Normal : FormWindowState.Maximized; break;
                    case "close": Close(); break;
                }
            };
            core.NavigationCompleted += delegate(object s, CoreWebView2NavigationCompletedEventArgs e)
            {
                if (!e.IsSuccess) SetFramed(false);
                else if (ContainsFocus || Form.ActiveForm == this) web.Focus();
            };
            // キーボードでの操作が、画面を一度クリックしなくても届くように、窓が前に来たら画面に入力を渡す
            Activated += delegate { if (ready && !web.ContainsFocus) web.Focus(); };
            Resize += delegate { if (framed) { UpdateFramePadding(); PostWindowState(); } };

            ready = true;
            web.Source = new Uri(pendingUrl);
        }

        // ---------- 独自のタイトルバー ----------
        // 標準の枠（影・端での大きさ変更・スナップ）は残し、タイトルバーの分だけ画面を上に広げる。
        // 画面（WebView2）の上では Windows が端を判定できないので、通常の大きさのときは上端に細い帯を残して大きさ変更に使う。

        const int WM_NCCALCSIZE = 0x0083, WM_NCHITTEST = 0x0084;
        const int HTCLIENT = 1, HTTOP = 12, HTTOPLEFT = 13, HTTOPRIGHT = 14;
        bool canFrame, framed;

        [System.Runtime.InteropServices.DllImport("user32.dll")]
        static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        static extern int GetSystemMetricsForDpi(int index, uint dpi);
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        static extern uint GetDpiForWindow(IntPtr hWnd);

        int FrameThickness()
        {
            uint dpi = GetDpiForWindow(Handle);
            return GetSystemMetricsForDpi(33 /*SM_CYSIZEFRAME*/, dpi) + GetSystemMetricsForDpi(92 /*SM_CXPADDEDBORDER*/, dpi);
        }

        int ResizeStrip { get { return WindowState == FormWindowState.Normal ? Math.Max(1, LogicalToDeviceUnits(4)) : 0; } }

        void SetFramed(bool on)
        {
            if (framed != on)
            {
                framed = on;
                UpdateFramePadding();
                ApplyTheme();
                // 0x27 = SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER、0x10 = SWP_NOACTIVATE
                SetWindowPos(Handle, IntPtr.Zero, 0, 0, 0, 0, 0x27 | 0x10);
            }
            PostWindowState();
        }

        void UpdateFramePadding()
        {
            var padding = new Padding(0, framed ? ResizeStrip : 0, 0, 0);
            if (Padding != padding) Padding = padding;
        }

        void PostWindowState()
        {
            if (!ready || web.CoreWebView2 == null) return;
            web.CoreWebView2.PostWebMessageAsJson(string.Format("{{\"type\":\"window\",\"framed\":{0},\"maximized\":{1}}}",
                framed ? "true" : "false", WindowState == FormWindowState.Maximized ? "true" : "false"));
        }

        protected override void WndProc(ref Message m)
        {
            if (framed && m.Msg == WM_NCCALCSIZE && m.WParam != IntPtr.Zero)
            {
                // 標準の計算のうち、上端（タイトルバー）だけを画面に返す。最大化中は画面の外にはみ出す枠の分を引く
                int top = System.Runtime.InteropServices.Marshal.ReadInt32(m.LParam, 4);
                base.WndProc(ref m);
                if (WindowState == FormWindowState.Maximized) top += FrameThickness();
                System.Runtime.InteropServices.Marshal.WriteInt32(m.LParam, 4, top);
                m.Result = IntPtr.Zero;
                return;
            }
            if (framed && m.Msg == WM_NCHITTEST)
            {
                base.WndProc(ref m);
                if ((int)m.Result != HTCLIENT || WindowState != FormWindowState.Normal) return;
                long lp = m.LParam.ToInt64();
                var p = PointToClient(new Point((short)(lp & 0xFFFF), (short)((lp >> 16) & 0xFFFF)));
                if (p.Y >= ResizeStrip) return;
                int corner = LogicalToDeviceUnits(12);
                m.Result = (IntPtr)(p.X < corner ? HTTOPLEFT : p.X >= ClientSize.Width - corner ? HTTOPRIGHT : HTTOP);
                return;
            }
            base.WndProc(ref m);
        }

        protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
        {
            // ブラウザーのショートカットを止めたので、再読み込みだけ自前で受ける
            if (ready && (keyData == Keys.F5 || keyData == (Keys.Control | Keys.R))) { web.Reload(); return true; }
            return base.ProcessCmdKey(ref msg, keyData);
        }

        bool IsApp(Uri u)
        {
            return (u.Scheme == "http" || u.Scheme == "https") &&
                string.Equals(u.Host, home.Host, StringComparison.OrdinalIgnoreCase) && u.Port == home.Port;
        }

        void Navigate(string url)
        {
            pendingUrl = url;
            home = new Uri(url);
            if (ready) web.Source = new Uri(url);
        }

        // ---------- ウィンドウ位置の保存（ファイル） ----------

        void RestoreSavedBounds()
        {
            // 初回は作業領域に収まる横長（16:10、論理 1280×800 まで、作業領域の 85% まで）で中央に置く。
            // コンストラクターではハンドルがなく LogicalToDeviceUnits が 96dpi 基準になるので、実際の拡大率で求める
            var area = Screen.FromPoint(Cursor.Position).WorkingArea;
            int w = Math.Min(ModernDialog.Px(1280), area.Width * 85 / 100);
            int h = Math.Min(ModernDialog.Px(800), area.Height * 85 / 100);
            h = Math.Min(h, w * 10 / 16);
            w = Math.Min(w, h * 16 / 10);
            Bounds = new Rectangle(area.Left + (area.Width - w) / 2, area.Top + (area.Height - h) / 2, w, h);
            try
            {
                if (!File.Exists(BoundsFile)) return;
                string[] p = File.ReadAllText(BoundsFile).Trim().Split(',');
                var r = new Rectangle(int.Parse(p[0], CultureInfo.InvariantCulture), int.Parse(p[1], CultureInfo.InvariantCulture),
                                      int.Parse(p[2], CultureInfo.InvariantCulture), int.Parse(p[3], CultureInfo.InvariantCulture));
                if (r.Width < 400 || r.Height < 300) return;
                // 保存した位置が今の画面（モニター構成の変更など）からはみ出すときは、その画面の作業領域に収める
                foreach (var s in Screen.AllScreens)
                {
                    var a = s.WorkingArea;
                    if (!a.IntersectsWith(r)) continue;
                    int rw = Math.Min(r.Width, a.Width), rh = Math.Min(r.Height, a.Height);
                    int rx = Math.Max(a.Left, Math.Min(r.Left, a.Right - rw)), ry = Math.Max(a.Top, Math.Min(r.Top, a.Bottom - rh));
                    Bounds = new Rectangle(rx, ry, rw, rh);
                    if (p.Length > 4 && p[4] == "max") WindowState = FormWindowState.Maximized;
                    break;
                }
            }
            catch { }
        }

        void SaveBounds()
        {
            try
            {
                Directory.CreateDirectory(DataDir);
                var r = WindowState == FormWindowState.Normal ? Bounds : RestoreBounds;
                File.WriteAllText(BoundsFile, string.Format(CultureInfo.InvariantCulture, "{0},{1},{2},{3},{4}",
                    r.X, r.Y, r.Width, r.Height, WindowState == FormWindowState.Maximized ? "max" : "normal"));
            }
            catch { }
        }
    }
}
