from fastapi import FastAPI
import requests

app = FastAPI()

OLLAMA_BASE = "http://127.0.0.1:11434"

PREFERRED_MODELS = [
    "llama3:latest",
    "llama3",
    "qwen2:7b",
    "mistral",
    "gemma:7b",
    "phi3",
]

def get_installed_models():
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=10)
        data = r.json()
        return [m["name"] for m in data.get("models", [])]
    except:
        return []

def choose_model():
    installed = get_installed_models()
    for model in PREFERRED_MODELS:
        if model in installed:
            return model
    return installed[0] if installed else "llama3:latest"

@app.get("/")
def home():
    return {
        "status": "MindX AI Engine running",
        "engine": "ollama"
    }

@app.get("/models")
def models():
    return {
        "installed_models": get_installed_models()
    }

@app.post("/chat")
def chat(prompt: str):
    model = choose_model()

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }

    response = requests.post(
        f"{OLLAMA_BASE}/api/generate",
        json=payload,
        timeout=120
    )

    return {
        "model_used": model,
        "response": response.json()
    }