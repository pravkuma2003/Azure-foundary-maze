#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = PROJECT_ROOT / "runs"
VISUALS_DIR = PROJECT_ROOT / "visuals"
PROGRESS_PATH = PROJECT_ROOT / "PROGRESS.html"

LOCATION = "eastus"
RESOURCE_GROUP = "rg-maze-foundry-lab"
FOUNDRY_RESOURCE_PREFIX = "maze-foundry-prav"
FOUNDRY_PROJECT = "maze-migration-lab"
MODEL_DEPLOYMENT = "gpt41mini-maze"
MODEL_NAME = "gpt-4.1-mini"
MODEL_VERSION = "2025-04-14"
MODEL_FORMAT = "OpenAI"
MODEL_SKU = "GlobalStandard"
MODEL_CAPACITY = "50"


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    returncode: int | None
    stdout: str
    stderr: str


def run_command(args: list[str], timeout: int = 120) -> CommandResult:
    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return CommandResult(False, None, "", "command not found")
    except subprocess.TimeoutExpired as exc:
        return CommandResult(False, None, exc.stdout or "", "command timed out")
    return CommandResult(
        ok=completed.returncode == 0,
        returncode=completed.returncode,
        stdout=sanitize_output(completed.stdout),
        stderr=sanitize_output(completed.stderr),
    )


def sanitize_output(value: str) -> str:
    sanitized = value.replace(str(Path.home()), "~")
    return "\n".join(line for line in sanitized.splitlines() if "token" not in line.lower()).strip()


def parse_json(result: CommandResult) -> Any | None:
    if not result.ok or not result.stdout:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def mask(value: str | None) -> str | None:
    if not value:
        return value
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def resource_name(subscription_id: str) -> str:
    digest = hashlib.sha1(subscription_id.encode("utf-8")).hexdigest()[:6]
    return f"{FOUNDRY_RESOURCE_PREFIX}-{digest}"


def arm_id(subscription_id: str, provider_path: str) -> str:
    return f"/subscriptions/{subscription_id}/{provider_path}"


def wait_for_get(uri: str, expected_state: str = "Succeeded", attempts: int = 30) -> tuple[str, dict[str, Any] | None]:
    last_state = "unknown"
    last_payload: dict[str, Any] | None = None
    for _ in range(attempts):
        result = run_command(["az", "rest", "--method", "get", "--uri", uri, "--output", "json"], timeout=60)
        payload = parse_json(result)
        if isinstance(payload, dict):
            last_payload = payload
            state = payload.get("properties", {}).get("provisioningState") or payload.get("provisioningState")
            if state:
                last_state = state
            if state == expected_state:
                return last_state, payload
        time.sleep(5)
    return last_state, last_payload


def ensure_resource_group(apply: bool) -> dict[str, Any]:
    show = run_command(["az", "group", "show", "--name", RESOURCE_GROUP, "--output", "json"], timeout=60)
    if show.ok:
        payload = parse_json(show) or {}
        return {"name": RESOURCE_GROUP, "status": "reused", "state": payload.get("properties", {}).get("provisioningState")}
    if not apply:
        return {"name": RESOURCE_GROUP, "status": "planned", "state": "not_created"}
    create = run_command(
        [
            "az",
            "group",
            "create",
            "--name",
            RESOURCE_GROUP,
            "--location",
            LOCATION,
            "--tags",
            "course=azure-foundry-maze-migration",
            "costProfile=learning",
            "phase=4",
            "--output",
            "json",
        ],
        timeout=120,
    )
    payload = parse_json(create) or {}
    return {
        "name": RESOURCE_GROUP,
        "status": "created" if create.ok else "failed",
        "state": payload.get("properties", {}).get("provisioningState"),
        "error": create.stderr if not create.ok else "",
    }


