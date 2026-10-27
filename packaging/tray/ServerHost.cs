// 本体（app.py --host）の起動と、標準入出力での JSON の行のやり取り（host_channel.py と対）。
//   本体 → トレイ: {"event":"ready","web_url":...,"profile":...,"pid":...}、{"id":n,"ok":...,"result"|"error":...}、{"event":"exit"}
//   トレイ → 本体: {"id":n,"method":"sessions"|"command","params":{...}}
// 標準入力を閉じると本体は終了する。JSON でない行は無視する。
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace PokeControllerTray
{
    delegate void ReplyHandler(bool ok, object result, string error);

    class ServerHost
    {
        readonly Action<MethodInvoker> post;          // UI スレッドで実行する
        readonly Dictionary<int, ReplyHandler> pending = new Dictionary<int, ReplyHandler>();
        readonly object gate = new object();
        Process process;
        StreamWriter input;
        int nextId;

        public event Action<Dictionary<string, object>> Ready;
        public event Action<int> Exited;              // 終了コード

        public ServerHost(Action<MethodInvoker> post) { this.post = post; }

        public bool Alive { get { return process != null; } }

        internal static string Quote(string value)
        {
            var result = new StringBuilder("\"");
            int slashes = 0;
            foreach (char c in value)
            {
                if (c == '\\') { slashes++; continue; }
                if (c == '"') result.Append('\\', slashes * 2 + 1);
                else result.Append('\\', slashes);
                result.Append(c);
                slashes = 0;
            }
            result.Append('\\', slashes * 2);
            return result.Append('"').ToString();
        }

        // install.ps1 が記録した Python（exe の隣の python.txt が先。MSIX のクライアントなどから見える %APPDATA% は仮想化されることがある）
        internal static string FindPython()
        {
            string root = Program.Root;
            string python = null;
            string beside = Path.Combine(root, "python.txt");
            string recorded = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), Program.AppName, "python.txt");
            try
            {
                if (File.Exists(Path.Combine(root, "portable")) && File.Exists(Path.Combine(root, "runtime-python", "python.exe")))
                    python = Path.Combine(root, "runtime-python", "python.exe");
                else if (File.Exists(beside)) python = File.ReadAllText(beside).Trim();
                else if (File.Exists(recorded)) python = File.ReadAllText(recorded).Trim();
                else if (File.Exists(Path.Combine(root, ".venv", "Scripts", "python.exe")))   // ソースから使うとき
                    python = Path.Combine(root, ".venv", "Scripts", "python.exe");
            }
            catch { return null; }
            return python != null && File.Exists(python) ? python : null;
        }

        // 専用の環境は利用者のユーザーサイトを見ない（-s）。利用者が選んだ Python はそのまま
        internal static string PythonOptions(string python)
        {
            return python.StartsWith(Program.LocalDir, StringComparison.OrdinalIgnoreCase) ? "-E -s " : "-E ";
        }

        internal static ProcessStartInfo PythonStartInfo(string python, string arguments)
        {
            var psi = new ProcessStartInfo(python, PythonOptions(python) + arguments)
            {
                UseShellExecute = false,
                CreateNoWindow = true,
                WorkingDirectory = Program.Root
            };
            psi.EnvironmentVariables.Remove("PYTHONHOME");
            psi.EnvironmentVariables.Remove("PYTHONPATH");
            return psi;
        }

        public bool Start(out string error)
        {
            error = null;
            string python = FindPython();
            if (python == null)
            {
                error = "Python の実行環境が見つかりません。インストールをやり直してください。";
                return false;
            }
            var psi = PythonStartInfo(python, Quote(Path.Combine(Program.Root, "bootstrap.py")) + " app.py --host");
            psi.RedirectStandardInput = true;
            psi.RedirectStandardOutput = true;
            psi.StandardOutputEncoding = new UTF8Encoding(false);
            var p = new Process { StartInfo = psi, EnableRaisingEvents = true };
            try { p.Start(); }
            catch (Exception ex)
            {
                error = "Python を起動できませんでした: " + ex.Message;
                return false;
            }
            process = p;
            input = new StreamWriter(p.StandardInput.BaseStream, new UTF8Encoding(false)) { AutoFlush = true, NewLine = "\n" };
            p.Exited += delegate
            {
                int code = -1;
                try { code = p.ExitCode; } catch { }
                post(delegate { OnExited(p, code); });
            };
            var reader = new Thread(delegate() { ReadLoop(p); }) { IsBackground = true, Name = "server-stdout" };
            reader.Start();
            return true;
        }

        void ReadLoop(Process p)
        {
            var json = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
            try
            {
                string line;
                while ((line = p.StandardOutput.ReadLine()) != null)
                {
                    Dictionary<string, object> message;
                    try { message = json.DeserializeObject(line) as Dictionary<string, object>; }
                    catch { continue; }
                    if (message == null) continue;
                    object ev;
                    if (message.TryGetValue("event", out ev))
                    {
                        if ((ev as string) == "ready")
                            post(delegate { if (process == p && Ready != null) Ready(message); });
                        continue;
                    }
                    object idValue;
                    if (!message.TryGetValue("id", out idValue) || !(idValue is int)) continue;
                    ReplyHandler handler;
                    lock (gate)
                    {
                        if (!pending.TryGetValue((int)idValue, out handler)) continue;
                        pending.Remove((int)idValue);
                    }
                    object ok, result, error;
                    message.TryGetValue("ok", out ok);
                    message.TryGetValue("result", out result);
                    message.TryGetValue("error", out error);
                    post(delegate { handler(ok is bool && (bool)ok, result, error as string); });
                }
            }
            catch { }
        }

        void OnExited(Process p, int code)
        {
            if (process != p) return;
            process = null;
            List<ReplyHandler> dropped;
            lock (gate)
            {
                dropped = new List<ReplyHandler>(pending.Values);
                pending.Clear();
                try { if (input != null) input.Dispose(); } catch { }
                input = null;
            }
            foreach (var h in dropped) h(false, null, "本体が終了しました");
            p.Dispose();
            if (Exited != null) Exited(code);
        }

        public void Request(string method, Dictionary<string, object> parameters, ReplyHandler onReply)
        {
            string line;
            int id;
            lock (gate)
            {
                if (input == null) { if (onReply != null) onReply(false, null, "本体が動いていません"); return; }
                id = ++nextId;
                line = new JavaScriptSerializer().Serialize(new Dictionary<string, object> {
                    { "id", id }, { "method", method }, { "params", parameters ?? new Dictionary<string, object>() } });
                if (onReply != null) pending[id] = onReply;
                try { input.WriteLine(line); }
                catch (Exception ex)
                {
                    pending.Remove(id);
                    if (onReply != null) onReply(false, null, ex.Message);
                }
            }
        }

        public void Command(string action, Dictionary<string, object> values, ReplyHandler onReply)
        {
            Request("command", new Dictionary<string, object> {
                { "action", action }, { "values", values ?? new Dictionary<string, object>() } }, onReply);
        }

        // 標準入力を閉じて、本体に終了を頼む
        public void RequestStop()
        {
            lock (gate)
            {
                try { if (input != null) input.Dispose(); } catch { }
                input = null;
            }
        }

        public void Kill()
        {
            var p = process;
            if (p == null) return;
            try { p.Kill(); } catch { }
        }
    }
}
