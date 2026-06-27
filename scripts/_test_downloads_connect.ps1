$ErrorActionPreference = 'Stop'
$dir = 'C:\Users\Vuong-IT\Downloads\JustPlay-NAS-RaiDrive-Setup (2)'
Set-Location -LiteralPath $dir
. (Join-Path $dir 'JustPlay-NAS-RaiDrive-Setup.ps1')
Write-Host "Version: $NasScriptVersion"
Write-Host "Shares: $(Get-NasShareNamesLabel)"
Write-Host "Before net use:"
net use
Clear-JustPlayNasWebDavSession
Write-Host "After clear net use:"
net use
$env:JUSTPLAY_NAS_PASSWORD = '123123sS@@'
$result = Connect-AllJustPlayNasShares -Username Vuonglnt -Password $env:JUSTPLAY_NAS_PASSWORD
Write-Host "Mapped: $($result.Mapped.Count) WinUser: $($result.WinUser)"
foreach ($m in $result.Mapped) { Write-Host "  $($m.Letter): $($m.ShareName)" }
Write-Host "net use after map:"
net use
foreach ($m in $result.Mapped) {
    $p = "$($m.Letter):\"
    try {
        $c = (Get-ChildItem -LiteralPath $p -ErrorAction Stop).Count
        Write-Host "READ $($m.Letter): OK ($c items)"
    } catch {
        Write-Host "READ $($m.Letter): FAIL $($_.Exception.Message)"
    }
}
