# Chan doan nhanh NAS WebDAV — chay: powershell -File Diagnose-JustPlay-Nas.ps1
$ErrorActionPreference = 'Continue'
$hostName = 'justplay.synology.me'
$port = 5678
$tailscale = '100.93.5.42'

Write-Host '=== JustPlay NAS — chan doan mang ===' -ForegroundColor Cyan
Write-Host ''

Write-Host '[1] DNS / hosts'
try {
    $dnsOnly = $null
    try {
        $rec = @(Resolve-DnsName -Name $hostName -Type A -DnsOnly -ErrorAction Stop | Where-Object { $_.IPAddress })
        if ($rec.Count -gt 0) { $dnsOnly = [string]$rec[0].IPAddress }
    } catch {}
    $resolved = @([System.Net.Dns]::GetHostAddresses($hostName) | ForEach-Object { $_.IPAddressToString })
    Write-Host "  nslookup (DNS that): $hostName -> $dnsOnly"
    Write-Host "  Windows resolve (co hosts): $($resolved -join ', ')"

    $hostsPath = Join-Path $env:windir 'System32\drivers\etc\hosts'
    $hostsLines = @()
    if (Test-Path -LiteralPath $hostsPath) {
        $hostsLines = @(Get-Content -LiteralPath $hostsPath | Where-Object { $_ -match '(?i)justplay\.synology\.me' -and $_ -notmatch '^\s*#' })
    }
    if ($hostsLines.Count -gt 0) {
        Write-Host "  HOSTS file ($($hostsLines.Count) dong):" -ForegroundColor Yellow
        $hostsLines | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
        if ($dnsOnly -and $resolved -contains '192.168.1.254' -and $dnsOnly -notmatch '^(192\.168\.|10\.|100\.)') {
            Write-Host '  LOI: hosts ep LAN 192.168.1.254 nhung DNS that la IP public — WebDAV/RaiDrive hay 401!' -ForegroundColor Red
            Write-Host '  => Xoa dong justplay trong hosts (Admin), ipconfig /flushdns, test lai curl HTTP:207' -ForegroundColor Red
        }
    }

    if ($resolved -contains '100.93.5.42') {
        $lanNas = '192.168.1.254'
        $lanOk = $false
        try {
            $tcpLan = Test-NetConnection -ComputerName $lanNas -Port $port -WarningAction SilentlyContinue
            $lanOk = [bool]$tcpLan.TcpTestSucceeded
        } catch {}
        if ($lanOk) {
            Write-Host "  PHAT HIEN: DNS tro Tailscale nhung NAS LAN $lanNas`:$port mo duoc." -ForegroundColor Yellow
            Write-Host "  => May trong van phong: them hosts (Admin): $lanNas $hostName" -ForegroundColor Yellow
            Write-Host "  => Hoac chap nhan UAC khi mo EXE NAS (script .29+ tu sua hosts)" -ForegroundColor Yellow
        } else {
            Write-Host '  CANH BAO: DNS tro Tailscale 100.93.5.42 — can Tailscale hoac DNS noi bo -> IP NAS LAN' -ForegroundColor Yellow
        }
    }
    if ($resolved -contains '14.161.25.119' -or ($resolved | Where-Object { $_ -notmatch '^100\.|^192\.168\.|^10\.' })) {
        if (-not ($hostsLines.Count -gt 0 -and $resolved -contains '192.168.1.254')) {
            Write-Host '  DNS/resolve tro IP PUBLIC — on neu khong co hosts ep LAN.' -ForegroundColor Green
        }
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
    $limit = $p.FileSizeLimitInBytes
    if ($null -eq $limit) {
        Write-Host '  FileSizeLimitInBytes: (mac dinh ~50MB) — file >50MB se loi 0x800700DF' -ForegroundColor Yellow
    } else {
        $mb = [math]::Round([uint32]$limit / 1MB, 1)
        $color = if ([uint32]$limit -ge 100MB) { 'Green' } else { 'Yellow' }
        Write-Host "  FileSizeLimitInBytes: $limit (~${mb} MB)" -ForegroundColor $color
    }
    $fwd = ($p.AuthForwardServerList -split "`n" | Where-Object { $_ }) -join '; '
    if ($fwd) { Write-Host "  AuthForward: $fwd" }
} catch {
    Write-Host '  Registry WebClient: chua cau hinh (chay prep / EXE mo lan dau)' -ForegroundColor Yellow
}

Write-Host ''
Write-Host '[4] WebDAV PROPFIND (share — Windows can 207)'
$shareTest = '00_QUY_DINH_CHUNG'
$propUrl = "https://${hostName}:${port}/${shareTest}/"
try {
    if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
        $pfCode = & curl.exe -s -k -o NUL -w '%{http_code}' -X PROPFIND -H 'Depth: 0' $propUrl 2>$null
        Write-Host "  PROPFIND $propUrl -> $pfCode"
        if ($pfCode -eq '405') {
            Write-Host '  LOI NAS: share tra 405 — WebClient khong map duoc (sua WebDAV/reverse proxy tren Synology)' -ForegroundColor Red
        } elseif ($pfCode -eq '207') {
            Write-Host '  OK: share ho tro WebDAV day du' -ForegroundColor Green
        }
    } else {
        Write-Host '  Bo qua (khong co curl.exe)'
    }
} catch {
    Write-Host "  LOI PROPFIND: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ''
Write-Host '[5] net use (can user/pass)'
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
Write-Host '- PROPFIND share = 405 => sua WebDAV NAS (khong phai loi mat khau Portal)'
Write-Host '- PROPFIND OK + net use FAIL 67 => DNS noi bo / prep WebClient (UAC)'
Write-Host '- TCP FAIL => firewall / port 5678 bi chan'
Write-Host '- Loi 1244 qua IP 100.x => dung hostname + cert NAS, khong map bang IP Tailscale'
Write-Host '- Doi user Portal => Go mount truoc khi Ket noi'
