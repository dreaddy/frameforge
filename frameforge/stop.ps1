#Requires -Version 5.1
<#
.SYNOPSIS
  Stop Frameforge processes started by start.ps1 (ports 8787 / 4200).
#>
$ErrorActionPreference = "Continue"
$Root = $PSScriptRoot
$LogsDir = Join-Path $Root "logs"
$PidFile = Join-Path $LogsDir "pids.json"

function Stop-Port([int]$Port, [string]$Label) {
  $pids = @(
    Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
      Select-Object -ExpandProperty OwningProcess -Unique
  )
  if (-not $pids -or $pids.Count -eq 0) {
    Write-Host "$Label : not listening on :$Port"
    return
  }
  foreach ($procId in $pids) {
    try {
      $proc = Get-Process -Id $procId -ErrorAction Stop
      Write-Host "$Label : stopping pid $procId ($($proc.ProcessName))"
      Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    } catch {
      Write-Host "$Label : could not stop pid $procId"
    }
  }
}

Write-Host "=== Frameforge stop ==="
Stop-Port 8787 "backend"
Stop-Port 4200 "frontend"

if (Test-Path $PidFile) {
  try {
    $pids = Get-Content $PidFile -Raw | ConvertFrom-Json
    foreach ($name in @("backend", "frontend")) {
      $procId = $pids.$name
      if ($procId) {
        Stop-Process -Id ([int]$procId) -Force -ErrorAction SilentlyContinue
      }
    }
  } catch { }
  Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

Write-Host "Done."
