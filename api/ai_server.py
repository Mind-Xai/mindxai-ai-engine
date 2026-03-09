# ──────────────────────────────────────────────────────────────────────────────
#  main.py  –  FastAPI “super‑fast” wrapper for a local Ollama server
# ──────────────────────────────────────────────────────────────────────────────

import os
import json
import logging
from datetime import datetime
from typing import List, Optional, Literal, Dict, Any

import httpx
from fastapi import FastAPI, HTTPException, Depends, Query, status
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, BaseSettings, Field, validator
from starlette.requests import Request

# --------------------------------------------------------------------------- #
# 1️⃣  Settings (read from env / .env – no hard‑coded values)
# --------------------------------------------------------------------------- #
class Settings(BaseSettings):
    """All configurable values live here."""
    OLLAMA_BASE: str = Field(
        "http://127.0.0.1:11434",
        description="Base URL of the local Ollama HTTP API."
    )
    OLLAMA_TIMEOUT: float = Field(
        12.0,
        description="HTTP timeout (seconds) for any Ollama request."
    )
    # Preferred order when the caller does **not** request a specific model.
    PREFERRED_MODELS: List[str] = Field(
        default_factory=lambda: [
            "phi3:latest",
            "mistral:latest",
            "llama3:latest",
            "qwen2.5:7b",
            "gemma2:9b",
        ]
    )
    # Maximum number of installed models we expose on the health endpoint.
    MAX_MODELS_IN_HEALTH: int = 10

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

# --------------------------------------------------------------------------- #
# 2️⃣  Logging – a minimal but useful config
# --------------------------------------------------------------------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("ollama_fastapi")

# --------------------------------------------------------------------------- #
# 3️⃣  FastAPI app creation
# --------------------------------------------------------------------------- #
app = FastAPI(
    title="Ollama FastAPI Wrapper",
    description=(
        "A tiny, async, auto‑selecting, streaming‑enabled wrapper around a "
        "local Ollama server.  Designed for maximum speed and zero‑downtime."
    ),
    version="1.0.0",
)

# --------------------------------------------------------------------------- #
# 4️⃣  Internal helpers – async client, model cache, selection logic
# --------------------------------------------------------------------------- #
class OllamaClient:
    """Singleton async HTTP client used by all routes."""
    _client: Optional[httpx.AsyncClient] = None

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        if cls._client is None:
            cls._client = httpx.AsyncClient(
                base_url=settings.OLLAMA_BASE,
                timeout=settings.OLLAMA_TIMEOUT,
                follow_redirects=True,
            )
        return cls._client

    @classmethod
    async def close(cls):
        if cls._client is not None:
            await cls._client.aclose()


# Cached list of installed models – refreshed on startup and when a pull finishes.
installed_models_cache: List[str] = []


async def refresh_installed_models() -> List[str]:
    """Ask Ollama for the tags list and store the model names."""
    client = OllamaClient.get_client()
    try:
        resp = await client.get("/api/tags")
        resp.raise_for_status()
        data = resp.json()
        models = [m["name"] for m in data.get("models", [])]
        global installed_models_cache
        installed_models_cache = models
        log.info("Installed models refreshed – %d models found", len(models))
        return models
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        log.error("Failed to get installed models from Ollama: %s", exc)
        return []


def choose_model(requested: Optional[str]) -> str:
    """
    Return the model that should be used for a request.

    * If the caller gave a model and it is installed → use it.
    * Otherwise walk through ``settings.PREFERRED_MODELS`` and pick the first that is installed.
    * Fallback → the very first installed model (if any) or the first preferred model as a last‑resort string.
    """
    if requested and requested in installed_models_cache:
        return requested

    for pref in settings.PREFERRED_MODELS:
        if pref in installed_models_cache:
            return pref

    # No installed model matches – pick whatever is available or a safe default.
    if installed_models_cache:
        return installed_models_cache[0]
    return settings.PREFERRED_MODELS[0]  # will be pulled on‑the‑fly later


