# PortalJustPlay - commit, push, deploy VPS
# Usage: .\publish.ps1
#        .\publish.ps1 "your commit message"

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

# SSH/deploy.sh in ra UTF-8; Windows mặc định CP437/850 → chữ Việt thành "c├┤ng viß╗çc".
try {
    $utf8 = [System.Text.UTF8Encoding]::new($false)
    [Console]::OutputEncoding = $utf8
    [Console]::InputEncoding = $utf8
    $OutputEncoding = $utf8
    cmd /c "chcp 65001 >nul" | Out-Null
} catch {
    # Console ẩn / non-interactive — bỏ qua
}

function Load-DeployEnv {
    $path = Join-Path $Root "deploy.local.env"
    if (-not (Test-Path $path)) { return @{} }
    $cfg = @{}
    Get-Content $path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $i = $line.IndexOf("=")
        if ($i -lt 1) { return }
        $key = $line.Substring(0, $i).Trim()
        $val = $line.Substring($i + 1).Trim()
        $cfg[$key] = $val
    }
    return $cfg
}

function Invoke-Git {
    param([string[]]$GitArgs)
    & git @GitArgs
    if ($LASTEXITCODE -ne 0) {
        throw "git failed: git $($GitArgs -join ' ') (exit $LASTEXITCODE)"
    }
}

function Test-TcpPort {
    param(
        [Parameter(Mandatory = $true)][string]$Target,
        [int]$Port = 22,
        [int]$TimeoutSec = 2
    )
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($Target, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutSec * 1000, $false)) {
            return $false
        }
        if (-not $client.Connected) { return $false }
        $client.EndConnect($iar) | Out-Null
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Get-SshIdentity {
    param($cfg)
    if ($cfg["VPS_SSH_KEY"]) { return $cfg["VPS_SSH_KEY"] }
    $defaultKey = Join-Path $env:USERPROFILE ".ssh\vps_portal"
    if (Test-Path $defaultKey) { return $defaultKey }
    return $null
}

function Get-DeployHostCandidates {
    param($cfg, [string]$PublicHost)
    $list = New-Object System.Collections.Generic.List[string]
    if ($PublicHost) { [void]$list.Add($PublicHost) }
    $ts = $cfg["VPS_TAILSCALE_HOST"]
    if ($ts -and $ts -ne $PublicHost) { [void]$list.Add($ts) }
    return @($list | Select-Object -Unique)
}

function Invoke-SshDeploy {
    param(
        [string]$User,
        [string]$HostName,
        [string]$Port,
        [string]$RemoteCmd,
        [string]$IdentityFile
    )
    $sshArgs = @(
        "-T",
        "-p", $Port,
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=8",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=8",
        "-o", "StrictHostKeyChecking=accept-new"
    )
    if ($IdentityFile) {
        $sshArgs += @("-i", $IdentityFile, "-o", "IdentitiesOnly=yes")
    }
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $prevNative = $null
    if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
        $prevNative = $PSNativeCommandUseErrorActionPreference
        $PSNativeCommandUseErrorActionPreference = $false
    }
    try {
        # Out-Host: log Docker khong bi function capture thanh gia tri tra ve.
        # Ghi từng dòng qua Write-Host với console UTF-8 (đã set ở đầu script).
        & ssh @sshArgs "${User}@${HostName}" $RemoteCmd 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) {
                Write-Host $_.ToString()
            } else {
                Write-Host $_
            }
        }
        if ($null -eq $LASTEXITCODE) { return 1 }
        return [int]$LASTEXITCODE
    } catch {
        Write-Host $_.Exception.Message
        if ($null -ne $LASTEXITCODE) { return [int]$LASTEXITCODE }
        return 1
    } finally {
        $ErrorActionPreference = $prevEap
        if ($null -ne $prevNative) {
            $PSNativeCommandUseErrorActionPreference = $prevNative
        }
    }
}

