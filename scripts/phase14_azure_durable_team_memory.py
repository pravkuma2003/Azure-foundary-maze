#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEBUI_ROOT = PROJECT_ROOT / "webui" / "phase8-azure-webui"
RUNS_DIR = PROJECT_ROOT / "runs"
VISUALS_DIR = PROJECT_ROOT / "visuals"
PROGRESS_PATH = PROJECT_ROOT / "PROGRESS.html"

RESOURCE_GROUP = "rg-maze-foundry-lab"
WEBUI_FUNCTION_APP_NAME = "maze-webui-func-prav-ada483"
WEBUI_BASE_URL = f"https://{WEBUI_FUNCTION_APP_NAME}.azurewebsites.net"
TEAM_MEMORY_CONTAINER = "team-memory"
PACKAGE_PATH = RUNS_DIR / "phase14_azure_durable_team_memory_webui.zip"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def safe_text(value: str) -> str:
    value = value.replace(str(Path.home()), "~")
    value = re.sub(r'(x-functions-key=)[^\s"]+', r"\1[redacted]", value)
    value = re.sub(r'(sig=)[^"&\s]+', r"\1[redacted]", value)
    value = re.sub(r'("value"\s*:\s*")[^"]{20,}(")', r'\1[redacted]\2', value)
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


def build_package() -> dict[str, Any]:
    PACKAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if PACKAGE_PATH.exists():
        PACKAGE_PATH.unlink()
    excluded_parts = {".git", ".python_packages", "__pycache__", ".venv", "venv"}
    with zipfile.ZipFile(PACKAGE_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in WEBUI_ROOT.rglob("*"):
            if path.is_dir():
                continue
            rel = path.relative_to(WEBUI_ROOT)
            if any(part in excluded_parts for part in rel.parts):
                continue
            archive.write(path, rel.as_posix())
    return {
        "path": str(PACKAGE_PATH.relative_to(PROJECT_ROOT)),
        "bytes": PACKAGE_PATH.stat().st_size,
        "excluded": sorted(excluded_parts),
    }


def configure_webui(apply: bool) -> dict[str, Any]:
    if not apply:
        return {"attempted": False, "status": "planned"}
    result = run_command(
        [
            "az",
            "functionapp",
            "config",
            "appsettings",
            "set",
            "--resource-group",
            RESOURCE_GROUP,
            "--name",
            WEBUI_FUNCTION_APP_NAME,
            "--settings",
            "TEAM_MEMORY_BACKEND=azure-blob",
            f"TEAM_MEMORY_CONTAINER={TEAM_MEMORY_CONTAINER}",
            "SCM_DO_BUILD_DURING_DEPLOYMENT=true",
            "ENABLE_ORYX_BUILD=true",
        ],
        PROJECT_ROOT,
        timeout=300,
    )
    return {"attempted": True, "status": "configured" if result["returncode"] == 0 else "action_required", "command": summarize(result)}


def deploy_webui(apply: bool) -> dict[str, Any]:
    if not apply:
        return {"attempted": False, "status": "planned"}
    result = run_command(
        [
            "az",
            "functionapp",
            "deployment",
            "source",
            "config-zip",
            "--resource-group",
            RESOURCE_GROUP,
            "--name",
            WEBUI_FUNCTION_APP_NAME,
            "--src",
            str(PACKAGE_PATH),
        ],
        PROJECT_ROOT,
        timeout=900,
    )
    return {"attempted": True, "status": "deployed" if result["returncode"] == 0 else "action_required", "command": summarize(result)}


def post_json(url: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=900) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body[:1600]}
        return int(exc.code), parsed


def get_json(url: str) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body[:1600]}
        return int(exc.code), parsed


