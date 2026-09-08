// MIT. Uses the CPython runtime shipped beside the executable.
using System;
using System.Diagnostics;
using System.IO;
using System.Text;

class Launcher {
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
    static int Main(string[] args) {
        string root = AppDomain.CurrentDomain.BaseDirectory;
#if MCP
        string interpreter = "python.exe", script = "controller_mcp.py";
#else
        string interpreter = "pythonw.exe", script = "app.py";
#endif
        var arguments = new StringBuilder("-I ");
        // Bootstrap explicitly adds the trusted application directory in isolated mode.
        arguments.Append(Quote(Path.Combine(root, "bootstrap.py")));
        arguments.Append(" ").Append(Quote(script));
        foreach (string arg in args) arguments.Append(" ").Append(Quote(arg));
        string runtime = "runtime-python";
        string pointer = Path.Combine(root, "runtime-choice.txt");
        if (File.Exists(pointer)) {
            string choice = File.ReadAllText(pointer).Trim();
            if (System.Text.RegularExpressions.Regex.IsMatch(choice, @"\A(?:runtime-python|\.runtime-updates/[a-f0-9]{32})\z") &&
                File.Exists(Path.Combine(root, choice, interpreter))) runtime = choice;
        }
        if (Array.IndexOf(args, "--reset-libraries") >= 0) {
            File.WriteAllText(pointer, "runtime-python");
            return 0;
        }
        var start = new ProcessStartInfo(Path.Combine(root, runtime, interpreter), arguments.ToString());
        start.WorkingDirectory = root;
        start.UseShellExecute = false;
        start.EnvironmentVariables.Remove("PYTHONHOME");
        start.EnvironmentVariables.Remove("PYTHONPATH");
        try {
            using (var process = Process.Start(start)) {
                process.WaitForExit();
                return process.ExitCode;
            }
        } catch (Exception e) {
            File.WriteAllText(Path.Combine(root, "launch-error.txt"), e.ToString());
            return 1;
        }
    }
}
