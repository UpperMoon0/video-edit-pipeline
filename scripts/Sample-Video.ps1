[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$OutputDirectory,
    [double]$IntervalSeconds = 10,
    [double]$StartSeconds = 0,
    [double]$EndSeconds = 0,
    [int]$Columns = 4,
    [int]$Rows = 4,
    [int]$ThumbnailWidth = 320
)

$ErrorActionPreference = 'Stop'
$resolved = (Resolve-Path -LiteralPath $InputPath).Path
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$frames = Join-Path $OutputDirectory 'frames'
New-Item -ItemType Directory -Path $frames -Force | Out-Null

$durationText = & ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 $resolved
if ($LASTEXITCODE -ne 0) { throw 'ffprobe failed.' }
$duration = [double]::Parse(($durationText | Select-Object -First 1), [Globalization.CultureInfo]::InvariantCulture)
$rangeEnd = if ($EndSeconds -gt $StartSeconds) { [math]::Min($EndSeconds, $duration) } else { $duration }
$rangeDuration = $rangeEnd - $StartSeconds
$frameCount = [math]::Ceiling($rangeDuration / $IntervalSeconds)
$perSheet = $Columns * $Rows

for ($index = 0; $index -lt $frameCount; $index++) {
    $timestamp = [math]::Min($StartSeconds + (($index + 0.5) * $IntervalSeconds), $rangeEnd - 0.05)
    $stamp = $timestamp.ToString('0.0', [Globalization.CultureInfo]::InvariantCulture)
    $frame = Join-Path $frames ("frame-{0:D4}.jpg" -f $index)
    & ffmpeg -hide_banner -loglevel error -y -ss $stamp -i $resolved -frames:v 1 -vf "scale=${ThumbnailWidth}:-2" -q:v 3 $frame
    if ($LASTEXITCODE -ne 0) { throw "Frame extraction failed at $stamp seconds." }
}

$sheetCount = [math]::Ceiling($frameCount / $perSheet)
for ($sheet = 0; $sheet -lt $sheetCount; $sheet++) {
    $start = $sheet * $perSheet
    $count = [math]::Min($perSheet, $frameCount - $start)
    $pattern = Join-Path $frames 'frame-%04d.jpg'
    $output = Join-Path $OutputDirectory ("sheet-{0:D2}.jpg" -f ($sheet + 1))
    $filter = "tile=${Columns}x${Rows}:nb_frames=${count}:padding=2:margin=2:color=black"
    & ffmpeg -hide_banner -loglevel error -y -framerate 1 -start_number $start -i $pattern -vf $filter -frames:v 1 -q:v 3 $output
    if ($LASTEXITCODE -ne 0) { throw "Contact sheet $sheet failed." }
}

[ordered]@{
    input = $resolved
    duration = $duration
    interval_seconds = $IntervalSeconds
    start_seconds = $StartSeconds
    end_seconds = $rangeEnd
    frame_count = $frameCount
    columns = $Columns
    rows = $Rows
    mapping = 'Frame N (zero-based) is sampled at min(start_seconds + (N + 0.5) * interval_seconds, end_seconds - 0.05).'
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'index.json') -Encoding utf8

Write-Output "Created $sheetCount contact sheets with $frameCount sampled frames in $OutputDirectory"
