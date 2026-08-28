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

RESOURCE_GROUP = os.environ.get("AZURE_RESOURCE_GROUP") or "rg-maze-foundry-lab"
ACR_NAME = os.environ.get("PHASE21_ACR_NAME") or "mazefoundryacrpravada483"
IMAGE_REPOSITORY = os.environ.get("PHASE21_IMAGE_REPOSITORY") or "maze-role-agent"
IMAGE_TAG = os.environ.get("PHASE21_IMAGE_TAG") or "phase21-github-main"
GITHUB_REPO_URL = os.environ.get("PHASE21_GITHUB_REPO_URL") or "https://github.com/pravkuma2003/Azure-foundary-maze.git"
GITHUB_REF = os.environ.get("PHASE21_GITHUB_REF") or "main"
GITHUB_CONTEXT_SUBDIR = os.environ.get("PHASE21_GITHUB_CONTEXT_SUBDIR") or "hosted/phase13-split-role-agents"
ROLE_AGENTS = ["maze-analyst-agent-docker", "maze-worker-agent-a-docker", "maze-worker-agent-b-docker"]


def safe_text(value: str) -> str:
    value = value.replace(str(Path.home()), "~")
    value = re.sub(r"(password|secret|token|key)=\S+", r"\1=[redacted]", value, flags=re.IGNORECASE)
    value = re.sub(r"(sig=)[^&\s]+", r"\1[redacted]", value)
    return value.strip()


def run_command(args: list[str], cwd: Path = PROJECT_ROOT, timeout: int = 900) -> dict[str, Any]:
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
        "stdout_tail": safe_text(result.get("stdout", ""))[-2400:],
        "stderr_tail": safe_text(result.get("stderr", ""))[-2400:],
    }


