[CmdletBinding()]
param(
    [ValidateSet('Setup', 'Discover', 'Ingest', 'Resume', 'Watch')]
    [string]$Action = 'Discover',
    [string]$SourcePath,
    [string]$JobPath,
    [string]$ConfigPath = (Join-Path (Split-Path $PSScriptRoot -Parent) 'config.json'),
    [switch]$Once
)

$ErrorActionPreference = 'Stop'
$PipelineRoot = Split-Path $PSScriptRoot -Parent
$JobsRoot = Join-Path $PipelineRoot 'jobs'
$StateRoot = Join-Path $PipelineRoot 'state'
$RegistryPath = Join-Path $StateRoot 'processed.json'

function Read-Config {
    if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
        throw "Configuration file not found: $ConfigPath"
    }
    return Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
}

function Initialize-Pipeline {
    param([object]$Config)

    foreach ($path in @($JobsRoot, $StateRoot, (Join-Path $PipelineRoot 'logs'))) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
    foreach ($path in $Config.inbox_paths) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
    if (-not (Test-Path -LiteralPath $RegistryPath)) {
        '[]' | Set-Content -LiteralPath $RegistryPath -Encoding utf8
    }
}

function Get-MediaFiles {
    param([object]$Config)

    $allowed = @($Config.extensions | ForEach-Object { $_.ToLowerInvariant() })
    $files = foreach ($path in $Config.inbox_paths) {
        if (Test-Path -LiteralPath $path -PathType Container) {
            Get-ChildItem -LiteralPath $path -File -ErrorAction SilentlyContinue |
                Where-Object { $allowed -contains $_.Extension.ToLowerInvariant() }
        }
    }
    return @($files | Sort-Object LastWriteTime, FullName)
}

function Test-FileReady {
    param(
        [System.IO.FileInfo]$File,
        [int]$StableSeconds
    )

    if (((Get-Date) - $File.LastWriteTime).TotalSeconds -lt $StableSeconds) {
        return $false
    }
    try {
        $stream = [System.IO.File]::Open($File.FullName, 'Open', 'Read', 'Read')
        $stream.Dispose()
        return $true
    }
    catch {
        return $false
    }
}

function ConvertTo-SafeName {
    param([string]$Name)

    $safe = $Name -replace '[^A-Za-z0-9._-]+', '-'
    $safe = $safe.Trim('-', '.')
    if ([string]::IsNullOrWhiteSpace($safe)) { return 'media' }
    return $safe
}

function Read-Registry {
    if (-not (Test-Path -LiteralPath $RegistryPath)) { return @() }
    $content = Get-Content -LiteralPath $RegistryPath -Raw
    if ([string]::IsNullOrWhiteSpace($content)) { return @() }
    $parsed = ConvertFrom-Json $content
    foreach ($entry in @($parsed)) {
        if ($entry.PSObject.Properties['original_path']) { Write-Output $entry }
    }
}

function Write-Registry {
    param([object[]]$Entries)
    @($Entries) | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $RegistryPath -Encoding utf8
}

function Copy-WithSha256 {
    param(
        [string]$Source,
        [string]$Destination
    )

    $buffer = New-Object byte[] (8MB)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $inputStream = [System.IO.File]::Open($Source, 'Open', 'Read', 'Read')
    $outputStream = [System.IO.File]::Open($Destination, 'CreateNew', 'Write', 'None')
    try {
        while (($read = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $outputStream.Write($buffer, 0, $read)
            [void]$sha.TransformBlock($buffer, 0, $read, $null, 0)
        }
        [void]$sha.TransformFinalBlock($buffer, 0, 0)
        $outputStream.Flush($true)
        return ([BitConverter]::ToString($sha.Hash) -replace '-', '')
    }
    finally {
        $outputStream.Dispose()
        $inputStream.Dispose()
        $sha.Dispose()
    }
}

function Get-SampledSha256 {
    param([string]$Path)

    $sampleSize = 4MB
    $file = Get-Item -LiteralPath $Path
    [int64]$length = $file.Length
    [int64]$middle = [math]::Floor(($length - $sampleSize) / 2)
    [int64]$last = $length - $sampleSize
    if ($middle -lt 0) { $middle = 0 }
    if ($last -lt 0) { $last = 0 }
    $positions = @(
        [int64]0,
        $middle,
        $last
    ) | Select-Object -Unique
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $stream = [System.IO.File]::Open($file.FullName, 'Open', 'Read', 'Read')
    $buffer = New-Object byte[] $sampleSize
    try {
        $lengthBytes = [BitConverter]::GetBytes([int64]$length)
        [void]$sha.TransformBlock($lengthBytes, 0, $lengthBytes.Length, $null, 0)
        foreach ($position in $positions) {
            [void]$stream.Seek($position, 'Begin')
            [int64]$available = $length - $position
            $remaining = if ($available -lt $sampleSize) { [int]$available } else { [int]$sampleSize }
            $offset = 0
            while ($remaining -gt 0) {
                $read = $stream.Read($buffer, $offset, $remaining)
                if ($read -le 0) { break }
                $offset += $read
                $remaining -= $read
            }
            [void]$sha.TransformBlock($buffer, 0, $offset, $null, 0)
        }
        [void]$sha.TransformFinalBlock($buffer, 0, 0)
        return ([BitConverter]::ToString($sha.Hash) -replace '-', '')
    }
    finally {
        $stream.Dispose()
        $sha.Dispose()
    }
}

function Invoke-External {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath failed with exit code $LASTEXITCODE"
    }
}

