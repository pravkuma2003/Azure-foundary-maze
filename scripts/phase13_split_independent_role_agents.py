#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOSTED_ROOT = PROJECT_ROOT / "hosted" / "maze-role-agents"
RUNS_DIR = PROJECT_ROOT / "runs"
VISUALS_DIR = PROJECT_ROOT / "visuals"
PROGRESS_PATH = PROJECT_ROOT / "PROGRESS.html"

PROJECT_ENDPOINT = "https://maze-foundry-prav-ada483.services.ai.azure.com/api/projects/maze-migration-lab"
TOOLBOX_NAME = "maze-toolbox"
ROLE_AGENTS = [
    ("maze-analyst-agent", "analyst"),
    ("maze-worker-agent-a", "worker_a"),
    ("maze-worker-agent-b", "worker_b"),
]


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def safe_text(value: str) -> str:
    value = value.replace(str(Path.home()), "~")
    value = re.sub(r'("MAZE_TOOL_KEY"\s*:\s*")[^"]+(")', r"\1[redacted]\2", value)
    value = re.sub(r'(MAZE_TOOL_KEY[=:]\s*)[^\s,}]+', r"\1[redacted]", value)
    value = re.sub(r'(x-functions-key=)[^\s"]+', r"\1[redacted]", value)
    value = re.sub(r'(sig=)[^"&\s]+', r"\1[redacted]", value)
    return value.strip()


def run_command(args: list[str], cwd: Path, timeout: int = 300) -> dict[str, Any]:
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
        "stdout_tail": safe_text(result.get("stdout", ""))[-1600:],
        "stderr_tail": safe_text(result.get("stderr", ""))[-1600:],
        "command": result["command"],
    }


def parse_json_result(result: dict[str, Any]) -> dict[str, Any]:
    if result["returncode"] != 0 or not result.get("stdout"):
        return {}
    try:
        payload = json.loads(result["stdout"])
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {"value": payload}


def local_role_validation() -> dict[str, Any]:
    roles: dict[str, Any] = {}
    for agent_name, role in ROLE_AGENTS:
        result = run_command(
            ["python3", "main.py", "--once", "--provider", "test", "--role", role],
            HOSTED_ROOT,
            timeout=300,
        )
        payload = parse_json_result(result)
        roles[role] = {
            "hosted_agent_name": agent_name,
            "status": "passed" if result["returncode"] == 0 and payload.get("status") == "complete" else "failed",
            "command": summarize(result),
            "summary": payload.get("summary") or {},
            "result_keys": sorted((payload.get("result") or {}).keys()) if isinstance(payload.get("result"), dict) else [],
        }
    return roles


def toolbox_endpoint() -> tuple[str, dict[str, Any]]:
    result = run_command(
        [
            "azd",
            "ai",
            "toolbox",
            "show",
            TOOLBOX_NAME,
            "--project-endpoint",
            PROJECT_ENDPOINT,
            "--output",
            "json",
        ],
        HOSTED_ROOT,
        timeout=300,
    )
    payload = parse_json_result(result)
    endpoint = str(payload.get("endpoint") or "")
    return endpoint, {"endpoint_found": bool(endpoint), "command": summarize(result)}


def configure_env(endpoint: str) -> dict[str, Any]:
    result = run_command(["azd", "env", "set", "MAZE_TOOL_MCP_ENDPOINT", endpoint], HOSTED_ROOT, timeout=300)
    return {"status": "configured" if result["returncode"] == 0 else "action_required", "command": summarize(result)}


def deploy_role_agents() -> dict[str, Any]:
    deployments: dict[str, Any] = {}
    for agent_name, _role in ROLE_AGENTS:
        deploy = run_command(["azd", "deploy", agent_name, "--no-prompt", "--timeout", "1200"], HOSTED_ROOT, timeout=1500)
        show = run_command(["azd", "ai", "agent", "show", agent_name, "--output", "json"], HOSTED_ROOT, timeout=300)
        show_payload = parse_json_result(show)
        deployments[agent_name] = {
            "status": "deployed" if deploy["returncode"] == 0 and show_payload.get("status") == "active" else "action_required",
            "deploy": summarize(deploy),
            "show": summarize(show),
            "active_version": show_payload.get("version"),
            "endpoint_present": bool(show_payload.get("endpoint")),
        }
    return deployments


