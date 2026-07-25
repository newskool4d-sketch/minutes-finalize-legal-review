[CmdletBinding()]
param(
    [ValidateSet('Codex', 'Claude')]
    [string]$Target = 'Codex',
    [string]$DestinationRoot,
    [switch]$Apply
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$skillName = 'minutes-hwpx-finalize-legal-review'
$source = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (-not $DestinationRoot) {
    $base = if ($Target -eq 'Codex') { '.codex\skills' } else { '.claude\skills' }
    $DestinationRoot = Join-Path $env:USERPROFILE $base
}
$destinationRootFull = [IO.Path]::GetFullPath($DestinationRoot)
$destination = Join-Path $destinationRootFull $skillName
$copyItems = @('SKILL.md', 'VERSION', 'agents', 'profiles', 'references', 'scripts')

foreach ($item in $copyItems) {
    if (-not (Test-Path -LiteralPath (Join-Path $source $item))) {
        throw "필수 배포 항목이 없습니다: $item"
    }
}

Write-Output "대상: $Target"
Write-Output "원본: $source"
Write-Output "설치 경로: $destination"
Write-Output "배포 항목: $($copyItems -join ', ')"

if (-not $Apply) {
    Write-Output '미리보기만 수행했습니다. 실제 설치는 -Apply를 붙여 다시 실행하십시오.'
    exit 0
}

if (-not (Test-Path -LiteralPath $destinationRootFull)) {
    New-Item -ItemType Directory -Path $destinationRootFull -Force | Out-Null
}

if (Test-Path -LiteralPath $destination) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backup = "$destination.backup-$stamp"
    Copy-Item -LiteralPath $destination -Destination $backup -Recurse -Force
    Write-Output "기존 설치본 백업: $backup"
}
else {
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
}

foreach ($item in $copyItems) {
    Copy-Item -LiteralPath (Join-Path $source $item) -Destination $destination -Recurse -Force
}

Write-Output "설치 완료: $destination"
Write-Output ("검증: .\scripts\verify_install.ps1 -Target {0}" -f $Target)
