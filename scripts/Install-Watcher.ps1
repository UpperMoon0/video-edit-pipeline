[CmdletBinding()]
param([switch]$Remove)

$ErrorActionPreference = 'Stop'
$taskName = 'CodexVideoMediaInbox'
$watcher = Join-Path $PSScriptRoot 'MediaPipeline.ps1'
$pipelineRoot = Split-Path $PSScriptRoot -Parent
$logPath = Join-Path $pipelineRoot 'logs\watcher.log'

if ($Remove) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "Removed scheduled task: $taskName"
    exit 0
}

& $watcher -Action Setup

$quotedWatcher = $watcher.Replace("'", "''")
$quotedLog = $logPath.Replace("'", "''")
$arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command `"& '$quotedWatcher' -Action Watch *>> '$quotedLog'`""
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description 'Clones and analyzes new media for the Codex video-edit pipeline.' -Force | Out-Null
Write-Output "Installed scheduled task: $taskName"
