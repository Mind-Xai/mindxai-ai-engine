cd C:\MindX\mindxai-ai-engine
.\.venv\Scripts\Activate.ps1
py -m uvicorn api.ai_server:app --host 127.0.0.1 --port 8000