function Send-IngestNotification {
    param(
        [string]$MediaName,
        [string]$JobPath
    )

    try {
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        $notification = New-Object System.Windows.Forms.NotifyIcon
        $notification.Icon = [System.Drawing.SystemIcons]::Information
        $notification.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Info
        $notification.BalloonTipTitle = 'Codex video is ready'
        $notification.BalloonTipText = "$MediaName was cloned and analyzed. Tell Codex: Use the latest inbox video."
        $notification.Visible = $true
        $notification.ShowBalloonTip(10000)
        Start-Sleep -Milliseconds 12000
        $notification.Dispose()
    }
    catch {
        Write-Warning "Could not display Windows notification: $($_.Exception.Message)"
    }
}

function New-ContactSheet {
    param(
        [string]$ClonePath,
        [string]$ProbePath,
        [string]$OutputPath,
        [int]$FrameCount
    )

    $probe = Get-Content -LiteralPath $ProbePath -Raw | ConvertFrom-Json
    $videoStream = @($probe.streams | Where-Object { $_.codec_type -eq 'video' } | Select-Object -First 1)
    if ($videoStream.Count -eq 0) { return }

    $duration = [double]$probe.format.duration
    if ($duration -le 0) { return }

    $columns = [math]::Ceiling([math]::Sqrt($FrameCount))
    $rows = [math]::Ceiling($FrameCount / $columns)
    $tempDir = Join-Path (Split-Path $OutputPath -Parent) 'contact-sheet-frames'
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
    try {
        for ($index = 0; $index -lt $FrameCount; $index++) {
            $timestamp = (($index + 0.5) * $duration / $FrameCount).ToString('0.######', [Globalization.CultureInfo]::InvariantCulture)
            $framePath = Join-Path $tempDir ("frame-{0:D3}.jpg" -f $index)
            Invoke-External -FilePath 'ffmpeg' -Arguments @('-hide_banner', '-loglevel', 'error', '-y', '-ss', $timestamp, '-i', $ClonePath, '-frames:v', '1', '-vf', 'scale=320:-2', '-q:v', '3', $framePath)
        }
        $pattern = Join-Path $tempDir 'frame-%03d.jpg'
        $filter = "tile=${columns}x${rows}:nb_frames=${FrameCount}:padding=2:margin=2:color=black"
        Invoke-External -FilePath 'ffmpeg' -Arguments @('-hide_banner', '-loglevel', 'error', '-y', '-framerate', '1', '-start_number', '0', '-i', $pattern, '-vf', $filter, '-frames:v', '1', '-q:v', '3', $OutputPath)
    }
    finally {
        if (Test-Path -LiteralPath $tempDir) {
            Remove-Item -LiteralPath $tempDir -Recurse -Force
        }
    }
}

