param(
    [string]$ModelName = 'aicodex',
    [switch]$Run
)

$ErrorActionPreference = 'Stop'

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    throw 'Ollama was not found. Install it from https://ollama.com/download, reopen PowerShell, and run this script again.'
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$modelfile = Join-Path $repoRoot 'Modelfile'

if (-not (Test-Path -LiteralPath $modelfile -PathType Leaf)) {
    throw "Modelfile not found: $modelfile"
}

$fromLine = Select-String -LiteralPath $modelfile -Pattern '^\s*FROM\s+(\S+)' | Select-Object -First 1
$baseModel = if ($fromLine) { $fromLine.Matches[0].Groups[1].Value } else { $null }
if (-not $baseModel) {
    throw "No FROM line found in $modelfile"
}

Write-Host "Downloading base model $baseModel (skips the download if already present)..."
& ollama pull $baseModel
if ($LASTEXITCODE -ne 0) {
    throw "ollama pull failed with exit code $LASTEXITCODE."
}

Write-Host "Building local model '$ModelName' from the repository Modelfile..."
& ollama create $ModelName -f $modelfile
if ($LASTEXITCODE -ne 0) {
    throw "ollama create failed with exit code $LASTEXITCODE."
}

Write-Host "AICodex is ready. Start it any time with: ollama run $ModelName"

if ($Run) {
    & ollama run $ModelName
}
