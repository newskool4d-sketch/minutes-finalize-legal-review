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

$source = Get-FullDeploymentPath (Join-Path $PSScriptRoot '..')
$dest = Get-DeploymentDestination $Target $DestinationRoot
Assert-DeploymentSeparation $source $dest.Root $dest.Storage
$entries = @(Get-DistributionEntries $source)
$token = (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [Guid]::NewGuid().ToString('N')
$stage = Join-Path $dest.Storage ('stage-' + $token)
$backup = Join-Path $dest.Storage ('backup-' + $token)
$command = '& ' + (ConvertTo-DeploymentQuotedArgument (Join-Path $source 'scripts\verify_install.ps1')) +
    ' -Target ' + $Target + ' -DestinationRoot ' + (ConvertTo-DeploymentQuotedArgument $dest.Root) +
    ' -SourceRoot ' + (ConvertTo-DeploymentQuotedArgument $source)

Write-Output "대상: $Target"
Write-Output "원본: $source"
Write-Output "설치 경로: $($dest.Path)"
Write-Output "스테이징: $stage"
Write-Output "기존본 보존 경로(기존본이 있을 때): $backup"
Write-Output "배포 파일: $($entries.Count)개 + 생성 설치 매니페스트"
foreach ($entry in $entries) { Write-Output (Join-Path $dest.Path $entry.path) }
Write-Output "VERIFY_COMMAND: $command"
if (-not $Apply) {
    Write-Output '미리보기만 수행했습니다. 실제 설치는 -Apply를 붙여 다시 실행하십시오.'
    exit 0
}

$oldMoved = $false
$newMoved = $false
try {
    # Inspect an existing tree before any mutation; extras are retained in the backup.
    if (Test-Path -LiteralPath $dest.Path) { $null = @(Get-DeploymentTreeFiles $dest.Path) }
    Invoke-DeploymentTestFailure 'stage'
    New-Item -ItemType Directory -Path $stage -Force | Out-Null
    foreach ($entry in $entries) {
        $from = Get-SafeDeploymentPath $source $entry.path
        $to = Get-SafeDeploymentPath $stage $entry.path
        New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($to)) -Force | Out-Null
        [IO.File]::Copy($from, $to, $false)
        Invoke-DeploymentTestFailure 'copy'
    }
    $manifest = New-DeploymentManifest $entries
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $stage $script:MinutesManifestName) -Encoding UTF8
    Invoke-DeploymentTestFailure 'verify'
    $check = Test-DeploymentInstallation $stage $source $entries
    if (-not $check.valid) { throw ('스테이징 검증 실패: ' + ($check | ConvertTo-Json -Depth 6 -Compress)) }
    # A concurrent source edit must not install a mixed snapshot.
    $fresh = @(Get-DistributionEntries $source)
    $recheck = Test-DeploymentInstallation $stage $source $fresh
    if (-not $recheck.valid) { throw '복사 중 소스가 변경되었습니다. 기존 설치를 보존합니다.' }
    Assert-NoDeploymentReparse $dest.Root
    Assert-NoDeploymentReparse $dest.Storage
    New-Item -ItemType Directory -Path $dest.Root -Force | Out-Null
    if (Test-Path -LiteralPath $dest.Path) {
        Move-Item -LiteralPath $dest.Path -Destination $backup
        $oldMoved = $true
    }
    Invoke-DeploymentTestFailure 'swap'
    Move-Item -LiteralPath $stage -Destination $dest.Path
    $newMoved = $true
    Invoke-DeploymentTestFailure 'after-swap'
    $final = Test-DeploymentInstallation $dest.Path $source $fresh
    if (-not $final.valid) { throw ('최종 검증 실패: ' + ($final | ConvertTo-Json -Depth 6 -Compress)) }
}
catch {
    $failure = $_
    if ($newMoved -and (Test-Path -LiteralPath $dest.Path)) {
        $failed = Join-Path $dest.Storage ('failed-' + $token)
        Move-Item -LiteralPath $dest.Path -Destination $failed
        Write-Output "실패 후보 보존: $failed"
    }
    if ($oldMoved) {
        Move-Item -LiteralPath $backup -Destination $dest.Path
        Write-Output "기존 설치 복원: $($dest.Path)"
    }
    if (Test-Path -LiteralPath $stage) { Write-Output "미완성 스테이징 보존: $stage" }
    throw $failure
}
if ($oldMoved) { Write-Output "BACKUP_PATH: $backup" }
Write-Output "설치 완료: $($dest.Path)"
Write-Output "VERIFY_COMMAND: $command"
