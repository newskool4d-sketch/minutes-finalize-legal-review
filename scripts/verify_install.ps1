[CmdletBinding()]
param(
    [ValidateSet('Codex', 'Claude')]
    [string]$Target = 'Codex',
    [string]$DestinationRoot,
    [string]$SourceRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
# Do not execute any installed helper, even when -SourceRoot names a trusted copy.
# Trust starts at the verifier the operator launches, not at a parameter value.
$selfRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd([char[]]'\/')
if (Test-Path -LiteralPath (Join-Path $selfRoot '.minutes-install-manifest.json')) {
    throw 'TRUSTED_SOURCE_REQUIRED: 설치본 검증기는 실행하지 않습니다. 별도 신뢰 소스의 scripts/verify_install.ps1을 실행하십시오.'
}
if ($SourceRoot -and -not [IO.Path]::GetFullPath($SourceRoot).TrimEnd([char[]]'\/').Equals($selfRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'TRUSTED_SOURCE_REQUIRED: SourceRoot는 현재 실행한 신뢰 소스 검증기의 루트와 같아야 합니다.'
}
$SourceRoot = $selfRoot
. (Join-Path $PSScriptRoot 'deployment_common.ps1')
$source = Get-FullDeploymentPath $SourceRoot
$dest = Get-DeploymentDestination $Target $DestinationRoot
Assert-DeploymentSeparation $source $dest.Root $dest.Storage
$entries = @(Get-DistributionEntries $source)
$result = Test-DeploymentInstallation $dest.Path $source $entries
$result | Add-Member -NotePropertyName target -NotePropertyValue $Target
$result | ConvertTo-Json -Depth 6
if (-not $result.valid) { exit 1 }