function Resume-PreparedJob {
    param(
        [string]$Path,
        [string]$OriginalPath,
        [object]$Config
    )

    $resolvedJob = (Resolve-Path -LiteralPath $Path).Path
    $clone = Get-ChildItem -LiteralPath (Join-Path $resolvedJob 'source') -File | Select-Object -First 1
    if (-not $clone) { throw "No cloned media found in $resolvedJob\source" }
    $analysisDir = Join-Path $resolvedJob 'analysis'
    $editDir = Join-Path $resolvedJob 'edit'
    $outputDir = Join-Path $resolvedJob 'output'
    foreach ($dir in @($analysisDir, $editDir, $outputDir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

    $probePath = Join-Path $analysisDir 'probe.json'
    & ffprobe -v error -show_format -show_streams -of json $clone.FullName | Set-Content -LiteralPath $probePath -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "ffprobe failed with exit code $LASTEXITCODE" }
    $probe = Get-Content -LiteralPath $probePath -Raw | ConvertFrom-Json
    $voicePath = Join-Path $analysisDir 'voiceover.wav'
    if (-not (Test-Path -LiteralPath $voicePath) -and @($probe.streams | Where-Object { $_.codec_type -eq 'audio' }).Count -gt 0) {
        Invoke-External -FilePath 'ffmpeg' -Arguments @('-hide_banner', '-loglevel', 'error', '-y', '-i', $clone.FullName, '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', $voicePath)
    }
    New-ContactSheet -ClonePath $clone.FullName -ProbePath $probePath -OutputPath (Join-Path $analysisDir 'contact-sheet.jpg') -FrameCount ([int]$Config.contact_sheet_frames)

    if (-not (Test-Path -LiteralPath (Join-Path $analysisDir 'transcript.json'))) {
        [ordered]@{ version = 1; status = 'awaiting_transcription'; language = $null; segments = @() } |
            ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $analysisDir 'transcript.json') -Encoding utf8
    }
    if (-not (Test-Path -LiteralPath (Join-Path $editDir 'timeline.json'))) {
        [ordered]@{
            version = 1; source = "../source/$($clone.Name)"; output = '../output/final.mp4'
            video = [ordered]@{ width = 1920; height = 1080; fps = 30 }; cuts = @()
        } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $editDir 'timeline.json') -Encoding utf8
    }

    $resolvedOriginal = if ($OriginalPath) { (Resolve-Path -LiteralPath $OriginalPath).Path } else { $null }
    $verified = $true
    if ($resolvedOriginal) {
        $verified = (Get-Item -LiteralPath $resolvedOriginal).Length -eq $clone.Length -and
            (Get-SampledSha256 -Path $resolvedOriginal) -eq (Get-SampledSha256 -Path $clone.FullName)
    }
    if (-not $verified) { throw 'Resumed clone verification failed.' }
    [ordered]@{
        version = 1; job_id = (Split-Path $resolvedJob -Leaf); created_at = (Get-Date).ToString('o')
        original_path = $resolvedOriginal; original_size = $clone.Length; clone_path = $clone.FullName
        clone_verified = $true; clone_verification_mode = 'size-and-sampled-blocks'; original_modified = $false
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $resolvedJob 'manifest.json') -Encoding utf8
    @('READY', "Media: $($clone.Name)", "Prepared: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')", "Job: $resolvedJob", 'Next: Tell Codex "Use the latest inbox video."') |
        Set-Content -LiteralPath (Join-Path $resolvedJob 'READY.txt') -Encoding utf8

    if ($resolvedOriginal) {
        $registry = @(Read-Registry)
        $original = Get-Item -LiteralPath $resolvedOriginal
        $registry += [pscustomobject]@{
            sha256 = $null; original_path = $resolvedOriginal; original_size = $original.Length
            original_last_write_utc = $original.LastWriteTimeUtc.ToString('o'); job_path = $resolvedJob
            ingested_at = (Get-Date).ToString('o')
        }
        Write-Registry -Entries $registry
    }
    Send-IngestNotification -MediaName $clone.Name -JobPath $resolvedJob
    Write-Output "Resumed and prepared: $resolvedJob"
}

