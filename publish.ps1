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

function Get-SshIdentity {
    param($cfg)
    if ($env:VPS_SSH_KEY) { return $env:VPS_SSH_KEY }
    if ($cfg["VPS_SSH_KEY"]) { return $cfg["VPS_SSH_KEY"] }
    return (Join-Path $env:USERPROFILE ".ssh\vps_portal")
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
if ($deployAfter -eq "0" -or $deployAfter -eq "false") {
    Write-Host ""
    Write-Host "Pushed. DEPLOY_AFTER_PUSH=0 - skip SSH deploy."
    exit 0
}

# Deploy thang IP public — khong probe / fallback Tailscale.
$host_ = if ($env:VPS_HOST) { $env:VPS_HOST } elseif ($cfg["VPS_HOST"]) { $cfg["VPS_HOST"] } else { "103.90.224.203" }
$user = if ($env:VPS_USER) { $env:VPS_USER } elseif ($cfg["VPS_USER"]) { $cfg["VPS_USER"] } else { "root" }
$port = if ($env:VPS_PORT) { $env:VPS_PORT } elseif ($cfg["VPS_PORT"]) { $cfg["VPS_PORT"] } else { "22" }
$projectDir = if ($cfg["PROJECT_DIR"]) { $cfg["PROJECT_DIR"] } else { "/opt/portaljustplay" }
$branch = if ($cfg["BRANCH"]) { $cfg["BRANCH"] } else { "main" }
$identity = Get-SshIdentity $cfg
$sshHost = $host_
$remoteCmd = "set -Eeuo pipefail; cd '$projectDir' && sed -i 's/\r`$//' deploy.sh && BRANCH='$branch' bash ./deploy.sh"

Write-Host ""
Write-Host "==> SSH deploy ${user}@${sshHost}:${port}"
Write-Host "    ssh -i $identity -p ${port} ${user}@${sshHost}"
Write-Host "    $projectDir -> ./deploy.sh"
if ($identity -and -not (Test-Path $identity)) {
    Write-Host "SSH key not found: $identity"
    Write-Host "Test: ssh -i `$env:USERPROFILE\.ssh\vps_portal ${user}@${sshHost}"
    exit 1
}

$exitCode = Invoke-SshDeploy -User $user -HostName $sshHost -Port $port -RemoteCmd $remoteCmd -IdentityFile $identity

if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host "SSH deploy failed. Test: ssh -i `$env:USERPROFILE\.ssh\vps_portal -p ${port} ${user}@${sshHost}"
    exit $exitCode
}

Write-Host ""
Write-Host "Done: pushed and deployed on VPS."
