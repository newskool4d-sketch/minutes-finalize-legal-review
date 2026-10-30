Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:MinutesSkillName = 'minutes-hwpx-finalize-legal-review'
$script:MinutesManifestName = '.minutes-install-manifest.json'

function Get-FullDeploymentPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $full = [IO.Path]::GetFullPath($Path)
    if ($full.Length -gt [IO.Path]::GetPathRoot($full).Length) { $full = $full.TrimEnd([char[]]'\/') }
    return $full
}

function Test-DeploymentChild {
    param([string]$Path, [string]$Parent)
    return $Path.StartsWith($Parent.TrimEnd([char[]]'\/') + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)
}

function Assert-NoDeploymentReparse {
    param([string]$Path)
    $cursor = Get-FullDeploymentPath $Path
    while ($cursor) {
        $attributes = $null
        try { $attributes = [IO.File]::GetAttributes($cursor) }
        catch [IO.FileNotFoundException] { }
        catch [IO.DirectoryNotFoundException] { }
        if ($null -ne $attributes -and ($attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "재분석 지점(reparse point)은 허용하지 않습니다: $cursor"
        }
        $parent = [IO.Path]::GetDirectoryName($cursor)
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
}

function Get-DeploymentDestination {
    param([string]$Target, [string]$DestinationRoot)
    if (-not $DestinationRoot) {
        $base = if ($Target -eq 'Codex') { '.codex\skills' } else { '.claude\skills' }
        $DestinationRoot = Join-Path $env:USERPROFILE $base
    }
    $root = Get-FullDeploymentPath $DestinationRoot
    if ($root -eq [IO.Path]::GetPathRoot($root)) { throw '볼륨 루트는 DestinationRoot로 사용할 수 없습니다.' }
    Assert-NoDeploymentReparse $root
    if ((Test-Path -LiteralPath $root) -and -not (Test-Path -LiteralPath $root -PathType Container)) {
        throw "DestinationRoot가 디렉터리가 아닙니다: $root"
    }
    $destination = Join-Path $root $script:MinutesSkillName
    Assert-NoDeploymentReparse $destination
    $storage = Join-Path ([IO.Path]::GetDirectoryName($root)) '.minutes-skill-deployment'
    if ($storage -eq $root -or (Test-DeploymentChild $storage $root)) {
        throw '보관 경로가 활성 DestinationRoot 내부가 되는 경로는 사용할 수 없습니다.'
    }
    Assert-NoDeploymentReparse $storage
    if ([IO.Path]::GetPathRoot($storage) -ne [IO.Path]::GetPathRoot($destination)) {
        throw '스테이징과 설치본은 같은 볼륨에 있어야 합니다.'
    }
    return [pscustomobject]@{ Root = $root; Path = $destination; Storage = $storage }
}

function Assert-DeploymentSeparation {
    param([string]$Source, [string]$DestinationRoot, [string]$Storage)
    foreach ($other in @($DestinationRoot, $Storage)) {
        if ($Source -eq $other -or (Test-DeploymentChild $Source $other) -or (Test-DeploymentChild $other $Source)) {
            throw "원본과 설치/보관 경로는 중첩될 수 없습니다: $Source / $other"
        }
    }
}

function Get-DeploymentRelativePath {
    param([string]$Root, [string]$Path)
    $prefix = $Root.TrimEnd([char[]]'\/') + [IO.Path]::DirectorySeparatorChar
    if (-not $Path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw "루트 밖의 경로입니다: $Path" }
    return $Path.Substring($prefix.Length).Replace('\', '/')
}

function Get-SafeDeploymentPath {
    param([string]$Root, [string]$Relative)
    if (-not $Relative -or [IO.Path]::IsPathRooted($Relative) -or $Relative -match '[:\x00]' -or
        @($Relative -split '[\\/]' | Where-Object { $_ -eq '..' -or $_ -eq '.' -or -not $_ }).Count -gt 0) {
        throw "허용되지 않은 상대 배포 경로입니다: $Relative"
    }
    $full = Get-FullDeploymentPath (Join-Path $Root $Relative)
    if (-not (Test-DeploymentChild $full $Root)) { throw "루트 밖의 배포 경로입니다: $Relative" }
    Assert-NoDeploymentReparse $full
    return $full
}

function Get-DeploymentTreeFiles {
    param([string]$Root)
    Assert-NoDeploymentReparse $Root
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { throw "디렉터리가 없습니다: $Root" }
    foreach ($item in Get-ChildItem -LiteralPath $Root -Force) {
        Assert-NoDeploymentReparse $item.FullName
        if ($item.PSIsContainer) { Get-DeploymentTreeFiles $item.FullName }
        else { $item.FullName }
    }
}

function Get-DistributionEntries {
    param([string]$SourceRoot)
    $source = Get-FullDeploymentPath $SourceRoot
    Assert-NoDeploymentReparse $source
    $manifestPath = Join-Path $source 'distribution-manifest.json'
    Assert-NoDeploymentReparse $manifestPath
    $rules = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($rules.schema_version -ne 1 -or $rules.skill_name -ne $script:MinutesSkillName -or
        'distribution-manifest.json' -notin @($rules.include)) { throw '배포 목록 형식 또는 스킬명이 올바르지 않습니다.' }
    $seen = @{}
    $included = @{}
    $entries = @()
    foreach ($relative in @($rules.include)) {
        $path = Get-SafeDeploymentPath $source $relative
        if ($included.ContainsKey($relative)) { throw "중복 배포 항목입니다: $relative" }
        $included[$relative] = $true
        if (-not (Test-Path -LiteralPath $path)) { throw "필수 배포 항목이 없습니다: $relative" }
        $files = if (Test-Path -LiteralPath $path -PathType Container) { @(Get-DeploymentTreeFiles $path) } else { @($path) }
        foreach ($file in $files) {
            $rel = Get-DeploymentRelativePath $source $file
            $parts = @($rel -split '/')
            $excluded = @($parts | Where-Object { $_ -in @($rules.exclude_names) }).Count -gt 0
            $ext = [IO.Path]::GetExtension($file).ToLowerInvariant()
            if ($excluded -or $ext -in @($rules.exclude_extensions) -or
                ($rel -ne 'VERSION' -and $ext -notin @($rules.allowed_extensions))) { continue }
            if ($seen.ContainsKey($rel)) { throw "중복 배포 파일입니다: $rel" }
            $seen[$rel] = $true
            $entries += [pscustomobject]@{ path = $rel; sha256 = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash; length = (Get-Item -LiteralPath $file).Length }
        }
    }
    if ($entries.Count -eq 0) { throw '배포 파일 목록이 비어 있습니다.' }
    return @($entries | Sort-Object path)
}

function New-DeploymentManifest {
    param([object[]]$Entries)
    return [pscustomobject]@{ schema_version = 1; skill_name = $script:MinutesSkillName; files = @($Entries) }
}

function Get-DeploymentLinkErrors {
    param([string]$Root, [object[]]$Entries)
    $errors = @()
    foreach ($entry in $Entries) {
        if (-not $entry.path.EndsWith('.md', [StringComparison]::OrdinalIgnoreCase)) { continue }
        $markdown = Get-SafeDeploymentPath $Root $entry.path
        if (-not (Test-Path -LiteralPath $markdown -PathType Leaf)) { continue }
        $text = Get-Content -LiteralPath $markdown -Raw -Encoding UTF8
        $targets = @()
        foreach ($match in [regex]::Matches($text, '\[[^\]]*\]\(([^)]+)\)')) { $targets += $match.Groups[1].Value }
        foreach ($match in [regex]::Matches($text, '(?m)^\s*\[[^\]]+\]:\s*(\S+)')) { $targets += $match.Groups[1].Value }
        foreach ($target in $targets) {
            $target = ($target.Trim() -replace '\s+["''][^"'']*["'']\s*$', '').Trim('<', '>')
            if ($target -match '^(https?:|mailto:|ftp:|data:|//)') { continue }
            $target = [Uri]::UnescapeDataString(($target -split '[#?]', 2)[0])
            if (-not $target) { continue }
            try {
                if ([IO.Path]::IsPathRooted($target) -or $target -match ':') { throw '절대 로컬 링크' }
                $resolved = Get-FullDeploymentPath (Join-Path ([IO.Path]::GetDirectoryName($markdown)) $target)
                if (-not (Test-DeploymentChild $resolved $Root)) { throw '설치본 밖의 링크' }
                Assert-NoDeploymentReparse $resolved
                if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) { throw '링크 대상 없음' }
            }
            catch { $errors += "$($entry.path): $target ($($_.Exception.Message))" }
        }
    }
    return @($errors)
}

function Test-DeploymentInstallation {
    param([string]$Root, [string]$SourceRoot, [object[]]$Entries)
    $missing = @(); $modified = @(); $unexpected = @(); $runtimeCache = @(); $manifestErrors = @(); $links = @()
    $expected = @{}
    foreach ($entry in $Entries) { $expected[$entry.path] = $entry }
    $exists = Test-Path -LiteralPath $Root -PathType Container
    if ($exists) {
        foreach ($entry in $Entries) {
            $file = Get-SafeDeploymentPath $Root $entry.path
            if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { $missing += $entry.path }
            elseif ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $entry.sha256) { $modified += $entry.path }
        }
        foreach ($file in @(Get-DeploymentTreeFiles $Root)) {
            $rel = Get-DeploymentRelativePath $Root $file
            if ($rel -ne $script:MinutesManifestName -and -not $expected.ContainsKey($rel)) {
                # Normal imports may generate CPython caches. They are not deployed or
                # integrity-attested; report only caches corresponding to shipped .py files.
                $cache = [regex]::Match($rel, '^(.+/)?__pycache__/([^/]+)\.cpython-[0-9]+t?(?:\.opt-[12])?\.pyc$')
                $pythonPath = $cache.Groups[1].Value + $cache.Groups[2].Value + '.py'
                if ($cache.Success -and $expected.ContainsKey($pythonPath)) { $runtimeCache += $rel }
                else { $unexpected += $rel }
            }
        }
        $manifestPath = Join-Path $Root $script:MinutesManifestName
        if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { $manifestErrors += '설치 매니페스트 없음' }
        else {
            try {
                $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($manifest.schema_version -ne 1 -or $manifest.skill_name -ne $script:MinutesSkillName) { throw '설치 매니페스트 형식 오류' }
                $seen = @{}
                foreach ($entry in @($manifest.files)) {
                    $null = Get-SafeDeploymentPath $Root $entry.path
                    if ($seen.ContainsKey($entry.path)) { throw "중복 설치 매니페스트 경로: $($entry.path)" }
                    $seen[$entry.path] = $true
                    if (-not $expected.ContainsKey($entry.path) -or $entry.sha256 -ne $expected[$entry.path].sha256 -or $entry.length -ne $expected[$entry.path].length) {
                        $manifestErrors += "신뢰 소스와 다른 매니페스트 항목: $($entry.path)"
                    }
                }
                foreach ($path in $expected.Keys) { if (-not $seen.ContainsKey($path)) { $manifestErrors += "매니페스트 누락: $path" } }
            }
            catch { $manifestErrors += $_.Exception.Message }
        }
        $links = @(Get-DeploymentLinkErrors $Root $Entries)
    }
    else { $missing = @($Entries | ForEach-Object { $_.path }); $manifestErrors += '설치본 없음' }
    $name = ''; $version = ''
    if (Test-Path -LiteralPath (Join-Path $Root 'SKILL.md') -PathType Leaf) {
        $line = Get-Content -LiteralPath (Join-Path $Root 'SKILL.md') -Encoding UTF8 | Where-Object { $_ -match '^name:\s*' } | Select-Object -First 1
        if ($line) { $name = ($line -replace '^name:\s*', '').Trim() }
    }
    if (Test-Path -LiteralPath (Join-Path $Root 'VERSION') -PathType Leaf) { $version = (Get-Content -LiteralPath (Join-Path $Root 'VERSION') -Raw -Encoding UTF8).Trim() }
    $valid = $exists -and $name -eq $script:MinutesSkillName -and $version -match '^\d+\.\d+\.\d+$' -and
        $missing.Count -eq 0 -and $modified.Count -eq 0 -and $unexpected.Count -eq 0 -and $manifestErrors.Count -eq 0 -and $links.Count -eq 0
    return [pscustomobject]@{
        path = $Root; source_root = $SourceRoot; exists = $exists; skill_name = $name; skill_name_matches = ($name -eq $script:MinutesSkillName)
        version = $version; version_valid = ($version -match '^\d+\.\d+\.\d+$'); file_count = $Entries.Count
        missing = @($missing); modified = @($modified); unexpected = @($unexpected); runtime_cache = @($runtimeCache)
        manifest_errors = @($manifestErrors); broken_links = @($links); valid = [bool]$valid
    }
}

function Invoke-DeploymentTestFailure {
    param([string]$Phase)
    # Failure-only hook: it cannot bypass verification or write outside the chosen installation.
    if ($env:MINUTES_INSTALL_TEST_FAIL_PHASE -eq $Phase) { throw "격리 시험용 실패 주입: $Phase" }
}

function ConvertTo-DeploymentQuotedArgument {
    param([string]$Value)
    return "'" + $Value.Replace("'", "''") + "'"
}
