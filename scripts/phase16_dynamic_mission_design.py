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
HOSTED_ROOT = PROJECT_ROOT / "hosted" / "phase13-split-role-agents"
TOOL_ROOT = PROJECT_ROOT / "tools" / "phase10-maze-tool-function"
WEBUI_ROOT = PROJECT_ROOT / "webui" / "phase8-azure-webui"
TOOLBOX_DIR = PROJECT_ROOT / "tools" / "phase11-foundry-toolbox"
RUNS_DIR = PROJECT_ROOT / "runs"
VISUALS_DIR = PROJECT_ROOT / "visuals"
PROGRESS_PATH = PROJECT_ROOT / "PROGRESS.html"

RESOURCE_GROUP = "rg-maze-foundry-lab"
PROJECT_ENDPOINT = "https://maze-foundry-prav-ada483.services.ai.azure.com/api/projects/maze-migration-lab"
TOOL_FUNCTION_APP = "maze-tool-func-prav-ada483"
WEBUI_FUNCTION_APP = "maze-webui-func-prav-ada483"
TOOL_BASE_URL = f"https://{TOOL_FUNCTION_APP}.azurewebsites.net"
WEBUI_BASE_URL = f"https://{WEBUI_FUNCTION_APP}.azurewebsites.net"
OPENAPI_URL = f"{TOOL_BASE_URL}/api/maze/openapi.json"
CONNECTION_NAME = "maze-tool-function-key"
TOOLBOX_NAME = "maze-toolbox-dynamic"
OPENAPI_TOOL_NAME = "maze_tool_api"
ROLE_AGENTS = ["maze-analyst-agent", "maze-worker-agent-a", "maze-worker-agent-b"]
TOOL_ZIP = RUNS_DIR / "phase16_maze_tool_dynamic.zip"
WEBUI_ZIP = RUNS_DIR / "phase16_webui_dynamic_mission.zip"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def safe_text(value: str) -> str:
    value = value.replace(str(Path.home()), "~")
    value = re.sub(r'(x-functions-key=)[^\s"]+', r"\1[redacted]", value)
    value = re.sub(r'("MAZE_TOOL_KEY"\s*:\s*")[^"]+(")', r"\1[redacted]\2", value)
    value = re.sub(r'(MAZE_TOOL_KEY[=:]\s*)[^\s,}]+', r"\1[redacted]", value)
    value = re.sub(r'(sig=)[^"&\s]+', r"\1[redacted]", value)
    value = re.sub(r'("value"\s*:\s*")[^"]{20,}(")', r'\1[redacted]\2', value)
    return value.strip()


def run_command(args: list[str], cwd: Path = PROJECT_ROOT, timeout: int = 300) -> dict[str, Any]:
    try:
        completed = subprocess.run(args, cwd=cwd, check=False, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return {"command": args[:1], "returncode": 127, "stdout": "", "stderr": f"{args[0]} not found"}
    except subprocess.TimeoutExpired as exc:
        return {"command": args, "returncode": 124, "stdout": safe_text(exc.stdout or ""), "stderr": "timed out"}
    return {
        "command": redact_command(args),
        "returncode": completed.returncode,
        "stdout": safe_text(completed.stdout),
        "stderr": safe_text(completed.stderr),
    }


def redact_command(args: list[str]) -> list[str]:
    redacted: list[str] = []
    for arg in args:
        if "sig=" in arg:
            redacted.append(re.sub(r'(sig=)[^&]+', r"\1[redacted]", arg))
        else:
            redacted.append(arg)
    return redacted


def summarize(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "returncode": result["returncode"],
        "stdout_tail": safe_text(result.get("stdout", ""))[-1600:],
        "stderr_tail": safe_text(result.get("stderr", ""))[-1600:],
        "command": result["command"],
    }


def parse_json(result: dict[str, Any]) -> dict[str, Any]:
    if result["returncode"] != 0 or not result.get("stdout"):
        return {}
    try:
        payload = json.loads(result["stdout"])
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {"value": payload}


def zip_dir(root: Path, destination: Path) -> dict[str, Any]:
    if destination.exists():
        destination.unlink()
    excluded_parts = {".git", ".python_packages", "__pycache__", ".venv", "venv"}
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in root.rglob("*"):
            if path.is_dir() or path.suffix == ".pyc":
                continue
            rel = path.relative_to(root)
            if any(part in excluded_parts for part in rel.parts):
                continue
            archive.write(path, rel.as_posix())
    return {"path": str(destination.relative_to(PROJECT_ROOT)), "bytes": destination.stat().st_size}


def deploy_zip(app_name: str, zip_path: Path, apply: bool) -> dict[str, Any]:
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
            app_name,
            "--src",
            str(zip_path),
        ],
        timeout=900,
    )
    return {"attempted": True, "status": "deployed" if result["returncode"] == 0 else "action_required", "command": summarize(result)}


