$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:COMFY_LOCAL_URL = "http://127.0.0.1:8000"
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8787 --reload
