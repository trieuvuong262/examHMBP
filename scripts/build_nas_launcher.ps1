# Build Ket-Noi-NAS-JustPlay.exe tu JustPlay-NAS-Launcher.cs
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$cs = Join-Path $root 'JustPlay-NAS-Launcher.cs'
$out = Join-Path $root 'Ket-Noi-NAS-JustPlay.exe'
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $csc)) {
    throw "Khong tim thay csc.exe: $csc"
}
& $csc /nologo /target:winexe /optimize+ `
    /r:System.Windows.Forms.dll `
    /r:System.Drawing.dll `
    /out:$out `
    $cs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "OK: $out ($((Get-Item $out).Length) bytes)"
