[CmdletBinding()]
param(
    [ValidateSet('Codex', 'Claude')]
    [string]$Target = 'Codex',
    [string]$DestinationRoot,
    [switch]$Apply
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'deployment_common.ps1')

$dest = Get-DeploymentDestination $Target $DestinationRoot
if (-not (Test-Path -LiteralPath $dest.Path)) {
    Write-Output "설치본이 없습니다: $($dest.Path)"
    exit 0
}
$manifestPath = Join-Path $dest.Path $script:MinutesManifestName
Assert-NoDeploymentReparse $manifestPath
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw '설치 매니페스트가 없는 미등록 폴더는 제거하지 않습니다.' }
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.schema_version -ne 1 -or $manifest.skill_name -ne $script:MinutesSkillName -or @($manifest.files).Count -eq 0) {
    throw '설치 매니페스트 등록 정보가 올바르지 않습니다.'
}
$seen = @{}
foreach ($entry in @($manifest.files)) {
    $null = Get-SafeDeploymentPath $dest.Path $entry.path
    if ($seen.ContainsKey($entry.path) -or $entry.sha256 -notmatch '^[A-Fa-f0-9]{64}$') { throw '설치 매니페스트 파일 정보가 올바르지 않습니다.' }
    $seen[$entry.path] = $true
}
$files = @(Get-DeploymentTreeFiles $dest.Path | Sort-Object)
$token = (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [Guid]::NewGuid().ToString('N')
$backup = Join-Path $dest.Storage ('uninstalled-' + $token)
Write-Output "제거 대상(폴더 전체를 복구 가능한 위치로 이동): $($dest.Path)"
Write-Output "파일 목록: $($files.Count)개"
foreach ($file in $files) { Write-Output $file }
Write-Output "복구 보관 경로: $backup"
if (-not $Apply) {
    Write-Output '미리보기만 수행했습니다. 실제 이동은 -Apply를 붙여 다시 실행하십시오.'
    exit 0
}
Assert-NoDeploymentReparse $dest.Path
Assert-NoDeploymentReparse $dest.Storage
New-Item -ItemType Directory -Path $dest.Storage -Force | Out-Null
Move-Item -LiteralPath $dest.Path -Destination $backup
Write-Output "BACKUP_PATH: $backup"
Write-Output "제거 완료(영구 삭제 없음). 복구 시 이 폴더를 원래 설치 경로로 이동하십시오: $($dest.Path)"
