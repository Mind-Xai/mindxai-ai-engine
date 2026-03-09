Set-Location C:\MindX\mindxai-ai-engine

# Activate venv
& .\.venv\Scripts\Activate.ps1

# Start FastAPI in background if not already running
$portCheck = netstat -ano | findstr :8000
if (-not $portCheck) {
    Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -Command `"cd C:\MindX\mindxai-ai-engine; .\.venv\Scripts\Activate.ps1; py -m uvicorn api.ai_server:app --host 127.0.0.1 --port 8000 *> logs\fastapi.log`"" -WindowStyle Minimized
}

Start-Sleep -Seconds 3

# Start tunnel
Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -Command `"cloudflared tunnel --url http://127.0.0.1:8000 --protocol http2 *> logs\tunnel.log`"" -WindowStyle Minimized