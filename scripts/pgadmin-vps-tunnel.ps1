# Mở SSH tunnel local:5433 -> VPS localhost:5432 (PostgreSQL portal)
# Giữ cửa sổ PowerShell này mở khi dùng pgAdmin.
#
# Neu bi loi ExecutionPolicy: dung pgadmin-vps-tunnel.cmd hoac chay truc tiep:
#   ssh -N -L 5433:127.0.0.1:5432 root@103.90.224.203
# Hoac (mot lan): powershell -ExecutionPolicy Bypass -File .\scripts\pgadmin-vps-tunnel.ps1
#
# pgAdmin (tab Connection, KHÔNG bật SSH Tunnel):
#   Host: localhost
#   Port: 5433
#   Database: portaljustplay_db
#   Username: postgres
#   Password: (DB_PASSWORD trong /opt/portaljustplay/.env trên VPS)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$cfgPath = Join-Path $Root "deploy.local.env"

$host_ = "103.90.224.203"
$user = "root"
$port = 22

if (Test-Path $cfgPath) {
    Get-Content $cfgPath -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $i = $line.IndexOf("=")
        if ($i -lt 1) { return }
        $key = $line.Substring(0, $i).Trim()
        $val = $line.Substring($i + 1).Trim()
        switch ($key) {
            "VPS_HOST" { $host_ = $val }
            "VPS_USER" { $user = $val }
            "VPS_PORT" { $port = $val }
        }
    }
}

$localPort = 5433
Write-Host "SSH tunnel: localhost:${localPort} -> ${user}@${host_}:127.0.0.1:5432"
Write-Host "Dung pgAdmin: Host=localhost Port=${localPort} Database=portaljustplay_db User=postgres"
Write-Host "Nhan Ctrl+C de dong tunnel."
Write-Host ""

ssh -p $port -N -L "${localPort}:127.0.0.1:5432" "${user}@${host_}"