def ensure_foundry_resource(subscription_id: str, foundry_resource: str, apply: bool) -> dict[str, Any]:
    show = run_command(
        ["az", "cognitiveservices", "account", "show", "--name", foundry_resource, "--resource-group", RESOURCE_GROUP, "--output", "json"],
        timeout=60,
    )
    if show.ok:
        payload = parse_json(show) or {}
        return {
            "name": foundry_resource,
            "status": "reused",
            "state": payload.get("properties", {}).get("provisioningState"),
            "endpoint": payload.get("properties", {}).get("endpoint"),
        }
    if not apply:
        return {"name": foundry_resource, "status": "planned", "state": "not_created"}

    uri = arm_id(
        subscription_id,
        f"resourceGroups/{RESOURCE_GROUP}/providers/Microsoft.CognitiveServices/accounts/{foundry_resource}?api-version=2025-04-01-preview",
    )
    body = {
        "location": LOCATION,
        "kind": "AIServices",
        "sku": {"name": "S0"},
        "identity": {"type": "SystemAssigned"},
        "tags": {
            "course": "azure-foundry-maze-migration",
            "costProfile": "learning",
            "phase": "4",
        },
        "properties": {
            "allowProjectManagement": True,
            "customSubDomainName": foundry_resource,
        },
    }
    create = run_command(["az", "rest", "--method", "put", "--uri", uri, "--body", json.dumps(body), "--output", "json"], timeout=180)
    if not create.ok:
        return {"name": foundry_resource, "status": "failed", "state": "unknown", "error": create.stderr}
    state, payload = wait_for_get(uri)
    return {
        "name": foundry_resource,
        "status": "created" if state == "Succeeded" else "creating",
        "state": state,
        "endpoint": (payload or {}).get("properties", {}).get("endpoint"),
    }


def ensure_project(subscription_id: str, foundry_resource: str, apply: bool) -> dict[str, Any]:
    uri = arm_id(
        subscription_id,
        f"resourceGroups/{RESOURCE_GROUP}/providers/Microsoft.CognitiveServices/accounts/{foundry_resource}/projects/{FOUNDRY_PROJECT}?api-version=2025-04-01-preview",
    )
    show = run_command(["az", "rest", "--method", "get", "--uri", uri, "--output", "json"], timeout=60)
    if show.ok:
        payload = parse_json(show) or {}
        return {
            "name": FOUNDRY_PROJECT,
            "status": "reused",
            "state": payload.get("properties", {}).get("provisioningState"),
            "endpoint": payload.get("properties", {}).get("endpoints", {}).get("AI Foundry API"),
        }
    if not apply:
        return {"name": FOUNDRY_PROJECT, "status": "planned", "state": "not_created"}
    body = {
        "location": LOCATION,
        "identity": {"type": "SystemAssigned"},
        "tags": {
            "course": "azure-foundry-maze-migration",
            "costProfile": "learning",
            "phase": "4",
        },
        "properties": {},
    }
    create = run_command(["az", "rest", "--method", "put", "--uri", uri, "--body", json.dumps(body), "--output", "json"], timeout=180)
    if not create.ok:
        return {"name": FOUNDRY_PROJECT, "status": "failed", "state": "unknown", "error": create.stderr}
    state, payload = wait_for_get(uri)
    return {
        "name": FOUNDRY_PROJECT,
        "status": "created" if state == "Succeeded" else "creating",
        "state": state,
        "endpoint": (payload or {}).get("properties", {}).get("endpoints", {}).get("AI Foundry API"),
    }


def ensure_model_deployment(foundry_resource: str, apply: bool) -> dict[str, Any]:
    show = run_command(
        [
            "az",
            "cognitiveservices",
            "account",
            "deployment",
            "show",
            "--name",
            foundry_resource,
            "--resource-group",
            RESOURCE_GROUP,
            "--deployment-name",
            MODEL_DEPLOYMENT,
            "--output",
            "json",
        ],
        timeout=60,
    )
    if show.ok:
        payload = parse_json(show) or {}
        return {
            "name": MODEL_DEPLOYMENT,
            "status": "reused",
            "state": payload.get("properties", {}).get("provisioningState"),
            "model": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "sku": payload.get("sku", {}).get("name"),
            "capacity": payload.get("sku", {}).get("capacity"),
        }
    if not apply:
        return {"name": MODEL_DEPLOYMENT, "status": "planned", "state": "not_created", "model": MODEL_NAME}

    create = run_command(
        [
            "az",
            "cognitiveservices",
            "account",
            "deployment",
            "create",
            "--name",
            foundry_resource,
            "--resource-group",
            RESOURCE_GROUP,
            "--deployment-name",
            MODEL_DEPLOYMENT,
            "--model-name",
            MODEL_NAME,
            "--model-version",
            MODEL_VERSION,
            "--model-format",
            MODEL_FORMAT,
            "--sku-capacity",
            MODEL_CAPACITY,
            "--sku-name",
            MODEL_SKU,
            "--output",
            "json",
        ],
        timeout=240,
    )
    payload = parse_json(create) or {}
    return {
        "name": MODEL_DEPLOYMENT,
        "status": "created" if create.ok else "failed",
        "state": payload.get("properties", {}).get("provisioningState"),
        "model": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "sku": payload.get("sku", {}).get("name"),
        "capacity": payload.get("sku", {}).get("capacity"),
        "error": create.stderr if not create.ok else "",
    }


