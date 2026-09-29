[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$OutputDirectory,
    [double]$IntervalSeconds = 10,
    [double]$StartSeconds = 0,
    [double]$EndSeconds = 0,
    [int]$Columns = 4,
    [int]$Rows = 4,
    [int]$ThumbnailWidth = 320,
    [string]$PythonPath
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Python-Bridge.ps1')
$python = Resolve-PipelinePython -Root (Split-Path $PSScriptRoot -Parent) -PythonPath $PythonPath
$culture = [Globalization.CultureInfo]::InvariantCulture
$arguments = @((Join-Path $PSScriptRoot 'pipeline.py'), 'sample', $InputPath, $OutputDirectory,
    '--interval', $IntervalSeconds.ToString('R', $culture), '--start', $StartSeconds.ToString('R', $culture),
    '--end', $EndSeconds.ToString('R', $culture), '--columns', $Columns, '--rows', $Rows, '--width', $ThumbnailWidth)
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw "Sampling failed with exit code $LASTEXITCODE; see the structured error above." }