function Ingest-Media {
    param(
        [string]$Path,
        [object]$Config
    )

    $resolved = (Resolve-Path -LiteralPath $Path).Path
    $source = Get-Item -LiteralPath $resolved
    if (-not $source.PSIsContainer -and -not (Test-FileReady -File $source -StableSeconds ([int]$Config.stable_seconds))) {
        throw "Source is still changing or locked: $resolved"
    }

    $registry = @(Read-Registry)
    $existing = @($registry | Where-Object {
        $_.original_path -eq $resolved -and
        ((-not $_.PSObject.Properties['original_size']) -or (
            $_.original_size -eq $source.Length -and
            $_.original_last_write_utc -eq $source.LastWriteTimeUtc.ToString('o')
        ))
    } | Select-Object -First 1)
    if ($existing.Count -gt 0) {
        Write-Output "Already ingested: $($existing[0].job_path)"
        return $existing[0].job_path
    }

    $stem = ConvertTo-SafeName ([System.IO.Path]::GetFileNameWithoutExtension($source.Name))
    $jobId = "$(Get-Date -Format 'yyyyMMdd-HHmmss')-$stem"
    $jobPath = Join-Path $JobsRoot $jobId
    $sourceDir = Join-Path $jobPath 'source'
    $analysisDir = Join-Path $jobPath 'analysis'
    $editDir = Join-Path $jobPath 'edit'
    $outputDir = Join-Path $jobPath 'output'
    foreach ($dir in @($sourceDir, $analysisDir, $editDir, $outputDir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    $clonePath = Join-Path $sourceDir $source.Name
    $sourceHash = Copy-WithSha256 -Source $resolved -Destination $clonePath
    if ($source.Length -gt 2GB) {
        $verificationMode = 'size-and-sampled-blocks'
        $sourceSampleHash = Get-SampledSha256 -Path $resolved
        $cloneSampleHash = Get-SampledSha256 -Path $clonePath
        if ($source.Length -ne (Get-Item -LiteralPath $clonePath).Length -or $sourceSampleHash -ne $cloneSampleHash) {
            throw "Sampled clone verification failed for $resolved"
        }
    }
    else {
        $verificationMode = 'full-sha256'
        $cloneHash = (Get-FileHash -LiteralPath $clonePath -Algorithm SHA256).Hash
        if ($cloneHash -ne $sourceHash) {
            throw "Clone verification failed for $resolved"
        }
    }
    (Get-Item -LiteralPath $clonePath).IsReadOnly = $true

    $probePath = Join-Path $analysisDir 'probe.json'
    & ffprobe -v error -show_format -show_streams -of json $clonePath | Set-Content -LiteralPath $probePath -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "ffprobe failed with exit code $LASTEXITCODE" }

    $voicePath = Join-Path $analysisDir 'voiceover.wav'
    $probe = Get-Content -LiteralPath $probePath -Raw | ConvertFrom-Json
    if (@($probe.streams | Where-Object { $_.codec_type -eq 'audio' }).Count -gt 0) {
        Invoke-External -FilePath 'ffmpeg' -Arguments @('-hide_banner', '-loglevel', 'error', '-y', '-i', $clonePath, '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', $voicePath)
    }

    New-ContactSheet -ClonePath $clonePath -ProbePath $probePath -OutputPath (Join-Path $analysisDir 'contact-sheet.jpg') -FrameCount ([int]$Config.contact_sheet_frames)

    [ordered]@{
        version = 1
        status = 'awaiting_transcription'
        language = $null
        segments = @()
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $analysisDir 'transcript.json') -Encoding utf8

    [ordered]@{
        version = 1
        source = "../source/$($source.Name)"
        output = '../output/final.mp4'
        video = [ordered]@{ width = 1920; height = 1080; fps = 30 }
        cuts = @()
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $editDir 'timeline.json') -Encoding utf8

    $manifest = [ordered]@{
        version = 1
        job_id = $jobId
        created_at = (Get-Date).ToString('o')
        original_path = $resolved
        original_last_write_utc = $source.LastWriteTimeUtc.ToString('o')
        original_size = $source.Length
        sha256 = $sourceHash
        clone_path = $clonePath
        clone_verified = $true
        clone_verification_mode = $verificationMode
        original_modified = $false
    }
    $manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $jobPath 'manifest.json') -Encoding utf8

    @(
        'READY'
        "Media: $($source.Name)"
        "Prepared: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        "Job: $jobPath"
        'Next: Tell Codex "Use the latest inbox video."'
    ) | Set-Content -LiteralPath (Join-Path $jobPath 'READY.txt') -Encoding utf8

    $registry += [pscustomobject]@{
        sha256 = $sourceHash
        original_path = $resolved
        original_size = $source.Length
        original_last_write_utc = $source.LastWriteTimeUtc.ToString('o')
        job_path = $jobPath
        ingested_at = (Get-Date).ToString('o')
    }
    Write-Registry -Entries $registry

    Write-Output "Ingested and verified: $jobPath"
    Send-IngestNotification -MediaName $source.Name -JobPath $jobPath
    return $jobPath
}

$config = Read-Config
Initialize-Pipeline -Config $config

switch ($Action) {
    'Setup' {
        Write-Output 'Media pipeline folders are ready.'
        $config.inbox_paths | ForEach-Object { Write-Output "Inbox: $_" }
    }
    'Discover' {
        Get-MediaFiles -Config $config | Select-Object FullName, Length, LastWriteTime
    }
    'Ingest' {
        if ([string]::IsNullOrWhiteSpace($SourcePath)) { throw '-SourcePath is required for Ingest.' }
        Ingest-Media -Path $SourcePath -Config $config
    }
    'Resume' {
        if ([string]::IsNullOrWhiteSpace($JobPath)) { throw '-JobPath is required for Resume.' }
        Resume-PreparedJob -Path $JobPath -OriginalPath $SourcePath -Config $config
    }
    'Watch' {
        Write-Output 'Watching media inboxes. Press Ctrl+C to stop.'
        do {
            foreach ($file in Get-MediaFiles -Config $config) {
                if (Test-FileReady -File $file -StableSeconds ([int]$config.stable_seconds)) {
                    try { Ingest-Media -Path $file.FullName -Config $config | Write-Output }
                    catch { Write-Error $_ -ErrorAction Continue }
                }
            }
            if (-not $Once) { Start-Sleep -Seconds ([int]$config.poll_seconds) }
        } while (-not $Once)
    }
}