def build_report(apply: bool) -> dict[str, Any]:
    account_result = run_command(["az", "account", "show", "--output", "json"], timeout=60)
    account = parse_json(account_result)
    if not isinstance(account, dict):
        raise RuntimeError("az account show failed; complete Phase 3 first")

    subscription_id = account["id"]
    foundry_resource = resource_name(subscription_id)

    group = ensure_resource_group(apply)
    resource = ensure_foundry_resource(subscription_id, foundry_resource, apply) if group["status"] != "failed" else {"status": "skipped"}
    project = (
        ensure_project(subscription_id, foundry_resource, apply)
        if resource.get("status") in {"created", "reused", "creating"}
        else {"name": FOUNDRY_PROJECT, "status": "skipped", "state": "not_created"}
    )
    deployment = (
        ensure_model_deployment(foundry_resource, apply)
        if resource.get("status") in {"created", "reused", "creating"}
        else {"name": MODEL_DEPLOYMENT, "status": "skipped", "state": "not_created"}
    )

    created_count = sum(1 for item in (group, resource, project, deployment) if item.get("status") == "created")
    failed = [item for item in (group, resource, project, deployment) if item.get("status") == "failed"]
    succeeded = all(
        item.get("status") in {"created", "reused"} and item.get("state") in {None, "Succeeded"}
        for item in (group, resource, project, deployment)
    )
    status = "complete" if succeeded and not failed else ("planned" if not apply else "action_required")

    return {
        "course": "Azure Foundry Maze Migration From Scratch",
        "phase": 4,
        "phase_name": "Foundry Project and Model Deployment",
        "status": status,
        "mode": "apply" if apply else "plan",
        "subscription": {
            "name": account.get("name"),
            "subscription_id_masked": mask(subscription_id),
            "tenant_id_masked": mask(account.get("tenantId")),
        },
        "cost_posture": {
            "resource_group": "single learning resource group",
            "foundry_resource": "single AIServices S0 resource",
            "project": "single Foundry project",
            "model_deployment": f"{MODEL_NAME} with {MODEL_SKU} capacity {MODEL_CAPACITY}",
            "fixed_hosted_agent_cost": "none in Phase 4; hosted agents start later",
            "expected_model_cost": "pay-per-token only during test calls; Phase 4 does not run inference",
            "cleanup_command": f"az group delete --name {RESOURCE_GROUP} --yes --no-wait",
        },
        "resources": {
            "resource_group": group,
            "foundry_resource": resource,
            "project": project,
            "model_deployment": deployment,
        },
        "summary": {
            "azure_resources_created_or_reused": created_count + sum(1 for item in (group, resource, project, deployment) if item.get("status") == "reused"),
            "new_resources_created": created_count,
            "failed_resources": len(failed),
            "inference_calls_made": 0,
            "hosted_agents_created": 0,
            "next_phase": "Add a Foundry provider adapter while keeping the local Pydantic AI agent behavior unchanged.",
        },
        "commands": {
            "resource_group": f"az group create --name {RESOURCE_GROUP} --location {LOCATION}",
            "foundry_resource": "az rest PUT Microsoft.CognitiveServices/accounts with kind AIServices, S0, project management, and managed identity",
            "project": "az rest PUT Microsoft.CognitiveServices/accounts/projects",
            "model_deployment": (
                f"az cognitiveservices account deployment create --deployment-name {MODEL_DEPLOYMENT} "
                f"--model-name {MODEL_NAME} --model-version {MODEL_VERSION} --model-format {MODEL_FORMAT} "
                f"--sku-name {MODEL_SKU} --sku-capacity {MODEL_CAPACITY}"
            ),
            "cleanup": f"az group delete --name {RESOURCE_GROUP} --yes --no-wait",
        },
    }


