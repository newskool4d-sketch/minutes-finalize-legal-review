[CmdletBinding()]
param(
    [ValidateSet('Codex', 'Claude')]
    [string]$Target = 'Codex',
    [string]$DestinationRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$skillName = 'minutes-hwpx-finalize-legal-review'
if (-not $DestinationRoot) {
    $base = if ($Target -eq 'Codex') { '.codex\skills' } else { '.claude\skills' }
    $DestinationRoot = Join-Path $env:USERPROFILE $base
}
$destination = Join-Path ([IO.Path]::GetFullPath($DestinationRoot)) $skillName
$required = @('SKILL.md', 'agents\openai.yaml', 'profiles\README.md', 'references\checklist.md', 'scripts\apply_approved_edits.py')
$missing = @($required | Where-Object { -not (Test-Path -LiteralPath (Join-Path $destination $_)) })
$name = ''
if (Test-Path -LiteralPath (Join-Path $destination 'SKILL.md')) {
    $nameLine = Get-Content -LiteralPath (Join-Path $destination 'SKILL.md') | Where-Object { $_ -match '^name:\s*' } | Select-Object -First 1
    if ($nameLine) { $name = ($nameLine -replace '^name:\s*', '').Trim() }
}

$result = [pscustomobject]@{
    target = $Target
    path = $destination
    exists = Test-Path -LiteralPath $destination
    skill_name = $name
    skill_name_matches = ($name -eq $skillName)
    missing = $missing
    valid = ((Test-Path -LiteralPath $destination) -and $name -eq $skillName -and $missing.Count -eq 0)
}
$result | ConvertTo-Json -Depth 3
if (-not $result.valid) { exit 1 }
