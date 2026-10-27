// メニュー項目にマウスを乗せたときの説明（説明が要る項目だけ）。
// Windows 標準（Win32）のメニューには項目ごとのツールチップがないため、メニューの持ち主である
// NotifyIcon のウィンドウに届く WM_MENUSELECT を受け取り、少し待ってから小さな説明を表示する。
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace PokeControllerTray
{
    partial class TrayContext
    {
        readonly Dictionary<MenuItem, Func<string>> hoverTexts = new Dictionary<MenuItem, Func<string>>();
        MenuSelectHook hoverHook;
        HoverTip hoverTip;
        System.Windows.Forms.Timer hoverTimer;
        Func<string> hoverPending;

        static readonly PropertyInfo MenuIdProperty = typeof(MenuItem).GetProperty("MenuID", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);

        [DllImport("user32.dll")] static extern IntPtr GetSubMenu(IntPtr hMenu, int nPos);

        void SetHover(MenuItem item, Func<string> text) { hoverTexts[item] = text; }

        void InitMenuHover()
        {
            hoverTimer = new System.Windows.Forms.Timer { Interval = 450 };
            hoverTimer.Tick += delegate
            {
                hoverTimer.Stop();
                string text = hoverPending == null ? null : hoverPending();
                if (string.IsNullOrEmpty(text)) { HideHover(); return; }
                if (hoverTip == null || hoverTip.IsDisposed) hoverTip = new HoverTip();
                hoverTip.ShowAt(text, Cursor.Position);
            };
            menu.Collapse += delegate { HideHover(); };

            try
            {
                var field = typeof(NotifyIcon).GetField("window", BindingFlags.Instance | BindingFlags.NonPublic);
                var owner = field == null ? null : field.GetValue(tray) as NativeWindow;
                if (owner == null || owner.Handle == IntPtr.Zero) return;
                hoverHook = new MenuSelectHook(this);
                hoverHook.AssignHandle(owner.Handle);
            }
            catch { }   // 取れない環境では説明を出さないだけ
        }

        void HideHover()
        {
            hoverPending = null;
            if (hoverTimer != null) hoverTimer.Stop();
            if (hoverTip != null && !hoverTip.IsDisposed) hoverTip.Hide();
        }

        // WM_MENUSELECT: wParam の下位 = 項目 ID（サブメニューを持つ項目は位置）、上位 = フラグ、lParam = メニュー
        internal void OnMenuSelect(IntPtr hmenu, int idOrPos, int flags)
        {
            if (flags == 0xFFFF && hmenu == IntPtr.Zero) { HideHover(); return; }   // メニューが閉じた
            MenuItem item = FindMenuItem(menu.MenuItems, hmenu, idOrPos, (flags & 0x10 /* MF_POPUP */) != 0);
            Func<string> text;
            if (item == null || !hoverTexts.TryGetValue(item, out text)) { HideHover(); return; }
            if (hoverPending == text && hoverTip != null && hoverTip.Visible) return;
            if (hoverTip != null && !hoverTip.IsDisposed) hoverTip.Hide();
            hoverPending = text;
            hoverTimer.Stop();
            hoverTimer.Start();
        }

        static MenuItem FindMenuItem(Menu.MenuItemCollection items, IntPtr hmenu, int idOrPos, bool popup)
        {
            IntPtr sub = popup ? GetSubMenu(hmenu, idOrPos) : IntPtr.Zero;
            foreach (MenuItem mi in items)
            {
                if (popup)
                {
                    if (mi.MenuItems.Count > 0 && mi.Handle == sub) return mi;
                }
                else if (mi.MenuItems.Count == 0 && MenuIdProperty != null)
                {
                    try { if ((int)MenuIdProperty.GetValue(mi, null) == idOrPos) return mi; } catch { }
                }
                if (mi.MenuItems.Count > 0)
                {
                    var found = FindMenuItem(mi.MenuItems, hmenu, idOrPos, popup);
                    if (found != null) return found;
                }
            }
            return null;
        }

        class MenuSelectHook : NativeWindow
        {
            readonly TrayContext owner;
            public MenuSelectHook(TrayContext owner) { this.owner = owner; }

            protected override void WndProc(ref Message m)
            {
                if (m.Msg == 0x011F /* WM_MENUSELECT */)
                {
                    long w = m.WParam.ToInt64();
                    try { owner.RememberPopupSelection(m.LParam, (int)(w & 0xFFFF), (int)((w >> 16) & 0xFFFF)); } catch { }
                    try { owner.OnMenuSelect(m.LParam, (int)(w & 0xFFFF), (int)((w >> 16) & 0xFFFF)); } catch { }
                }
                base.WndProc(ref m);
            }
        }
    }

    // 説明用の小さな吹き出し（Windows 11 のツールチップに近い見た目。フォーカスは奪わない）
    class HoverTip : Form
    {
        [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);
        [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags);

        string text = "";
        readonly bool dark = Theme.IsDark;

        public HoverTip()
        {
            FormBorderStyle = FormBorderStyle.None;
            ShowInTaskbar = false;
            StartPosition = FormStartPosition.Manual;
            Font = new Font(L.UiFont, 9f);
            BackColor = dark ? Color.FromArgb(0x2B, 0x2B, 0x2B) : Color.FromArgb(0xF9, 0xF9, 0xF9);
            SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint | ControlStyles.UserPaint, true);
        }

        protected override bool ShowWithoutActivation { get { return true; } }

        protected override CreateParams CreateParams
        {
            get
            {
                var cp = base.CreateParams;
                cp.ExStyle |= 0x08000000 /* NOACTIVATE */ | 0x80 /* TOOLWINDOW */ | 0x8 /* TOPMOST */;
                cp.ClassStyle |= 0x20000;   // CS_DROPSHADOW
                return cp;
            }
        }

        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            int round = 3;   // DWMWCP_ROUNDSMALL（Windows 11）
            try { DwmSetWindowAttribute(Handle, 33 /* DWMWA_WINDOW_CORNER_PREFERENCE */, ref round, sizeof(int)); } catch { }
        }

        Padding Pad { get { return new Padding(ModernDialog.Px(10), ModernDialog.Px(7), ModernDialog.Px(10), ModernDialog.Px(8)); } }

        public void ShowAt(string value, Point cursor)
        {
            text = value;
            var pad = Pad;
            var sz = TextRenderer.MeasureText(text, Font, new Size(ModernDialog.Px(340), int.MaxValue), TextFormatFlags.WordBreak);
            int w = sz.Width + pad.Horizontal + 2, h = sz.Height + pad.Vertical + 2;
            var area = Screen.FromPoint(cursor).WorkingArea;
            int x = cursor.X + ModernDialog.Px(14), y = cursor.Y + ModernDialog.Px(20);
            if (x + w > area.Right) x = Math.Max(area.Left, cursor.X - w - ModernDialog.Px(8));
            if (y + h > area.Bottom) y = Math.Max(area.Top, cursor.Y - h - ModernDialog.Px(8));
            Bounds = new Rectangle(x, y, w, h);
            Invalidate();
            if (!Visible) Show();
            // メニュー（最前面）より上に出す
            SetWindowPos(Handle, new IntPtr(-1) /* HWND_TOPMOST */, x, y, w, h, 0x0010 /* NOACTIVATE */ | 0x0040 /* SHOWWINDOW */);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(BackColor);
            using (var pen = new Pen(dark ? Color.FromArgb(0x48, 0x48, 0x48) : Color.FromArgb(0xD8, 0xD8, 0xD8)))
                g.DrawRectangle(pen, 0, 0, Width - 1, Height - 1);
            var pad = Pad;
            var r = new Rectangle(pad.Left + 1, pad.Top + 1, Width - pad.Horizontal - 2, Height - pad.Vertical - 2);
            TextRenderer.DrawText(g, text, Font, r, dark ? Color.FromArgb(0xF0, 0xF0, 0xF0) : Color.FromArgb(0x1B, 0x1B, 0x1B), TextFormatFlags.WordBreak | TextFormatFlags.Left | TextFormatFlags.Top);
        }
    }
}
