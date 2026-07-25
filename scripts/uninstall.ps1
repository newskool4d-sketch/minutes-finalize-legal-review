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
if (-not $DestinationRoot) {
    $base = if ($Target -eq 'Codex') { '.codex\skills' } else { '.claude\skills' }
    $DestinationRoot = Join-Path $env:USERPROFILE $base
}
$root = [IO.Path]::GetFullPath($DestinationRoot).TrimEnd('\')
$destination = [IO.Path]::GetFullPath((Join-Path $root $skillName))
if ((Split-Path -Leaf $destination) -ne $skillName -or -not $destination.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw "허용되지 않은 제거 경로입니다: $destination"
}

if (-not (Test-Path -LiteralPath $destination)) {
    Write-Output "설치본이 없습니다: $destination"
    exit 0
}

Write-Output "제거 대상: $destination"
if (-not $Apply) {
    Write-Output '미리보기만 수행했습니다. 실제 제거는 -Apply를 붙여 다시 실행하십시오.'
    exit 0
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = "$destination.backup-$stamp"
Copy-Item -LiteralPath $destination -Destination $backup -Recurse -Force
Remove-Item -LiteralPath $destination -Recurse -Force
Write-Output "제거 완료. 백업: $backup"
