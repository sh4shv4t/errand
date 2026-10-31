# Errand one-command start for Windows (PowerShell): installs on first run, then opens the dashboard.
#   powershell -ExecutionPolicy Bypass -File start.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path ".venv")) {
    $py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
    Write-Host "First run: creating .venv and installing Errand..."
    & $py -m venv .venv
    & .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
    & .\.venv\Scripts\python.exe -m pip install --quiet -e .
}
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
& .\.venv\Scripts\errand.exe up @args
