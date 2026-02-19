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

& $pythonExe .\otto_state.py set-status working --task 'Demo OTTO HQ en progreso'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$taskJson = & $pythonExe .\otto_state.py add-task --title 'Validar flujo HQ' --detail 'Crear tarea y moverla entre columnas' --priority high
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$task = $taskJson | ConvertFrom-Json
$taskId = $task.id
if (-not $taskId) {
  Write-Host '[OTTO HQ] No se pudo obtener task id desde add-task.' -ForegroundColor Yellow
  exit 1
}

& $pythonExe .\otto_state.py move-task $taskId --to in_progress
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $pythonExe .\scripts\append_ledger.py leads `
  --fecha '2026-02-11' `
  --empresa 'Empresa Demo' `
  --contacto 'operaciones@demo.com' `
  --canal 'whatsapp' `
  --ciudad 'Lima' `
  --proyecto 'Acabados interior' `
  --archivo-doc 'docs/empresa/leads/leads_2026-02-11.md'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $pythonExe .\otto_state.py move-task $taskId --to done
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $pythonExe .\otto_state.py set-status idle --task 'Demo completada'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $pythonExe .\index_docs.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host '[OTTO HQ] Demo completada.' -ForegroundColor Green
