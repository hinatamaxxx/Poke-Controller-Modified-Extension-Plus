<#
Poke-Controller のアンインストール。PokeController.exe --uninstall から、一時フォルダーにコピーして実行される。
ドキュメントの PokeController フォルダー（利用者のスクリプト・画像・キャプチャ）は消さない。
#>
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'Programs\PokeController'),
    [string]$ProgressLog,
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

try {
    Step 'Poke-Controller を終了しています'
    $self = $PID
    $owned = Get-CimInstance Win32_Process | Where-Object {
        $_.ProcessId -ne $self -and (
            ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($InstallDir, [StringComparison]::OrdinalIgnoreCase)) -or
            ($_.CommandLine -and $_.CommandLine.IndexOf($InstallDir, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
             $_.Name -match '^pythonw?\.exe$'))
    }
    foreach ($process in $owned) { Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue }
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
