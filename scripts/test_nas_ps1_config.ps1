# Unit test logic doc config NAS — chay: powershell -File scripts/test_nas_ps1_config.ps1
$ErrorActionPreference = 'Stop'

function Get-ShareNameList {
    param([object]$Raw)
    if ($null -eq $Raw) { return @() }
    if ($Raw -is [string]) {
        return @(
            $Raw -split ',' |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ }
        )
    }
    return @(
        @($Raw) |
        ForEach-Object { [string]$_ } |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ }
    )
}

function Merge-ShareNameLists {
    param([object[]]$Lists)
    $merged = New-Object System.Collections.Generic.List[string]
    $seen = @{}
    foreach ($list in $Lists) {
        if (-not $list) { continue }
        foreach ($name in $list) {
            $n = [string]$name
            if (-not $n -or $seen.ContainsKey($n)) { continue }
            $seen[$n] = $true
            [void]$merged.Add($n)
        }
    }
    return @($merged.ToArray())
}

function Import-JsonConfigFile {
    param([string]$Path)
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    $raw = [System.Text.Encoding]::UTF8.GetString($bytes)
    if ($raw.StartsWith([char]0xFEFF)) { $raw = $raw.Substring(1) }
    return ($raw | ConvertFrom-Json)
}

function Assert-EqualList {
    param([string]$Name, [string[]]$Expected, [string[]]$Actual)
    $e = ($Expected -join '|')
    $a = ($Actual -join '|')
    if ($e -ne $a) {
        throw "FAIL $Name expected=[$e] actual=[$a]"
    }
    Write-Host "OK: $Name"
}

$tmp = Join-Path $env:TEMP "JustPlay-NAS-ps1-test-$([guid]::NewGuid().ToString('N').Substring(0,8))"
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    $obj1 = @{ shares = @('10_HE_THONG_CNTT'); server = 'justplay.synology.me' }
    $p1 = Join-Path $tmp 'c1.json'
    $obj1 | ConvertTo-Json -Compress | Set-Content -Path $p1 -Encoding UTF8
    $cfg1 = Import-JsonConfigFile $p1
    Assert-EqualList 'single-share-json' @('10_HE_THONG_CNTT') (Get-ShareNameList $cfg1.shares)

    $obj2 = @{ shares = @('10_HE_THONG_CNTT', '02_HANH_CHINH_NHAN_SU') }
    $p2 = Join-Path $tmp 'c2.json'
    $obj2 | ConvertTo-Json -Compress | Set-Content -Path $p2 -Encoding UTF8
    $cfg2 = Import-JsonConfigFile $p2
    Assert-EqualList 'multi-share-json' @('10_HE_THONG_CNTT', '02_HANH_CHINH_NHAN_SU') (Get-ShareNameList $cfg2.shares)

    # merge inline + json
    $inline = Get-ShareNameList '02_HANH_CHINH_NHAN_SU'
    $jsonShares = Get-ShareNameList $cfg2.shares
    $merged = Merge-ShareNameLists @($jsonShares, $inline)
    Assert-EqualList 'merge-dedupe' @('10_HE_THONG_CNTT', '02_HANH_CHINH_NHAN_SU') $merged

    # empty json shares must not wipe inline when merged second
    $merged2 = Merge-ShareNameLists @( @(), $inline )
    Assert-EqualList 'inline-only-merge' @('02_HANH_CHINH_NHAN_SU') $merged2

    Write-Host '--- ALL PS1 CONFIG TESTS PASSED ---'
    exit 0
} catch {
    Write-Host $_.Exception.Message
    exit 1
} finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