# --------------------------------------------------------------------------- #
# 5️⃣  Pydantic request / response models – used for OpenAPI docs
# --------------------------------------------------------------------------- #
class ChatRequest(BaseModel):
    """Payload sent by the client."""
    prompt: str = Field(..., description="User message / prompt.")
    model: Optional[str] = Field(
        None,
        description="Optional model name.  If omitted the service picks the best one."
    )
    stream: bool = Field(
        False,
        description="Set true to receive a streaming response (SSE)."
    )
    # Users may want to tweak temperature etc. – we expose a generic dict.
    options: Optional[Dict[str, Any]] = Field(
        None,
        description="Extra Ollama generation options (e.g. temperature, top_p)."
    )

    @validator("prompt")
    def not_empty(cls, v):
        if not v.strip():
            raise ValueError("Prompt must not be empty")
        return v


class ChatResponse(BaseModel):
    ok: bool
    source: Literal["LOCAL_FASTAPI"]
    model_used: str
    reply: str
    raw: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class HealthResponse(BaseModel):
    ok: bool = True
    engine: Literal["ollama"]
    models_count: int
    models: List[str] = Field(..., description="A truncated list of installed models.")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class ModelListResponse(BaseModel):
    installed_models: List[str]


class PullResponseChunk(BaseModel):
    status: str = Field(..., description="Current state (pulling, digest, etc.).")
    total: Optional[int] = None
    completed: Optional[int] = None
    details: Optional[Dict[str, Any]] = None


# --------------------------------------------------------------------------- #
# 6️⃣  Lifecycle hooks – populate model cache once on start
# --------------------------------------------------------------------------- #
@app.on_event("startup")
async def on_startup() -> None:
    # Warm‑up client and model list immediately – later calls are fast.
    await refresh_installed_models()
    log.info("FastAPI‑Ollama service started.")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await OllamaClient.close()
    log.info("FastAPI‑Ollama service stopped.")