def fetch_openapi() -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        with urllib.request.urlopen(OPENAPI_URL, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload, {"status_code": int(response.status), "url": OPENAPI_URL}
    except Exception as exc:
        return {}, {"status_code": 0, "url": OPENAPI_URL, "error": str(exc)}


def write_toolbox_file(openapi_spec: dict[str, Any]) -> Path:
    toolbox = {
        "description": "Dynamic Maze Tool OpenAPI toolbox for per-run Analyst-generated layouts.",
        "tools": [
            {
                "type": "openapi",
                "name": OPENAPI_TOOL_NAME,
                "openapi": {
                    "name": OPENAPI_TOOL_NAME,
                    "spec": openapi_spec,
                    "auth": {
                        "type": "project_connection",
                        "security_scheme": {"project_connection_id": CONNECTION_NAME},
                    },
                },
            }
        ],
    }
    path = TOOLBOX_DIR / "maze_toolbox_dynamic.json"
    write_text(path, json.dumps(toolbox, indent=2) + "\n")
    return path


def show_toolbox(name: str) -> dict[str, Any]:
    result = run_command(
        ["azd", "ai", "toolbox", "show", name, "--project-endpoint", PROJECT_ENDPOINT, "--output", "json"],
        cwd=HOSTED_ROOT,
        timeout=300,
    )
    return {"exists": result["returncode"] == 0, "command": summarize(result), "payload": parse_json(result)}


def create_toolbox(toolbox_file: Path, apply: bool) -> dict[str, Any]:
    existing = show_toolbox(TOOLBOX_NAME)
    if existing["exists"]:
        return {"attempted": False, "status": "reused", "name": TOOLBOX_NAME, "show": existing}
    if not apply:
        return {"attempted": False, "status": "planned", "name": TOOLBOX_NAME}
    result = run_command(
        ["azd", "ai", "toolbox", "create", TOOLBOX_NAME, "--from-file", str(toolbox_file), "--project-endpoint", PROJECT_ENDPOINT, "--output", "json"],
        cwd=HOSTED_ROOT,
        timeout=300,
    )
    after = show_toolbox(TOOLBOX_NAME)
    return {"attempted": True, "status": "created" if result["returncode"] == 0 and after["exists"] else "action_required", "name": TOOLBOX_NAME, "create": summarize(result), "show": after}


def extract_mcp_endpoint(toolbox: dict[str, Any]) -> str:
    payload = toolbox.get("show", {}).get("payload", {}) if toolbox else {}
    for key in ("mcp_endpoint", "mcpEndpoint", "endpoint", "runtime_mcp_endpoint"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    match = re.search(r"https://[^\" ]+/mcp[^\" ]*", json.dumps(payload))
    return match.group(0) if match else ""


def configure_agent_env(endpoint: str, apply: bool) -> dict[str, Any]:
    if not apply:
        return {"attempted": False, "status": "planned"}
    result = run_command(["azd", "env", "set", "MAZE_TOOL_MCP_ENDPOINT", endpoint], cwd=HOSTED_ROOT, timeout=300)
    return {"attempted": True, "status": "configured" if result["returncode"] == 0 else "action_required", "command": summarize(result)}


def deploy_role_agents(apply: bool) -> dict[str, Any]:
    deployments: dict[str, Any] = {}
    if not apply:
        return {name: {"attempted": False, "status": "planned"} for name in ROLE_AGENTS}
    for name in ROLE_AGENTS:
        deploy = run_command(["azd", "deploy", name, "--no-prompt", "--timeout", "1200"], cwd=HOSTED_ROOT, timeout=1500)
        deployments[name] = {"status": "deployed" if deploy["returncode"] == 0 else "action_required", "deploy": summarize(deploy)}
    return deployments


def post_json(url: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=1200) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body[:1600]}
        return int(exc.code), parsed


def health(url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            return {"status_code": int(response.status), "body": response.read().decode("utf-8", errors="replace")[:300]}
    except Exception as exc:
        return {"status_code": 0, "error": str(exc)}


def validate_live(apply: bool) -> dict[str, Any]:
    if not apply:
        return {"attempted": False, "status": "planned"}
    status_code, payload = post_json(f"{WEBUI_BASE_URL}/api/run", {})
    trace = payload.get("trace") or {}
    summary = trace.get("summary") or {}
    mazes = trace.get("mazes") if isinstance(trace.get("mazes"), list) else []
    rows_by_maze = {maze.get("id"): maze.get("rows") for maze in mazes if isinstance(maze, dict)}
    sample_a = ["S..#.", "##.#.", ".....", ".###.", "....G"]
    sample_b = ["S.#..", "..#..", "#....", ".###.", "....G"]
    return {
        "attempted": True,
        "status_code": status_code,
        "source": payload.get("source"),
        "phase": trace.get("phase"),
        "concept": trace.get("concept"),
        "llm_calls": summary.get("llm_call_budget_used"),
        "foundry_toolbox_mcp_calls": summary.get("foundry_toolbox_mcp_calls"),
        "direct_http_tool_calls": summary.get("direct_http_tool_calls"),
        "dynamic_maze_generation": summary.get("dynamic_maze_generation"),
        "worker_a_goal_reached": summary.get("worker_a_goal_reached"),
        "worker_b_goal_reached": summary.get("worker_b_goal_reached"),
        "worker_a_outcome": summary.get("worker_a_outcome"),
        "worker_b_outcome": summary.get("worker_b_outcome"),
        "worker_invalid_moves": summary.get("worker_invalid_moves"),
        "worker_side_path_rescue": summary.get("worker_side_path_rescue"),
        "guardrail_corrections": summary.get("guardrail_corrections"),
        "maze_a_rows": rows_by_maze.get("maze_a"),
        "maze_b_rows": rows_by_maze.get("maze_b"),
        "passed": (
            status_code == 200
            and payload.get("source") == "foundry-split-role-agents"
            and trace.get("phase") == 16
            and summary.get("dynamic_maze_generation") is True
            and rows_by_maze.get("maze_a") not in (None, sample_a)
            and rows_by_maze.get("maze_b") not in (None, sample_b)
            and summary.get("worker_side_path_rescue") is False
            and int(summary.get("guardrail_corrections") or 0) == 0
            and summary.get("worker_a_outcome") in {"goal_reached", "reported_impossible", "reported_stuck", "budget_exhausted"}
            and summary.get("worker_b_outcome") in {"goal_reached", "reported_impossible", "reported_stuck", "budget_exhausted"}
        ),
    }


def build_report(apply: bool) -> dict[str, Any]:
    tool_package = zip_dir(TOOL_ROOT, TOOL_ZIP)
    webui_package = zip_dir(WEBUI_ROOT, WEBUI_ZIP)
    compile_tool = run_command(["python3", "-m", "py_compile", "tools/phase10-maze-tool-function/maze_common.py"], timeout=120)
    compile_hosted = run_command(["python3", "-m", "py_compile", "hosted/phase13-split-role-agents/main.py", "hosted/phase13-split-role-agents/src/maze_tool_boundary.py"], timeout=120)
    compile_webui = run_command(["python3", "-m", "py_compile", "webui/phase8-azure-webui/function_app.py"], timeout=120)
    deploy_tool = deploy_zip(TOOL_FUNCTION_APP, TOOL_ZIP, apply)
    openapi_spec, openapi_validation = fetch_openapi() if deploy_tool.get("status") in {"deployed", "planned"} else ({}, {"status_code": 0, "error": "blocked by tool deploy"})
    toolbox_file = write_toolbox_file(openapi_spec) if openapi_spec else TOOLBOX_DIR / "maze_toolbox_dynamic.json"
    toolbox = create_toolbox(toolbox_file, apply) if openapi_spec else {"attempted": False, "status": "blocked_by_openapi"}
    endpoint = extract_mcp_endpoint(toolbox)
    env = configure_agent_env(endpoint, apply) if endpoint else {"attempted": apply, "status": "action_required" if apply else "planned", "error": "MCP endpoint unavailable"}
    role_deployments = deploy_role_agents(apply) if env.get("status") in {"configured", "planned"} else {}
    deploy_webui = deploy_zip(WEBUI_FUNCTION_APP, WEBUI_ZIP, apply)
    webui_restart = run_command(["az", "functionapp", "restart", "--resource-group", RESOURCE_GROUP, "--name", WEBUI_FUNCTION_APP], timeout=180) if apply and deploy_webui.get("status") == "deployed" else {"returncode": 0, "stdout": "", "stderr": "", "command": []}
    live = validate_live(apply) if deploy_webui.get("status") in {"deployed", "planned"} else {"attempted": apply, "status": "blocked_by_webui_deploy", "passed": False}
    passed = all(item["returncode"] == 0 for item in (compile_tool, compile_hosted, compile_webui)) and (not apply or live.get("passed"))
    return {
        "course": "Azure Foundry Maze Migration From Scratch",
        "phase": 16,
        "phase_name": "Dynamic Mission Design",
        "status": "complete" if passed else "action_required",
        "mode": "apply" if apply else "plan",
        "learning_objective": "Make the Analyst use LLM reasoning for per-run mission design while Workers solve Analyst-generated mazes from Team Memory.",
        "architecture": {
            "before": "Analyst assigned fixed Maze A and Maze B layouts that Workers repeatedly solved.",
            "after": "Analyst creates fresh maze layouts, stores rows in durable Team Memory, and assigns each Worker without route steps or solvability claims.",
            "tool_contract": "Maze Tool accepts optional rows so validation uses the Analyst-generated layout.",
            "orchestrator": "WebUI coordinator remains deterministic and only dispatches role-agent calls.",
        },
        "packages": {"tool": tool_package, "webui": webui_package},
        "compile": {"tool": summarize(compile_tool), "hosted": summarize(compile_hosted), "webui": summarize(compile_webui)},
        "deploy_tool": deploy_tool,
        "openapi_validation": openapi_validation,
        "toolbox": toolbox,
        "agent_env": env,
        "role_deployments": role_deployments,
        "deploy_webui": deploy_webui,
        "webui_restart": summarize(webui_restart),
        "live_validation": live,
        "summary": {
            "dynamic_maze_generation": live.get("dynamic_maze_generation") if apply else "planned",
            "worker_a_goal_reached": live.get("worker_a_goal_reached") if apply else "planned",
            "worker_b_goal_reached": live.get("worker_b_goal_reached") if apply else "planned",
            "worker_a_outcome": live.get("worker_a_outcome") if apply else "planned",
            "worker_b_outcome": live.get("worker_b_outcome") if apply else "planned",
            "worker_side_path_rescue": live.get("worker_side_path_rescue") if apply else "planned",
            "llm_calls": live.get("llm_calls") if apply else "planned",
            "new_compute_resources": 0,
            "new_storage_accounts": 0,
            "new_toolbox": TOOLBOX_NAME,
            "next_phase": "Agent Quality Telemetry can now monitor dynamic task quality instead of a repeated fixed maze.",
        },
    }


def render_visual(report: dict[str, Any]) -> str:
    live = report["live_validation"]
    maze_a = live.get("maze_a_rows") or []
    maze_b = live.get("maze_b_rows") or []
    maze_a_text = "<br>".join(html.escape(str(row)) for row in maze_a) or "planned"
    maze_b_text = "<br>".join(html.escape(str(row)) for row in maze_b) or "planned"
    escaped = html.escape(json.dumps(report, indent=2, default=str))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Azure Foundry Maze Migration - Phase 16</title>
  <style>
    body {{ margin:0; font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:#f7f8fa; color:#17202a; line-height:1.5; }}
    main {{ width:min(1180px,calc(100% - 32px)); margin:0 auto; padding:32px 0 48px; }}
    header {{ display:grid; grid-template-columns:minmax(0,1fr) 300px; gap:18px; border-bottom:1px solid #d9dee7; padding-bottom:20px; margin-bottom:20px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(30px,4vw,44px); line-height:1.08; }}
    h2 {{ margin:0 0 12px; font-size:20px; }}
    p {{ margin:0; color:#5f6b7a; }}
    .panel,.metric,.node {{ background:#fff; border:1px solid #d9dee7; border-radius:8px; box-shadow:0 10px 28px rgba(28,36,48,.08); padding:16px; }}
    .metric strong {{ display:block; font-size:28px; }}
    .diagram,.mazes {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; align-items:start; }}
    .mazes {{ grid-template-columns:repeat(2,minmax(0,1fr)); margin-top:14px; }}
    .node strong {{ display:block; font-size:17px; }}
    .node span {{ color:#5f6b7a; font-weight:800; font-size:12px; text-transform:uppercase; }}
    .agent {{ border-left:5px solid #285da8; }}
    .memory {{ border-left:5px solid #9a6500; }}
    .tool {{ border-left:5px solid #1f6f5b; }}
    code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }}
    pre {{ white-space:pre-wrap; background:#111827; color:#e5e7eb; border-radius:8px; padding:14px; overflow:auto; }}
    @media (max-width:900px) {{ header,.diagram,.mazes {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <div><h1>Phase 16 - Dynamic Mission Design</h1><p>{html.escape(report['learning_objective'])}</p></div>
    <aside class="metric"><span>Status</span><strong>{html.escape(report['status'])}</strong><p>Mode: {html.escape(report['mode'])}</p></aside>
  </header>
  <section class="diagram">
    <article class="node agent"><span>Analyst</span><strong>Generate mission</strong><p>Creates fresh wall layouts and assigns mazes without route steps or solvability claims.</p></article>
    <article class="node memory"><span>Team Memory</span><strong>Persist layouts</strong><p>Stores maze rows, profiles, assignments, and worker results by run id.</p></article>
    <article class="node tool"><span>Maze Tool</span><strong>Validate dynamic rows</strong><p>Inspect and move calls validate against rows supplied with the request.</p></article>
  </section>
  <section class="mazes">
    <article class="panel"><h2>Live Maze A</h2><p><code>{maze_a_text}</code></p></article>
    <article class="panel"><h2>Live Maze B</h2><p><code>{maze_b_text}</code></p></article>
  </section>
  <section class="panel" style="margin-top:14px">
    <h2>Validation</h2>
    <p>LLM calls: {html.escape(str(live.get('llm_calls')))}. Worker A outcome: {html.escape(str(live.get('worker_a_outcome')))}. Worker B outcome: {html.escape(str(live.get('worker_b_outcome')))}. Hidden path rescue: {html.escape(str(live.get('worker_side_path_rescue')))}.</p>
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
    return """# Phase 16 - Dynamic Mission Design

## Objective

Make the Analyst do meaningful mission design instead of assigning the same
fixed mazes every run.

## What Changed

Before:

```text
Analyst -> assign fixed Maze A to Worker A, fixed Maze B to Worker B
Workers -> solve the same layouts each run
```

After:

```text
Analyst -> generate fresh maze rows
Analyst -> store maze rows and task profiles in Team Memory
Workers -> read assigned rows from Team Memory
Workers -> solve or report blocked/impossible through their own reasoning
```

## Analyst Intelligence Added

The Analyst now contributes useful reasoning at the mission-design level:

```text
create varied per-run tasks
decide wall counts and mission framing
avoid handing Workers a known route
avoid claiming the generated maze is solvable
publish only layouts/profiles/assignments, not step-by-step moves
explain why the generated work is suitable for the learning objective
```

The platform validates only the grid shape and legal moves. It does not solve
the Worker path or rescue Worker decisions with a deterministic shortest path.
If a generated maze is impossible, the Worker should discover and report that.
"""


def render_validation(report: dict[str, Any]) -> str:
    live = report["live_validation"]
    return f"""# Phase 16 Validation

## Expected Result

```text
Analyst produces dynamic Maze A and Maze B rows without pre-solving them.
Team Memory stores maze.maze_a.rows and maze.maze_b.rows.
Workers solve those rows or report blocked/impossible instead of package-fixed mazes.
Maze Tool validates inspect/move against request-provided rows.
WebUI renders the generated layouts.
```

## Live Result

```text
status: {report['status']}
source: {live.get('source')}
phase: {live.get('phase')}
concept: {live.get('concept')}
dynamic_maze_generation: {live.get('dynamic_maze_generation')}
worker_a_goal_reached: {live.get('worker_a_goal_reached')}
worker_b_goal_reached: {live.get('worker_b_goal_reached')}
worker_a_outcome: {live.get('worker_a_outcome')}
worker_b_outcome: {live.get('worker_b_outcome')}
worker_invalid_moves: {live.get('worker_invalid_moves')}
worker_side_path_rescue: {live.get('worker_side_path_rescue')}
llm_calls: {live.get('llm_calls')}
foundry_toolbox_mcp_calls: {live.get('foundry_toolbox_mcp_calls')}
guardrail_corrections: {live.get('guardrail_corrections')}
maze_a_rows: {live.get('maze_a_rows')}
maze_b_rows: {live.get('maze_b_rows')}
```
"""


def refresh_progress(report: dict[str, Any]) -> None:
    existing = PROGRESS_PATH.read_text(encoding="utf-8") if PROGRESS_PATH.exists() else ""
    phase15 = '<section class="card"><h2>Phase 15: Monitoring Consolidation</h2><p>Status: complete. Shared App Insights: maze-webui-func-prav-ada483. Storage changes: 0.</p><p><a href="visuals/PHASE15_VISUAL.html">Open visual</a> | <a href="PHASE15_MONITORING_CONSOLIDATION.md">Notes</a> | <a href="PHASE15_VALIDATION.md">Validation</a></p></section>'
    phase16 = f'<section class="card current"><h2>Phase 16: Dynamic Mission Design</h2><p>Status: {html.escape(report["status"])}. Analyst-generated mazes: {html.escape(str(report["summary"]["dynamic_maze_generation"]))}. Storage changes: 0.</p><p><a href="visuals/PHASE16_VISUAL.html">Open visual</a> | <a href="PHASE16_DYNAMIC_MISSION_DESIGN.md">Notes</a> | <a href="PHASE16_VALIDATION.md">Validation</a></p></section>'
    if "Phase 16: Dynamic Mission Design" in existing:
        updated = re.sub(r'<section class="card(?: current)?"><h2>Phase 16: Dynamic Mission Design.*?</section>', phase16, existing, flags=re.S)
    else:
        updated = re.sub(r'<section class="card(?: current)?"><h2>Phase 15:.*?</section>', phase15 + phase16, existing, flags=re.S)
    updated = re.sub(r'<section class="card(?: current)?"><h2>Phase 15:.*?</section>', phase15, updated, flags=re.S)
    updated = re.sub(
        r"<section class=\"card\"><h2>Next</h2>.*?</section>",
        '<section class="card"><h2>Next</h2><p>Add Agent Quality Telemetry for plan quality, path quality, memory freshness, and LLM budget.</p></section>',
        updated,
        flags=re.S,
    )
    write_text(PROGRESS_PATH, updated)


def write_artifacts(report: dict[str, Any]) -> None:
    write_text(RUNS_DIR / "phase16_dynamic_mission_design.json", json.dumps(report, indent=2, default=str) + "\n")
    write_text(VISUALS_DIR / "PHASE16_VISUAL.html", render_visual(report))
    write_text(PROJECT_ROOT / "PHASE16_DYNAMIC_MISSION_DESIGN.md", render_notes(report))
    write_text(PROJECT_ROOT / "PHASE16_VALIDATION.md", render_validation(report))
    refresh_progress(report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy and validate Phase 16 dynamic mission design.")
    parser.add_argument("--apply", action="store_true", help="Deploy Azure components and run a live dynamic mission.")
    args = parser.parse_args()
    report = build_report(args.apply)
    write_artifacts(report)
    print(
        json.dumps(
            {
                "phase": report["phase"],
                "status": report["status"],
                "mode": report["mode"],
                "summary": report["summary"],
                "live_validation": report["live_validation"],
            },
            indent=2,
        )
    )
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