def build_report(apply: bool) -> dict[str, Any]:
    local_roles = local_role_validation()
    endpoint = ""
    toolbox = {"attempted": False}
    env = {"attempted": False, "status": "planned"}
    deployments: dict[str, Any] = {}
    if apply:
        endpoint, toolbox = toolbox_endpoint()
        env = configure_env(endpoint) if endpoint else {"attempted": True, "status": "action_required", "error": "Toolbox MCP endpoint not found"}
        deployments = deploy_role_agents() if endpoint and env.get("status") == "configured" else {}

    local_passed = all(role["status"] == "passed" for role in local_roles.values())
    deploy_passed = (not apply) or all(deployment.get("status") == "deployed" for deployment in deployments.values())
    return {
        "course": "Azure Foundry Maze Migration From Scratch",
        "phase": 13,
        "phase_name": "Independent Foundry-Hosted Role Agents",
        "status": "complete" if local_passed and deploy_passed else "action_required",
        "mode": "apply" if apply else "plan",
        "learning_objective": "Split the monolithic maze runtime into separate Foundry-hosted Analyst, Worker A, and Worker B agents.",
        "architecture": {
            "before": "one maze-monolithic-agent contains Analyst, Worker A, Worker B, orchestrator, memory, and tool client",
            "after": "maze-analyst-agent, maze-worker-agent-a, and maze-worker-agent-b run as independent Foundry-hosted role agents",
            "shared_memory_scope": "request-scoped Team Memory passed by the coordinator; durable Azure storage is intentionally deferred",
            "tool_boundary": "Worker agents keep using the Foundry toolbox MCP endpoint for Maze Tool calls",
        },
        "role_agents": [
            {
                "name": "maze-analyst-agent",
                "role": "Analyst",
                "responsibility": "global assignment and Team Memory writes",
                "uses_pydantic_ai": True,
                "uses_maze_tool_mcp": False,
            },
            {
                "name": "maze-worker-agent-a",
                "role": "Worker Agent A",
                "responsibility": "Maze A local reasoning and result publication",
                "uses_pydantic_ai": True,
                "uses_maze_tool_mcp": True,
            },
            {
                "name": "maze-worker-agent-b",
                "role": "Worker Agent B",
                "responsibility": "Maze B local reasoning and result publication",
                "uses_pydantic_ai": True,
                "uses_maze_tool_mcp": True,
            },
        ],
        "local_validation": local_roles,
        "toolbox": {"name": TOOLBOX_NAME, "mcp_endpoint": endpoint, "lookup": toolbox},
        "hosted_agent_environment": env,
        "hosted_agent_deployments": deployments,
        "summary": {
            "independent_hosted_agents_planned": 3,
            "independent_hosted_agents_deployed": sum(1 for deployment in deployments.values() if deployment.get("status") == "deployed"),
            "new_storage_resources": 0,
            "new_model_deployments": 0,
            "new_toolboxes": 0,
            "next_phase": "Move Team Memory from request-scoped JSON into low-cost Azure durable storage after independent role-agent boundaries are validated.",
        },
    }


