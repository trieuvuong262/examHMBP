# Kiem tra script NAS truoc deploy — bat buoc PASS truoc khi copy len VPS.
# Chay: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_nas_ps1_validate.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ps1 = Join-Path $root 'JustPlay-NAS-RaiDrive-Setup.ps1'

function Fail([string]$Msg) {
    Write-Host "FAIL: $Msg" -ForegroundColor Red
    exit 1
}

function Ok([string]$Msg) {
    Write-Host "OK: $Msg" -ForegroundColor Green
}

if (-not (Test-Path -LiteralPath $ps1)) { Fail "missing $ps1" }

# 0) Bundle files for Portal ZIP
$exe = Join-Path $root 'Ket-Noi-NAS-JustPlay.exe'
$prep = Join-Path $root 'Prepare-JustPlay-WebClient.ps1'
foreach ($f in @($ps1, $prep, $exe)) {
    if (-not (Test-Path -LiteralPath $f)) { Fail "missing bundle file $f" }
}
if ((Get-Content -LiteralPath $ps1 -Raw) -notmatch 'Invoke-JustPlayNasCliFromExe') {
    Fail 'ps1 must support EXE CLI (Invoke-JustPlayNasCliFromExe)'
}
Ok 'bundle companion files'

# 0b) No Unicode em-dash in strings (PowerShell 5.1 parse bug on some encodings)
$rawPs1 = Get-Content -LiteralPath $ps1 -Raw
if ($rawPs1 -match 'Add_Paint\s*\(') { Fail 'GUI uses Add_Paint - unstable on PS 5.1' }
Ok 'GUI no Add_Paint'

# 0c) em-dash check
if ($rawPs1 -match [char]0x2014) { Fail 'file contains em-dash U+2014; use ASCII hyphen' }

# 1) Syntax parse
$parseErrors = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile($ps1, [ref]$null, [ref]$parseErrors)
if ($parseErrors) {
    foreach ($e in $parseErrors) { Write-Host $e.ToString() }
    Fail 'PowerShell syntax errors'
}
Ok 'syntax parse'

# 2) No duplicate function names
$tokens = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($ps1, [ref]$tokens, [ref]$parseErrors)
$fnNames = @(
    $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true) |
    ForEach-Object { $_.Name }
)
$dupes = $fnNames | Group-Object | Where-Object { $_.Count -gt 1 }
if ($dupes) {
    Fail ("duplicate functions: " + (($dupes | ForEach-Object { $_.Name }) -join ', '))
}
Ok ("functions ($($fnNames.Count)) unique")

# 3) Required symbols
$requiredFns = @(
    'Ensure-WebClientReady',
    'Get-WebDavShareUrl',
    'Invoke-NasWebDavMapTimed',
    'Resolve-NasConnectPlans',
    'Connect-JustPlayNasShare',
    'Connect-AllJustPlayNasShares',
    'Clear-JustPlayNasWebDavSession',
    'Clear-JustPlayNasCmdKeyByList',
    'Clear-JustPlayNasNetworkRegistry',
    'Test-NasServerPortWithRetry',
    'Test-NasWebDavReachable',
    'Clear-JustPlayNasWmiNetworkConnections',
    'Clear-JustPlayNasSmbMappings',
    'Clear-JustPlayNasExplorerDriveRemnants',
    'Get-NetUseMappedDriveLetters',
    'Get-NetUseDriveEntries',
    'Show-JustPlayNasDialog'
)
$src = Get-Content -LiteralPath $ps1 -Raw
foreach ($fn in $requiredFns) {
    if ($src -notmatch "function\s+$fn\s*\{") { Fail "missing function $fn" }
}
Ok 'required functions present'

# 4) Dot-source + test helpers (khong chay UI, khong load config local dev)
Remove-Item Env:JUSTPLAY_NAS_LOCAL_DEV -ErrorAction SilentlyContinue
. $ps1
if ($WebDavPort -ne 5678) { Fail "default WebDavPort=$WebDavPort expected 5678" }
if ($SmbPort -ne 445) { Fail "default SmbPort=$SmbPort expected 445" }
Ok 'defaults WebDAV=5678 SMB=445'

