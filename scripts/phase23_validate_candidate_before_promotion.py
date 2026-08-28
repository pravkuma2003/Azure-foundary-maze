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
RUNS_DIR = PROJECT_ROOT / "runs"

RESOURCE_GROUP = os.environ.get("AZURE_RESOURCE_GROUP") or "rg-maze-foundry-lab"
ACR_NAME = os.environ.get("PHASE22_ACR_NAME") or "mazefoundryacrpravada483"
TASK_NAME = os.environ.get("PHASE22_TASK_NAME") or "maze-role-agent-github-build"
IMAGE_REPOSITORY = os.environ.get("PHASE22_IMAGE_REPOSITORY") or "maze-role-agent"
MAX_VALIDATION_SECONDS = int(os.environ.get("PHASE23_MAX_VALIDATION_SECONDS") or "900")
ROLES = ["analyst", "worker_a", "worker_b"]


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


def summarize(result: dict[str, Any], *, limit: int = 2600) -> dict[str, Any]:
    return {
        "returncode": result["returncode"],
        "command": result["command"],
        "stdout_tail": safe_text(result.get("stdout", ""))[-limit:],
        "stderr_tail": safe_text(result.get("stderr", ""))[-limit:],
    }


def parse_json_text(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def latest_successful_run() -> tuple[dict[str, Any] | None, dict[str, Any]]:
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
    run = payload[0] if isinstance(payload, list) and payload else None
    return run if isinstance(run, dict) else None, summarize(result)


def acr_login_server() -> tuple[str, dict[str, Any]]:
    result = run_command(["az", "acr", "show", "--name", ACR_NAME, "--resource-group", RESOURCE_GROUP, "--output", "json"], timeout=180)
    payload = parse_json_text(result.get("stdout", "")) if result["returncode"] == 0 else None
    if isinstance(payload, dict) and isinstance(payload.get("loginServer"), str):
        return payload["loginServer"], summarize(result)
    return f"{ACR_NAME}.azurecr.io", summarize(result)


def image_from_run(login_server: str, run: dict[str, Any] | None) -> tuple[str | None, str | None]:
    if not run:
        return None, None
    run_id = run.get("runId")
    output_images = run.get("outputImages")
    if isinstance(output_images, list):
        for image in output_images:
            if not isinstance(image, dict):
                continue
            if image.get("repository") == IMAGE_REPOSITORY and image.get("tag") == f"phase22-{run_id}":
                return f"{login_server}/{IMAGE_REPOSITORY}:phase22-{run_id}", image.get("digest")
    if isinstance(run_id, str):
        return f"{login_server}/{IMAGE_REPOSITORY}:phase22-{run_id}", None
    return None, None


def validate_image_tag(image: str | None) -> dict[str, Any]:
    if not image:
        return {"status": "failed", "reason": "No candidate image was found."}
    registry, remainder = image.split("/", 1)
    repository, tag = remainder.rsplit(":", 1)
    registry_name = registry.split(".")[0]
    result = run_command(
        [
            "az",
            "acr",
            "repository",
            "show-tags",
            "--name",
            registry_name,
            "--repository",
            repository,
            "--output",
            "json",
        ],
        timeout=180,
    )
    tags = parse_json_text(result.get("stdout", "")) if result["returncode"] == 0 else None
    return {
        "status": "passed" if isinstance(tags, list) and tag in tags else "failed",
        "image": image,
        "tag": tag,
        "command": summarize(result),
    }


def smoke_command(image: str, role: str) -> str:
    return f"$Registry/{IMAGE_REPOSITORY}:{image.rsplit(':', 1)[1]} python main.py --once --provider test --role {role}"


def validate_role_smoke(image: str | None, role: str, apply: bool) -> dict[str, Any]:
    if not image:
        return {"role": role, "attempted": False, "status": "failed", "reason": "No candidate image was found."}
    command = [
        "az",
        "acr",
        "run",
        "--registry",
        ACR_NAME,
        "--cmd",
        smoke_command(image, role),
        "/dev/null",
    ]
    if not apply:
        return {"role": role, "attempted": False, "status": "planned", "command": command}
    result = run_command(command, timeout=MAX_VALIDATION_SECONDS)
    output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}"
    return {
        "role": role,
        "attempted": True,
        "status": "passed" if result["returncode"] == 0 and '"status": "complete"' in output and f'"role": "{role}"' in output else "failed",
        "json_status_seen": '"status": "complete"' in output,
        "role_seen": f'"role": "{role}"' in output,
        "command": summarize(result, limit=5000),
    }


def promote_latest_run(apply: bool) -> dict[str, Any]:
    if not apply:
        return {"attempted": False, "status": "blocked_until_validation_passes"}
    result = run_command(["python3", "scripts/phase22_acr_task_build_trigger.py", "--promote-latest-run"], timeout=2400)
    return {"attempted": True, "status": "complete" if result["returncode"] == 0 else "failed", "command": summarize(result, limit=5000)}


def validation_status(image_check: dict[str, Any], role_smoke: dict[str, Any]) -> str:
    if image_check.get("status") != "passed":
        return "failed"
    if any(result.get("status") != "passed" for result in role_smoke.values()):
        return "failed"
    return "passed"


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 23: validate the latest ACR candidate image before Foundry promotion.")
    parser.add_argument("--apply", action="store_true", help="Run validation checks against the latest successful ACR Task image.")
    parser.add_argument("--promote-if-valid", action="store_true", help="Promote only when validation passes in this run.")
    args = parser.parse_args()

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RUNS_DIR / "phase23_validate_candidate_before_promotion.json"

    account = run_command(["az", "account", "show", "--query", "{tenantId:tenantId,subscriptionId:id,name:name}", "--output", "json"], timeout=120)
    run, latest_run_command = latest_successful_run()
    login_server, acr_show = acr_login_server()
    candidate_image, digest = image_from_run(login_server, run)
    image_check = validate_image_tag(candidate_image)
    role_smoke = {role: validate_role_smoke(candidate_image, role, args.apply) for role in ROLES}
    status = "planned" if not args.apply else validation_status(image_check, role_smoke)
    promotion = promote_latest_run(args.promote_if_valid and status == "passed")

    result = {
        "phase": 23,
        "concept": "Automated Validation Before Promotion",
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "candidate_run_id": run.get("runId") if isinstance(run, dict) else None,
        "candidate_run_type": run.get("runType") if isinstance(run, dict) else None,
        "candidate_source_commit": (
            run.get("sourceTrigger", {}).get("commitId")
            if isinstance(run, dict) and isinstance(run.get("sourceTrigger"), dict)
            else None
        ),
        "candidate_image": candidate_image,
        "candidate_digest": digest,
        "promotion_policy": "promote only after image tag check and all role smoke tests pass",
        "checks": {
            "account": summarize(account),
            "acr_show": acr_show,
            "latest_successful_run": latest_run_command,
            "image_tag": image_check,
            "role_smoke": role_smoke,
        },
        "promotion": promotion,
        "next_manual_commands": {
            "validate": "python3 scripts/phase23_validate_candidate_before_promotion.py --apply",
            "validate_and_promote": "python3 scripts/phase23_validate_candidate_before_promotion.py --apply --promote-if-valid",
        },
    }
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if status in {"planned", "passed"} and promotion.get("status") != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