def validate_live(apply: bool) -> dict[str, Any]:
    if not apply:
        return {"attempted": False, "status": "planned"}
    status_code, payload = post_json(f"{WEBUI_BASE_URL}/api/run", {})
    trace = payload.get("trace") or {}
    summary = trace.get("summary") or {}
    run_id = summary.get("team_memory_run_id") or ""
    memory_status = 0
    memory_payload: dict[str, Any] = {}
    if run_id:
        memory_status, memory_payload = get_json(f"{WEBUI_BASE_URL}/api/memory?{urllib.parse.urlencode({'run_id': run_id})}")
    memory = memory_payload.get("memory") if isinstance(memory_payload.get("memory"), dict) else {}
    return {
        "attempted": True,
        "status_code": status_code,
        "source": payload.get("source"),
        "phase": trace.get("phase"),
        "shared_memory_backend": summary.get("shared_memory_backend"),
        "team_memory_run_id": run_id,
        "team_memory_container": summary.get("team_memory_container"),
        "team_memory_fallback_error": summary.get("team_memory_fallback_error"),
        "team_memory_reads": summary.get("team_memory_reads"),
        "team_memory_writes": summary.get("team_memory_writes"),
        "llm_calls": summary.get("llm_call_budget_used"),
        "foundry_toolbox_mcp_calls": summary.get("foundry_toolbox_mcp_calls"),
        "direct_http_tool_calls": summary.get("direct_http_tool_calls"),
        "memory_readback_status_code": memory_status,
        "memory_readback_keys": sorted(memory.keys()),
        "passed": (
            status_code == 200
            and payload.get("source") == "foundry-split-role-agents"
            and trace.get("phase") == 14
            and summary.get("shared_memory_backend") == "Azure Blob Storage"
            and bool(run_id)
            and memory_status == 200
            and "assignment.maze_a" in memory
            and "assignment.maze_b" in memory
            and "result.maze_a" in memory
            and "result.maze_b" in memory
        ),
    }


def build_report(apply: bool) -> dict[str, Any]:
    package = build_package()
    compile_result = run_command(
        ["python3", "-m", "py_compile", "webui/phase8-azure-webui/function_app.py"],
        PROJECT_ROOT,
        timeout=120,
    )
    config = configure_webui(apply)
    deploy = deploy_webui(apply) if config.get("status") in {"configured", "planned"} else {"attempted": False, "status": "blocked_by_config"}
    live = validate_live(apply) if deploy.get("status") in {"deployed", "planned"} else {"attempted": False, "status": "blocked_by_deploy"}
    passed = compile_result["returncode"] == 0 and (not apply or live.get("passed"))
    return {
        "course": "Azure Foundry Maze Migration From Scratch",
        "phase": 14,
        "phase_name": "Azure Durable Team Memory",
        "status": "complete" if passed else "action_required",
        "mode": "apply" if apply else "plan",
        "learning_objective": "Move Team Memory from request-scoped JSON to durable Azure Blob Storage while keeping the split Foundry role agents unchanged.",
        "architecture": {
            "before": "WebUI coordinator kept Team Memory in a request-local dict.",
            "after": "WebUI coordinator persists Team Memory records to Azure Blob Storage using the Function App storage account.",
            "storage_choice": "Reuse the existing Function App storage account; create one Blob container only.",
            "why_low_cost": "No new storage account, model deployment, toolbox, or hosted agent is created.",
        },
        "package": package,
        "compile": summarize(compile_result),
        "webui_configuration": config,
        "webui_deployment": deploy,
        "live_validation": live,
        "summary": {
            "new_storage_accounts": 0,
            "new_blob_containers": 1 if apply and live.get("passed") else 0,
            "memory_backend": live.get("shared_memory_backend") if apply else "Azure Blob Storage",
            "durable_memory_verified": bool(live.get("passed")),
            "next_phase": "Use durable Team Memory for replay, audit, and multi-run comparison.",
        },
    }