$url = Get-WebDavShareUrl -HostName 'justplay.synology.me' -DavPort 5678 -ShareName '10_HE_THONG_CNTT'
if ($url -ne 'https://justplay.synology.me:5678/10_HE_THONG_CNTT/') {
    Fail "WebDAV URL wrong: $url"
}
Ok 'WebDAV URL format'

$unc = Get-WebDavUncPath -HostName 'justplay.synology.me' -DavPort 5678 -ShareName '10_HE_THONG_CNTT'
if ($unc -notmatch 'DavWWWRoot') { Fail "UNC path wrong: $unc" }
Ok 'WebDAV UNC format'

# 5) TCP port 5678 reachable (WebDAV)
try {
    $tcp = New-Object Net.Sockets.TcpClient
    $r = $tcp.BeginConnect('justplay.synology.me', 5678, $null, $null)
    if (-not $r.AsyncWaitHandle.WaitOne(8000)) { Fail 'TCP 5678 timeout' }
    $tcp.EndConnect($r)
    $tcp.Close()
    Ok 'TCP justplay.synology.me:5678 reachable'
} catch {
    Fail "TCP 5678: $($_.Exception.Message)"
}

# 6) WebDAV endpoint returns 401 (can xac thuc)
try {
    $req = [System.Net.WebRequest]::Create('https://justplay.synology.me:5678/10_HE_THONG_CNTT/')
    $req.Method = 'HEAD'
    $req.Timeout = 8000
    [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
    try {
        $resp = $req.GetResponse()
        $code = [int]$resp.StatusCode
        $resp.Close()
    } catch [System.Net.WebException] {
        $code = [int]$_.Exception.Response.StatusCode
    }
    if ($code -ne 401 -and $code -ne 200 -and $code -ne 403) {
        Fail "WebDAV HEAD HTTP $code (expected 401)"
    }
    Ok "WebDAV HEAD HTTP $code"
} catch {
    Fail "WebDAV HEAD: $($_.Exception.Message)"
}

# 7) Config JSON mau (giong Portal bundle)
$tmp = Join-Path $env:TEMP "jp-nas-val-$([guid]::NewGuid().ToString('N').Substring(0,6))"
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    $bundle = @{
        server           = 'justplay.synology.me'
        webdav_port      = 5678
        smb_port         = 445
        port             = 5678
        fallback_server  = '100.93.5.42'
        ldap_domain      = 'ldap.justplay.local'
        shares           = @('10_HE_THONG_CNTT')
        drive_letter     = 'Z'
    }
    $jsonPath = Join-Path $tmp 'JustPlay-NAS-Config.json'
    $bundle | ConvertTo-Json | Set-Content -Path $jsonPath -Encoding UTF8
    $bytes = [System.IO.File]::ReadAllBytes($jsonPath)
    $raw = [System.Text.Encoding]::UTF8.GetString($bytes).TrimStart([char]0xFEFF)
    $obj = $raw | ConvertFrom-Json
    if ([int]$obj.webdav_port -ne 5678) { Fail 'bundle webdav_port' }
    if ([int]$obj.smb_port -ne 445) { Fail 'bundle smb_port' }
    if ($obj.shares.Count -lt 1) { Fail 'bundle shares empty' }
    Ok 'bundle JSON ports'
} finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}

# 8) Single-share scalar unwrap (Share "0" bug)
$testShares = [string[]]@(Merge-ShareNameLists @(,(Get-ShareNameList '02_HANH_CHINH_NHAN_SU')))
if ($testShares[0] -ne '02_HANH_CHINH_NHAN_SU') { Fail "scalar [0]=$($testShares[0]) expected full share name" }
Ok 'single-share index [0]'

$arg = Format-NetUseArgumentString -LocalPath 'Z:' `
    -RemotePath 'https://justplay.synology.me:5678/10_HE_THONG_CNTT/' `
    -WinUser 'vuonglnt@ldap.justplay.local' -PlainPassword 'p@ss/word' -WebDavOrder
if ($arg -notmatch 'vuonglnt@ldap\.justplay\.local') { Fail "net use arg missing user: $arg" }
if ($arg -notmatch 'https://') { Fail "net use arg missing url: $arg" }
Ok 'net use WebDAV quoting'

