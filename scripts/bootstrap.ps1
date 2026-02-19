Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root

$py = Get-Command py -ErrorAction SilentlyContinue
$python = Get-Command python -ErrorAction SilentlyContinue

if ($py) {
  $pythonExe = $py.Source
  $pythonArgs = @('-3')
} elseif ($python) {
  $pythonExe = $python.Source
  $pythonArgs = @()
} else {
  Write-Host '[OTTO HQ] Python no encontrado. Instala Python 3.10+ y vuelve a ejecutar.' -ForegroundColor Yellow
  exit 1
}

if (-not (Test-Path '.venv')) {
  Write-Host '[OTTO HQ] Creando entorno virtual .venv ...'
  & $pythonExe @pythonArgs -m venv .venv
}

$venvPython = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
  Write-Host '[OTTO HQ] No se encontro .venv\Scripts\python.exe. Revisa tu instalacion de Python.' -ForegroundColor Yellow
  exit 1
}

Write-Host '[OTTO HQ] Instalando dependencias...'
& $venvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
  Write-Host '[OTTO HQ] Fallo instalando dependencias.' -ForegroundColor Yellow
  exit $LASTEXITCODE
}

Write-Host '[OTTO HQ] Ejecutando tests...'
& $venvPython -m pytest -q
if ($LASTEXITCODE -ne 0) {
  Write-Host '[OTTO HQ] Tests con fallos.' -ForegroundColor Yellow
  exit $LASTEXITCODE
}

Write-Host '[OTTO HQ] Bootstrap completado.' -ForegroundColor Green
