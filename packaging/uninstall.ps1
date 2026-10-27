<#
Poke-Controller のアンインストール。PokeController.exe --uninstall から、一時フォルダーにコピーして実行される。
ドキュメントの PokeController フォルダー（利用者のスクリプト・画像・キャプチャ）は消さない。
#>
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'Programs\PokeController'),
    [string]$ProgressLog,
    [int]$CallerPid = 0,
    [switch]$KeepSettings
)
$ErrorActionPreference = 'Stop'
$App = 'PokeController'
$Local = Join-Path $env:LOCALAPPDATA $App
$Config = Join-Path $env:APPDATA $App

function Step([string]$Text) {
    Write-Host $Text
    if ($ProgressLog) { Add-Content -LiteralPath $ProgressLog -Value $Text -Encoding UTF8 }
}

function Remove-Folder([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    for ($attempt = 0; $attempt -lt 10; $attempt++) {
        try { Remove-Item -LiteralPath $Path -Recurse -Force; return } catch { Start-Sleep -Milliseconds 500 }
    }
    throw "$Path を削除できません。使用中のファイルがないか確認してください。"
}

# Processes started from the install folder, the Python processes running its code, and their children.
# The caller (PokeController.exe --uninstall) and this script are never included.
function Get-OwnedProcesses {
    $all = @(Get-CimInstance Win32_Process)
    $skip = @($PID, $CallerPid)
    $owned = @($all | Where-Object {
        $skip -notcontains $_.ProcessId -and (
            ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($InstallDir, [StringComparison]::OrdinalIgnoreCase)) -or
            ($_.CommandLine -and $_.CommandLine.IndexOf($InstallDir, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
             $_.Name -match '^pythonw?\.exe$'))
    })
    $ids = @($owned | ForEach-Object { $_.ProcessId })
    $children = @($all | Where-Object { $ids -contains $_.ParentProcessId -and $ids -notcontains $_.ProcessId -and $skip -notcontains $_.ProcessId })
    return @($owned) + $children
}

try {
    Step 'Poke-Controller を終了しています'
    # Ask the tray app to quit first so the app can close the camera and COM port and save its settings.
    $exe = Join-Path $InstallDir 'PokeController.exe'
    if (Test-Path -LiteralPath $exe) {
        try { Start-Process -FilePath $exe -ArgumentList '--quit' -Wait -WindowStyle Hidden } catch { }
        $deadline = [DateTime]::Now.AddSeconds(15)
        while ([DateTime]::Now -lt $deadline -and
               @(Get-OwnedProcesses | Where-Object { $_.Name -ieq 'PokeController.exe' }).Count -gt 0) {
            Start-Sleep -Milliseconds 500
        }
    }
    foreach ($process in Get-OwnedProcesses) { Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 500

    Step 'スタートメニューの項目を削除しています'
    foreach ($link in (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Poke-Controller.lnk'),
                      (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Poke-Controller.lnk'),
                      (Join-Path ([Environment]::GetFolderPath('Startup')) 'Poke-Controller.lnk')) {
        Remove-Item -LiteralPath $link -Force -ErrorAction SilentlyContinue
    }

    Step 'Windows の登録を解除しています'
    Remove-Item -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$App" -Recurse -Force -ErrorAction SilentlyContinue

    Step 'プログラムを削除しています'
    # A running exe cannot be deleted but can be moved: the caller's own exe goes to this script's temporary folder,
    # which the caller removes after it exits.
    if ($CallerPid) {
        $caller = Get-Process -Id $CallerPid -ErrorAction SilentlyContinue
        $callerPath = if ($caller) { $caller.Path } else { $null }
        if ($callerPath -and $callerPath.StartsWith($InstallDir, [StringComparison]::OrdinalIgnoreCase)) {
            Move-Item -LiteralPath $callerPath -Destination (Join-Path $PSScriptRoot ("caller-" + [DateTime]::Now.Ticks + '.exe')) -Force
        }
    }
    Remove-Folder $InstallDir

    Step '専用の Python 環境とログを削除しています'
    Remove-Folder $Local

    if (-not $KeepSettings) {
        Step '設定を削除しています'
        Remove-Folder $Config
    }
    if ($ProgressLog) { Add-Content -LiteralPath $ProgressLog -Value '#done' -Encoding UTF8 }
} catch {
    if ($ProgressLog) { Add-Content -LiteralPath $ProgressLog -Value "#error $($_.Exception.Message)" -Encoding UTF8 }
    Write-Error $_.Exception.Message
    exit 1
}
