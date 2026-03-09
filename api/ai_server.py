from fastapi import FastAPI
import requests
from datetime import datetime

app = FastAPI()

OLLAMA_BASE = "http://127.0.0.1:11434"

PREFERRED_MODELS = [
    "llama3:latest",
    "qwen2.5:7b",
    "mistral:latest",
    "phi3:latest",
    "gemma2:9b",
]

def get_installed_models():
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=10)
        r.raise_for_status()
        data = r.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []

def choose_model(requested_model: str | None = None):
    installed = get_installed_models()

    if requested_model and requested_model in installed:
        return requested_model

    for model in PREFERRED_MODELS:
        if model in installed:
            return model

    return installed[0] if installed else "llama3:latest"

@app.get("/")
def home():
    return {
        "status": "MindX AI Engine running",
        "engine": "ollama",
        "time": datetime.utcnow().isoformat() + "Z"
    }

@app.get("/health")
def health():
    models = get_installed_models()
    return {
        "ok": True,
        "engine": "ollama",
        "models_count": len(models),
        "models": models[:10]
    }

@app.get("/models")
def models():
    return {
        "installed_models": get_installed_models()
    }

@app.post("/chat")
def chat(prompt: str, model: str | None = None):
    selected_model = choose_model(model)

    payload = {
        "model": selected_model,
        "prompt": prompt,
        "stream": False
    }

    try:
        response = requests.post(
            f"{OLLAMA_BASE}/api/generate",
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        ollama_data = response.json()

        text = (
            ollama_data.get("response")
            or ollama_data.get("message")
            or ollama_data.get("output")
            or ollama_data.get("text")
            or ""
        )

        return {
            "ok": True,
            "source": "LOCAL_FASTAPI_8000",
            "model_used": selected_model,
            "reply": text,
            "raw": ollama_data
        }

    except Exception as e:
        return {
            "ok": False,
            "source": "LOCAL_FASTAPI_8000",
            "model_used": selected_model,
            "reply": "",
            "error": str(e)
        }