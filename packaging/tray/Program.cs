// Poke-Controller の通知領域アプリ。本体（画面を持たない Python のプロセス）を起動・終了し、操作画面のウィンドウを開く。
// アンインストールとインストール完了の画面もこの exe が出す。MIT。
// .NET Framework 4.x 付属の csc.exe (C# 5) でビルドする: packaging\build.py を参照。
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

namespace PokeControllerTray
{
    static class Program
    {
        internal const string AppName = "PokeController";
        internal const string Title = "Poke-Controller";
        internal const string AppUserModelId = "hinatamaxxx.PokeController";
        // 起動済みのトレイに「画面を開いて」と伝えるイベント（2 回目の起動から）
        internal const string ShowWindowEvent = "Local\\PokeController_ShowWindow";
        // 起動済みのトレイに終了を頼むイベント（--quit。確認画面は出さない）
        internal const string QuitEvent = "Local\\PokeController_Quit";

        [DllImport("shell32.dll", CharSet = CharSet.Unicode)] static extern int SetCurrentProcessExplicitAppUserModelID(string appId);
        [DllImport("user32.dll")] static extern bool AllowSetForegroundWindow(int processId);

        // フォルダーは裏で動く本体が開くので、そのままでは Windows がエクスプローラーを前面に出さない。
        // 前面にいるこのプロセス（メニューや画面を操作した直後）から、ほかのプロセスが前面に出ることを許す
        internal static void AllowForeground() { AllowSetForegroundWindow(-1 /*ASFW_ANY*/); }

        internal static string Root { get { return AppDomain.CurrentDomain.BaseDirectory; } }
        internal static string LocalDir { get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), AppName); } }

        static bool Has(string[] args, string name)
        {
            return Array.Exists(args, delegate(string a) { return string.Equals(a, name, StringComparison.OrdinalIgnoreCase); });
        }

        internal static string ArgValue(string[] args, string name)
        {
            int i = Array.FindIndex(args, delegate(string a) { return string.Equals(a, name, StringComparison.OrdinalIgnoreCase); });
            return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
        }

        static void InitUi()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
        }

        [STAThread]
        static int Main(string[] args)
        {
            SetCurrentProcessExplicitAppUserModelID(AppUserModelId);   // ウィンドウやトレイアイコンを作る前に
            if (Has(args, "--uninstall")) return Uninstaller.Start(Has(args, "--quiet"), Has(args, "--keep-settings"));
            string temp = ArgValue(args, "--uninstall-ui");
            if (temp != null)
            {
                InitUi();
                return UninstallFlow.Run(temp, ArgValue(args, "--install-dir") ?? Root.TrimEnd('\\'), Has(args, "--keep-settings"));
            }
            if (Has(args, "--install-finished")) { InitUi(); return InstallFinishedDialog.Run(); }

            if (Has(args, "--quit"))
            {
                try { using (var ev = EventWaitHandle.OpenExisting(QuitEvent)) ev.Set(); } catch { }
                return 0;
            }
            bool background = Has(args, "--background");
            bool created;
            using (var mutex = new Mutex(true, "Local\\PokeController_SingleInstance", out created))
            {
                if (!created)
                {
                    // 2 回目の起動: 画面を開く合図だけ送る（--background なら何もしない）
                    if (!background)
                    {
                        AllowSetForegroundWindow(-1);   // 起動済みのトレイが画面を前面に出せるように
                        try { using (var ev = EventWaitHandle.OpenExisting(ShowWindowEvent)) ev.Set(); } catch { }
                    }
                    return 0;
                }
                InitUi();
                Theme.FollowSystemForMenus();
                Application.Run(new TrayContext(!background));
                GC.KeepAlive(mutex);
            }
            return 0;
        }
    }

    static class L
    {
        public const string UiFont = "Yu Gothic UI";
        public const string UiFontSemibold = "Yu Gothic UI Semibold";
    }

    // アプリのアイコン（build.py が make_icon.py で作り、exe に埋め込んだ .ico）
    static class AppIcon
    {
        static byte[] data;

        static byte[] Data
        {
            get
            {
                if (data == null)
                {
                    using (var s = typeof(AppIcon).Assembly.GetManifestResourceStream("PokeController.ico"))
                    {
                        if (s == null) return null;
                        var ms = new MemoryStream();
                        s.CopyTo(ms);
                        data = ms.ToArray();
                    }
                }
                return data;
            }
        }

        // gray: 本体が止まっているときのグレーのアイコン
        public static Bitmap Render(int size, bool gray)
        {
            Bitmap src = null;
            try
            {
                if (Data != null) src = LoadEntry(Data, size);
                if (src == null)
                    using (var ico = Icon.ExtractAssociatedIcon(Application.ExecutablePath)) src = ico.ToBitmap();
                var bmp = new Bitmap(size, size);
                using (var g = Graphics.FromImage(bmp))
                using (var attr = new ImageAttributes())
                {
                    g.Clear(Color.Transparent);
                    g.InterpolationMode = InterpolationMode.HighQualityBicubic;
                    g.PixelOffsetMode = PixelOffsetMode.HighQuality;
                    if (gray)
                        attr.SetColorMatrix(new ColorMatrix(new float[][] {
                            new float[] { 0.30f, 0.30f, 0.30f, 0, 0 },
                            new float[] { 0.59f, 0.59f, 0.59f, 0, 0 },
                            new float[] { 0.11f, 0.11f, 0.11f, 0, 0 },
                            new float[] { 0, 0, 0, 1, 0 },
                            new float[] { 0, 0, 0, 0, 1 } }));
                    g.DrawImage(src, new Rectangle(0, 0, size, size), 0, 0, src.Width, src.Height, GraphicsUnit.Pixel, attr);
                }
                return bmp;
            }
            finally { if (src != null) src.Dispose(); }
        }

        // .ico の中から、求める大きさ以上で最も小さい画像を読む。make_icon.py（Pillow）は各サイズを PNG で入れるが、
        // System.Drawing.Icon は PNG の項目を正しく読めないことがあるので、PNG は Bitmap として直接読む
        static Bitmap LoadEntry(byte[] ico, int size)
        {
            try
            {
                int count = BitConverter.ToUInt16(ico, 4), best = -1, bestSize = 0;
                for (int i = 0; i < count; i++)
                {
                    int s = ico[6 + i * 16] == 0 ? 256 : ico[6 + i * 16];
                    bool better = best < 0 || (s >= size ? (bestSize < size || s < bestSize) : (bestSize < size && s > bestSize));
                    if (better) { best = i; bestSize = s; }
                }
                if (best < 0) return null;
                int length = BitConverter.ToInt32(ico, 6 + best * 16 + 8), offset = BitConverter.ToInt32(ico, 6 + best * 16 + 12);
                bool png = ico[offset] == 0x89 && ico[offset + 1] == (byte)'P' && ico[offset + 2] == (byte)'N' && ico[offset + 3] == (byte)'G';
                if (png)
                    using (var ms = new MemoryStream(ico, offset, length))
                    using (var decoded = new Bitmap(ms)) return new Bitmap(decoded);   // GDI+ は元のストリームを使い続けるので複製する
                using (var ms = new MemoryStream(ico))
                using (var icon = new Icon(ms, size, size)) return icon.ToBitmap();
            }
            catch { return null; }
        }

        public static Icon Make(int size, bool gray)
        {
            using (var bmp = Render(size, gray)) return Icon.FromHandle(bmp.GetHicon());
        }
    }
}
