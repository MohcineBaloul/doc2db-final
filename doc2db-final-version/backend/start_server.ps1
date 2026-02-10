# Doc2DB-Gen: start server on 8000 (try to free port first)
$port = 8000
Write-Host "Checking port $port..."
$conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    $pids = $conn.OwningProcess | Sort-Object -Unique
    foreach ($p in $pids) {
        if ($p -gt 0) {
            Write-Host "Stopping process $p..."
            Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 2
}
$venv = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venv)) {
    Write-Host "Run first: python -m venv .venv && .venv\Scripts\pip install -r requirements.txt"
    exit 1
}
Write-Host "Starting Doc2DB-Gen on http://localhost:$port (single process, no reload)"
Set-Location $PSScriptRoot
& $venv -m uvicorn main:app --host 0.0.0.0 --port $port
