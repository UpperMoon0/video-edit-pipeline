[CmdletBinding()]
param(
    [ValidateSet('Install', 'Status', 'Start', 'Stop', 'Remove')][string]$Action = 'Install',
    [switch]$Remove,
    [switch]$StartNow,
    [string]$Root = (Split-Path $PSScriptRoot -Parent),
    [string]$ConfigPath,
    [string]$PythonPath,
    [string]$TaskName
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Python-Bridge.ps1')
$Root = [IO.Path]::GetFullPath($Root)
if (-not $ConfigPath) { $ConfigPath = Join-Path $Root 'config.json' }
if ($Remove) { $Action = 'Remove' }
$hash = [Security.Cryptography.SHA256]::Create()
try { $rootHash = ([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($Root.ToLowerInvariant()))) -replace '-', '').Substring(0, 12) }
finally { $hash.Dispose() }
if (-not $TaskName) { $TaskName = "VideoEditPipeline-$rootHash" }
if ($TaskName -notmatch '^VideoEditPipeline-[A-Za-z0-9_-]+$') { throw 'TaskName must use the VideoEditPipeline- prefix and safe identifier characters.' }
$state = Join-Path $Root 'state'
$settingsPath = Join-Path $state 'watcher-task.json'
$launcher = Join-Path $state 'watcher-launch.ps1'
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$settings = if (Test-Path -LiteralPath $settingsPath) { Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json } else { $null }
if ($task -and ((-not $settings) -or $settings.task_name -ne $TaskName -or $settings.root -ne $Root)) {
    throw 'Existing task ownership cannot be established; refusing to modify it.'
}
function Show-WatcherStatus {
    $current = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    $info = if ($current) { Get-ScheduledTaskInfo -TaskName $TaskName } else { $null }
    $healthPath = Join-Path $state 'watcher-health.json'
    $health = if (Test-Path -LiteralPath $healthPath) { Get-Content -LiteralPath $healthPath -Raw -Encoding UTF8 | ConvertFrom-Json } else { $null }
    [ordered]@{ version=1; task_name=$TaskName; installed=[bool]$current;
        state=if ($current) { [string]$current.State } else { 'NotInstalled' };
        last_task_result=if ($info) { $info.LastTaskResult } else { $null };
        health=$health; root=$Root } | ConvertTo-Json -Depth 10
}
if ($Action -eq 'Status') { Show-WatcherStatus; return }
if ($Action -eq 'Stop') {
    # Scheduler state may lag a live child/health update. Always signal the
    # proven owned workspace when its task exists; never gate shutdown on it.
    if ($task) {
        [IO.File]::WriteAllText((Join-Path $state 'watcher-stop.request'), 'stop', [Text.UTF8Encoding]::new($false))
        [ordered]@{ version=1; task_name=$TaskName; status='stop-requested' } | ConvertTo-Json
    } else { Show-WatcherStatus }
    return
}
if ($Action -eq 'Remove') {
    if ($task) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
    [ordered]@{ version=1; task_name=$TaskName; status='removed'; workspace_preserved=$true } | ConvertTo-Json
    return
}
if ($Action -eq 'Start') {
    if (-not $task) { throw 'Watcher is not installed for this checkout.' }
    Start-ScheduledTask -TaskName $TaskName
    Show-WatcherStatus
    return
}
$python = Resolve-PipelinePython -Root (Split-Path $PSScriptRoot -Parent) -PythonPath $PythonPath
$cli = Join-Path $PSScriptRoot 'pipeline.py'
$diagnostic = & $python $cli --root $Root --config $ConfigPath doctor
if ($LASTEXITCODE -ne 0) { $diagnostic; throw 'Doctor failed; watcher was not installed.' }
& $python $cli --root $Root --config $ConfigPath setup | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Pipeline setup failed.' }
$ffmpeg = if ($env:PIPELINE_FFMPEG) { (Get-Command $env:PIPELINE_FFMPEG).Source } else { (Get-Command ffmpeg).Source }
$ffprobe = if ($env:PIPELINE_FFPROBE) { (Get-Command $env:PIPELINE_FFPROBE).Source } else { (Get-Command ffprobe).Source }
$settings = [ordered]@{ version=1; task_name=$TaskName; root=$Root; config=[IO.Path]::GetFullPath($ConfigPath);
    python=$python; cli=$cli; ffmpeg=$ffmpeg; ffprobe=$ffprobe }
[IO.File]::WriteAllText($settingsPath, ($settings | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
$content = @'
$ErrorActionPreference = 'Stop'
$settings = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'watcher-task.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$env:PIPELINE_FFMPEG = $settings.ffmpeg
$env:PIPELINE_FFPROBE = $settings.ffprobe
$env:PYTHONUTF8 = '1'
& $settings.python $settings.cli --root $settings.root --config $settings.config watch
exit $LASTEXITCODE
'@
[IO.File]::WriteAllText($launcher, $content, [Text.UTF8Encoding]::new($false))
$powerShell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$actionObject = New-ScheduledTaskAction -Execute $powerShell -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $launcher + '"') -WorkingDirectory $Root
$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$taskSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $TaskName -Action $actionObject -Trigger $trigger -Principal $principal -Settings $taskSettings -Description 'Local video ingest watcher; scoped to one checkout, no provider downloads.' -Force | Out-Null
if ($StartNow) { Start-ScheduledTask -TaskName $TaskName }
Show-WatcherStatus
