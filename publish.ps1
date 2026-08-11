# PortalJustPlay - commit, push, deploy VPS
# Usage: .\publish.ps1
#        .\publish.ps1 "your commit message"

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

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

$remoteCmd = "set -Eeuo pipefail; cd '$projectDir' && BRANCH='$branch' ./deploy.sh"
Write-Host ""
Write-Host "==> SSH deploy ${user}@${host_}:${port}"
Write-Host "    $projectDir -> ./deploy.sh"

& ssh -p $port -o BatchMode=yes -o ConnectTimeout=15 "${user}@${host_}" $remoteCmd
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "SSH deploy failed. Test: ssh ${user}@${host_}"
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Done: pushed and deployed on VPS."