def render_visual(report: dict[str, Any]) -> str:
    rows = "".join(
        f"<tr><td>{html.escape(agent['name'])}</td><td>{html.escape(agent['role'])}</td><td>{html.escape(agent['responsibility'])}</td><td>{agent['uses_maze_tool_mcp']}</td></tr>"
        for agent in report["role_agents"]
    )
    local_rows = "".join(
        f"<tr><td>{html.escape(role)}</td><td>{html.escape(result['status'])}</td><td>{html.escape(str(result.get('summary', {})))}</td></tr>"
        for role, result in report["local_validation"].items()
    )
    escaped = html.escape(json.dumps(report, indent=2, default=str))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Azure Foundry Maze Migration - Phase 13</title>
  <style>
    body {{ margin:0; font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:#f7f8fa; color:#17202a; line-height:1.5; }}
    main {{ width:min(1180px,calc(100% - 32px)); margin:0 auto; padding:32px 0 48px; }}
    header {{ display:grid; grid-template-columns:minmax(0,1fr) 320px; gap:18px; border-bottom:1px solid #d9dee7; padding-bottom:20px; margin-bottom:20px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(30px,4vw,44px); line-height:1.08; }}
    h2 {{ margin:0 0 12px; font-size:20px; }}
    p {{ margin:0; color:#5f6b7a; }}
    .panel,.metric,.node {{ background:#fff; border:1px solid #d9dee7; border-radius:8px; box-shadow:0 10px 28px rgba(28,36,48,.08); padding:16px; }}
    .metric strong {{ display:block; font-size:28px; }}
    .grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }}
    .diagram {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:14px; align-items:start; }}
    .node strong {{ display:block; font-size:17px; }}
    .node span {{ color:#5f6b7a; font-weight:800; font-size:12px; text-transform:uppercase; }}
    .memory {{ border-left:5px solid #9a6500; }}
    .agent {{ border-left:5px solid #285da8; }}
    .worker {{ border-left-color:#1f6f5b; }}
    table {{ width:100%; border-collapse:collapse; background:#fff; border:1px solid #d9dee7; border-radius:8px; overflow:hidden; }}
    th,td {{ padding:10px; border-bottom:1px solid #e6eaf1; text-align:left; vertical-align:top; }}
    th {{ background:#eef2f7; }}
    pre {{ white-space:pre-wrap; background:#111827; color:#e5e7eb; border-radius:8px; padding:14px; overflow:auto; }}
    @media (max-width:900px) {{ header,.grid,.diagram {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Phase 13 - Independent Foundry-Hosted Role Agents</h1>
      <p>{html.escape(report['learning_objective'])}</p>
    </div>
    <aside class="metric"><span>Status</span><strong>{html.escape(report['status'])}</strong><p>Mode: {html.escape(report['mode'])}</p></aside>
  </header>
  <section class="diagram">
    <article class="node agent"><span>Hosted Agent</span><strong>maze-analyst-agent</strong><p>Writes assignment and coordination boundary to Team Memory.</p></article>
    <article class="node memory"><span>Coordinator Memory</span><strong>Request-Scoped Team Memory</strong><p>Visible boundary now; durable Azure backend is deferred to the next phase.</p></article>
    <article class="node agent worker"><span>Hosted Agents</span><strong>maze-worker-agent-a / b</strong><p>Read assignment, reason locally, call the Foundry toolbox MCP Maze Tool, publish result.</p></article>
  </section>
  <section class="grid" style="margin-top:14px">
    <article class="panel"><h2>Before</h2><p>{html.escape(report['architecture']['before'])}</p></article>
    <article class="panel"><h2>After</h2><p>{html.escape(report['architecture']['after'])}</p></article>
  </section>
  <section class="panel" style="margin-top:14px">
    <h2>Role Split</h2>
    <table><thead><tr><th>Hosted Agent</th><th>Role</th><th>Responsibility</th><th>Uses MCP Tool</th></tr></thead><tbody>{rows}</tbody></table>
  </section>
  <section class="panel" style="margin-top:14px">
    <h2>Validation</h2>
    <table><thead><tr><th>Role</th><th>Status</th><th>Summary</th></tr></thead><tbody>{local_rows}</tbody></table>
  </section>
  <section class="panel" style="margin-top:14px">
    <h2>Raw Report</h2>
    <details><summary>Open JSON</summary><pre>{escaped}</pre></details>
  </section>
</main>
</body>
</html>
"""


def render_notes(report: dict[str, Any]) -> str:
    return f"""# Phase 13 - Independent Foundry-Hosted Role Agents

## Objective

Split the Phase 12 monolithic hosted runtime into independent Foundry-hosted
role agents:

```text
maze-analyst-agent
maze-worker-agent-a
maze-worker-agent-b
```

## What Changes

Before Phase 13:

```text
maze-monolithic-agent
  -> Analyst role
  -> Worker Agent A role
  -> Worker Agent B role
  -> in-process coordinator memory
  -> Foundry toolbox MCP Maze Tool
```

After Phase 13:

```text
Coordinator / WebUI boundary
  -> maze-analyst-agent
  -> request-scoped Team Memory
  -> maze-worker-agent-a
  -> maze-worker-agent-b
```

Worker agents still call:

```text
Foundry toolbox MCP -> OpenAPI wrapper -> Azure Function Maze Tool
```

## Why This Matters

This is the first phase where Analyst, Worker A, and Worker B are no longer
just role functions inside one hosted process. Each role has its own hosted-agent
deployment boundary and can be monitored, authorized, scaled, or replaced
independently.

## Shared Memory Boundary

This phase intentionally keeps Team Memory request-scoped. That teaches the
agent split without adding a storage service in the same step.

The next phase should move Team Memory into low-cost Azure durable storage.
"""


def render_validation(report: dict[str, Any]) -> str:
    deployment_lines = "\n".join(
        f"{name}: {deployment.get('status')}"
        for name, deployment in sorted(report.get("hosted_agent_deployments", {}).items())
    ) or "not attempted"
    return f"""# Phase 13 Validation

## Expected Result

```text
Analyst role validates as an independent role entrypoint.
Worker Agent A validates as an independent role entrypoint.
Worker Agent B validates as an independent role entrypoint.
Each role returns JSON with status=complete.
The hosted deployment path creates three Foundry-hosted agents when --apply is used.
```

## Local Validation

```text
analyst: {report['local_validation']['analyst']['status']}
worker_a: {report['local_validation']['worker_a']['status']}
worker_b: {report['local_validation']['worker_b']['status']}
```

## Hosted Deployment

```text
{deployment_lines}
```

## Generated Artifacts

```text
runs/phase13_split_independent_role_agents.json
visuals/PHASE13_VISUAL.html
PHASE13_SPLIT_INDEPENDENT_ROLE_AGENTS.md
PHASE13_VALIDATION.md
PROGRESS.html
```
"""


def refresh_progress(report: dict[str, Any]) -> None:
    existing = PROGRESS_PATH.read_text(encoding="utf-8") if PROGRESS_PATH.exists() else ""
    next_text = "Move Team Memory from request-scoped JSON into low-cost Azure durable storage."
    if "Phase 13: Independent Foundry-Hosted Role Agents" in existing:
        updated = re.sub(
            r'<section class="card current"><h2>Phase 12:.*?</section>',
            '<section class="card"><h2>Phase 12: PydanticAI Runtime Uses Foundry Toolbox MCP</h2><p>Status: complete. MCP calls: 32. Direct HTTP calls: 0. LLM calls: 17.</p><p><a href="visuals/PHASE12_VISUAL.html">Open visual</a> | <a href="PHASE12_FOUNDRY_TOOLBOX_MCP_RUNTIME.md">Notes</a> | <a href="PHASE12_VALIDATION.md">Validation</a></p></section>',
            existing,
            flags=re.S,
        )
        updated = re.sub(
            r'<section class="card(?: current)?"><h2>Phase 13: Independent Foundry-Hosted Role Agents.*?</section>',
            f'<section class="card current"><h2>Phase 13: Independent Foundry-Hosted Role Agents</h2><p>Status: {html.escape(report["status"])}. Planned hosted agents: 3. Durable storage added: 0.</p><p><a href="visuals/PHASE13_VISUAL.html">Open visual</a> | <a href="PHASE13_SPLIT_INDEPENDENT_ROLE_AGENTS.md">Notes</a> | <a href="PHASE13_VALIDATION.md">Validation</a></p></section>',
            updated,
            flags=re.S,
        )
        updated = re.sub(r"<section class=\"card\"><h2>Next</h2>.*?</section>", f'<section class="card"><h2>Next</h2><p>{html.escape(next_text)}</p></section>', updated, flags=re.S)
        write_text(PROGRESS_PATH, updated)
        return

    phase13 = f'<section class="card current"><h2>Phase 13: Independent Foundry-Hosted Role Agents</h2><p>Status: {html.escape(report["status"])}. Planned hosted agents: 3. Durable storage added: 0.</p><p><a href="visuals/PHASE13_VISUAL.html">Open visual</a> | <a href="PHASE13_SPLIT_INDEPENDENT_ROLE_AGENTS.md">Notes</a> | <a href="PHASE13_VALIDATION.md">Validation</a></p></section>'
    updated = re.sub(
        r'<section class="card current"><h2>Phase 12:.*?</section>',
        '<section class="card"><h2>Phase 12: PydanticAI Runtime Uses Foundry Toolbox MCP</h2><p>Status: complete. MCP calls: 32. Direct HTTP calls: 0. LLM calls: 17.</p><p><a href="visuals/PHASE12_VISUAL.html">Open visual</a> | <a href="PHASE12_FOUNDRY_TOOLBOX_MCP_RUNTIME.md">Notes</a> | <a href="PHASE12_VALIDATION.md">Validation</a></p></section>' + phase13,
        existing,
        flags=re.S,
    )
    updated = re.sub(r"<section class=\"card\"><h2>Next</h2>.*?</section>", f'<section class="card"><h2>Next</h2><p>{html.escape(next_text)}</p></section>', updated, flags=re.S)
    write_text(PROGRESS_PATH, updated)


def write_artifacts(report: dict[str, Any]) -> None:
    write_text(RUNS_DIR / "phase13_split_independent_role_agents.json", json.dumps(report, indent=2, default=str) + "\n")
    write_text(VISUALS_DIR / "PHASE13_VISUAL.html", render_visual(report))
    write_text(PROJECT_ROOT / "PHASE13_SPLIT_INDEPENDENT_ROLE_AGENTS.md", render_notes(report))
    write_text(PROJECT_ROOT / "PHASE13_VALIDATION.md", render_validation(report))
    refresh_progress(report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare and optionally deploy Phase 13 split role agents.")
    parser.add_argument("--apply", action="store_true", help="Deploy the three Foundry-hosted role agents.")
    args = parser.parse_args()
    report = build_report(apply=args.apply)
    write_artifacts(report)
    print(json.dumps({"phase": report["phase"], "status": report["status"], "mode": report["mode"], "summary": report["summary"]}, indent=2))
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
