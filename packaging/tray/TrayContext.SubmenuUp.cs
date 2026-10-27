// 子メニューを、親の項目より上に向かって開く（通知領域のメニューは画面の下にあるため）。
// Windows 標準（Win32）のメニューは、子メニューを親の項目の上端に合わせて下へ開くので、
// 子メニューのウィンドウが開いたことを WinEvent で受け取り、下端が親の項目の下端にそろうよう上へ移す。
using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace PokeControllerTray
{
    partial class TrayContext
    {
        delegate void WinEventProc(IntPtr hook, uint evt, IntPtr hwnd, int idObject, int idChild, uint thread, uint time);

        [DllImport("user32.dll")] static extern IntPtr SetWinEventHook(uint min, uint max, IntPtr module, WinEventProc proc, uint pid, uint tid, uint flags);
        [DllImport("user32.dll")] static extern bool GetMenuItemRect(IntPtr hwnd, IntPtr hmenu, uint item, out RECT rc);
        [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr hwnd, out RECT rc);
        [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int cx, int cy, uint flags);

        [StructLayout(LayoutKind.Sequential)] struct RECT { public int Left, Top, Right, Bottom; }

        const uint EVENT_SYSTEM_MENUPOPUPSTART = 0x0006, EVENT_SYSTEM_MENUPOPUPEND = 0x0007;
        const uint SWP_NOSIZE = 0x0001, SWP_NOZORDER = 0x0004, SWP_NOACTIVATE = 0x0010;

        WinEventProc submenuProc;   // ガベージコレクションで消えないよう保持する
        int openPopups;
        IntPtr selectedPopupMenu = IntPtr.Zero;   // 最後に選ばれた「子メニューを持つ項目」（WM_MENUSELECT で記録）
        int selectedPopupPos = -1;

        void InitSubmenuUp()
        {
            // 数え間違いが残らないよう、開くたび・閉じるたびに戻す
            menu.Popup += delegate { openPopups = 0; selectedPopupMenu = IntPtr.Zero; };
            menu.Collapse += delegate { openPopups = 0; selectedPopupMenu = IntPtr.Zero; };
            submenuProc = OnMenuPopupEvent;
            SetWinEventHook(EVENT_SYSTEM_MENUPOPUPSTART, EVENT_SYSTEM_MENUPOPUPEND, IntPtr.Zero, submenuProc,
                (uint)System.Diagnostics.Process.GetCurrentProcess().Id, 0, 0 /* WINEVENT_OUTOFCONTEXT */);
        }

        // WM_MENUSELECT から呼ぶ。子メニューを持つ項目が選ばれたら、その位置を覚えておく
        void RememberPopupSelection(IntPtr hmenu, int pos, int flags)
        {
            if (flags != 0xFFFF && (flags & 0x10 /* MF_POPUP */) != 0) { selectedPopupMenu = hmenu; selectedPopupPos = pos; }
        }

        void OnMenuPopupEvent(IntPtr hook, uint evt, IntPtr hwnd, int idObject, int idChild, uint thread, uint time)
        {
            if (evt == EVENT_SYSTEM_MENUPOPUPEND) { if (openPopups > 0) openPopups--; return; }
            openPopups++;
            if (openPopups < 2 || selectedPopupMenu == IntPtr.Zero) return;   // 最初のメニュー（通知領域のメニュー本体）は動かさない
            try
            {
                RECT item, sub;
                if (!GetMenuItemRect(IntPtr.Zero, selectedPopupMenu, (uint)selectedPopupPos, out item)) return;
                if (!GetWindowRect(hwnd, out sub)) return;
                int itemHeight = item.Bottom - item.Top, height = sub.Bottom - sub.Top;
                int k = item.Top - sub.Top;   // 標準の位置では、子メニューの上端は親の項目の上端より少し上
                if (k < 0 || k > itemHeight) return;   // すでに上へ開いている（画面に収まらなかった）場合はそのまま
                int top = item.Bottom + k - height;
                int workTop = Screen.FromHandle(hwnd).WorkingArea.Top;
                if (top < workTop) top = workTop;
                if (top >= sub.Top) return;
                SetWindowPos(hwnd, IntPtr.Zero, sub.Left, top, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE);
            }
            catch { }
        }
    }
}
