from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


TOKEN_RESOURCE = "https://ai.azure.com"


@dataclass(frozen=True)
class FoundryProviderConfig:
    project_endpoint: str
    deployment_name: str
    token_resource: str = TOKEN_RESOURCE
    temperature: float = 0.0
    max_output_tokens: int = 24


@dataclass(frozen=True)
class FoundryProviderResult:
    provider: str
    deployment_name: str
    response_id: str | None
    output_text: str
    usage: dict[str, Any]
    request_path: str
    auth_mode: str


def get_azure_ai_token(resource: str = TOKEN_RESOURCE) -> str:
    completed = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource, "--query", "accessToken", "--output", "tsv"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"failed to get Azure AI token: {completed.stderr.strip()}")
    token = completed.stdout.strip()
    if not token:
        raise RuntimeError("az returned an empty Azure AI token")
    return token


def call_foundry_responses(config: FoundryProviderConfig, prompt: str) -> FoundryProviderResult:
    token = get_azure_ai_token(config.token_resource)
    endpoint = config.project_endpoint.rstrip("/")
    path = "/openai/v1/responses"
    url = f"{endpoint}{path}"
    body = {
        "model": config.deployment_name,
        "input": prompt,
        "temperature": config.temperature,
        "max_output_tokens": config.max_output_tokens,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Foundry request failed: HTTP {exc.code}: {error_body}") from exc

    return FoundryProviderResult(
        provider="foundry",
        deployment_name=config.deployment_name,
        response_id=payload.get("id"),
        output_text=extract_output_text(payload),
        usage=payload.get("usage") or {},
        request_path=path,
        auth_mode="azure_cli_entra_id",
    )


def extract_output_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"].strip()

    output_parts: list[str] = []
    for item in payload.get("output") or []:
        for content in item.get("content") or []:
            text = content.get("text")
            if isinstance(text, str):
                output_parts.append(text)
    return "\n".join(output_parts).strip()
