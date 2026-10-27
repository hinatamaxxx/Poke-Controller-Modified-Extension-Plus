<#
Poke-Controller のインストール・更新（ユーザーごと、管理者権限は不要）。

  -Python Auto      おすすめ。python.org 版の Python 3.12 があれば専用の仮想環境を作り、
                    なければ公式の Python 3.12 を専用フォルダーに展開する。既存の環境には触らない。
  -Python Existing  -PythonPath（省略時は見つかった Python）にライブラリを入れて使う。
  -Python Manual    -PythonPath の Python をそのまま使う。ライブラリは入れない。
#>
param(
    [string]$Source = $PSScriptRoot,
    [ValidateSet('Auto', 'Existing', 'Manual')][string]$Python = 'Auto',
    [string]$PythonPath,
    [switch]$Update,
    [switch]$DesktopShortcut,
    [switch]$RegisterClaudeDesktop,
    [switch]$NoFinishScreen,
    [string]$ProgressLog
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$App = 'PokeController'
$Target = Join-Path $env:LOCALAPPDATA "Programs\$App"
$Local = Join-Path $env:LOCALAPPDATA $App
$Config = Join-Path $env:APPDATA $App
$PythonVersion = '3.12.10'
$script:Step = 0

function Step([string]$Text) {
    $script:Step++
    Write-Host "[$script:Step] $Text"
    if ($ProgressLog) { Add-Content -LiteralPath $ProgressLog -Value $Text -Encoding UTF8 }
}

function Invoke-Checked([string]$File, [string[]]$Arguments) {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$File $($Arguments -join ' ') が失敗しました（終了コード $LASTEXITCODE）" }
}

function Test-Python312([string]$Path) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $false }
    # The Microsoft Store Python needs its own camera permission, so it is not used for the app.
    if ($Path -like '*\WindowsApps\*') { return $false }
    $version = & $Path -c "import sys, tkinter; print('%d.%d-%d' % (sys.version_info[0], sys.version_info[1], sys.maxsize > 2**32))" 2>$null
    return $LASTEXITCODE -eq 0 -and $version -eq '3.12-1'
}

function Find-Python312 {
    foreach ($root in 'HKCU:\Software\Python\PythonCore\3.12\InstallPath', 'HKLM:\Software\Python\PythonCore\3.12\InstallPath') {
        $item = Get-ItemProperty -LiteralPath $root -ErrorAction SilentlyContinue
        if ($item) {
            $candidate = if ($item.ExecutablePath) { $item.ExecutablePath } else { Join-Path $item.'(default)' 'python.exe' }
            if (Test-Python312 $candidate) { return $candidate }
        }
    }
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        $candidate = & $launcher.Source -3.12 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and (Test-Python312 $candidate)) { return $candidate }
    }
    foreach ($command in Get-Command python.exe -All -ErrorAction SilentlyContinue) {
        if (Test-Python312 $command.Source) { return $command.Source }
    }
    return $null
}

function Install-PrivatePython([string]$Folder) {
    # Official python.org MSIs unpacked with an administrative install: no registry entries, no admin rights.
    $download = Join-Path $env:TEMP "$App-python-$PythonVersion"
    New-Item -ItemType Directory -Force $download | Out-Null
    foreach ($part in 'core', 'exe', 'lib', 'tcltk') {
        $msi = Join-Path $download "$part.msi"
        if (-not (Test-Path -LiteralPath $msi)) {
            Invoke-WebRequest "https://www.python.org/ftp/python/$PythonVersion/amd64/$part.msi" -OutFile $msi -UseBasicParsing
        }
        $signature = Get-AuthenticodeSignature -LiteralPath $msi
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike '*Python Software Foundation*') {
            throw "$part.msi の署名を確認できません。ダウンロードをやり直してください。"
        }
        $process = Start-Process msiexec.exe -ArgumentList "/a `"$msi`" /qn TARGETDIR=`"$Folder`"" -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw "$part.msi を展開できません（$($process.ExitCode)）" }
    }
    Get-ChildItem -LiteralPath $Folder -Filter *.msi | Remove-Item -Force
    Remove-Item -LiteralPath $download -Recurse -Force -ErrorAction SilentlyContinue
    # -s: never read or change the user's own site-packages (%APPDATA%\Python\Python312).
    Invoke-Checked (Join-Path $Folder 'python.exe') @('-s', '-m', 'ensurepip', '--default-pip')
}

function Install-Libraries([string]$Interpreter, [string]$Requirements, [switch]$Isolated) {
    # A dedicated environment must not see the user's site-packages, or pip would replace packages there.
    $prefix = if ($Isolated) { @('-s') } else { @() }
    Invoke-Checked $Interpreter ($prefix + @('-m', 'pip', 'install', '--disable-pip-version-check', '--no-warn-script-location', '--upgrade', 'pip'))
    Invoke-Checked $Interpreter ($prefix + @('-m', 'pip', 'install', '--disable-pip-version-check', '--no-warn-script-location', '-r', $Requirements))
}

