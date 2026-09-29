[CmdletBinding()]
param(
    [ValidateSet('Setup', 'Discover', 'Ingest', 'Resume', 'Watch', 'Doctor', 'List', 'Status', 'LatestReady', 'Retry', 'Cancel', 'Quarantine')]
    [string]$Action = 'Discover',
    [string]$SourcePath,
    [string]$JobPath,
    [string]$JobId,
    [string]$ConfigPath,
    [string]$Root = (Split-Path $PSScriptRoot -Parent),
    [string]$PythonPath,
    [switch]$Once
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Python-Bridge.ps1')
$python = Resolve-PipelinePython -Root (Split-Path $PSScriptRoot -Parent) -PythonPath $PythonPath
if (-not $ConfigPath) { $ConfigPath = Join-Path $Root 'config.json' }
$names = @{ Setup='setup'; Discover='discover'; Ingest='ingest'; Resume='resume'; Watch='watch'; Doctor='doctor'; List='jobs-list'; Status='job-status'; LatestReady='latest-ready'; Retry='retry'; Cancel='cancel'; Quarantine='quarantine' }
$arguments = @((Join-Path $PSScriptRoot 'pipeline.py'), '--root', $Root, '--config', $ConfigPath, $names[$Action])
switch ($Action) {
    'Ingest' {
        if (-not $SourcePath) { throw '-SourcePath is required for Ingest.' }
        $arguments += $SourcePath
    }
    'Resume' {
        if (-not $JobPath) { throw '-JobPath is required for Resume.' }
        $arguments += $JobPath
        if ($SourcePath) { $arguments += @('--source', $SourcePath) }
    }
    'Watch' { if ($Once) { $arguments += '--once' } }
    { $_ -in @('Status', 'Retry', 'Cancel', 'Quarantine') } {
        $identifier = if ($JobId) { $JobId } else { $JobPath }
        if (-not $identifier) { throw '-JobId or -JobPath is required for this action.' }
        $arguments += $identifier
    }
}
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw "Pipeline action $Action failed with exit code $LASTEXITCODE; see the structured error above." }