$commitMsg = if ($args.Count -gt 0 -and $args[0]) { $args[0] } else { "update" }
$cfg = Load-DeployEnv

Write-Host "==> PortalJustPlay publish"
Write-Host "    Dir: $Root"

if (-not (Test-Path (Join-Path $Root ".git"))) {
    throw "No .git folder - run this inside PortalJustPlay project root."
}

Write-Host "==> git add ."
Invoke-Git @("add", ".")

$staged = & git diff --cached --name-only
if ($LASTEXITCODE -ne 0) {
    throw "git failed: git diff --cached --name-only (exit $LASTEXITCODE)"
}
if ($staged) {
    Write-Host "==> git commit -m `"$commitMsg`""
    Invoke-Git @("commit", "-m", $commitMsg)
} else {
    Write-Host "    No staged changes - skip commit."
}

Write-Host "==> git push"
Invoke-Git @("push")

$deployAfter = $cfg["DEPLOY_AFTER_PUSH"]
$host_ = $cfg["VPS_HOST"]
if ($deployAfter -eq "0" -or $deployAfter -eq "false") {
    Write-Host ""
    Write-Host "Pushed. DEPLOY_AFTER_PUSH=0 - skip SSH deploy."
    exit 0
}

if (-not $host_) {
    Write-Host ""
    Write-Host "Pushed to Git."
    Write-Host "VPS deploy: GitHub Actions (push main) or create deploy.local.env - see docs/HUONG_DAN_AUTO_DEPLOY.md"
    exit 0
}

$user = if ($cfg["VPS_USER"]) { $cfg["VPS_USER"] } else { "root" }
$port = if ($cfg["VPS_PORT"]) { $cfg["VPS_PORT"] } else { "22" }
$projectDir = if ($cfg["PROJECT_DIR"]) { $cfg["PROJECT_DIR"] } else { "/opt/portaljustplay" }
$branch = if ($cfg["BRANCH"]) { $cfg["BRANCH"] } else { "main" }
$identity = Get-SshIdentity $cfg
$candidates = Get-DeployHostCandidates $cfg $host_

$remoteCmd = "set -Eeuo pipefail; cd '$projectDir' && BRANCH='$branch' ./deploy.sh"

$sshHost = $null
Write-Host ""
Write-Host "==> Chon SSH host (IP public truoc)"
foreach ($h in $candidates) {
    Write-Host "    probe ${h}:${port} ..."
    if (Test-TcpPort -Target $h -Port ([int]$port) -TimeoutSec 2) {
        $sshHost = $h
        Write-Host "    OK: $h"
        break
    }
    Write-Host "    timeout: $h"
}

if (-not $sshHost) {
    $sshHost = $candidates[0]
    Write-Host "    Khong probe duoc TCP, van thu SSH: $sshHost"
}

Write-Host "==> SSH deploy ${user}@${sshHost}:${port}"
Write-Host "    $projectDir -> ./deploy.sh"

$exitCode = Invoke-SshDeploy -User $user -HostName $sshHost -Port $port -RemoteCmd $remoteCmd -IdentityFile $identity
# 255 = khong ket noi duoc. Khong retry khi deploy.sh da chay (tranh 2 tien trinh song song).
if ($exitCode -eq 255) {
    $fallback = @($candidates | Where-Object { $_ -ne $sshHost } | Select-Object -First 1)
    if ($fallback) {
        Write-Host ""
        Write-Host "==> Retry SSH ${user}@$($fallback[0]):${port} (loi ket noi)"
        $exitCode = Invoke-SshDeploy -User $user -HostName $fallback[0] -Port $port -RemoteCmd $remoteCmd -IdentityFile $identity
    }
}

if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host "SSH deploy failed. Test: ssh -i `$env:USERPROFILE\.ssh\vps_portal ${user}@$sshHost"
    exit $exitCode
}

Write-Host ""
Write-Host "Done: pushed and deployed on VPS."