function New-Shortcut([string]$Path, [string]$TargetPath) {
    # The AppUserModelID ties the taskbar and notifications to this shortcut's name and icon.
    if (-not ('ShortcutWriter' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class ShortcutWriter {
    [ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IShellLinkW {
        void GetPath(IntPtr a, int b, IntPtr c, int d); void GetIDList(out IntPtr a); void SetIDList(IntPtr a);
        void GetDescription(IntPtr a, int b); void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string a);
        void GetWorkingDirectory(IntPtr a, int b); void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string a);
        void GetArguments(IntPtr a, int b); void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string a);
        void GetHotkey(out short a); void SetHotkey(short a); void GetShowCmd(out int a); void SetShowCmd(int a);
        void GetIconLocation(IntPtr a, int b, out int c); void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string a, int b);
        void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string a, int b); void Resolve(IntPtr a, int b);
        void SetPath([MarshalAs(UnmanagedType.LPWStr)] string a);
    }
    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPropertyStore {
        void GetCount(out uint a); void GetAt(uint a, out PropertyKey b); void GetValue(ref PropertyKey a, IntPtr b);
        void SetValue(ref PropertyKey a, PropVariant b); void Commit();
    }
    [ComImport, Guid("0000010B-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPersistFile {
        void GetClassID(out Guid a); [PreserveSig] int IsDirty();
        void Load([MarshalAs(UnmanagedType.LPWStr)] string a, int b);
        void Save([MarshalAs(UnmanagedType.LPWStr)] string a, bool b);
        void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string a); void GetCurFile(out IntPtr a);
    }
    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    struct PropertyKey { public Guid fmtid; public uint pid; }
    [StructLayout(LayoutKind.Sequential)]
    class PropVariant { public ushort vt = 31; ushort r1, r2, r3; public IntPtr value; IntPtr padding; }
    [ComImport, Guid("00021401-0000-0000-C000-000000000046")] class ShellLink { }
    public static void Write(string path, string target, string directory, string appId) {
        var link = (IShellLinkW)new ShellLink();
        link.SetPath(target);
        link.SetWorkingDirectory(directory);
        link.SetIconLocation(target, 0);
        var key = new PropertyKey { fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), pid = 5 };
        var value = new PropVariant { value = Marshal.StringToCoTaskMemUni(appId) };
        var store = (IPropertyStore)link;
        store.SetValue(ref key, value);
        store.Commit();
        Marshal.FreeCoTaskMem(value.value);
        ((IPersistFile)link).Save(path, true);
    }
}
'@
    }
    [ShortcutWriter]::Write($Path, $TargetPath, (Split-Path $TargetPath), 'hinatamaxxx.PokeController')
}

