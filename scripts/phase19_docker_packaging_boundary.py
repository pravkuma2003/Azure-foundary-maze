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
HOSTED_ROOT = PROJECT_ROOT / "hosted" / "phase13-split-role-agents"
RUNS_DIR = PROJECT_ROOT / "runs"

RESOURCE_GROUP = os.environ.get("AZURE_RESOURCE_GROUP") or os.environ.get("LAB_RESOURCE_GROUP") or "rg-maze-foundry-lab"
LOCATION = os.environ.get("AZURE_LOCATION") or os.environ.get("LAB_LOCATION") or "eastus2"
ACR_NAME = os.environ.get("PHASE19_ACR_NAME") or "mazefoundryacrpravada483"
IMAGE_REPOSITORY = os.environ.get("PHASE19_IMAGE_REPOSITORY") or "maze-role-agent"
IMAGE_TAG = os.environ.get("PHASE19_IMAGE_TAG") or "phase19"


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
        "stdout_tail": safe_text(result.get("stdout", ""))[-1800:],
        "stderr_tail": safe_text(result.get("stderr", ""))[-1800:],
    }


def parse_json(result: dict[str, Any]) -> Any:
    if result["returncode"] != 0 or not result.get("stdout"):
        return None
    try:
        return json.loads(result["stdout"])
    except json.JSONDecodeError:
        return None


def validate_files() -> dict[str, Any]:
    required = [
        HOSTED_ROOT / "Dockerfile",
        HOSTED_ROOT / ".dockerignore",
        HOSTED_ROOT / "main.py",
        HOSTED_ROOT / "requirements.txt",
        HOSTED_ROOT / "src" / "reasoning_curriculum.py",
        HOSTED_ROOT / "src" / "provider_config.py",
        HOSTED_ROOT / "src" / "maze_tool_boundary.py",
    ]
    return {
        "required_files": [str(path.relative_to(PROJECT_ROOT)) for path in required],
        "missing": [str(path.relative_to(PROJECT_ROOT)) for path in required if not path.exists()],
    }


def image_name() -> str:
    return f"{IMAGE_REPOSITORY}:{IMAGE_TAG}"


def acr_login_server(acr_payload: dict[str, Any] | None) -> str:
    if isinstance(acr_payload, dict):
        login_server = acr_payload.get("loginServer")
        if isinstance(login_server, str):
            return login_server
    return f"{ACR_NAME}.azurecr.io"


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 19: build hosted-agent Docker image in Azure Container Registry.")
    parser.add_argument("--apply", action="store_true", help="Create/reuse ACR and run az acr build.")
    parser.add_argument("--skip-build", action="store_true", help="Create/reuse ACR but skip image build.")
    args = parser.parse_args()

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RUNS_DIR / "phase19_docker_packaging_boundary.json"

    file_check = validate_files()
    account = run_command(["az", "account", "show", "--query", "{tenantId:tenantId,subscriptionId:id,name:name}", "--output", "json"], timeout=120)
    acr_show = run_command(["az", "acr", "show", "--name", ACR_NAME, "--resource-group", RESOURCE_GROUP, "--output", "json"], timeout=180)

    created_acr: dict[str, Any] | None = None
    if args.apply and acr_show["returncode"] != 0:
        created_acr = run_command(
            [
                "az",
                "acr",
                "create",
                "--name",
                ACR_NAME,
                "--resource-group",
                RESOURCE_GROUP,
                "--location",
                LOCATION,
                "--sku",
                "Basic",
                "--admin-enabled",
                "false",
                "--output",
                "json",
            ],
            timeout=600,
        )
        acr_show = run_command(["az", "acr", "show", "--name", ACR_NAME, "--resource-group", RESOURCE_GROUP, "--output", "json"], timeout=180)

    build: dict[str, Any] | None = None
    if args.apply and not args.skip_build and not file_check["missing"] and acr_show["returncode"] == 0:
        build = run_command(
            [
                "az",
                "acr",
                "build",
                "--registry",
                ACR_NAME,
                "--image",
                image_name(),
                "--file",
                "Dockerfile",
                ".",
            ],
            cwd=HOSTED_ROOT,
            timeout=1800,
        )

    tags = run_command(
        ["az", "acr", "repository", "show-tags", "--name", ACR_NAME, "--repository", IMAGE_REPOSITORY, "--output", "json"],
        timeout=180,
    )

    acr_payload = parse_json(acr_show)
    result = {
        "phase": 19,
        "concept": "Docker Packaging Boundary",
        "status": "complete" if build and build["returncode"] == 0 else ("planned" if not args.apply else "action_required"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "option": "B - Azure Container Registry remote build; no local Docker required",
        "resource_group": RESOURCE_GROUP,
        "location": LOCATION,
        "acr_name": ACR_NAME,
        "acr_login_server": acr_login_server(acr_payload if isinstance(acr_payload, dict) else None),
        "image": image_name(),
        "hosted_source": str(HOSTED_ROOT.relative_to(PROJECT_ROOT)),
        "dockerfile": str((HOSTED_ROOT / "Dockerfile").relative_to(PROJECT_ROOT)),
        "local_docker_required": False,
        "agent_behavior_changed": False,
        "same_image_can_run_roles": ["analyst", "worker_a", "worker_b"],
        "file_check": file_check,
        "commands": {
            "account": summarize(account),
            "acr_show": summarize(acr_show),
            "acr_create": summarize(created_acr) if created_acr else None,
            "acr_build": summarize(build) if build else None,
            "tags": summarize(tags),
        },
        "tags_payload": parse_json(tags),
        "next_foundry_step": (
            "Use the ACR image as the hosted-agent runtime only after validating the customer's "
            "current Foundry image-deployment schema. Phase 19 proves the package boundary first."
        ),
    }
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in {"complete", "planned"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
