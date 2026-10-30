[CmdletBinding()]
param(
    [ValidateSet('Codex', 'Claude')]
    [string]$Target = 'Codex',
    [string]$DestinationRoot,
    [string]$SourceRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'deployment_common.ps1')

$selfRoot = Get-FullDeploymentPath (Join-Path $PSScriptRoot '..')
if (-not $SourceRoot) {
    if (Test-Path -LiteralPath (Join-Path $selfRoot $script:MinutesManifestName)) {
        throw '설치본 내부에서 검증할 때는 신뢰할 수 있는 별도 소스의 -SourceRoot를 명시하십시오.'
    }
    $SourceRoot = $selfRoot
}
$source = Get-FullDeploymentPath $SourceRoot
$dest = Get-DeploymentDestination $Target $DestinationRoot
Assert-DeploymentSeparation $source $dest.Root $dest.Storage
$entries = @(Get-DistributionEntries $source)
$result = Test-DeploymentInstallation $dest.Path $source $entries
$result | Add-Member -NotePropertyName target -NotePropertyValue $Target
$result | ConvertTo-Json -Depth 6
if (-not $result.valid) { exit 1 }