def render_visual(report: dict[str, Any]) -> str:
    validation = report["live_validation"]
    keys = validation.get("memory_readback_keys") or []
    key_items = "".join(f"<li>{html.escape(str(key))}</li>" for key in keys) or "<li>not validated yet</li>"
    escaped = html.escape(json.dumps(report, indent=2, default=str))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Azure Foundry Maze Migration - Phase 14</title>
  <style>
    body {{ margin:0; font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:#f7f8fa; color:#17202a; line-height:1.5; }}
    main {{ width:min(1180px,calc(100% - 32px)); margin:0 auto; padding:32px 0 48px; }}
    header {{ display:grid; grid-template-columns:minmax(0,1fr) 320px; gap:18px; border-bottom:1px solid #d9dee7; padding-bottom:20px; margin-bottom:20px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(30px,4vw,44px); line-height:1.08; }}
    h2 {{ margin:0 0 12px; font-size:20px; }}
    p {{ margin:0; color:#5f6b7a; }}
    .panel,.metric,.node {{ background:#fff; border:1px solid #d9dee7; border-radius:8px; box-shadow:0 10px 28px rgba(28,36,48,.08); padding:16px; }}
    .metric strong {{ display:block; font-size:28px; }}
    .diagram {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:14px; align-items:start; }}
    .node strong {{ display:block; font-size:17px; }}
    .node span {{ color:#5f6b7a; font-weight:800; font-size:12px; text-transform:uppercase; }}
    .agent {{ border-left:5px solid #285da8; }}
    .memory {{ border-left:5px solid #9a6500; }}
    .tool {{ border-left:5px solid #1f6f5b; }}
    table {{ width:100%; border-collapse:collapse; background:#fff; border:1px solid #d9dee7; border-radius:8px; overflow:hidden; }}
    th,td {{ padding:10px; border-bottom:1px solid #e6eaf1; text-align:left; vertical-align:top; }}
    th {{ background:#eef2f7; }}
    pre {{ white-space:pre-wrap; background:#111827; color:#e5e7eb; border-radius:8px; padding:14px; overflow:auto; }}
    @media (max-width:900px) {{ header,.diagram {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Phase 14 - Azure Durable Team Memory</h1>
      <p>{html.escape(report['learning_objective'])}</p>
    </div>
    <aside class="metric"><span>Status</span><strong>{html.escape(report['status'])}</strong><p>Mode: {html.escape(report['mode'])}</p></aside>
  </header>
  <section class="diagram">
    <article class="node agent"><span>Split Agents</span><strong>Analyst + Worker A + Worker B</strong><p>No new role agents are created in this phase.</p></article>
    <article class="node memory"><span>Durable Memory</span><strong>Azure Blob Storage</strong><p>Team Memory is persisted by run id and can be read back after the trace completes.</p></article>
    <article class="node tool"><span>Tool Boundary</span><strong>Foundry toolbox MCP</strong><p>Maze inspect/move calls continue through the Foundry-registered tool path.</p></article>
  </section>
  <section class="panel" style="margin-top:14px">
    <h2>Live Validation</h2>
    <table><tbody>
      <tr><th>Source</th><td>{html.escape(str(validation.get('source')))}</td></tr>
      <tr><th>Memory Backend</th><td>{html.escape(str(validation.get('shared_memory_backend')))}</td></tr>
      <tr><th>Run ID</th><td>{html.escape(str(validation.get('team_memory_run_id')))}</td></tr>
      <tr><th>LLM Calls</th><td>{html.escape(str(validation.get('llm_calls')))} / 25</td></tr>
      <tr><th>MCP Tool Calls</th><td>{html.escape(str(validation.get('foundry_toolbox_mcp_calls')))}</td></tr>
      <tr><th>Direct HTTP Tool Calls</th><td>{html.escape(str(validation.get('direct_http_tool_calls')))}</td></tr>
    </tbody></table>
  </section>
  <section class="panel" style="margin-top:14px">
    <h2>Persisted Keys</h2>
    <ul>{key_items}</ul>
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
    return """# Phase 14 - Azure Durable Team Memory

## Objective

Move Team Memory from request-scoped JSON into durable Azure Blob Storage while
keeping the split Foundry-hosted role agents unchanged.

## What Changed

Before:

```text
Azure WebUI Coordinator
  -> request-local Team Memory dict
  -> maze-analyst-agent
  -> maze-worker-agent-a
  -> maze-worker-agent-b
```

After:

```text
Azure WebUI Coordinator
  -> Azure Blob Storage Team Memory
  -> maze-analyst-agent
  -> maze-worker-agent-a
  -> maze-worker-agent-b
```

## Why This Matters

Independent agents need a shared state boundary that survives a single request.
This phase keeps orchestration simple but makes memory durable and inspectable.

## Cost Posture

The phase reuses the existing Function App storage account and creates only one
Blob container, `team-memory`. No new hosted agents, model deployments,
toolboxes, or storage accounts are created.
"""


def render_validation(report: dict[str, Any]) -> str:
    live = report["live_validation"]
    return f"""# Phase 14 Validation

## Expected Result

```text
WebUI /api/run returns source=foundry-split-role-agents.
Trace summary reports shared_memory_backend=Azure Blob Storage.
Trace summary includes a team_memory_run_id.
/api/memory?run_id=<id> reads back persisted Team Memory.
Persisted memory includes assignment.maze_a, assignment.maze_b, result.maze_a, and result.maze_b.
```

## Live Result

```text
status: {report['status']}
source: {live.get('source')}
memory_backend: {live.get('shared_memory_backend')}
team_memory_run_id: {live.get('team_memory_run_id')}
team_memory_writes: {live.get('team_memory_writes')}
team_memory_reads: {live.get('team_memory_reads')}
llm_calls: {live.get('llm_calls')} / 25
foundry_toolbox_mcp_calls: {live.get('foundry_toolbox_mcp_calls')}
direct_http_tool_calls: {live.get('direct_http_tool_calls')}
memory_readback_keys: {', '.join(live.get('memory_readback_keys') or [])}
```

## Generated Artifacts

```text
runs/phase14_azure_durable_team_memory.json
runs/phase14_azure_durable_team_memory_webui.zip
visuals/PHASE14_VISUAL.html
PHASE14_AZURE_DURABLE_TEAM_MEMORY.md
PHASE14_VALIDATION.md
PROGRESS.html
```
"""


def refresh_progress(report: dict[str, Any]) -> None:
    existing = PROGRESS_PATH.read_text(encoding="utf-8") if PROGRESS_PATH.exists() else ""
    phase12 = '<section class="card"><h2>Phase 12: PydanticAI Runtime Uses Foundry Toolbox MCP</h2><p>Status: complete. MCP calls: 32. Direct HTTP calls: 0. LLM calls: 17.</p><p><a href="visuals/PHASE12_VISUAL.html">Open visual</a> | <a href="PHASE12_FOUNDRY_TOOLBOX_MCP_RUNTIME.md">Notes</a> | <a href="PHASE12_VALIDATION.md">Validation</a></p></section>'
    phase13 = '<section class="card"><h2>Phase 13: Independent Foundry-Hosted Role Agents</h2><p>Status: complete. Hosted role agents deployed: 3. Durable storage added: 0.</p><p><a href="visuals/PHASE13_VISUAL.html">Open visual</a> | <a href="PHASE13_SPLIT_INDEPENDENT_ROLE_AGENTS.md">Notes</a> | <a href="PHASE13_VALIDATION.md">Validation</a></p></section>'
    phase14 = f'<section class="card current"><h2>Phase 14: Azure Durable Team Memory</h2><p>Status: {html.escape(report["status"])}. Backend: {html.escape(str(report["summary"]["memory_backend"]))}. Durable readback: {report["summary"]["durable_memory_verified"]}.</p><p><a href="visuals/PHASE14_VISUAL.html">Open visual</a> | <a href="PHASE14_AZURE_DURABLE_TEAM_MEMORY.md">Notes</a> | <a href="PHASE14_VALIDATION.md">Validation</a></p></section>'
    if "Phase 14: Azure Durable Team Memory" in existing:
        updated = re.sub(r'<section class="card(?: current)?"><h2>Phase 14: Azure Durable Team Memory.*?</section>', phase14, existing, flags=re.S)
    else:
        updated = existing
        updated = re.sub(r'<section class="card current"><h2>Phase 13:.*?</section>', phase13 + phase14, updated, flags=re.S)
    updated = re.sub(r'<section class="card(?: current)?"><h2>Phase 12:.*?</section>', phase12, updated, flags=re.S)
    updated = re.sub(r'<section class="card(?: current)?"><h2>Phase 13:.*?</section>', phase13, updated, flags=re.S)
    updated = re.sub(
        r"<section class=\"card\"><h2>Next</h2>.*?</section>",
        '<section class="card"><h2>Next</h2><p>Use durable Team Memory for replay, audit, and multi-run comparison.</p></section>',
        updated,
        flags=re.S,
    )
    write_text(PROGRESS_PATH, updated)


def write_artifacts(report: dict[str, Any]) -> None:
    write_text(RUNS_DIR / "phase14_azure_durable_team_memory.json", json.dumps(report, indent=2, default=str) + "\n")
    write_text(VISUALS_DIR / "PHASE14_VISUAL.html", render_visual(report))
    write_text(PROJECT_ROOT / "PHASE14_AZURE_DURABLE_TEAM_MEMORY.md", render_notes(report))
    write_text(PROJECT_ROOT / "PHASE14_VALIDATION.md", render_validation(report))
    refresh_progress(report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy and validate Phase 14 durable Team Memory.")
    parser.add_argument("--apply", action="store_true", help="Deploy the WebUI Function changes and run live validation.")
    args = parser.parse_args()
    report = build_report(apply=args.apply)
    write_artifacts(report)
    print(json.dumps({"phase": report["phase"], "status": report["status"], "mode": report["mode"], "summary": report["summary"], "live_validation": report["live_validation"]}, indent=2))
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
