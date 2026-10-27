// MIT. PokeControllerMCP.exe: starts the MCP server (controller_mcp.py) with the Python chosen at install time,
// handing it this process's stdio. The tray app, window and install/uninstall screens live in packaging\tray.
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

static class Launcher {
    const string AppName = "PokeController";

    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    static extern int SetCurrentProcessExplicitAppUserModelID(string id);

    static string Quote(string value) {
        var result = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in value) {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') { result.Append('\\', slashes * 2 + 1); }
            else { result.Append('\\', slashes); }
            result.Append(c); slashes = 0;
        }
        result.Append('\\', slashes * 2);
        return result.Append('"').ToString();
    }

    static string Root { get { return AppDomain.CurrentDomain.BaseDirectory; } }

    // Python recorded by install.ps1, or a runtime-python folder beside a portable copy.
    static string FindPython() {
        // The copy beside the exe comes first: packaged (MSIX) parents such as some MCP clients
        // can see a virtualized %APPDATA% that does not contain the installer's record.
        string beside = Path.Combine(Root, "python.txt");
        string recorded = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), AppName, "python.txt");
        string python = null;
        if (File.Exists(Path.Combine(Root, "portable")) && File.Exists(Path.Combine(Root, "runtime-python", "python.exe")))
            python = Path.Combine(Root, "runtime-python", "python.exe");
        else if (File.Exists(beside))
            python = File.ReadAllText(beside).Trim();
        else if (File.Exists(recorded))
            python = File.ReadAllText(recorded).Trim();
        if (python == null || !File.Exists(python)) return null;
        return python;  // stdio needs the console interpreter
    }

    static int Main(string[] args) {
        SetCurrentProcessExplicitAppUserModelID("hinatamaxxx.PokeController");
        string python = FindPython();
        if (python == null) {
            Console.Error.WriteLine("Pythonの実行環境が見つかりません。インストールをやり直すか、install.ps1 の -Python で使うPythonを指定してください。");
            return 1;
        }
        // The dedicated environment ignores the user's own site-packages; a Python the user chose keeps them.
        string dedicated = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), AppName);
        var arguments = new StringBuilder(python.StartsWith(dedicated, StringComparison.OrdinalIgnoreCase) ? "-E -s " : "-E ");
        // Bootstrap adds the trusted application directory explicitly.
        arguments.Append(Quote(Path.Combine(Root, "bootstrap.py"))).Append(" ").Append(Quote("controller_mcp.py"));
        foreach (string arg in args) arguments.Append(" ").Append(Quote(arg));
        Environment.SetEnvironmentVariable("PYTHONHOME", null);
        Environment.SetEnvironmentVariable("PYTHONPATH", null);
        try {
            return RunWithOurStdio(python, arguments.ToString());
        } catch (Exception e) {
            string log = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), AppName, "launch-error.txt");
            Directory.CreateDirectory(Path.GetDirectoryName(log));
            File.WriteAllText(log, e.ToString());
            Console.Error.WriteLine("Pythonを起動できませんでした。詳細: " + log);
            return 1;
        }
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct StartupInfo {
        public int cb; public string reserved, desktop, title;
        public int x, y, width, height, columns, rows, fill, flags;
        public short show, reserved2; public IntPtr reserved3, stdin, stdout, stderr;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct ProcessInfo { public IntPtr process, thread; public int pid, tid; }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool CreateProcessW(string app, StringBuilder command, IntPtr pa, IntPtr ta, bool inherit, uint flags,
                                      IntPtr env, string dir, ref StartupInfo si, out ProcessInfo pi);
    [DllImport("kernel32.dll")] static extern IntPtr GetStdHandle(int which);
    [DllImport("kernel32.dll")] static extern bool SetHandleInformation(IntPtr handle, int mask, int flags);
    [DllImport("kernel32.dll")] static extern int WaitForSingleObject(IntPtr handle, int ms);
    [DllImport("kernel32.dll")] static extern bool GetExitCodeProcess(IntPtr handle, out int code);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);

    // An MCP client starts this exe without a console. Hand our stdio pipes to Python explicitly;
    // otherwise Windows gives the child a new console and the client's pipes are never read.
    static int RunWithOurStdio(string python, string arguments) {
        var si = new StartupInfo { cb = Marshal.SizeOf(typeof(StartupInfo)), flags = 0x100 };  // STARTF_USESTDHANDLES
        si.stdin = GetStdHandle(-10); si.stdout = GetStdHandle(-11); si.stderr = GetStdHandle(-12);
        foreach (var handle in new[] { si.stdin, si.stdout, si.stderr }) SetHandleInformation(handle, 1, 1);
        ProcessInfo pi;
        var command = new StringBuilder(Quote(python) + " " + arguments);
        if (!CreateProcessW(null, command, IntPtr.Zero, IntPtr.Zero, true, 0x08000000, IntPtr.Zero, Root, ref si, out pi))
            throw new System.ComponentModel.Win32Exception();
        WaitForSingleObject(pi.process, -1);
        int code;
        GetExitCodeProcess(pi.process, out code);
        CloseHandle(pi.thread); CloseHandle(pi.process);
        return code;
    }
}
