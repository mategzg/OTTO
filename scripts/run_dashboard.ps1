Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root

$venvPython = Join-Path $Root '.venv\Scripts\python.exe'
if (Test-Path $venvPython) {
  $pythonExe = $venvPython
} else {
  $python = Get-Command python -ErrorAction SilentlyContinue
  if (-not $python) {
    Write-Host '[OTTO HQ] Python no encontrado. Ejecuta scripts\bootstrap.ps1 primero.' -ForegroundColor Yellow
    exit 1
  }
  $pythonExe = $python.Source
  Write-Host '[OTTO HQ] Usando Python global (sin .venv).' -ForegroundColor Yellow
}

& $pythonExe .\dashboard_server.py --host 127.0.0.1 --port 18999 --root $Root
