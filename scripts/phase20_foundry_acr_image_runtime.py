#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHASE20_ROOT = PROJECT_ROOT / "hosted" / "phase20-docker-image-runtime"
RUNS_DIR = PROJECT_ROOT / "runs"

PROJECT_ENDPOINT = os.environ.get("FOUNDRY_PROJECT_ENDPOINT") or "https://maze-foundry-prav-ada483.services.ai.azure.com/api/projects/maze-migration-lab"
MODEL_DEPLOYMENT = os.environ.get("FOUNDRY_MODEL_DEPLOYMENT") or "gpt41mini-maze"
TOOL_MCP_ENDPOINT = os.environ.get("MAZE_TOOL_MCP_ENDPOINT") or "https://maze-foundry-prav-ada483.services.ai.azure.com/api/projects/maze-migration-lab/toolboxes/maze-toolbox-dynamic/versions/1/mcp?api-version=v1"
AGENT_IMAGE = os.environ.get("PHASE20_AGENT_IMAGE") or "mazefoundryacrpravada483.azurecr.io/maze-role-agent:phase19"
ACR_ENDPOINT = os.environ.get("AZURE_CONTAINER_REGISTRY_ENDPOINT") or AGENT_IMAGE.split("/", 1)[0]
SUBSCRIPTION_ID = os.environ.get("AZURE_SUBSCRIPTION_ID") or "0ecda5cf-8c20-4818-856e-0acac9ce9aa9"
RESOURCE_GROUP = os.environ.get("AZURE_RESOURCE_GROUP") or "rg-maze-foundry-lab"
LOCATION = os.environ.get("AZURE_LOCATION") or "eastus"
AI_ACCOUNT_NAME = os.environ.get("AZURE_AI_ACCOUNT_NAME") or "maze-foundry-prav-ada483"
AI_PROJECT_NAME = os.environ.get("AZURE_AI_PROJECT_NAME") or "maze-migration-lab"
AI_PROJECT_ID = os.environ.get("AZURE_AI_PROJECT_ID") or (
    f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/{RESOURCE_GROUP}/providers/"
    f"Microsoft.CognitiveServices/accounts/{AI_ACCOUNT_NAME}/projects/{AI_PROJECT_NAME}"
)
ROLE_AGENTS = ["maze-analyst-agent-docker", "maze-worker-agent-a-docker", "maze-worker-agent-b-docker"]


def safe_text(value: str) -> str:
    value = value.replace(str(Path.home()), "~")
    value = re.sub(r"(x-functions-key=)[^\s\"]+", r"\1[redacted]", value)
    value = re.sub(r"(MAZE_TOOL_KEY[=:]\s*)[^\s,}]+", r"\1[redacted]", value)
    return value.strip()


