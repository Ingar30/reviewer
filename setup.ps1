param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".venv")) {
    & $Python -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

Write-Host ""
Write-Host "Setup complete."
Write-Host "Activate with: .\.venv\Scripts\Activate.ps1"
Write-Host "Run tests with: python -m unittest"

if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
    Write-Warning "Codex CLI was not found on PATH. Install/authenticate Codex before running scripts\review_paper.py."
}
