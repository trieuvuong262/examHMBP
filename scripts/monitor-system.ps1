# Theo doi RAM / CPU / SSD tren VPS (mac dinh), format giong may local
# Usage:
#   .\monitor.cmd              -> chi VPS
#   .\monitor.cmd watch        -> VPS, lap lai moi 5 giay
#   .\monitor.cmd watch 10
#   .\monitor.cmd local        -> may local (neu can)
#   .\monitor.cmd all          -> local + VPS

param(
    [Parameter(Position = 0)]
    [ValidateSet('all', 'local', 'vps', 'watch')]
    [string]$Mode = 'vps',

    [Parameter(Position = 1)]
    [int]$IntervalSec = 5
)

$ErrorActionPreference = 'Continue'
$Root = Split-Path $PSScriptRoot -Parent
$DisplayMode = if ($Mode -eq 'watch') { 'vps' } else { $Mode }

function Load-DeployEnv {
    $path = Join-Path $Root 'deploy.local.env'
    $cfg = @{
        VPS_HOST = '103.90.224.203'
        VPS_USER = 'root'
        VPS_PORT = '22'
    }
    if (-not (Test-Path $path)) { return $cfg }
    Get-Content $path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith('#')) { return }
        $i = $line.IndexOf('=')
        if ($i -lt 1) { return }
        $key = $line.Substring(0, $i).Trim()
        $val = $line.Substring($i + 1).Trim()
        if ($key -in @('VPS_HOST', 'VPS_USER', 'VPS_PORT')) {
            $cfg[$key] = $val
        }
    }
    return $cfg
}

function Get-UsageBar {
    param(
        [double]$Percent,
        [int]$Width = 28
    )
    $pct = [math]::Max(0, [math]::Min(100, $Percent))
    $filled = [int][math]::Round($Width * $pct / 100)
    $empty = $Width - $filled
    return ('[' + ('#' * $filled) + ('-' * $empty) + '] {0,5:N1}%' -f $pct)
}

function Convert-BytesToGb {
    param([double]$Bytes)
    return [math]::Round($Bytes / 1GB, 2)
}

function Get-VpsMetricsScript {
    return @'
hostname=$(hostname 2>/dev/null || echo vps)
echo "HOSTNAME=$hostname"
free -b | awk '/^Mem:/ {print "RAM_TOTAL=" $2; print "RAM_USED=" $3}'
cores=$(nproc 2>/dev/null || echo 1)
echo "CPU_CORES=$cores"
idle=$(top -bn1 2>/dev/null | grep -E '%Cpu|Cpu\(s\)' | head -1 | sed -E 's/.*, *([0-9.]+) *id.*/\1/')
if [ -n "$idle" ]; then
  awk -v i="$idle" 'BEGIN{printf "CPU_PCT=%.1f\n", 100-i}'
else
  echo "CPU_PCT=0"
fi
load=$(uptime 2>/dev/null | sed -n 's/.*load average: *//p')
echo "LOADAVG=$load"
df -B1 --output=target,size,used,avail -x tmpfs -x devtmpfs -x overlay -x fuse 2>/dev/null | awk 'NR>1 {print "DISK|" $1 "|" $2 "|" $3 "|" $4}'
docker stats --no-stream --format '{{.Name}}|{{.MemUsage}}' 2>/dev/null | head -5 | sed 's/^/DOCKER|/'
'@
}

function Invoke-VpsMetrics {
    param($Cfg)
    $target = '{0}@{1}' -f $Cfg.VPS_USER, $Cfg.VPS_HOST
    $remoteScript = (Get-VpsMetricsScript) -replace "`r", ''
    $output = $remoteScript | & ssh -o BatchMode=yes -o ConnectTimeout=12 -p $Cfg.VPS_PORT $target 'bash -s' 2>&1
    $lines = @($output | ForEach-Object { "$_".Trim() } | Where-Object { $_ })
    $hasMetrics = $lines | Where-Object { $_ -match '^(HOSTNAME|RAM_TOTAL|RAM_USED|CPU_|LOADAVG|DISK|DOCKER)=' -or $_ -match '^(HOSTNAME|RAM_TOTAL|RAM_USED|CPU_|LOADAVG|DISK|DOCKER)\|' }
    return @{
        Ok = ($hasMetrics.Count -gt 0)
        Lines = $lines
        Target = $target
    }
}

