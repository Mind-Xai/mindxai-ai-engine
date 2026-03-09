Write-Host "=== MindX Health Check ==="
Write-Host ""

Write-Host "1. FastAPI root:"
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8000/" -Method Get
} catch {
    Write-Host "FastAPI not responding"
}

Write-Host ""
Write-Host "2. FastAPI health:"
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method Get
} catch {
    Write-Host "Health endpoint failed"
}

Write-Host ""
Write-Host "3. Ollama models:"
try {
    ollama list
} catch {
    Write-Host "Ollama not responding"
}