#!/usr/bin/env python3
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass


TOKEN_RESOURCE = "https://ai.azure.com"
LOCAL_BASE_URL = "http://localhost:4000/v1"
TOKEN_CACHE: dict[str, object] = {}
TOKEN_CACHE_LOCK = threading.Lock()
AZURE_CREDENTIAL = None


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    base_url: str
    api_key: str
    model: str
    model_note: str
    temperature: float


def build_provider_config(provider: str, model: str | None = None) -> ProviderConfig:
    normalized = provider.strip().lower()
    if normalized == "local":
        selected_model = model or "fast"
        return ProviderConfig(
            provider="local",
            base_url=os.environ.get("OPENAI_BASE_URL") or LOCAL_BASE_URL,
            api_key=os.environ.get("OPENAI_API_KEY") or "anything",
            model=selected_model,
            model_note=_local_model_note(selected_model),
            temperature=0.2,
        )
    if normalized == "foundry":
        deployment = model or os.environ.get("FOUNDRY_MODEL_DEPLOYMENT") or "gpt41mini-maze"
        project_endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "").rstrip("/")
        base_url = os.environ.get("FOUNDRY_OPENAI_BASE_URL") or (f"{project_endpoint}/openai/v1" if project_endpoint else "")
        if not base_url:
            raise ValueError("FOUNDRY_PROJECT_ENDPOINT or FOUNDRY_OPENAI_BASE_URL is required for provider='foundry'")
        return ProviderConfig(
            provider="foundry",
            base_url=base_url,
            api_key=os.environ.get("FOUNDRY_API_KEY") or _get_azure_ai_token(),
            model=deployment,
            model_note="Azure Foundry project model deployment",
            temperature=0.0,
        )
    raise ValueError(f"unknown provider: {provider!r}; expected 'local' or 'foundry'")


def _get_azure_ai_token() -> str:
    cached = TOKEN_CACHE.get(TOKEN_RESOURCE)
    now = time.time()
    if isinstance(cached, dict) and cached.get("token") and float(cached.get("expires_at") or 0) > now + 60:
        return str(cached["token"])
    with TOKEN_CACHE_LOCK:
        cached = TOKEN_CACHE.get(TOKEN_RESOURCE)
        now = time.time()
        if isinstance(cached, dict) and cached.get("token") and float(cached.get("expires_at") or 0) > now + 60:
            return str(cached["token"])
        try:
            from azure.identity import DefaultAzureCredential
        except Exception as exc:
            raise RuntimeError("azure-identity is required for Foundry provider authentication when FOUNDRY_API_KEY is not set") from exc

        global AZURE_CREDENTIAL
        if AZURE_CREDENTIAL is None:
            AZURE_CREDENTIAL = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        token = AZURE_CREDENTIAL.get_token(f"{TOKEN_RESOURCE}/.default")
        TOKEN_CACHE[TOKEN_RESOURCE] = {"token": token.token, "expires_at": float(token.expires_on)}
        return token.token


def _local_model_note(model: str) -> str:
    notes = {
        "fast": "LiteLLM alias for qwen3:14b on a local model host",
        "reasoner": "LiteLLM alias for deepseek-r1:14b on a local model host",
        "research": "LiteLLM alias for qwen3.6:27b on a local model host",
    }
    return notes.get(model, "custom local OpenAI-compatible model name")
