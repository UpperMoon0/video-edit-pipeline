param(
    [Parameter(Mandatory = $true)][string]$Project,
    [ValidateRange(1, 65535)][int]$Port = 8766,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$projectPath = (Resolve-Path -LiteralPath $Project).Path
if (Test-Path -LiteralPath $projectPath -PathType Container) {
    $projectPath = Join-Path $projectPath 'project.json'
}
$repoRoot = Split-Path $PSScriptRoot -Parent
$pythonPath = $env:PIPELINE_PYTHON
if (-not $pythonPath) {
    $localPython = Join-Path $repoRoot '.venv/Scripts/python.exe'
    if (Test-Path -LiteralPath $localPython) { $pythonPath = $localPython }
    else { $pythonPath = (Get-Command python -ErrorAction Stop).Source }
}
$serverPath = Join-Path $PSScriptRoot 'workspace.py'
$description = & $pythonPath $serverPath $projectPath --describe
if ($LASTEXITCODE -ne 0) { throw 'Workspace validation failed; server was not started.' }
$expected = $description | ConvertFrom-Json
$workspaceUrl = "http://127.0.0.1:$Port/"
$running = $null
try { $running = Invoke-RestMethod ($workspaceUrl + 'api/project') -TimeoutSec 2 } catch {}
if ($running) {
    if ($running.workspace_id -ne $expected.workspace_id) {
        throw "Port $Port is serving another workspace. Choose a different -Port; the existing server was preserved."
    }
    if ($running.version -ne $expected.version) {
        throw "Port $Port is running an older workspace API. Restart this workspace's owned server to load the updated pipeline code."
    }
} else {
    $workspaceDirectory = Split-Path $projectPath -Parent
    $serverProcess = Start-Process -FilePath $pythonPath -ArgumentList @(
        ('"' + $serverPath + '"'), ('"' + $projectPath + '"'), '--port', "$Port"
    ) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $workspaceDirectory "server-$Port.log") -RedirectStandardError (Join-Path $workspaceDirectory "server-$Port-error.log")
    $serverProcess.Id | Set-Content (Join-Path $workspaceDirectory "server-$Port.pid")
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try { $running = Invoke-RestMethod ($workspaceUrl + 'api/project') -TimeoutSec 1 } catch {}
        if ($running) { break }
        if ($serverProcess.HasExited) { throw "Workspace server exited. See server-$Port-error.log in the workspace." }
        Start-Sleep -Milliseconds 200
    }
    if (-not $running -or $running.workspace_id -ne $expected.workspace_id) {
        throw "Could not start this workspace on port $Port. Check the workspace's server logs."
    }
}
if (-not $NoBrowser) { Start-Process $workspaceUrl }
Write-Output "Video workspace: $workspaceUrl"