def parse_json_text(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def image_name() -> str:
    return f"{IMAGE_REPOSITORY}:{IMAGE_TAG}"


def github_context() -> str:
    return f"{GITHUB_REPO_URL}#{GITHUB_REF}:{GITHUB_CONTEXT_SUBDIR}"


def acr_login_server(acr_payload: dict[str, Any] | None = None) -> str:
    if isinstance(acr_payload, dict) and isinstance(acr_payload.get("loginServer"), str):
        return str(acr_payload["loginServer"])
    return f"{ACR_NAME}.azurecr.io"


def full_image(acr_payload: dict[str, Any] | None = None) -> str:
    return f"{acr_login_server(acr_payload)}/{image_name()}"


def configure_foundry_image(image: str, apply: bool) -> dict[str, Any]:
    commands = [
        ["azd", "env", "select", "maze-migration-lab"],
        ["azd", "env", "set", "PHASE20_AGENT_IMAGE", image],
        ["azd", "env", "set", "AZURE_CONTAINER_REGISTRY_ENDPOINT", image.split("/", 1)[0]],
        ["azd", "env", "set", "AZD_AGENT_SKIP_ACR", "true"],
    ]
    if not apply:
        return {"attempted": False, "commands": commands}
    results = []
    for command in commands:
        results.append(summarize(run_command(command, cwd=PHASE20_ROOT, timeout=180)))
    return {"attempted": True, "commands": results}


def deploy_docker_agents(apply: bool) -> dict[str, Any]:
    deployments: dict[str, Any] = {}
    for agent in ROLE_AGENTS:
        if not apply:
            deployments[agent] = {"attempted": False, "status": "planned"}
            continue
        result = run_command(["azd", "deploy", agent, "--no-prompt", "--timeout", "1200"], cwd=PHASE20_ROOT, timeout=1500)
        deployments[agent] = {
            "attempted": True,
            "status": "deployed" if result["returncode"] == 0 else "action_required",
            "command": summarize(result),
        }
    return deployments


def show_agents() -> dict[str, Any]:
    shows: dict[str, Any] = {}
    for agent in ROLE_AGENTS:
        result = run_command(["azd", "ai", "agent", "show", agent, "--output", "json"], cwd=PHASE20_ROOT, timeout=240)
        payload = parse_json_text(result.get("stdout", "")) if result["returncode"] == 0 else None
        definition = payload.get("definition", {}) if isinstance(payload, dict) else {}
        container_configuration = definition.get("container_configuration", {}) if isinstance(definition, dict) else {}
        shows[agent] = {
            "exists": result["returncode"] == 0,
            "status": payload.get("status") if isinstance(payload, dict) else None,
            "version": payload.get("version") if isinstance(payload, dict) else None,
            "image": container_configuration.get("image") if isinstance(container_configuration, dict) else None,
            "command": summarize(result),
        }
    return shows


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 21: build the agent image from GitHub source through ACR.")
    parser.add_argument("--apply", action="store_true", help="Run ACR build from GitHub and redeploy Docker-backed Foundry agents.")
    parser.add_argument("--skip-deploy", action="store_true", help="Build the GitHub image but do not redeploy Foundry agents.")
    args = parser.parse_args()

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RUNS_DIR / "phase21_github_acr_image_build.json"

    account = run_command(["az", "account", "show", "--query", "{tenantId:tenantId,subscriptionId:id,name:name}", "--output", "json"], timeout=120)
    git_head = run_command(["git", "rev-parse", "HEAD"], timeout=120)
    git_remote = run_command(["git", "remote", "get-url", "origin"], timeout=120)
    acr_show = run_command(["az", "acr", "show", "--name", ACR_NAME, "--resource-group", RESOURCE_GROUP, "--output", "json"], timeout=180)
    acr_payload = parse_json_text(acr_show.get("stdout", "")) if acr_show["returncode"] == 0 else None
    target_image = full_image(acr_payload if isinstance(acr_payload, dict) else None)

    build = None
    if args.apply and acr_show["returncode"] == 0:
        build = run_command(
            [
                "az",
                "acr",
                "build",
                "--registry",
                ACR_NAME,
                "--image",
                image_name(),
                github_context(),
            ],
            timeout=1800,
        )

    tags = run_command(
        ["az", "acr", "repository", "show-tags", "--name", ACR_NAME, "--repository", IMAGE_REPOSITORY, "--output", "json"],
        timeout=180,
    )
    tag_payload = parse_json_text(tags.get("stdout", "")) if tags["returncode"] == 0 else []
    image_exists = isinstance(tag_payload, list) and IMAGE_TAG in tag_payload

    env = configure_foundry_image(target_image, args.apply and image_exists and not args.skip_deploy)
    deployments = deploy_docker_agents(args.apply and image_exists and not args.skip_deploy)
    shows = show_agents()

    deployed = [name for name, payload in deployments.items() if payload.get("status") == "deployed"]
    all_agents_on_target = all(payload.get("image") == target_image for payload in shows.values())
    result = {
        "phase": 21,
        "concept": "GitHub Source to ACR Image Build",
        "status": (
            "complete"
            if args.apply and (args.skip_deploy or len(deployed) == len(ROLE_AGENTS)) and image_exists
            else ("planned" if not args.apply else "action_required")
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "flow": "edit on Mac -> commit/push to GitHub -> ACR pulls GitHub source -> ACR builds image -> Foundry runs image",
        "github_repo_url": GITHUB_REPO_URL,
        "github_ref": GITHUB_REF,
        "github_context": github_context(),
        "acr_name": ACR_NAME,
        "target_image": target_image,
        "foundry_agent_names": ROLE_AGENTS,
        "foundry_agents_on_target_image": all_agents_on_target,
        "commands": {
            "account": summarize(account),
            "git_head": summarize(git_head),
            "git_remote": summarize(git_remote),
            "acr_show": summarize(acr_show),
            "acr_build": summarize(build) if build else None,
            "tags": summarize(tags),
            "env": env,
            "deployments": deployments,
            "shows": shows,
        },
    }
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in {"complete", "planned"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
