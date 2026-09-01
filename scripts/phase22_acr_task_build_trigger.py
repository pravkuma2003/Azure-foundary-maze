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
ACR_NAME = os.environ.get("PHASE22_ACR_NAME") or "mazefoundryacrpravada483"
TASK_NAME = os.environ.get("PHASE22_TASK_NAME") or "maze-role-agent-github-build"
IMAGE_REPOSITORY = os.environ.get("PHASE22_IMAGE_REPOSITORY") or "maze-role-agent"
GITHUB_REPO_URL = os.environ.get("PHASE22_GITHUB_REPO_URL") or "https://github.com/pravkuma2003/Azure-foundary-maze.git"
GITHUB_REF = os.environ.get("PHASE22_GITHUB_REF") or "main"
GITHUB_CONTEXT_SUBDIR = os.environ.get("PHASE22_GITHUB_CONTEXT_SUBDIR") or "hosted/maze-role-agents"
ROLE_AGENTS = ["maze-analyst-agent-docker", "maze-worker-agent-a-docker", "maze-worker-agent-b-docker", "maze-reviewer-agent-docker"]


def safe_text(value: str) -> str:
    value = value.replace(str(Path.home()), "~")
    value = re.sub(r"(password|secret|token|key)=\S+", r"\1=[redacted]", value, flags=re.IGNORECASE)
    value = re.sub(r"(--git-access-token\s+)\S+", r"\1[redacted]", value)
    value = re.sub(r"(sig=)[^&\s]+", r"\1[redacted]", value)
    return value.strip()


def safe_command(args: list[str]) -> list[str]:
    redacted: list[str] = []
    skip_next = False
    for arg in args:
        if skip_next:
            redacted.append("[redacted]")
            skip_next = False
            continue
        redacted.append(arg)
        if arg == "--git-access-token":
            skip_next = True
    return redacted


