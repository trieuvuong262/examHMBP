# Chan doan nhanh NAS WebDAV — chay: powershell -File Diagnose-JustPlay-Nas.ps1
$ErrorActionPreference = 'Continue'
$hostName = 'justplay.synology.me'
$port = 5678
$tailscale = '100.93.5.42'

Write-Host '=== JustPlay NAS — chan doan mang ===' -ForegroundColor Cyan
Write-Host ''

Write-Host '[1] DNS'
try {
    $dns = [System.Net.Dns]::GetHostAddresses($hostName) | ForEach-Object { $_.IPAddressToString }
    Write-Host "  $hostName -> $($dns -join ', ')"
    if ($dns -contains '14.161.25.119' -or ($dns | Where-Object { $_ -notmatch '^100\.|^192\.168\.|^10\.' })) {
        Write-Host '  CANH BAO: DNS tro IP PUBLIC — trong LAN de loi WebClient 67. Nen DNS noi bo -> IP NAS (100.93.5.42 / LAN).' -ForegroundColor Yellow
    }
} catch {
    Write-Host "  LOI DNS: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ''
Write-Host '[2] TCP port'
foreach ($h in @($hostName, $tailscale)) {
    try {
        $tcp = Test-NetConnection -ComputerName $h -Port $port -WarningAction SilentlyContinue
        $ok = if ($tcp.TcpTestSucceeded) { 'OK' } else { 'FAIL' }
        $color = if ($tcp.TcpTestSucceeded) { 'Green' } else { 'Red' }
        Write-Host "  ${h}:${port} -> $ok" -ForegroundColor $color
    } catch {
        Write-Host "  ${h}:${port} -> FAIL" -ForegroundColor Red
    }
}

Write-Host ''
Write-Host '[3] WebClient'
$svc = Get-Service WebClient -ErrorAction SilentlyContinue
if ($svc) {
    Write-Host "  Service: $($svc.Status) ($($svc.StartType))"
} else {
    Write-Host '  LOI: khong co dich vu WebClient' -ForegroundColor Red
}
try {
    $p = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\WebClient\Parameters' -ErrorAction Stop
    Write-Host "  BasicAuthLevel: $($p.BasicAuthLevel)"
    $fwd = ($p.AuthForwardServerList -split "`n" | Where-Object { $_ }) -join '; '
    if ($fwd) { Write-Host "  AuthForward: $fwd" }
} catch {
    Write-Host '  Registry WebClient: chua cau hinh (chay prep / EXE mo lan dau)' -ForegroundColor Yellow
}

Write-Host ''
Write-Host '[4] net use (can user/pass)'
Write-Host '  Dat bien: $env:JUSTPLAY_NAS_TEST_USER va $env:JUSTPLAY_NAS_TEST_PASS roi chay lai script'
$u = $env:JUSTPLAY_NAS_TEST_USER
$p = $env:JUSTPLAY_NAS_TEST_PASS
if ($u -and $p) {
    cmdkey /generic:"https://${hostName}:${port}" /user:$u /pass:$p 2>$null | Out-Null
    net use J: /delete /y 2>$null | Out-Null
    $out = net use J: "\\${hostName}@SSL@${port}\DavWWWRoot\00_QUY_DINH_CHUNG" /user:$u $p /persistent:no 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host '  net use -> OK' -ForegroundColor Green
        net use J: /delete /y 2>$null | Out-Null
    } else {
        Write-Host "  net use -> FAIL: $out" -ForegroundColor Red
        if ("$out" -match '67') {
            Write-Host '  => Loi 67: DNS noi bo / hairpin NAT / SSL inspection FortiGate' -ForegroundColor Yellow
        }
        if ("$out" -match '1244') {
            Write-Host '  => Loi 1244: user/pass hoac WebClient prep' -ForegroundColor Yellow
        }
    }
} else {
    Write-Host '  Bo qua (chua dat JUSTPLAY_NAS_TEST_USER / PASS)'
}

Write-Host ''
Write-Host '=== Ket luan nhanh ==='
Write-Host '- TCP OK + net use FAIL 67 => sua DNS FortiGate (justplay.synology.me -> IP noi bo), tat SSL inspect'
Write-Host '- TCP FAIL => firewall / port 5678 bi chan'
Write-Host '- Loi Persist trong EXE => tai ZIP script .23+'
Write-Host '- Doi user Portal => Go mount truoc khi Ket noi'
