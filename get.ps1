<#
Poke-Controller をコマンド1行で入れる: irm https://raw.githubusercontent.com/hinatamaxxx/Poke-Controller-Modified-Extension-Plus/master/get.ps1 | iex
（irm | iex は先頭の BOM で失敗するので、このファイルは BOM なしの UTF-8 で保存する）
最新のリリースを取得し、SHA-256 を照合してから install.ps1 を実行する（ユーザーごと、管理者権限は不要）。
#>
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Base = 'https://github.com/hinatamaxxx/Poke-Controller-Modified-Extension-Plus/releases/latest/download/'
$Asset = 'PokeController-win64.zip'
$Work = Join-Path $env:TEMP ('PokeController-setup-' + [DateTime]::Now.Ticks)
New-Item -ItemType Directory $Work | Out-Null
$failed = $false
try {
    Write-Host 'Poke-Controller の最新版を取得しています'
    $zip = Join-Path $Work $Asset
    Invoke-WebRequest ($Base + $Asset) -OutFile $zip -UseBasicParsing
    # PowerShell 5.1 returns .Content as byte[] for application/octet-stream, so read the hash from a file.
    $hashFile = Join-Path $Work ($Asset + '.sha256')
    Invoke-WebRequest ($Base + $Asset + '.sha256') -OutFile $hashFile -UseBasicParsing
    $expected = ((Get-Content -LiteralPath $hashFile -Raw -Encoding ASCII).Trim() -split '\s+')[0].ToLower()
    if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLower() -ne $expected) {
        throw 'ダウンロードしたファイルの SHA-256 が一致しません。'
    }
    Expand-Archive -LiteralPath $zip -DestinationPath $Work
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Work 'PokeController\install.ps1') @args
    if ($LASTEXITCODE -ne 0) { throw 'インストールに失敗しました。表示された理由を確認してください。' }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    $failed = $true
} finally {
    Remove-Item -LiteralPath $Work -Recurse -Force -ErrorAction SilentlyContinue
}
# irm | iex runs in the user's own session, where exit would close their window.
if ($failed) { if ($MyInvocation.MyCommand.Path) { exit 1 } else { $global:LASTEXITCODE = 1 } }
