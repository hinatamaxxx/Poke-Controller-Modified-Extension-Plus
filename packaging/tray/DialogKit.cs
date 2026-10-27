// 確認画面（セットアップ・アンインストール・終了）の共通部品。Windows 11 の標準ダイアログに近い見た目:
// 上に本文、下に色の違うボタン帯、角丸のボタンとチェックボックス。高 DPI と Windows のライト/ダークに対応する。
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace PokeControllerTray
{
    // 削除・終了のような操作も赤くせず、主ボタンと同じ落ち着いた色にする（不安をあおらない）
    enum ButtonKind { Normal, Primary }

    class DialogPalette
    {
        public readonly bool Dark;
        public readonly Color Back, Footer, Line, Fore, Sub, Accent, AccentText;

        public DialogPalette()
        {
            Dark = Theme.IsDark;
            Back = Dark ? Color.FromArgb(0x2B, 0x2B, 0x2B) : Color.White;
            Footer = Dark ? Color.FromArgb(0x20, 0x20, 0x20) : Color.FromArgb(0xF3, 0xF3, 0xF3);
            Line = Dark ? Color.FromArgb(0x1A, 0x1A, 0x1A) : Color.FromArgb(0xE5, 0xE5, 0xE5);
            Fore = Dark ? Color.White : Color.FromArgb(0x1B, 0x1B, 0x1B);
            Sub = Dark ? Color.FromArgb(0xC5, 0xC5, 0xC5) : Color.FromArgb(0x5C, 0x5C, 0x5C);
            // Windows 11 の既定のアクセント（青）。ダークでは明るい色に濃い文字
            Accent = Dark ? Color.FromArgb(0x4C, 0xC2, 0xFF) : Color.FromArgb(0x00, 0x5F, 0xB8);
            AccentText = Dark ? Color.FromArgb(0x00, 0x1A, 0x2E) : Color.White;
        }
    }

    // 本文（アイコン・見出し・文章・チェックボックス）と、下のボタン帯からなるダイアログ
    class ModernDialog : Form
    {
        protected readonly DialogPalette P = new DialogPalette();
        protected readonly Label TitleLabel;
        protected readonly FlowLayoutPanel Stack;      // 見出しの下に縦に積む領域
        // 下の帯のボタン（追加した順に右から並ぶ）。帯（footer）の中ではなくウィンドウ直下に置き、OnLayout で帯の上に並べる。
        // WinForms は表示の瞬間、Windows の「既定のボタンにマウスを自動で移動する」がオンなら既定のボタンへカーソルを移すが、
        // ボタンの位置をウィンドウ直下の部品として計算するので、帯の中に入れると移動先がずれる
        readonly List<ModernButton> buttons = new List<ModernButton>();
        readonly int textWidth;
        readonly Panel footer;
        readonly RowStyle footerRow;
        readonly int footerHeight = Px(18) * 2 + Px(34);   // 上下の余白 18 ＋ ボタンの高さ 34
        Point center;
        bool centerKnown;

        public ModernDialog(string caption, string title, int widthLogical = 440)
        {
            textWidth = Px(widthLogical);
            Text = caption;
            Icon = Theme.TitleBarIcon();
            Font = new Font(L.UiFont, 9.75f);
            AutoScaleMode = AutoScaleMode.None;   // 大きさは Px() で実際の拡大率から求める
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            ShowInTaskbar = true;
            StartPosition = FormStartPosition.CenterScreen;
            AutoSize = true;
            AutoSizeMode = AutoSizeMode.GrowAndShrink;
            BackColor = P.Back;
            ForeColor = P.Fore;

            var root = new TableLayoutPanel { ColumnCount = 1, RowCount = 2, AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink, Margin = new Padding(0), Padding = new Padding(0), BackColor = P.Back };
            root.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));

            var content = new TableLayoutPanel { ColumnCount = 2, AutoSize = true, BackColor = P.Back, Margin = new Padding(0), Padding = new Padding(Px(28), Px(26), Px(32), Px(18)) };
            content.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            content.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            var logo = new PictureBox { Image = AppIcon.Render(Px(36), false), SizeMode = PictureBoxSizeMode.AutoSize, Margin = new Padding(0, Px(2), Px(16), 0) };
            content.Controls.Add(logo, 0, 0);

            Stack = new FlowLayoutPanel { FlowDirection = FlowDirection.TopDown, WrapContents = false, AutoSize = true, BackColor = P.Back, Margin = new Padding(0) };
            TitleLabel = new Label
            {
                Text = title,
                UseMnemonic = false,   // 「&」をそのまま表示する
                Font = new Font(L.UiFontSemibold, 14f),
                AutoSize = true,
                MaximumSize = new Size(textWidth, 0),
                ForeColor = P.Fore,
                Margin = new Padding(0, 0, 0, Px(12))
            };
            Stack.Controls.Add(TitleLabel);
            content.Controls.Add(Stack, 1, 0);
            root.Controls.Add(content, 0, 0);

            footer = new Panel { Dock = DockStyle.Fill, BackColor = P.Footer, Margin = new Padding(0) };
            footer.Paint += delegate(object s, PaintEventArgs e) { using (var pen = new Pen(P.Line)) e.Graphics.DrawLine(pen, 0, 0, footer.Width, 0); };
            root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            footerRow = new RowStyle(SizeType.Absolute, footerHeight);
            root.RowStyles.Add(footerRow);
            root.Controls.Add(footer, 0, 1);

            Controls.Add(root);
            HandleCreated += delegate { Theme.ApplyTitleBar(this); };
        }

        // 表示する前にレイアウトを確定させ、その大きさで画面の中央に置く。Windows の「既定のボタンにマウスを
        // 自動で移動する」は表示した瞬間のボタンの位置へ動かすので、レイアウトが表示後にずれ込むと移動先がずれる
        protected override void OnLoad(EventArgs e)
        {
            base.OnLoad(e);
            LayoutAll(this);
            CenterToScreen();
        }

        static void LayoutAll(Control c)
        {
            foreach (Control child in c.Controls) LayoutAll(child);
            c.PerformLayout();
        }

        // 画面の切り替えで大きさが変わっても、中心の位置を保つ
        protected override void OnShown(EventArgs e) { base.OnShown(e); center = new Point(Left + Width / 2, Top + Height / 2); centerKnown = true; }
        // 最小化中（位置が -32000 になる）や最大化中は記録も移動もしない
        protected override void OnMove(EventArgs e) { base.OnMove(e); if (centerKnown && WindowState == FormWindowState.Normal) center = new Point(Left + Width / 2, Top + Height / 2); }
        protected override void OnSizeChanged(EventArgs e)
        {
            base.OnSizeChanged(e);
            if (!centerKnown || WindowState != FormWindowState.Normal) return;
            var c = center;
            Location = new Point(c.X - Width / 2, c.Y - Height / 2);
            center = c;
        }

        // 実際の画面の拡大率でピクセル数を求める（ハンドル作成前でも使える）
        public static int Px(int logical)
        {
            using (var g = Graphics.FromHwnd(IntPtr.Zero)) return (int)Math.Round(logical * g.DpiX / 96f);
        }

        protected Label AddText(string text, bool emphasis = false)
        {
            var l = new Label
            {
                Text = text,
                UseMnemonic = false,
                AutoSize = true,
                MaximumSize = new Size(textWidth, 0),
                ForeColor = emphasis ? P.Fore : P.Sub,
                Margin = new Padding(0, 0, 0, Px(12))
            };
            Stack.Controls.Add(l);
            return l;
        }

        // 「・」で始まる箇条書き（2 行目以降も字下げをそろえる）
        protected void AddBullets(params string[] items)
        {
            var t = new TableLayoutPanel { ColumnCount = 2, AutoSize = true, BackColor = P.Back, Margin = new Padding(Px(2), 0, 0, Px(12)) };
            t.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            t.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            for (int i = 0; i < items.Length; i++)
            {
                t.Controls.Add(new Label { Text = "•", AutoSize = true, ForeColor = P.Sub, Margin = new Padding(0, 0, Px(8), Px(6)) }, 0, i);
                t.Controls.Add(new Label { Text = items[i], UseMnemonic = false, AutoSize = true, MaximumSize = new Size(textWidth - Px(20), 0), ForeColor = P.Fore, Margin = new Padding(0, 0, 0, Px(6)) }, 1, i);
            }
            Stack.Controls.Add(t);
        }

        protected ModernCheckBox AddCheck(string text, bool on)
        {
            var c = new ModernCheckBox(P) { Text = text, Checked = on, Margin = new Padding(0, Px(2), 0, Px(10)), MaximumSize = new Size(textWidth, 0) };
            Stack.Controls.Add(c);
            return c;
        }

        // 画面を切り替える（見出しを変え、本文とボタンを空にする）
        protected void ResetPage(string title)
        {
            SuspendLayout();
            TitleLabel.Text = title;
            while (Stack.Controls.Count > 1) { var c = Stack.Controls[1]; Stack.Controls.RemoveAt(1); c.Dispose(); }
            foreach (var b in buttons) { Controls.Remove(b); b.Dispose(); }
            buttons.Clear();
            footer.Visible = false;   // ボタンがない画面（処理中など）ではボタン帯ごと隠す
            footerRow.Height = 0;
            AcceptButton = null;
            CancelButton = null;
            ResumeLayout(true);
        }

        protected void AddControl(Control c) { Stack.Controls.Add(c); }

        protected ModernButton AddButton(string text, ButtonKind kind)
        {
            var b = new ModernButton(P, kind) { Text = text };
            footer.Visible = true;
            footerRow.Height = footerHeight;
            buttons.Add(b);
            Controls.Add(b);
            b.BringToFront();
            PerformLayout();
            return b;
        }

        // ボタンを帯の上に右から並べる（帯の右の余白 28、ボタンの間 8、上下は中央）
        protected override void OnLayout(LayoutEventArgs e)
        {
            base.OnLayout(e);
            if (footer == null || !footer.Visible) return;
            var root = footer.Parent;
            int right = root.Left + footer.Right - Px(28);
            int top = root.Top + footer.Top;
            foreach (var b in buttons)
            {
                right -= b.Width;
                b.Location = new Point(right, top + (footerHeight - b.Height) / 2);
                right -= Px(8);
            }
        }
    }

    // 角丸のボタン（Windows 11 風）。DialogResult・AcceptButton などは通常の Button と同じに使える
    class ModernButton : Button
    {
        readonly DialogPalette p;
        readonly ButtonKind kind;
        bool hover, down;

        public ModernButton(DialogPalette palette, ButtonKind kind)
        {
            p = palette;
            this.kind = kind;
            SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
            AutoSize = false;
            AccessibleRole = AccessibleRole.PushButton;   // 自分で描いても、読み上げソフトや UI オートメーションからはボタンとして扱う
        }

        protected override void OnTextChanged(EventArgs e)
        {
            base.OnTextChanged(e);
            var sz = TextRenderer.MeasureText(Text, Font);
            Size = new Size(Math.Max(ModernDialog.Px(108), sz.Width + ModernDialog.Px(32)), ModernDialog.Px(34));
        }

        protected override void OnFontChanged(EventArgs e) { base.OnFontChanged(e); OnTextChanged(e); }
        protected override void OnMouseEnter(EventArgs e) { hover = true; Invalidate(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { hover = false; down = false; Invalidate(); base.OnMouseLeave(e); }
        protected override void OnMouseDown(MouseEventArgs e) { if (e.Button == MouseButtons.Left) { down = true; Invalidate(); } base.OnMouseDown(e); }
        protected override void OnMouseUp(MouseEventArgs e) { down = false; Invalidate(); base.OnMouseUp(e); }
        protected override void OnEnabledChanged(EventArgs e) { Invalidate(); base.OnEnabledChanged(e); }

        static Color Shade(Color c, float f)
        {
            // f < 0 で暗く、f > 0 で明るく
            if (f < 0) return Color.FromArgb(c.A, (int)(c.R * (1 + f)), (int)(c.G * (1 + f)), (int)(c.B * (1 + f)));
            return Color.FromArgb(c.A, (int)(c.R + (255 - c.R) * f), (int)(c.G + (255 - c.G) * f), (int)(c.B + (255 - c.B) * f));
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(p.Footer);   // 下の帯の上に置く（親はウィンドウ）
            g.SmoothingMode = SmoothingMode.AntiAlias;
            Color fill, border, text;
            if (kind == ButtonKind.Normal)
            {
                fill = p.Dark ? Color.FromArgb(0x37, 0x37, 0x37) : Color.FromArgb(0xFD, 0xFD, 0xFD);
                if (hover) fill = p.Dark ? Color.FromArgb(0x3F, 0x3F, 0x3F) : Color.FromArgb(0xF5, 0xF5, 0xF5);
                if (down) fill = p.Dark ? Color.FromArgb(0x30, 0x30, 0x30) : Color.FromArgb(0xEC, 0xEC, 0xEC);
                border = p.Dark ? Color.FromArgb(0x48, 0x48, 0x48) : Color.FromArgb(0xD1, 0xD1, 0xD1);
                text = p.Fore;
            }
            else
            {
                float step = p.Dark ? -0.08f : -0.1f;
                fill = down ? Shade(p.Accent, step * 2) : hover ? Shade(p.Accent, step) : p.Accent;
                border = fill;
                text = p.AccentText;
            }
            if (!Enabled)
            {
                fill = p.Dark ? Color.FromArgb(0x33, 0x33, 0x33) : Color.FromArgb(0xF0, 0xF0, 0xF0);
                border = p.Dark ? Color.FromArgb(0x3C, 0x3C, 0x3C) : Color.FromArgb(0xDD, 0xDD, 0xDD);
                text = p.Dark ? Color.FromArgb(0x78, 0x78, 0x78) : Color.FromArgb(0xA0, 0xA0, 0xA0);
            }
            int r = ModernDialog.Px(4);
            var rect = new Rectangle(1, 1, Width - 3, Height - 3);
            using (var path = RoundRect(rect, r))
            using (var b = new SolidBrush(fill))
            using (var pen = new Pen(border))
            {
                g.FillPath(b, path);
                g.DrawPath(pen, path);
            }
            if (Focused && ShowFocusCues)
            {
                using (var path = RoundRect(new Rectangle(0, 0, Width - 1, Height - 1), r + 1))
                using (var pen = new Pen(p.Fore, 1.5f)) g.DrawPath(pen, path);
            }
            TextRenderer.DrawText(g, Text, Font, ClientRectangle, text, TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.SingleLine);
        }

        internal static GraphicsPath RoundRect(Rectangle r, int radius)
        {
            int d = radius * 2;
            var path = new GraphicsPath();
            path.AddArc(r.X, r.Y, d, d, 180, 90);
            path.AddArc(r.Right - d, r.Y, d, d, 270, 90);
            path.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
            path.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
            path.CloseFigure();
            return path;
        }
    }

    // 角丸の四角にチェックを描くチェックボックス（Windows 11 風）
    class ModernCheckBox : CheckBox
    {
        readonly DialogPalette p;
        bool hover;

        public ModernCheckBox(DialogPalette palette)
        {
            p = palette;
            SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
            AutoSize = true;
            AccessibleRole = AccessibleRole.CheckButton;
        }

        int Box { get { return ModernDialog.Px(18); } }
        int Gap { get { return ModernDialog.Px(10); } }

        public override Size GetPreferredSize(Size proposed)
        {
            int maxText = MaximumSize.Width > 0 ? MaximumSize.Width - Box - Gap : int.MaxValue;
            var sz = TextRenderer.MeasureText(Text, Font, new Size(maxText, int.MaxValue), TextFormatFlags.WordBreak);
            return new Size(Box + Gap + sz.Width + ModernDialog.Px(2), Math.Max(Box, sz.Height) + ModernDialog.Px(4));
        }

        protected override void OnMouseEnter(EventArgs e) { hover = true; Invalidate(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { hover = false; Invalidate(); base.OnMouseLeave(e); }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Parent != null ? Parent.BackColor : p.Back);
            g.SmoothingMode = SmoothingMode.AntiAlias;
            int lineH = TextRenderer.MeasureText("あA", Font).Height;   // 1 行の高さ（日本語の文字を含めて測る）
            int top = Math.Max(0, (lineH - Box) / 2) + ModernDialog.Px(1);
            var box = new Rectangle(1, top, Box - 2, Box - 2);
            using (var path = ModernButton.RoundRect(box, ModernDialog.Px(4)))
            {
                if (Checked)
                {
                    Color fill = hover ? (p.Dark ? Color.FromArgb(0x6C, 0xCF, 0xFF) : Color.FromArgb(0x00, 0x52, 0x9E)) : p.Accent;
                    using (var b = new SolidBrush(fill)) g.FillPath(b, path);
                    float s = box.Width / 16f;
                    using (var pen = new Pen(p.AccentText, 1.6f * s * 1.2f) { StartCap = LineCap.Round, EndCap = LineCap.Round, LineJoin = LineJoin.Round })
                        g.DrawLines(pen, new[] {
                            new PointF(box.X + 4 * s, box.Y + 8.2f * s),
                            new PointF(box.X + 6.8f * s, box.Y + 11 * s),
                            new PointF(box.X + 12 * s, box.Y + 5.2f * s) });
                }
                else
                {
                    Color fill = p.Dark ? Color.FromArgb(hover ? 0x34 : 0x27, hover ? 0x34 : 0x27, hover ? 0x34 : 0x27) : (hover ? Color.FromArgb(0xF0, 0xF0, 0xF0) : Color.FromArgb(0xFA, 0xFA, 0xFA));
                    using (var b = new SolidBrush(fill)) g.FillPath(b, path);
                    using (var pen = new Pen(p.Dark ? Color.FromArgb(0x9A, 0x9A, 0x9A) : Color.FromArgb(0x86, 0x86, 0x86))) g.DrawPath(pen, path);
                }
            }
            var textRect = new Rectangle(Box + Gap, 0, Width - Box - Gap, Height);
            TextRenderer.DrawText(g, Text, Font, textRect, Enabled ? p.Fore : p.Sub, TextFormatFlags.WordBreak | TextFormatFlags.Left | TextFormatFlags.Top);
            if (Focused && ShowFocusCues)
            {
                using (var path = ModernButton.RoundRect(new Rectangle(0, top - 1, Box, Box), ModernDialog.Px(5)))
                using (var pen = new Pen(p.Fore, 1.2f)) g.DrawPath(pen, path);
            }
        }
    }
}