def render_phase_html(report: dict[str, Any]) -> str:
    summary = report["summary"]
    cost = report["cost_posture"]
    resources = report["resources"]
    resource_rows = []
    for label, item in resources.items():
        resource_rows.append(
            "<tr>"
            f"<td>{html.escape(label.replace('_', ' ').title())}</td>"
            f"<td>{html.escape(str(item.get('name', '')))}</td>"
            f"<td>{html.escape(str(item.get('status', '')))}</td>"
            f"<td>{html.escape(str(item.get('state', '')))}</td>"
            f"<td>{html.escape(str(item.get('model', item.get('endpoint', '')) or ''))}</td>"
            "</tr>"
        )
    cost_rows = "".join(
        "<tr>"
        f"<td>{html.escape(key.replace('_', ' ').title())}</td>"
        f"<td>{html.escape(str(value))}</td>"
        "</tr>"
        for key, value in cost.items()
    )
    command_rows = "".join(
        "<tr>"
        f"<td>{html.escape(key.replace('_', ' ').title())}</td>"
        f"<td><code>{html.escape(value)}</code></td>"
        "</tr>"
        for key, value in report["commands"].items()
    )
    data = html.escape(json.dumps(report, indent=2))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Azure Foundry Maze Migration - Phase 4</title>
  <style>
    :root {{ --bg:#f7f8fa; --panel:#fff; --text:#17202a; --muted:#5f6b7a; --line:#d9dee7; --blue:#285da8; --green:#1f6f5b; --shadow:0 10px 28px rgba(28,36,48,.08); }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:var(--text); background:var(--bg); line-height:1.5; }}
    main {{ width:min(1180px, calc(100% - 32px)); margin:0 auto; padding:32px 0 48px; }}
    header {{ display:grid; grid-template-columns:minmax(0,1fr) 280px; gap:20px; border-bottom:1px solid var(--line); padding-bottom:20px; margin-bottom:22px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(28px,4vw,42px); line-height:1.08; }}
    h2 {{ margin:0 0 12px; font-size:20px; }}
    p {{ margin:0; color:var(--muted); }}
    .panel,.summary {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; box-shadow:var(--shadow); padding:16px; }}
    .summary strong {{ display:block; font-size:30px; text-transform:capitalize; }}
    .metrics {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }}
    .metric {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fff; }}
    .metric span {{ display:block; color:var(--muted); font-size:12px; font-weight:800; text-transform:uppercase; }}
    .metric strong {{ display:block; margin-top:6px; font-size:26px; }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th,td {{ padding:9px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-size:12px; text-transform:uppercase; }}
    code {{ color:#111827; background:#eef2f7; padding:2px 5px; border-radius:4px; }}
    pre {{ overflow:auto; max-height:420px; padding:12px; background:#111827; color:#e5e7eb; border-radius:8px; font-size:12px; }}
    .stack {{ display:grid; gap:14px; }}
    @media (max-width:900px) {{ header,.metrics {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Phase 4 - Foundry Project and Model Deployment</h1>
        <p>Create the smallest usable Foundry base: one resource group, one Foundry resource, one project, one model deployment.</p>
      </div>
      <aside class="summary">
        <span>Status</span>
        <strong>{html.escape(report['status'])}</strong>
        <p>Inference calls made: {summary['inference_calls_made']}.</p>
      </aside>
    </header>
    <div class="stack">
      <section class="panel">
        <h2>Phase Metrics</h2>
        <div class="metrics">
          <div class="metric"><span>New Resources</span><strong>{summary['new_resources_created']}</strong></div>
          <div class="metric"><span>Reused/Created</span><strong>{summary['azure_resources_created_or_reused']}</strong></div>
          <div class="metric"><span>Hosted Agents</span><strong>{summary['hosted_agents_created']}</strong></div>
          <div class="metric"><span>LLM Calls</span><strong>{summary['inference_calls_made']}</strong></div>
        </div>
      </section>
      <section class="panel">
        <h2>Resource State</h2>
        <table>
          <thead><tr><th>Resource</th><th>Name</th><th>Status</th><th>State</th><th>Detail</th></tr></thead>
          <tbody>{''.join(resource_rows)}</tbody>
        </table>
      </section>
      <section class="panel">
        <h2>Cost Controls</h2>
        <table>
          <thead><tr><th>Control</th><th>Value</th></tr></thead>
          <tbody>{cost_rows}</tbody>
        </table>
      </section>
      <section class="panel">
        <h2>Commands Used</h2>
        <table>
          <thead><tr><th>Step</th><th>Command Shape</th></tr></thead>
          <tbody>{command_rows}</tbody>
        </table>
      </section>
      <section class="panel">
        <h2>Next Phase</h2>
        <p>{html.escape(summary['next_phase'])}</p>
      </section>
      <section class="panel">
        <h2>Report JSON</h2>
        <details><summary>Open generated report</summary><pre>{data}</pre></details>
      </section>
    </div>
  </main>
</body>
</html>
"""


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def render_progress_html(report: dict[str, Any]) -> str:
    phase1 = load_json(RUNS_DIR / "phase1_inventory.json")
    phase2 = load_json(RUNS_DIR / "phase2_public_repo_hygiene.json")
    phase3 = load_json(RUNS_DIR / "phase3_azure_login_readiness.json")
    cards = []
    if phase1:
        s = phase1["summary"]
        cards.append(f"""<section class="card"><h2>Phase 1: Portability Inventory</h2><p>Status: complete. Files scanned: {s['files_scanned']}. Findings: {s['findings']}.</p><p><a href="visuals/PHASE1_VISUAL.html">Open visual</a> | <a href="PHASE1_PORTABILITY_INVENTORY.md">Notes</a> | <a href="PHASE1_VALIDATION.md">Validation</a></p></section>""")
    if phase2:
        s = phase2["summary"]
        cards.append(f"""<section class="card"><h2>Phase 2: Public Repo and Secret Hygiene</h2><p>Status: {html.escape(phase2['status'])}. Copied: {s['files_copied']}. Excluded: {s['files_excluded']}. Redacted: {s['files_redacted']}. Blocking findings: {s['blocking_findings_after_export']}.</p><p><a href="visuals/PHASE2_VISUAL.html">Open visual</a> | <a href="PHASE2_PUBLIC_REPO_HYGIENE.md">Notes</a> | <a href="PHASE2_VALIDATION.md">Validation</a></p></section>""")
    if phase3:
        s = phase3["summary"]
        cards.append(f"""<section class="card"><h2>Phase 3: Azure Login and Subscription Readiness</h2><p>Status: {html.escape(phase3['status'])}. Azure CLI logged in: {s['azure_cli_logged_in']}. azd logged in: {s['azd_logged_in']}. Azure resources created: {s['azure_resources_created']}.</p><p><a href="visuals/PHASE3_VISUAL.html">Open visual</a> | <a href="PHASE3_AZURE_LOGIN_READINESS.md">Notes</a> | <a href="PHASE3_VALIDATION.md">Validation</a></p></section>""")
    s = report["summary"]
    cards.append(f"""<section class="card"><h2>Phase 4: Foundry Project and Model Deployment</h2><p>Status: {html.escape(report['status'])}. New resources: {s['new_resources_created']}. Hosted agents: {s['hosted_agents_created']}. Inference calls: {s['inference_calls_made']}.</p><p><a href="visuals/PHASE4_VISUAL.html">Open visual</a> | <a href="PHASE4_FOUNDRY_PROJECT_MODEL.md">Notes</a> | <a href="PHASE4_VALIDATION.md">Validation</a></p></section>""")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Azure Foundry Maze Migration - Progress</title>
  <style>
    body {{ margin:0; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:#f7f8fa; color:#17202a; }}
    main {{ width:min(960px, calc(100% - 32px)); margin:0 auto; padding:32px 0; }}
    .card {{ background:#fff; border:1px solid #d9dee7; border-radius:8px; padding:16px; margin:12px 0; }}
    a {{ color:#285da8; font-weight:800; text-decoration:none; }}
    p {{ color:#5f6b7a; }}
  </style>
</head>
<body>
  <main>
    <h1>Azure Foundry Maze Migration From Scratch</h1>
    <p>Step-by-step migration of the local multi-agent maze program to Microsoft Foundry-hosted agents.</p>
    <section class="card"><h2>Cost Policy</h2><p>Personal-subscription learning lab: one Foundry project, one model deployment, one hosted agent first, short traces, and no extra Azure services until a phase teaches them.</p></section>
    {''.join(cards)}
    <section class="card"><h2>Next: Phase 5</h2><p>{html.escape(s['next_phase'])}</p></section>
  </main>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or plan the minimal Phase 4 Foundry resource set.")
    parser.add_argument("--apply", action="store_true", help="Create or reuse Azure resources. Without this flag, only render a plan.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(apply=args.apply)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    VISUALS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "phase4_foundry_project_model.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (VISUALS_DIR / "PHASE4_VISUAL.html").write_text(render_phase_html(report), encoding="utf-8")
    PROGRESS_PATH.write_text(render_progress_html(report), encoding="utf-8")
    print(f"phase={report['phase']}")
    print(f"mode={report['mode']}")
    print(f"status={report['status']}")
    print(f"new_resources_created={report['summary']['new_resources_created']}")
    print(f"hosted_agents_created={report['summary']['hosted_agents_created']}")
    print(f"inference_calls_made={report['summary']['inference_calls_made']}")
    print(f"cleanup={report['cost_posture']['cleanup_command']}")
    return 0 if report["status"] in {"complete", "planned"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