def run_command(args: list[str], cwd: Path = PHASE20_ROOT, timeout: int = 900) -> dict[str, Any]:
    try:
        completed = subprocess.run(args, cwd=cwd, check=False, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return {"command": args[:1], "returncode": 127, "stdout": "", "stderr": f"{args[0]} not found"}
    except subprocess.TimeoutExpired as exc:
        return {"command": args, "returncode": 124, "stdout": safe_text(exc.stdout or ""), "stderr": "timed out"}
    return {
        "command": args,
        "returncode": completed.returncode,
        "stdout": safe_text(completed.stdout),
        "stderr": safe_text(completed.stderr),
    }


def summarize(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "returncode": result["returncode"],
        "command": result["command"],
        "stdout_tail": safe_text(result.get("stdout", ""))[-2200:],
        "stderr_tail": safe_text(result.get("stderr", ""))[-2200:],
    }


def parse_json_text(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def check_image_exists() -> dict[str, Any]:
    registry, remainder = AGENT_IMAGE.split("/", 1)
    registry_name = registry.split(".")[0]
    repository, tag = remainder.rsplit(":", 1)
    result = run_command(
        ["az", "acr", "repository", "show-tags", "--name", registry_name, "--repository", repository, "--output", "json"],
        cwd=PROJECT_ROOT,
        timeout=180,
    )
    tags = parse_json_text(result.get("stdout", "")) if result["returncode"] == 0 else []
    return {
        "registry": registry_name,
        "repository": repository,
        "tag": tag,
        "exists": isinstance(tags, list) and tag in tags,
        "command": summarize(result),
    }


def configure_env(apply: bool) -> dict[str, Any]:
    commands = [
        ["azd", "env", "select", "maze-migration-lab"],
        ["azd", "env", "set", "FOUNDRY_PROJECT_ENDPOINT", PROJECT_ENDPOINT],
        ["azd", "env", "set", "FOUNDRY_MODEL_DEPLOYMENT", MODEL_DEPLOYMENT],
        ["azd", "env", "set", "MAZE_TOOL_MCP_ENDPOINT", TOOL_MCP_ENDPOINT],
        ["azd", "env", "set", "PHASE20_AGENT_IMAGE", AGENT_IMAGE],
        ["azd", "env", "set", "AZURE_CONTAINER_REGISTRY_ENDPOINT", ACR_ENDPOINT],
        ["azd", "env", "set", "AZD_AGENT_SKIP_ACR", "true"],
        ["azd", "env", "set", "USE_EXISTING_AI_PROJECT", "true"],
        ["azd", "env", "set", "AZURE_SUBSCRIPTION_ID", SUBSCRIPTION_ID],
        ["azd", "env", "set", "AZURE_RESOURCE_GROUP", RESOURCE_GROUP],
        ["azd", "env", "set", "AZURE_LOCATION", LOCATION],
        ["azd", "env", "set", "AZURE_AI_ACCOUNT_NAME", AI_ACCOUNT_NAME],
        ["azd", "env", "set", "AZURE_AI_PROJECT_NAME", AI_PROJECT_NAME],
        ["azd", "env", "set", "AZURE_AI_PROJECT_ID", AI_PROJECT_ID],
    ]
    if not apply:
        return {"attempted": False, "commands": commands}
    results = []
    for index, command in enumerate(commands):
        result = run_command(command, timeout=180)
        if index == 0 and result["returncode"] != 0:
            result = run_command(["azd", "env", "new", "maze-migration-lab"], timeout=180)
        results.append(summarize(result))
    return {"attempted": True, "commands": results}


def deploy_agents(apply: bool) -> dict[str, Any]:
    deployments: dict[str, Any] = {}
    for name in ROLE_AGENTS:
        if not apply:
            deployments[name] = {"attempted": False, "status": "planned"}
            continue
        result = run_command(["azd", "deploy", name, "--no-prompt", "--timeout", "1200"], timeout=1500)
        deployments[name] = {"attempted": True, "status": "deployed" if result["returncode"] == 0 else "action_required", "deploy": summarize(result)}
    return deployments


def show_agents() -> dict[str, Any]:
    shows: dict[str, Any] = {}
    for name in ROLE_AGENTS:
        result = run_command(["azd", "ai", "agent", "show", name, "--output", "json"], timeout=240)
        payload = parse_json_text(result.get("stdout", "")) if result["returncode"] == 0 else None
        definition = payload.get("definition", {}) if isinstance(payload, dict) else {}
        container_configuration = definition.get("container_configuration", {}) if isinstance(definition, dict) else {}
        shows[name] = {
            "exists": result["returncode"] == 0,
            "status": payload.get("status") if isinstance(payload, dict) else None,
            "version": payload.get("version") if isinstance(payload, dict) else None,
            "runtime": definition.get("code_configuration", {}).get("runtime") if isinstance(definition, dict) else None,
            "image": (
                container_configuration.get("image")
                or definition.get("image")
                or definition.get("container_image")
                if isinstance(definition, dict)
                else None
            ),
            "command": summarize(result),
        }
    return shows


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 20: deploy Foundry hosted agents from a prebuilt ACR image.")
    parser.add_argument("--apply", action="store_true", help="Deploy the Docker-backed hosted agents.")
    args = parser.parse_args()

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RUNS_DIR / "phase20_foundry_acr_image_runtime.json"

    file_check = {
        "azure_yaml": str((PHASE20_ROOT / "azure.yaml").relative_to(PROJECT_ROOT)),
        "exists": (PHASE20_ROOT / "azure.yaml").exists(),
    }
    account = run_command(["az", "account", "show", "--query", "{tenantId:tenantId,subscriptionId:id,name:name}", "--output", "json"], cwd=PROJECT_ROOT, timeout=120)
    image = check_image_exists()
    env = configure_env(args.apply)
    deployments = deploy_agents(args.apply and image["exists"] and file_check["exists"])
    shows = show_agents()

    deployed = [name for name, payload in deployments.items() if payload.get("status") == "deployed"]
    all_deployed = args.apply and len(deployed) == len(ROLE_AGENTS)
    any_exists = any(payload.get("exists") for payload in shows.values())
    result = {
        "phase": 20,
        "concept": "Foundry Hosted Agents From ACR Image",
        "status": "complete" if all_deployed else ("observed" if any_exists else ("planned" if not args.apply else "action_required")),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_image": AGENT_IMAGE,
        "acr_endpoint": ACR_ENDPOINT,
        "source_remote_build_agents_unchanged": True,
        "docker_agent_names": ROLE_AGENTS,
        "file_check": file_check,
        "image_check": image,
        "commands": {
            "account": summarize(account),
            "env": env,
            "deployments": deployments,
            "shows": shows,
        },
        "next_phase": "GitHub-triggered or GitHub-source ACR build feeding the same Foundry image runtime.",
    }
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in {"complete", "observed", "planned"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