function Write-LocalMonitor {
    $now = Get-Date -Format 'dd/MM/yyyy HH:mm:ss'
    Write-Host ''
    Write-Host "=== MAY LOCAL ($env:COMPUTERNAME) - $now ===" -ForegroundColor Cyan

    $os = Get-CimInstance Win32_OperatingSystem
    $ramTotalGb = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
    $ramFreeGb = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
    $ramUsedGb = [math]::Round($ramTotalGb - $ramFreeGb, 2)
    $ramPct = if ($ramTotalGb -gt 0) { ($ramUsedGb / $ramTotalGb) * 100 } else { 0 }

    Write-Host ('RAM : {0} / {1} GB dang dung' -f $ramUsedGb, $ramTotalGb)
    Write-Host ('      {0}' -f (Get-UsageBar $ramPct))

    $cpuLoads = @(Get-CimInstance Win32_Processor | ForEach-Object { $_.LoadPercentage })
    $cpuAvg = if ($cpuLoads.Count -gt 0) {
        [math]::Round(($cpuLoads | Measure-Object -Average).Average, 1)
    } else { 0 }
    $cpuName = (Get-CimInstance Win32_Processor | Select-Object -First 1).Name
    Write-Host ('CPU : {0}%' -f $cpuAvg)
    Write-Host ('      {0}' -f (Get-UsageBar $cpuAvg))
    if ($cpuName) {
        Write-Host ('      {0}' -f $cpuName.Trim())
    }

    Write-Host 'SSD :'
    Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' |
        Sort-Object DeviceID |
        ForEach-Object {
            $totalGb = [math]::Round($_.Size / 1GB, 1)
            $freeGb = [math]::Round($_.FreeSpace / 1GB, 1)
            $usedGb = [math]::Round($totalGb - $freeGb, 1)
            $usedPct = if ($_.Size -gt 0) { (1 - $_.FreeSpace / $_.Size) * 100 } else { 0 }
            Write-Host ('  {0} {1} / {2} GB da dung ({3} GB trong)' -f $_.DeviceID, $usedGb, $totalGb, $freeGb)
            Write-Host ('      {0}' -f (Get-UsageBar $usedPct))
        }

    Write-Host ''
    Write-Host 'Top RAM (local):' -ForegroundColor DarkGray
    Get-Process |
        Sort-Object WorkingSet64 -Descending |
        Select-Object -First 5 |
        ForEach-Object {
            $mb = [math]::Round($_.WorkingSet64 / 1MB, 0)
            Write-Host ('  {0,-28} {1,6} MB' -f $_.ProcessName, $mb)
        }
}