try {
    $version = ([regex]::Match((Get-Content -LiteralPath (Join-Path $Source 'product.py') -Raw), "VERSION = '([^']+)'")).Groups[1].Value
    Step 'フォルダーを準備しています'
    foreach ($folder in $Target, $Local, $Config) { New-Item -ItemType Directory -Force $folder | Out-Null }

    Step 'アプリのファイルをコピーしています'
    # A running tray app and its WebView2 DLLs are moved aside instead of stopped; the next update removes them.
    Get-ChildItem -LiteralPath $Target -Filter '*.old-*' -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
    foreach ($exe in Get-ChildItem -LiteralPath $Target -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in '.exe', '.dll' }) {
        Rename-Item -LiteralPath $exe.FullName -NewName "$($exe.Name).old-$([DateTime]::Now.Ticks)"
    }
    $copy = Start-Process robocopy.exe -ArgumentList "`"$Source`" `"$Target`" /MIR /XF *.old-* python.txt /NFL /NDL /NJH /NJS /NP" -Wait -PassThru -WindowStyle Hidden
    if ($copy.ExitCode -ge 8) { throw "ファイルをコピーできません（robocopy $($copy.ExitCode)）" }

    $record = Join-Path $Config 'python.txt'
    $requirements = Join-Path $Target 'requirements-lock.txt'
    $hash = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash
    $hashFile = Join-Path $Local 'requirements.sha256'
    $current = if (Test-Path -LiteralPath $record) { (Get-Content -LiteralPath $record -Raw).Trim() } else { $null }
    $dedicated = Join-Path $Local 'python'
    $needsLibraries = -not $Update -or -not $current -or -not (Test-Path -LiteralPath $current) -or
        ((Test-Path -LiteralPath $hashFile) -and (Get-Content -LiteralPath $hashFile -Raw).Trim() -ne $hash)
    if ($Update -and $current -and -not $current.StartsWith($dedicated, [StringComparison]::OrdinalIgnoreCase)) {
        $needsLibraries = $false  # the user's own Python is theirs to manage
    }
    if ($needsLibraries) {
        Step 'Python の環境を準備しています'
        switch ($Python) {
            'Manual' {
                if (-not $PythonPath -or -not (Test-Path -LiteralPath $PythonPath)) { throw '-PythonPath に python.exe を指定してください。' }
                $interpreter = (Resolve-Path -LiteralPath $PythonPath).Path
            }
            'Existing' {
                $interpreter = if ($PythonPath) { (Resolve-Path -LiteralPath $PythonPath).Path } else { Find-Python312 }
                if (-not $interpreter) { throw 'Python 3.12 が見つかりません。-PythonPath で指定してください。' }
                Step 'ライブラリを入れています（数分かかります）'
                Install-Libraries $interpreter $requirements
            }
            'Auto' {
                if (Test-Path -LiteralPath (Join-Path $dedicated 'python.exe')) {
                    $interpreter = Join-Path $dedicated 'python.exe'
                } elseif (Test-Path -LiteralPath (Join-Path $dedicated 'Scripts\python.exe')) {
                    $interpreter = Join-Path $dedicated 'Scripts\python.exe'
                } else {
                    $base = Find-Python312
                    if ($base) {
                        Step "Python $((& $base -c 'import sys; print(sys.version.split()[0])')) から専用の環境を作っています"
                        Invoke-Checked $base @('-m', 'venv', $dedicated)
                        $interpreter = Join-Path $dedicated 'Scripts\python.exe'
                    } else {
                        Step "公式の Python $PythonVersion を専用フォルダーに入れています"
                        Install-PrivatePython $dedicated
                        $interpreter = Join-Path $dedicated 'python.exe'
                    }
                }
                Step 'ライブラリを入れています（数分かかります）'
                Install-Libraries $interpreter $requirements -Isolated
            }
        }
        Set-Content -LiteralPath $record -Value $interpreter -Encoding UTF8
        Set-Content -LiteralPath $hashFile -Value $hash -Encoding ASCII
    }

    # The tray app and the MCP launcher read this copy first (tray\ServerHost.cs, Launcher.cs); robocopy /MIR removes it, so write it every time.
    Copy-Item -LiteralPath $record -Destination (Join-Path $Target 'python.txt') -Force

    Step 'スタートメニューに登録しています'
    $exePath = Join-Path $Target 'PokeController.exe'
    $programs = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
    New-Shortcut (Join-Path $programs 'Poke-Controller.lnk') $exePath
    if ($DesktopShortcut) { New-Shortcut (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Poke-Controller.lnk') $exePath }

    Step 'Windows に登録しています'
    $key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$App"
    New-Item -Path $key -Force | Out-Null
    $size = [int]((Get-ChildItem -LiteralPath $Target, $Local -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum / 1KB)
    $values = @{
        DisplayName = 'Poke-Controller'; DisplayVersion = $version; Publisher = 'hinatamaxxx'
        DisplayIcon = $exePath; InstallLocation = $Target
        UninstallString = "`"$exePath`" --uninstall"; QuietUninstallString = "`"$exePath`" --uninstall --quiet"
    }
    foreach ($name in $values.Keys) { Set-ItemProperty -Path $key -Name $name -Value $values[$name] }
    foreach ($name in 'NoModify', 'NoRepair') { New-ItemProperty -Path $key -Name $name -Value 1 -PropertyType DWord -Force | Out-Null }
    New-ItemProperty -Path $key -Name EstimatedSize -Value $size -PropertyType DWord -Force | Out-Null

    if ($RegisterClaudeDesktop) {
        Step 'Claude Desktop に登録しています'
        $interpreter = (Get-Content -LiteralPath $record -Raw).Trim()
        Push-Location $Target
        try { Invoke-Checked $interpreter @('-c', 'import mcp_setup, sys; [mcp_setup.register_desktop(p, sys.argv[1]) for p in mcp_setup.desktop_configs()]', $Target) }
        finally { Pop-Location }
    }

    Step "Poke-Controller $version を入れました"
    if ($ProgressLog) { Add-Content -LiteralPath $ProgressLog -Value '#done' -Encoding UTF8 }
    if (-not $Update -and -not $NoFinishScreen) { Start-Process -FilePath $exePath -ArgumentList '--install-finished' }
} catch {
    if ($ProgressLog) { Add-Content -LiteralPath $ProgressLog -Value "#error $($_.Exception.Message)" -Encoding UTF8 }
    Write-Error $_.Exception.Message
    exit 1
}
