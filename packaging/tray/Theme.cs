// Windows のライト/ダーク設定への追従（設定は読むだけ）。
using System;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using Microsoft.Win32;

namespace PokeControllerTray
{
    static class Theme
    {
        [DllImport("dwmapi.dll")]
        static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);
        const int DWMWA_USE_IMMERSIVE_DARK_MODE = 20;
        [DllImport("user32.dll")]
        static extern bool DestroyIcon(IntPtr handle);

        // アプリのモード（設定 → 個人用設定 → 色 →「既定のアプリ モード」）
        public static bool IsDark
        {
            get
            {
                try
                {
                    using (var k = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"))
                    {
                        object v = k == null ? null : k.GetValue("AppsUseLightTheme");
                        return v != null && Convert.ToInt32(v) == 0;
                    }
                }
                catch { return false; }
            }
        }

        public static readonly Color DarkBack = Color.FromArgb(0x20, 0x20, 0x20);
        public static readonly Color DarkMenu = Color.FromArgb(0x2B, 0x2B, 0x2B);
        public static readonly Color DarkHover = Color.FromArgb(0x3D, 0x3D, 0x3D);
        public static readonly Color DarkLine = Color.FromArgb(0x45, 0x45, 0x45);
        public static readonly Color DarkText = Color.FromArgb(0xF0, 0xF0, 0xF0);
        public static readonly Color DarkDisabled = Color.FromArgb(0x8A, 0x8A, 0x8A);

        // タイトルバーをダーク/ライトにする（Windows 10 20H1 以降）
        public static void ApplyTitleBar(Form form)
        {
            if (!form.IsHandleCreated) return;
            int on = IsDark ? 1 : 0;
            try { DwmSetWindowAttribute(form.Handle, DWMWA_USE_IMMERSIVE_DARK_MODE, ref on, sizeof(int)); } catch { }
        }

        // タイトルバー左の小さいアイコン。exe のアイコンは盾が枠いっぱいで、タイトルバーでは上と左が詰まって見えるため、
        // 実際の小アイコンの大きさ（拡大率に応じた 16/20/24 px など）の中央に、少し小さく描いて余白を取る
        public static Icon TitleBarIcon()
        {
            try
            {
                int size;
                using (var g = Graphics.FromHwnd(IntPtr.Zero)) size = (int)Math.Round(16 * g.DpiX / 96f);
                int glyph = size;   // アイコン自体に余白があるので、そのままの大きさで描く
                using (var bmp = new Bitmap(size, size))
                using (var mark = AppIcon.Render(glyph, false))
                {
                    using (var g = Graphics.FromImage(bmp))
                    {
                        g.Clear(Color.Transparent);
                        int off = (size - glyph) / 2;
                        g.DrawImageUnscaled(mark, off, off + ((size - glyph) % 2));
                    }
                    IntPtr h = bmp.GetHicon();
                    try
                    {
                        using (var temp = Icon.FromHandle(h)) return (Icon)temp.Clone();
                    }
                    finally { DestroyIcon(h); }   // FromHandle はハンドルを解放しない
                }
            }
            catch
            {
                try { return Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { return null; }
            }
        }

        // Windows 標準（Win32）のメニューを、OS のライト/ダーク設定に追従させる。
        // uxtheme.dll の非公開 API（序数 135 SetPreferredAppMode / 136 FlushMenuThemes）で、
        // エクスプローラーなど Windows 自身と同じ仕組み。使えない環境では何もしない（ライト表示のまま）。
        [DllImport("uxtheme.dll", EntryPoint = "#135")] static extern int SetPreferredAppMode(int mode);
        [DllImport("uxtheme.dll", EntryPoint = "#136")] static extern void FlushMenuThemes();

        public static void FollowSystemForMenus()
        {
            try { SetPreferredAppMode(1 /* AllowDark: システム設定に従う */); FlushMenuThemes(); } catch { }
        }

        // モード切り替え後に開いたメニューへ反映する
        public static void RefreshMenus()
        {
            try { FlushMenuThemes(); } catch { }
        }
    }
}
