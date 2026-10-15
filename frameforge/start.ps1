#Requires -Version 5.1
<#
.SYNOPSIS
  Start Frameforge backend (:8787) and frontend (:4200).
#>
param(
  [switch]$BackendOnly,
  [switch]$FrontendOnly,
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$LogsDir = Join-Path $Root "logs"
$PidFile = Join-Path $LogsDir "pids.json"

$BackendUrl = "http://127.0.0.1:8787"
$FrontendUrl = "http://127.0.0.1:4200"
$ComfyUrl = "http://127.0.0.1:8000"
$OllamaUrl = "http://127.0.0.1:11434"

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

function Test-HttpOk([string]$Url, [int]$TimeoutSec = 2) {
  try {
    $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
    return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500)
  } catch {
    return $false
  }
}

function Wait-HttpOk([string]$Url, [int]$Seconds = 60) {
  $deadline = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-HttpOk $Url) { return $true }
    Start-Sleep -Milliseconds 500
  }
  return $false
}

function Test-PortListen([int]$Port) {
  $c = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
  return ($c.Count -gt 0)
}

function Start-Backend {
  $health = $BackendUrl + "/health"
  if (Test-HttpOk $health 5) {
    Write-Host "backend: already running at $BackendUrl"
    return $null
  }
  if (Test-PortListen 8787) {
    Write-Host "backend: port 8787 in use, waiting for health ..."
    if (Wait-HttpOk $health 30) {
      Write-Host "backend: already running at $BackendUrl"
      return $null
    }
    throw "backend: port 8787 is in use but /health never answered"
  }
  $venvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
  if (-not (Test-Path $venvPython)) {
    throw "Backend venv missing: $venvPython. Create with: python -m venv .venv ; pip install -r requirements.txt"
  }
  $logOut = Join-Path $LogsDir "backend.out.log"
  $logErr = Join-Path $LogsDir "backend.err.log"
  $env:COMFY_LOCAL_URL = $ComfyUrl
  $env:PYTHONIOENCODING = "utf-8"
  Write-Host "backend: starting uvicorn on :8787 ..."
  $p = Start-Process -FilePath $venvPython `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8787") `
    -WorkingDirectory $BackendDir `
    -RedirectStandardOutput $logOut `
    -RedirectStandardError $logErr `
    -WindowStyle Hidden `
    -PassThru
  if (Wait-HttpOk $health 90) {
    Write-Host "backend: OK $BackendUrl/health (pid $($p.Id))"
    return $p.Id
  }
  # Health late / flaky port ownership: keep our process if /health answers.
  if (Test-HttpOk $health 5) {
    Write-Host "backend: OK $BackendUrl/health (pid $($p.Id))"
    return $p.Id
  }
  try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch { }
  throw "backend: failed to become healthy. See $logErr"
}

function Start-Frontend {
  if (Test-HttpOk $FrontendUrl 5) {
    Write-Host "frontend: already running at $FrontendUrl"
    return $null
  }
  if (Test-PortListen 4200) {
    Write-Host "frontend: port 4200 in use, waiting ..."
    if (Wait-HttpOk $FrontendUrl 60) {
      Write-Host "frontend: already running at $FrontendUrl"
      return $null
    }
    throw "frontend: port 4200 is in use but never answered"
  }
  $npmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
  if (-not $npmCmd) { $npmCmd = Get-Command npm -ErrorAction SilentlyContinue }
  if (-not $npmCmd) { throw "npm not found on PATH" }
  $nodeModules = Join-Path $FrontendDir "node_modules"
  if (-not (Test-Path $nodeModules)) {
    Write-Host "frontend: npm install ..."
    Push-Location $FrontendDir
    try { & npm.cmd install } finally { Pop-Location }
  }
  $logOut = Join-Path $LogsDir "frontend.out.log"
  $logErr = Join-Path $LogsDir "frontend.err.log"
  Write-Host "frontend: starting ng serve on :4200 ..."
  $p = Start-Process -FilePath $npmCmd.Source `
    -ArgumentList @("run", "start", "--", "--host", "127.0.0.1", "--port", "4200") `
    -WorkingDirectory $FrontendDir `
    -RedirectStandardOutput $logOut `
    -RedirectStandardError $logErr `
    -WindowStyle Hidden `
    -PassThru
  if (-not (Wait-HttpOk $FrontendUrl 120)) {
    throw "frontend: failed to become ready. See $logErr / $logOut"
  }
  Write-Host "frontend: OK $FrontendUrl (pid $($p.Id))"
  return $p.Id
}

function Ensure-Ollama {
  $tags = $OllamaUrl + "/api/tags"
  if (Test-HttpOk $tags 3) {
    Write-Host "ollama: OK $OllamaUrl"
    return
  }
  # Tray app alone is not enough - API must listen on :11434
  $ollamaCmd = Get-Command ollama.exe -ErrorAction SilentlyContinue
  if (-not $ollamaCmd) {
    $candidate = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path $candidate) {
      $ollamaCmd = @{ Source = $candidate }
    }
  }
  if (-not $ollamaCmd) {
    Write-Host "warn: Ollama not reachable at $OllamaUrl (prompt polish falls back)."
    return
  }
  Write-Host "ollama: API down - starting 'ollama serve' ..."
  Start-Process -FilePath $ollamaCmd.Source `
    -ArgumentList @("serve") `
    -WindowStyle Hidden `
    -ErrorAction SilentlyContinue | Out-Null
  if (Wait-HttpOk $tags 45) {
    Write-Host "ollama: OK $OllamaUrl"
  } else {
    Write-Host "warn: Ollama still not reachable at $OllamaUrl (prompt polish falls back)."
  }
}

Write-Host "=== Frameforge ==="
if (-not (Test-HttpOk ($ComfyUrl + "/system_stats"))) {
  Write-Host "warn: ComfyUI not reachable at $ComfyUrl - generation will fail until it is up."
} else {
  Write-Host "comfy: OK $ComfyUrl"
}
Ensure-Ollama

$pids = [ordered]@{
  backend   = $null
  frontend  = $null
  startedAt = (Get-Date).ToString("o")
}

if (-not $FrontendOnly) {
  $bid = Start-Backend
  if ($bid) { $pids.backend = $bid }
}
if (-not $BackendOnly) {
  $fid = Start-Frontend
  if ($fid) { $pids.frontend = $fid }
}

($pids | ConvertTo-Json) | Set-Content -Path $PidFile -Encoding UTF8

Write-Host ""
Write-Host "UI:  $FrontendUrl"
Write-Host "API: $BackendUrl/health"
Write-Host "Logs: $LogsDir"
Write-Host "Stop: .\stop.ps1"

if (-not $NoBrowser -and -not $BackendOnly) {
  Start-Process $FrontendUrl
}