# --------------------------------------------------------------------------- #
# 7️⃣  Core routes
# --------------------------------------------------------------------------- #
@app.get("/", response_model=Dict[str, str], tags=["Root"])
async def root() -> Dict[str, str]:
    """Very light health ping – just tells that the wrapper is alive."""
    return {
        "status": "MindX AI Engine running",
        "engine": "ollama",
        "time": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health() -> HealthResponse:
    """Overall service health plus a snapshot of installed models."""
    models = installed_models_cache
    return HealthResponse(
        models_count=len(models),
        models=models[: settings.MAX_MODELS_IN_HEALTH],
    )


@app.get("/models", response_model=ModelListResponse, tags=["Models"])
async def list_models() -> ModelListResponse:
    """Return the full list of locally installed Ollama models."""
    # Refresh lazily – ensures the endpoint always shows the current state.
    models = await refresh_installed_models()
    return ModelListResponse(installed_models=models)


@app.post(
    "/chat",
    response_model=ChatResponse,
    tags=["Chat"],
    responses={500: {"description": "Internal server error"}},
)
async def chat_endpoint(payload: ChatRequest) -> ChatResponse:
    """
    Generate a text completion from Ollama.

    - If ``payload.model`` is not supplied the wrapper automatically picks
      the best available model based on ``settings.PREFERRED_MODELS``.
    - ``stream`` can be set to ``true`` to get an SSE‑style response (see /chat/stream).
    """
    selected_model = choose_model(payload.model)

    # Build Ollama request payload
    ollama_body: Dict[str, Any] = {
        "model": selected_model,
        "prompt": payload.prompt,
        "stream": False,  # This endpoint is **non‑streaming**; use /chat/stream for SSE.
    }
    if payload.options:
        ollama_body["options"] = payload.options

    client = OllamaClient.get_client()
    try:
        resp = await client.post("/api/generate", json=ollama_body)
        resp.raise_for_status()
        data = resp.json()
        # The generate endpoint returns the field `response` for the text.
        reply_text = (
            data.get("response")
            or data.get("message")
            or data.get("output")
            or data.get("text")
            or ""
        )
        return ChatResponse(
            ok=True,
            source="LOCAL_FASTAPI",
            model_used=selected_model,
            reply=reply_text,
            raw=data,
        )
    except httpx.HTTPError as exc:
        log.exception("Ollama generation failed")
        return ChatResponse(
            ok=False,
            source="LOCAL_FASTAPI",
            model_used=selected_model,
            reply="",
            raw={},
            error=str(exc),
        )
    except Exception as exc:  # pragma: no cover – safety‑net
        log.exception("Unexpected error in /chat")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


# --------------------------------------------------------------------------- #
# 8️⃣  SSE / Streaming chat support (optional but “super‑fast” for large replies)
# --------------------------------------------------------------------------- #
@app.post(
    "/chat/stream",
    tags=["Chat"],
    response_class=StreamingResponse,
    responses={500: {"description": "Internal server error"}},
)
async def chat_stream(payload: ChatRequest) -> StreamingResponse:
    """
    Stream the Ollama response token‑by‑token (Server‑Sent Events).

    Example usage with ``curl``:

    ```bash
    curl -N -X POST http://localhost:8000/chat/stream \\
        -H "Content-Type: application/json" \\
        -d '{"prompt":"Write a haiku about AI"}'
    ```
    """
    selected_model = choose_model(payload.model)
    ollama_body: Dict[str, Any] = {
        "model": selected_model,
        "prompt": payload.prompt,
        "stream": True,
    }
    if payload.options:
        ollama_body["options"] = payload.options

    client = OllamaClient.get_client()

    async def event_generator():
        async with client.stream("POST", "/api/generate", json=ollama_body) as resp:
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    # Ollama streams a raw string when not JSON – forward as is.
                    yield f"data: {line}\n\n"
                    continue

                # Forward the token (usually under the key `response`).
                token = data.get("response") or data.get("delta")
                if token is not None:
                    # SSE spec: each line prefixed with "data: ".
                    safe_token = json.dumps(token)  # protect newlines etc.
                    yield f"data: {safe_token}\n\n"

                # When the stream ends, Ollama sends a `done` flag.
                if data.get("done"):
                    break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


# --------------------------------------------------------------------------- #
# 9️⃣  Pull a model on‑the‑fly (auto‑download) – optional but handy
# --------------------------------------------------------------------------- #
@app.post(
    "/models/pull",
    tags=["Models"],
    response_class=StreamingResponse,
    responses={400: {"description": "Invalid request"}, 500: {"description": "Ollama error"}},
)
async def pull_model(
    model_name: str = Query(..., description="Name of the model to pull, e.g. phi3:latest")
) -> StreamingResponse:
    """
    Pull a model from the Ollama registry and stream progress events.

    The endpoint streams the JSON chunks exactly as Ollama returns them.
    The server also refreshes the local model cache when the pull finishes.
    """
    client = OllamaClient.get_client()

    async def progress_generator():
        async with client.stream("POST", "/api/pull", json={"name": model_name}) as resp:
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    # Forward raw lines (rare) – they still convey progress.
                    yield f"data: {line}\n\n"
                    continue

                # Forward to client
                yield f"data: {json.dumps(data)}\n\n"

                # Detect completion – Ollama ends with `"status":"success"` or similar.
                if data.get("status") in ("success", "complete"):
                    break

        # Refresh cache after a successful pull (best‑effort, ignore errors)
        await refresh_installed_models()

    return StreamingResponse(
        progress_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


# --------------------------------------------------------------------------- #
# 10️⃣  Global exception handler → JSON error payload (nice for callers)
# --------------------------------------------------------------------------- #
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"ok": False, "error": exc.detail, "path": request.url.path},
    )


# --------------------------------------------------------------------------- #
# 11️⃣  That's it!  Run with `uvicorn main:app --workers 4` for maximum throughput.
# --------------------------------------------------------------------------- #
