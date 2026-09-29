function Resolve-PipelinePython {
    param([string]$Root, [string]$PythonPath)
    if ($PythonPath) { return (Get-Command $PythonPath -ErrorAction Stop).Source }
    if ($env:PIPELINE_PYTHON) { return (Get-Command $env:PIPELINE_PYTHON -ErrorAction Stop).Source }
    foreach ($relative in @('.venv/Scripts/python.exe', '.venv/bin/python')) {
        $candidate = Join-Path $Root $relative
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    return (Get-Command python -ErrorAction Stop).Source
}
