Set-Location C:\MindX\mindxai-ai-engine

# Ensure logs folder exists
New-Item -ItemType Directory -Force -Path .\logs | Out-Null

# Start FastAPI if port 8000 is not already listening
$fastApiRunning = netstat -ano | findstr :8000

if (-not $fastApiRunning) {
    Start-Process powershell.exe -ArgumentList @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-Command',
        'Set-Location C:\MindX\mindxai-ai-engine; & .\.venv\Scripts\python.exe -m uvicorn api.ai_server:app --host 127.0.0.1 --port 8000 *> C:\MindX\mindxai-ai-engine\logs\fastapi.log'
    ) -WindowStyle Minimized
}

Start-Sleep -Seconds 5

# Start cloudflared tunnel only if no cloudflared process is already running
$cloudflaredRunning = Get-Process cloudflared -ErrorAction SilentlyContinue

if (-not $cloudflaredRunning) {
    Start-Process powershell.exe -ArgumentList @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-Command',
        'cloudflared tunnel --url http://127.0.0.1:8000 --protocol http2 *> C:\MindX\mindxai-ai-engine\logs\tunnel.log'
    ) -WindowStyle Minimized
}