function Write-VpsMonitor {
    param($Cfg)

    $result = Invoke-VpsMetrics $Cfg
    if (-not $result.Ok) {
        Write-Host ''
        Write-Host "=== VPS ($($result.Target)) ===" -ForegroundColor Cyan
        Write-Host "Khong ket noi duoc VPS." -ForegroundColor Yellow
        if ($result.Lines) { $result.Lines | ForEach-Object { Write-Host $_ } }
        Write-Host 'Kiem tra SSH key hoac mang.' -ForegroundColor DarkGray
        return
    }

    $data = @{
        Hostname = $Cfg.VPS_HOST
        RamTotal = 0
        RamUsed = 0
        CpuPct = 0
        CpuCores = 1
        LoadAvg = ''
        Disks = [System.Collections.Generic.List[object]]::new()
        Docker = [System.Collections.Generic.List[object]]::new()
    }

    foreach ($line in $result.Lines) {
        $text = "$line".Trim()
        if (-not $text) { continue }
        if ($text -match 'syntax error|unexpected end of file') { continue }
        if ($text -match '^HOSTNAME=(.+)$') { $data.Hostname = $Matches[1]; continue }
        if ($text -match '^RAM_TOTAL=(\d+)$') { $data.RamTotal = [double]$Matches[1]; continue }
        if ($text -match '^RAM_USED=(\d+)$') { $data.RamUsed = [double]$Matches[1]; continue }
        if ($text -match '^CPU_PCT=([\d.]+)$') { $data.CpuPct = [double]$Matches[1]; continue }
        if ($text -match '^CPU_CORES=(\d+)$') { $data.CpuCores = [int]$Matches[1]; continue }
        if ($text -match '^LOADAVG=(.+)$') { $data.LoadAvg = $Matches[1].Trim(); continue }
        if ($text -match '^DISK\|([^|]+)\|(\d+)\|(\d+)\|(\d+)$') {
            $data.Disks.Add([pscustomobject]@{
                Mount = $Matches[1]
                Total = [double]$Matches[2]
                Used = [double]$Matches[3]
                Avail = [double]$Matches[4]
            })
            continue
        }
        if ($text -match '^DOCKER\|([^|]+)\|(.+)$') {
            $mem = $Matches[2].Trim()
            $mb = 0
            if ($mem -match '^([\d.]+)(MiB|GiB|KiB|B)') {
                $val = [double]$Matches[1]
                switch ($Matches[2]) {
                    'GiB' { $mb = [math]::Round($val * 1024, 0) }
                    'MiB' { $mb = [math]::Round($val, 0) }
                    'KiB' { $mb = [math]::Round($val / 1024, 0) }
                    default { $mb = [math]::Round($val / 1MB, 0) }
                }
            }
            $data.Docker.Add([pscustomobject]@{
                Name = $Matches[1]
                MemMb = $mb
                MemLabel = $mem
            })
        }
    }

    $now = Get-Date -Format 'dd/MM/yyyy HH:mm:ss'
    $titleHost = if ($data.Hostname -and $data.Hostname -ne $Cfg.VPS_HOST) {
        "$($data.Hostname) / $($Cfg.VPS_HOST)"
    } else {
        $Cfg.VPS_HOST
    }

    Write-Host ''
    Write-Host "=== VPS ($titleHost) - $now ===" -ForegroundColor Cyan

    $ramTotalGb = Convert-BytesToGb $data.RamTotal
    $ramUsedGb = Convert-BytesToGb $data.RamUsed
    $ramPct = if ($data.RamTotal -gt 0) { ($data.RamUsed / $data.RamTotal) * 100 } else { 0 }

    Write-Host ('RAM : {0} / {1} GB dang dung' -f $ramUsedGb, $ramTotalGb)
    Write-Host ('      {0}' -f (Get-UsageBar $ramPct))

    Write-Host ('CPU : {0}%' -f ([math]::Round($data.CpuPct, 1)))
    Write-Host ('      {0}' -f (Get-UsageBar $data.CpuPct))
    if ($data.LoadAvg) {
        Write-Host ('      {0} core - load avg: {1}' -f $data.CpuCores, $data.LoadAvg)
    } else {
        Write-Host ('      {0} core' -f $data.CpuCores)
    }

    Write-Host 'SSD :'
    $seenMounts = @{}
    $maxDiskBytes = 5 * 1TB
    foreach ($disk in $data.Disks) {
        if ($disk.Mount -match 'nas|fuse|/boot') { continue }
        if ($disk.Total -gt $maxDiskBytes) { continue }
        if ($seenMounts.ContainsKey($disk.Mount)) { continue }
        $seenMounts[$disk.Mount] = $true
        $totalGb = [math]::Round($disk.Total / 1GB, 1)
        $freeGb = [math]::Round($disk.Avail / 1GB, 1)
        $usedGb = [math]::Round($disk.Used / 1GB, 1)
        $usedPct = if ($disk.Total -gt 0) { ($disk.Used / $disk.Total) * 100 } else { 0 }
        $label = if ($disk.Mount -eq '/') { '/' } else { $disk.Mount }
        Write-Host ('  {0} {1} / {2} GB da dung ({3} GB trong)' -f $label, $usedGb, $totalGb, $freeGb)
        Write-Host ('      {0}' -f (Get-UsageBar $usedPct))
    }
    if ($data.Disks.Count -eq 0) {
        Write-Host '  (khong doc duoc dung luong o dia)' -ForegroundColor DarkGray
    }

    if ($data.Docker.Count -gt 0) {
        Write-Host ''
        Write-Host 'Top RAM (docker):' -ForegroundColor DarkGray
        $data.Docker |
            Sort-Object MemMb -Descending |
            Select-Object -First 5 |
            ForEach-Object {
                $label = if ($_.MemMb -gt 0) { '{0} MB' -f $_.MemMb } else { $_.MemLabel }
                Write-Host ('  {0,-28} {1,8}' -f $_.Name, $label)
            }
    }
}

function Write-MonitorSnapshot {
    param($Cfg)
    if ($DisplayMode -eq 'all' -or $DisplayMode -eq 'local') {
        Write-LocalMonitor
    }
    if ($DisplayMode -eq 'all' -or $DisplayMode -eq 'vps') {
        Write-VpsMonitor $Cfg
    }
}

$cfg = Load-DeployEnv

if ($Mode -eq 'watch') {
    if ($IntervalSec -lt 2) { $IntervalSec = 2 }
    Write-Host "Theo doi VPS moi $IntervalSec giay - Ctrl+C de dung." -ForegroundColor DarkGray
    while ($true) {
        try { Clear-Host } catch { }
        Write-MonitorSnapshot $cfg
        Start-Sleep -Seconds $IntervalSec
    }
}

Write-MonitorSnapshot $cfg
if ($Mode -ne 'watch') {
    Write-Host ''
    Write-Host 'Go y: .\monitor.cmd watch 10  - lap lai moi 10 giay' -ForegroundColor DarkGray
    Write-Host '      .\monitor.cmd local    - chi may local' -ForegroundColor DarkGray
    Write-Host '      .\monitor.cmd all      - local + VPS' -ForegroundColor DarkGray
}