def run_command(args: list[str], cwd: Path = PROJECT_ROOT, timeout: int = 900) -> dict[str, Any]:
    try:
        completed = subprocess.run(args, cwd=cwd, check=False, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return {"command": safe_command(args[:1]), "returncode": 127, "stdout": "", "stderr": f"{args[0]} not found"}
    except subprocess.TimeoutExpired as exc:
        return {"command": safe_command(args), "returncode": 124, "stdout": safe_text(exc.stdout or ""), "stderr": "timed out"}
    return {
        "command": safe_command(args),
        "returncode": completed.returncode,
        "stdout": safe_text(completed.stdout),
        "stderr": safe_text(completed.stderr),
    }


def summarize(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "returncode": result["returncode"],
        "command": result["command"],
        "stdout_tail": safe_text(result.get("stdout", ""))[-2600:],
        "stderr_tail": safe_text(result.get("stderr", ""))[-2600:],
    }


def parse_json_text(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def github_context() -> str:
    return f"{GITHUB_REPO_URL}#{GITHUB_REF}:{GITHUB_CONTEXT_SUBDIR}"


def get_git_token() -> tuple[str | None, str]:
    for key in ("PHASE22_GIT_ACCESS_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(key)
        if value:
            return value, key
    gh = run_command(["gh", "auth", "token"], timeout=120)
    if gh["returncode"] == 0 and gh.get("stdout"):
        return gh["stdout"].strip(), "gh auth token"
    return None, "missing"


def create_or_update_task(apply: bool, git_token: str | None) -> dict[str, Any]:
    command = [
        "az",
        "acr",
        "task",
        "create",
        "--registry",
        ACR_NAME,
        "--name",
        TASK_NAME,
        "--image",
        f"{IMAGE_REPOSITORY}:phase22-latest",
        "--image",
        f"{IMAGE_REPOSITORY}:phase22-{{{{.Run.ID}}}}",
        "--context",
        github_context(),
        "--file",
        "Dockerfile",
        "--commit-trigger-enabled",
        "true",
        "--pull-request-trigger-enabled",
        "false",
        "--base-image-trigger-enabled",
        "false",
        "--platform",
        "linux",
        "--output",
        "json",
    ]
    if not apply:
        return {"attempted": False, "command": safe_command(command + ["--git-access-token", "[required]"])}
    if not git_token:
        return {"attempted": False, "status": "missing_git_token", "command": safe_command(command + ["--git-access-token", "[required]"])}
    result = run_command(command + ["--git-access-token", git_token], timeout=600)
    if result["returncode"] != 0 and "already exists" in result.get("stderr", "").lower():
        update_command = [
            "az",
            "acr",
            "task",
            "update",
            "--registry",
            ACR_NAME,
            "--name",
            TASK_NAME,
            "--image",
            f"{IMAGE_REPOSITORY}:phase22-latest",
            "--image",
            f"{IMAGE_REPOSITORY}:phase22-{{{{.Run.ID}}}}",
            "--context",
            github_context(),
            "--file",
            "Dockerfile",
            "--auth-mode",
            "Default",
            "--commit-trigger-enabled",
            "true",
            "--pull-request-trigger-enabled",
            "false",
            "--base-image-trigger-enabled",
            "false",
            "--output",
            "json",
        ]
        result = run_command(update_command + ["--git-access-token", git_token], timeout=600)
    return {"attempted": True, "status": "ready" if result["returncode"] == 0 else "action_required", "command": summarize(result)}


def run_task_once(apply: bool) -> dict[str, Any]:
    if not apply:
        return {"attempted": False, "status": "planned"}
    result = run_command(["az", "acr", "task", "run", "--registry", ACR_NAME, "--name", TASK_NAME, "--output", "json"], timeout=1800)
    return {"attempted": True, "status": "complete" if result["returncode"] == 0 else "action_required", "command": summarize(result)}


def latest_successful_run_id() -> tuple[str | None, dict[str, Any]]:
    result = run_command(
        [
            "az",
            "acr",
            "task",
            "list-runs",
            "--registry",
            ACR_NAME,
            "--name",
            TASK_NAME,
            "--run-status",
            "Succeeded",
            "--top",
            "1",
            "--output",
            "json",
        ],
        timeout=180,
    )
    payload = parse_json_text(result.get("stdout", "")) if result["returncode"] == 0 else None
    run_id = None
    if isinstance(payload, list) and payload:
        candidate = payload[0].get("runId")
        if isinstance(candidate, str):
            run_id = candidate
    return run_id, summarize(result)


def configure_foundry_image(image: str, apply: bool) -> dict[str, Any]:
    commands = [
        ["azd", "env", "select", "maze-migration-lab"],
        ["azd", "env", "set", "PHASE20_AGENT_IMAGE", image],
        ["azd", "env", "set", "AZURE_CONTAINER_REGISTRY_ENDPOINT", image.split("/", 1)[0]],
        ["azd", "env", "set", "AZD_AGENT_SKIP_ACR", "true"],
    ]
    if not apply:
        return {"attempted": False, "commands": commands}
    return {"attempted": True, "commands": [summarize(run_command(command, cwd=PHASE20_ROOT, timeout=180)) for command in commands]}


def deploy_docker_agents(apply: bool) -> dict[str, Any]:
    deployments: dict[str, Any] = {}
    for agent in ROLE_AGENTS:
        if not apply:
            deployments[agent] = {"attempted": False, "status": "planned"}
            continue
        result = run_command(["azd", "deploy", agent, "--no-prompt", "--timeout", "1200"], cwd=PHASE20_ROOT, timeout=1500)
        deployments[agent] = {"attempted": True, "status": "deployed" if result["returncode"] == 0 else "action_required", "command": summarize(result)}
    return deployments


def phase_status(args: argparse.Namespace, task: dict[str, Any], run_once: dict[str, Any], promotion_image: str | None, deployments: dict[str, Any]) -> str:
    if not args.apply and not args.promote_latest_run:
        return "planned"
    if args.apply and task.get("status") != "ready":
        return "action_required"
    if args.run_once and run_once.get("status") != "complete":
        return "action_required"
    if args.promote_latest_run:
        if not promotion_image:
            return "action_required"
        if any(details.get("status") != "deployed" for details in deployments.values()):
            return "action_required"
    return "complete"


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 22: create a GitHub-triggered ACR build task and keep Foundry promotion manual.")
    parser.add_argument("--apply", action="store_true", help="Create or update the ACR task.")
    parser.add_argument("--run-once", action="store_true", help="Run the ACR task once after creation/update.")
    parser.add_argument("--promote-latest-run", action="store_true", help="Manually redeploy Foundry Docker-backed agents to the latest successful run image.")
    args = parser.parse_args()

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RUNS_DIR / "phase22_acr_task_build_trigger.json"

    account = run_command(["az", "account", "show", "--query", "{tenantId:tenantId,subscriptionId:id,name:name}", "--output", "json"], timeout=120)
    acr_show = run_command(["az", "acr", "show", "--name", ACR_NAME, "--resource-group", RESOURCE_GROUP, "--output", "json"], timeout=180)
    task_show_before = run_command(["az", "acr", "task", "show", "--registry", ACR_NAME, "--name", TASK_NAME, "--output", "json"], timeout=180)
    git_token, token_source = get_git_token()

    task = create_or_update_task(args.apply, git_token)
    task_ready = task.get("status") == "ready"
    run_once = run_task_once(args.apply and args.run_once and task_ready)
    run_id, latest_run = latest_successful_run_id()
    acr_payload = parse_json_text(acr_show.get("stdout", "")) if acr_show["returncode"] == 0 else None
    login_server = acr_payload.get("loginServer") if isinstance(acr_payload, dict) else f"{ACR_NAME}.azurecr.io"
    promotion_image = f"{login_server}/{IMAGE_REPOSITORY}:phase22-{run_id}" if run_id else None
    env = configure_foundry_image(promotion_image or "", args.promote_latest_run and bool(promotion_image))
    deployments = deploy_docker_agents(args.promote_latest_run and bool(promotion_image))
    task_show_after = run_command(["az", "acr", "task", "show", "--registry", ACR_NAME, "--name", TASK_NAME, "--output", "json"], timeout=180)
    status = phase_status(args, task, run_once, promotion_image, deployments)

    result = {
        "phase": 22,
        "concept": "Automated Build Trigger with Manual Foundry Promotion",
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "github_context": github_context(),
        "acr_task_name": TASK_NAME,
        "automatic_build_tags": [f"{IMAGE_REPOSITORY}:phase22-latest", f"{IMAGE_REPOSITORY}:phase22-{{{{.Run.ID}}}}"],
        "git_token_available": bool(git_token),
        "git_token_source": token_source if git_token else "missing",
        "latest_successful_run_id": run_id,
        "manual_promotion_image": promotion_image,
        "manual_foundry_promotion": "python3 scripts/phase22_acr_task_build_trigger.py --promote-latest-run",
        "commands": {
            "account": summarize(account),
            "acr_show": summarize(acr_show),
            "task_show_before": summarize(task_show_before),
            "task": task,
            "run_once": run_once,
            "latest_run": latest_run,
            "env": env,
            "deployments": deployments,
            "task_show_after": summarize(task_show_after),
        },
    }
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if status in {"complete", "planned"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