# 9) Scalar string must not become share "0" (pipe char bug)
$NasShareNames = '02_HANH_CHINH_NHAN_SU'
$NasSharesCsv = '02_HANH_CHINH_NHAN_SU'
$NasPrimaryShare = '02_HANH_CHINH_NHAN_SU'
if ((Get-PrimaryNasShareName) -ne '02_HANH_CHINH_NHAN_SU') {
    Fail "scalar-string share=$(Get-PrimaryNasShareName) expected 02_HANH_CHINH_NHAN_SU"
}
Ok 'scalar-string share name'

$NasSharesCsv = '10_HE_THONG_CNTT,02_HANH_CHINH_NHAN_SU'
$NasShareNames = [string[]]@('10_HE_THONG_CNTT', '02_HANH_CHINH_NHAN_SU')
$NasPrimaryShare = '10_HE_THONG_CNTT'
if ((Get-PrimaryNasShareName) -ne '10_HE_THONG_CNTT') {
    Fail "multi-share primary=$(Get-PrimaryNasShareName)"
}
Ok 'multi-share primary'

$NasSharesCsv = '10_HE_THONG_CNTT,02_HANH_CHINH_NHAN_SU'
$NasShareNames = [string[]]@('10_HE_THONG_CNTT', '02_HANH_CHINH_NHAN_SU')
$p2 = Get-PrimaryNasShareName
if ($p2 -match '\s') { Fail "primary has space: $p2" }
if ($p2 -ne '10_HE_THONG_CNTT') { Fail "cached primary=$p2" }
Ok 'vuonglnt dual-share primary'

$assignments = Get-NasShareDriveAssignments
if ($assignments.Count -ne 2) { Fail "drive assignments count=$($assignments.Count) expected 2" }
if ($assignments[0].Letter -ne 'Z' -or $assignments[0].ShareName -ne '10_HE_THONG_CNTT') {
    Fail "first assignment=$($assignments[0].Letter):$($assignments[0].ShareName)"
}
if ($assignments[1].Letter -ne 'Y' -or $assignments[1].ShareName -ne '02_HANH_CHINH_NHAN_SU') {
    Fail "second assignment=$($assignments[1].Letter):$($assignments[1].ShareName)"
}
Ok 'multi-share drive letters Z Y'

$NasSharesCsv = 'KD-MKT,05_MARKETING,KD-MKT'
$listAlias = New-NasShareNameList
if ($listAlias.Count -ne 1 -or $listAlias.Item(0) -ne '05_MARKETING') {
    Fail "alias dedupe=$($listAlias -join '|') expected 05_MARKETING"
}
Ok 'KD-MKT alias dedupe to 05_MARKETING'

$NasSharesCsv = '00_QUY_DINH_CHUNG,05_MARKETING,08_KHO_VAN_GIAO_HANG'
$NasPrimaryShare = '00_QUY_DINH_CHUNG'
$assignPrimary = Get-NasShareDriveAssignments
if ($assignPrimary.Count -ne 3) { Fail "primary-share assignments=$($assignPrimary.Count)" }
if ($assignPrimary[1].ShareName -ne '05_MARKETING') {
    Fail "assignment[1]=$($assignPrimary[1].ShareName) expected 05_MARKETING"
}
Ok 'drive assignments respect each share name'

$NasSharesCsv = '10_HE_THONG_CNTT 02_HANH_CHINH_NHAN_SU'
$NasPrimaryShare = '10_HE_THONG_CNTT'
$p3 = Resolve-SingleNasShareName '10_HE_THONG_CNTT 02_HANH_CHINH_NHAN_SU'
if ($p3 -ne '10_HE_THONG_CNTT') { Fail "space-corrupt csv primary=$p3" }
Ok 'space-corrupt csv fallback'

$reach = Test-NasServerPort -HostName 'justplay.synology.me' -NasPort 5678
if ($reach -ne 'justplay.synology.me') {
    Fail "port check returned IP/host $reach expected hostname"
}
Ok 'port check keeps hostname'

# 10) Connect plans must stay objects (not unwrap to property values)
$bag = Resolve-NasConnectPlans
$planCount = 0
foreach ($p in $bag) {
    if ($null -eq $p.ConnectHost -or -not $p.ConnectHost) { Fail "plan missing ConnectHost type=$($p.GetType().Name)" }
    $planCount++
}
if ($planCount -lt 1) { Fail 'no connect plans' }
Ok "connect plans=$planCount (webdav-only)"

Write-Host '--- ALL NAS PS1 VALIDATION PASSED ---' -ForegroundColor Cyan
exit 0