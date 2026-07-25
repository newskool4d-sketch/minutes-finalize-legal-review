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
$required = @(
    'SKILL.md',
    'VERSION',
    'agents\openai.yaml',
    'profiles\README.md',
    'references\checklist.md',
    'scripts\apply_approved_edits.py',
    'scripts\validate_hwpx.py',
    'scripts\verify_release_pair.py',
    'scripts\detect_legal_review_candidates.py',
    'scripts\prepare_legal_review_template.py',
    'scripts\generate_draft_legal_review.py',
    'scripts\render_legal_review_report.py',
    'scripts\validate_operation_metrics.py'
)
$missing = @($required | Where-Object { -not (Test-Path -LiteralPath (Join-Path $destination $_)) })
$name = ''
$version = ''
if (Test-Path -LiteralPath (Join-Path $destination 'SKILL.md')) {
    $nameLine = Get-Content -LiteralPath (Join-Path $destination 'SKILL.md') | Where-Object { $_ -match '^name:\s*' } | Select-Object -First 1
    if ($nameLine) { $name = ($nameLine -replace '^name:\s*', '').Trim() }
}
if (Test-Path -LiteralPath (Join-Path $destination 'VERSION')) {
    $version = (Get-Content -Raw -LiteralPath (Join-Path $destination 'VERSION')).Trim()
}

$result = [pscustomobject]@{
    target = $Target
    path = $destination
    exists = Test-Path -LiteralPath $destination
    skill_name = $name
    skill_name_matches = ($name -eq $skillName)
    version = $version
    version_valid = ($version -match '^\d+\.\d+\.\d+$')
    missing = $missing
    valid = ((Test-Path -LiteralPath $destination) -and $name -eq $skillName -and $version -match '^\d+\.\d+\.\d+$' -and $missing.Count -eq 0)
}
$result | ConvertTo-Json -Depth 3
if (-not $result.valid) { exit 1 }
