#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOSTED_ROOT = PROJECT_ROOT / "hosted" / "phase7-monolithic-maze-agent"
RUNS_DIR = PROJECT_ROOT / "runs"
VISUALS_DIR = PROJECT_ROOT / "visuals"
PROGRESS_PATH = PROJECT_ROOT / "PROGRESS.html"

PROJECT_ENDPOINT = "https://maze-foundry-prav-ada483.services.ai.azure.com/api/projects/maze-migration-lab"
TOOLBOX_NAME = "maze-toolbox"
WEBUI_FUNCTION_APP_NAME = "maze-webui-func-prav-ada483"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def safe_text(value: str) -> str:
    value = value.replace(str(Path.home()), "~")
    value = re.sub(r'("MAZE_TOOL_KEY"\s*:\s*")[^"]+(")', r"\1[redacted]\2", value)
    value = re.sub(r'(MAZE_TOOL_KEY[=:]\s*)[^\s,}]+', r"\1[redacted]", value)
    value = re.sub(r'(x-functions-key=)[^\s"]+', r"\1[redacted]", value)
    value = re.sub(r'(sig=)[^"&\s]+', r"\1[redacted]", value)
    return value.strip()


def safe_command(args: list[str]) -> list[str]:
    safe: list[str] = []
    hide_next = False
    for arg in args:
        if hide_next:
            safe.append("[redacted]")
            hide_next = False
            continue
        safe.append(arg)
        if arg in {"--custom-key", "--key", "--client-secret", "MAZE_TOOL_KEY"}:
            hide_next = True
    return safe


def run_command(args: list[str], cwd: Path, timeout: int = 300, redact_stdout: bool = False) -> dict[str, Any]:
    try:
        completed = subprocess.run(args, cwd=cwd, check=False, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return {"command": args[:1], "returncode": 127, "stdout": "", "stderr": f"{args[0]} not found"}
    except subprocess.TimeoutExpired as exc:
        return {"command": safe_command(args), "returncode": 124, "stdout": safe_text(exc.stdout or ""), "stderr": "timed out"}
    return {
        "command": safe_command(args),
        "returncode": completed.returncode,
        "stdout": "[redacted]" if redact_stdout and completed.stdout else safe_text(completed.stdout),
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
    return endpoint, {"command": summarize(result), "endpoint_found": bool(endpoint)}


def configure_hosted_agent_env(endpoint: str) -> dict[str, Any]:
    set_mcp = run_command(["azd", "env", "set", "MAZE_TOOL_MCP_ENDPOINT", endpoint], HOSTED_ROOT, timeout=300)
    return {
        "status": "configured" if set_mcp["returncode"] == 0 else "action_required",
        "maze_tool_mcp_endpoint": endpoint,
        "set_mcp": summarize(set_mcp),
    }


def deploy_hosted_agent() -> dict[str, Any]:
    deploy = run_command(["azd", "deploy", "maze-monolithic-agent", "--no-prompt", "--timeout", "1200"], HOSTED_ROOT, timeout=1500)
    show = run_command(["azd", "ai", "agent", "show", "maze-monolithic-agent", "--output", "json"], HOSTED_ROOT, timeout=300)
    agent_status = parse_json_result(show)
    return {
        "deploy": summarize(deploy),
        "show": summarize(show),
        "active_version": agent_status.get("version"),
        "status": "deployed" if deploy["returncode"] == 0 and agent_status.get("status") == "active" else "action_required",
    }


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


def validate_live_webui() -> dict[str, Any]:
    status, payload = post_json(f"https://{WEBUI_FUNCTION_APP_NAME}.azurewebsites.net/api/run", {})
    trace = payload.get("trace") or {}
    summary = trace.get("summary") or {}
    events = trace.get("events") or []
    return {
        "status_code": status,
        "source": payload.get("source"),
        "error": safe_text(str(payload.get("error", "")))[:1600] if payload.get("error") else "",
        "provider": (trace.get("provider") or {}).get("provider"),
        "model": (trace.get("provider") or {}).get("model"),
        "llm_calls": summary.get("llm_call_budget_used"),
        "maze_tool_boundary": summary.get("maze_tool_boundary_name"),
        "maze_tool_boundary_location": summary.get("maze_tool_boundary_location"),
        "external_maze_tool_calls": summary.get("external_maze_tool_calls"),
        "foundry_toolbox_mcp_calls": summary.get("foundry_toolbox_mcp_calls"),
        "direct_http_tool_calls": summary.get("direct_http_tool_calls"),
        "mcp_event_count": sum(1 for event in events if event.get("tool_runtime") == "foundry-toolbox-mcp"),
        "direct_http_event_count": sum(1 for event in events if event.get("tool_runtime") == "external-http"),
        "events": len(events),
        "passed": (
            status == 200
            and payload.get("source") == "foundry-hosted-agent"
            and summary.get("foundry_toolbox_mcp_calls", 0) > 0
            and summary.get("direct_http_tool_calls", 0) == 0
        ),
    }


def build_report(apply: bool) -> dict[str, Any]:
    endpoint, toolbox = toolbox_endpoint()
    env = {"attempted": False, "status": "planned"}
    deployment = {"attempted": False, "status": "planned"}
    live = {"attempted": False, "passed": False}
    if apply and endpoint:
        env = configure_hosted_agent_env(endpoint)
        deployment = deploy_hosted_agent()
        live = validate_live_webui()
    elif apply:
        env = {"attempted": True, "status": "action_required", "error": "Toolbox MCP endpoint not found"}

    passed = bool(endpoint) and (not apply or (env.get("status") == "configured" and deployment.get("status") == "deployed" and live.get("passed")))
    return {
        "course": "Azure Foundry Maze Migration From Scratch",
        "phase": 12,
        "phase_name": "PydanticAI Runtime Uses Foundry Toolbox MCP",
        "status": "complete" if passed else "action_required",
        "mode": "apply" if apply else "plan",
        "learning_objective": "Switch the hosted PydanticAI maze runtime from direct HTTP tool calls to the Foundry toolbox MCP endpoint.",
        "architecture": {
            "before": "PydanticAI hosted agent -> ExternalMazeToolProgram -> Azure Function Maze Tool",
            "after": "PydanticAI hosted agent -> Foundry toolbox MCP endpoint -> OpenAPI wrapper -> Azure Function Maze Tool",
            "fallback_order": "MAZE_TOOL_MCP_ENDPOINT, then MAZE_TOOL_BASE_URL, then in-process MazeToolProgram",
        },
        "toolbox": {
            "name": TOOLBOX_NAME,
            "project_endpoint": PROJECT_ENDPOINT,
            "mcp_endpoint": endpoint,
            "lookup": toolbox,
        },
        "hosted_agent_environment": env,
        "hosted_agent_deployment": deployment,
        "live_webui_validation": live,
        "summary": {
            "foundry_toolbox_mcp_runtime_enabled": bool(live.get("foundry_toolbox_mcp_calls", 0) if apply else endpoint),
            "foundry_toolbox_mcp_calls_observed": live.get("foundry_toolbox_mcp_calls") or live.get("mcp_event_count") or 0,
            "direct_http_tool_calls_observed": live.get("direct_http_tool_calls") or live.get("direct_http_event_count") or 0,
            "llm_calls_observed": live.get("llm_calls") or 0,
            "new_azure_compute_resources": 0,
            "new_foundry_toolboxes": 0,
            "new_runtime_dependency": "pydantic-ai-slim[mcp]",
            "next_phase": "Remove the legacy direct HTTP fallback or keep it as a resilience fallback after comparing observability and failure behavior.",
        },
    }


def table_rows(mapping: dict[str, Any]) -> str:
    rows = []
    for key, value in mapping.items():
        rendered = json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value)
        rows.append(f"<tr><td>{html.escape(key.replace('_', ' ').title())}</td><td>{html.escape(rendered)}</td></tr>")
    return "".join(rows)


def render_phase_html(report: dict[str, Any]) -> str:
    summary = report["summary"]
    data = html.escape(json.dumps(report, indent=2, default=str))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Azure Foundry Maze Migration - Phase 12</title>
  <style>
    :root {{ --bg:#f7f8fa; --panel:#fff; --text:#17202a; --muted:#5f6b7a; --line:#d9dee7; --blue:#285da8; --green:#1f6f5b; --amber:#9a6500; --shadow:0 10px 28px rgba(28,36,48,.08); }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--text); background:var(--bg); line-height:1.5; }}
    main {{ width:min(1180px,calc(100% - 32px)); margin:0 auto; padding:32px 0 48px; }}
    header {{ display:grid; grid-template-columns:minmax(0,1fr) 340px; gap:20px; border-bottom:1px solid var(--line); padding-bottom:20px; margin-bottom:22px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(28px,4vw,42px); line-height:1.08; }}
    h2 {{ margin:0 0 12px; font-size:20px; }}
    h3 {{ margin:0 0 8px; font-size:16px; }}
    p {{ margin:0; color:var(--muted); }}
    .panel,.summary,.step,.metric {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; box-shadow:var(--shadow); padding:16px; }}
    .summary strong {{ display:block; font-size:26px; text-transform:capitalize; }}
    .stack {{ display:grid; gap:14px; }}
    .metrics {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }}
    .metric {{ box-shadow:none; }}
    .metric span,.step span {{ display:block; color:var(--muted); font-size:12px; font-weight:800; text-transform:uppercase; }}
    .metric strong {{ display:block; margin-top:6px; font-size:26px; }}
    .flow {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; }}
    .step {{ box-shadow:none; min-height:150px; border-left:5px solid var(--blue); }}
    .step.tool {{ border-left-color:var(--green); background:#eef8f3; }}
    .step.note {{ border-left-color:var(--amber); background:#fff8e7; }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th,td {{ padding:9px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-size:12px; text-transform:uppercase; }}
    code {{ color:#111827; background:#eef2f7; padding:2px 5px; border-radius:4px; }}
    pre {{ overflow:auto; max-height:420px; padding:12px; background:#111827; color:#e5e7eb; border-radius:8px; font-size:12px; }}
    @media (max-width:980px) {{ header,.metrics,.flow {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Phase 12 - PydanticAI Runtime Uses Foundry Toolbox MCP</h1>
        <p>{html.escape(report['learning_objective'])}</p>
      </div>
      <aside class="summary">
        <span>Status</span>
        <strong>{html.escape(report['status'].replace('_', ' '))}</strong>
        <p>MCP calls observed: {summary['foundry_toolbox_mcp_calls_observed']}.</p>
      </aside>
    </header>
    <div class="stack">
      <section class="panel">
        <h2>Phase Metrics</h2>
        <div class="metrics">
          <div class="metric"><span>MCP Tool Calls</span><strong>{summary['foundry_toolbox_mcp_calls_observed']}</strong></div>
          <div class="metric"><span>Direct HTTP Calls</span><strong>{summary['direct_http_tool_calls_observed']}</strong></div>
          <div class="metric"><span>LLM Calls</span><strong>{summary['llm_calls_observed']}</strong></div>
          <div class="metric"><span>New Compute</span><strong>{summary['new_azure_compute_resources']}</strong></div>
        </div>
      </section>
      <section class="panel">
        <h2>Runtime Flow</h2>
        <div class="flow">
          <article class="step"><span>1. PydanticAI</span><h3>Hosted agent code</h3><p>The agent still owns orchestration, worker logic, and trace generation.</p></article>
          <article class="step tool"><span>2. Foundry MCP</span><h3>Toolbox endpoint</h3><p>The Maze Tool boundary now calls <code>maze-toolbox</code> over MCP.</p></article>
          <article class="step tool"><span>3. OpenAPI wrapper</span><h3>Foundry tool</h3><p>Foundry maps MCP tool calls to <code>inspectMaze</code> and <code>moveInMaze</code>.</p></article>
          <article class="step note"><span>4. Azure Function</span><h3>Implementation</h3><p>The deterministic Maze Tool code still runs as the Phase 10 Function App.</p></article>
        </div>
      </section>
      <section class="panel"><h2>Architecture</h2><table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{table_rows(report['architecture'])}</tbody></table></section>
      <section class="panel"><h2>Toolbox</h2><table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{table_rows({'name': report['toolbox']['name'], 'endpoint_present': bool(report['toolbox']['mcp_endpoint']), 'project_endpoint': report['toolbox']['project_endpoint']})}</tbody></table></section>
      <section class="panel"><h2>Live WebUI Validation</h2><table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{table_rows(report['live_webui_validation'])}</tbody></table></section>
      <section class="panel"><h2>Report JSON</h2><details><summary>Open generated report</summary><pre>{data}</pre></details></section>
    </div>
  </main>
</body>
</html>
"""


def render_progress_html(report: dict[str, Any]) -> str:
    phase_files = [
        ("Phase 1: Portability Inventory", RUNS_DIR / "phase1_inventory.json", "visuals/PHASE1_VISUAL.html", "PHASE1_PORTABILITY_INVENTORY.md", "PHASE1_VALIDATION.md"),
        ("Phase 2: Public Repo and Secret Hygiene", RUNS_DIR / "phase2_public_repo_hygiene.json", "visuals/PHASE2_VISUAL.html", "PHASE2_PUBLIC_REPO_HYGIENE.md", "PHASE2_VALIDATION.md"),
        ("Phase 3: Azure Login and Subscription Readiness", RUNS_DIR / "phase3_azure_login_readiness.json", "visuals/PHASE3_VISUAL.html", "PHASE3_AZURE_LOGIN_READINESS.md", "PHASE3_VALIDATION.md"),
        ("Phase 4: Foundry Project and Model Deployment", RUNS_DIR / "phase4_foundry_project_model.json", "visuals/PHASE4_VISUAL.html", "PHASE4_FOUNDRY_PROJECT_MODEL.md", "PHASE4_VALIDATION.md"),
        ("Phase 5: Model Provider Adapter", RUNS_DIR / "phase5_model_provider_adapter.json", "visuals/PHASE5_VISUAL.html", "PHASE5_MODEL_PROVIDER_ADAPTER.md", "PHASE5_VALIDATION.md"),
        ("Phase 6: Pydantic AI Analyst Agent on Foundry Model", RUNS_DIR / "phase6_foundry_analyst_agent.json", "visuals/PHASE6_VISUAL.html", "PHASE6_FOUNDRY_ANALYST_AGENT.md", "PHASE6_VALIDATION.md"),
        ("Phase 7: Monolithic Foundry-Hosted Maze Runtime", RUNS_DIR / "phase7_monolithic_hosted_runtime.json", "visuals/PHASE7_VISUAL.html", "PHASE7_MONOLITHIC_HOSTED_RUNTIME.md", "PHASE7_VALIDATION.md"),
        ("Phase 8: Azure-Hosted WebUI Adapter", RUNS_DIR / "phase8_azure_webui_adapter.json", "visuals/PHASE8_VISUAL.html", "PHASE8_AZURE_WEBUI_ADAPTER.md", "PHASE8_VALIDATION.md"),
        ("Phase 9: Maze Tool Boundary without New Azure Service", RUNS_DIR / "phase9_maze_tool_boundary.json", "visuals/PHASE9_VISUAL.html", "PHASE9_MAZE_TOOL_BOUNDARY.md", "PHASE9_VALIDATION.md"),
        ("Phase 10: External Azure Function Maze Tool", RUNS_DIR / "phase10_external_maze_tool.json", "visuals/PHASE10_VISUAL.html", "PHASE10_EXTERNAL_MAZE_TOOL.md", "PHASE10_VALIDATION.md"),
        ("Phase 11: Foundry-Registered Maze Tool", RUNS_DIR / "phase11_foundry_toolbox_registration.json", "visuals/PHASE11_VISUAL.html", "PHASE11_FOUNDRY_TOOLBOX_REGISTRATION.md", "PHASE11_VALIDATION.md"),
    ]
    cards = []
    for title, path, visual, notes, validation in phase_files:
        item = load_json(path)
        if not item:
            continue
        summary = item.get("summary", {})
        interesting = (
            "foundry_model_calls",
            "hosted_agents_created",
            "azure_webui_deployed",
            "external_maze_tool_created",
            "hosted_agent_uses_external_tool",
            "foundry_toolbox_registered",
        )
        detail = ", ".join(f"{key}: {summary[key]}" for key in interesting if key in summary)
        cards.append(f"""<section class="card"><h2>{html.escape(title)}</h2><p>Status: {html.escape(str(item.get('status')))}. {html.escape(detail)}</p><p><a href="{visual}">Open visual</a> | <a href="{notes}">Notes</a> | <a href="{validation}">Validation</a></p></section>""")
    s = report["summary"]
    cards.append(f"""<section class="card current"><h2>Phase 12: PydanticAI Runtime Uses Foundry Toolbox MCP</h2><p>Status: {html.escape(report['status'])}. MCP calls: {s['foundry_toolbox_mcp_calls_observed']}. Direct HTTP calls: {s['direct_http_tool_calls_observed']}. LLM calls: {s['llm_calls_observed']}.</p><p><a href="visuals/PHASE12_VISUAL.html">Open visual</a> | <a href="PHASE12_FOUNDRY_TOOLBOX_MCP_RUNTIME.md">Notes</a> | <a href="PHASE12_VALIDATION.md">Validation</a></p></section>""")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Azure Foundry Maze Migration - Progress</title><style>body{{margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f7f8fa;color:#17202a}}main{{width:min(960px,calc(100% - 32px));margin:0 auto;padding:32px 0}}.card{{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:16px;margin:12px 0}}.current{{border-left:5px solid #1f6f5b}}a{{color:#285da8;font-weight:800;text-decoration:none}}p{{color:#5f6b7a}}</style></head><body><main><h1>Azure Foundry Maze Migration From Scratch</h1><p>Step-by-step migration of the local multi-agent maze program to Microsoft Foundry-hosted agents and Azure-native tool boundaries.</p><section class="card"><h2>Cost Policy</h2><p>Personal-subscription learning lab: Phase 12 reuses the existing Function App, Foundry toolbox, model, hosted agent, and WebUI.</p></section>{''.join(cards)}<section class="card"><h2>Next</h2><p>{html.escape(s['next_phase'])}</p></section></main></body></html>"""


def write_docs() -> None:
    write_text(PROJECT_ROOT / "PHASE12_FOUNDRY_TOOLBOX_MCP_RUNTIME.md", """# Phase 12 - PydanticAI Runtime Uses Foundry Toolbox MCP

## Objective

Switch the hosted PydanticAI maze runtime from direct HTTP tool calls to the
Foundry toolbox MCP endpoint.

## What Changed

Before:

```text
PydanticAI hosted agent
  -> ExternalMazeToolProgram
  -> Azure Function Maze Tool
```

After:

```text
PydanticAI hosted agent
  -> FoundryToolboxMCPMazeToolProgram
  -> Foundry toolbox MCP endpoint
  -> Foundry OpenAPI wrapper
  -> Azure Function Maze Tool
```

## Why This Matters

Phase 11 made the tool visible in Foundry. Phase 12 makes the runtime consume
that Foundry-managed tool path.

This preserves PydanticAI as the agent framework while using Foundry as the
tool registry, auth holder, and MCP exposure layer.

## Fallback

The runtime still keeps the older direct HTTP path as a fallback if
`MAZE_TOOL_MCP_ENDPOINT` is not configured. The active Azure deployment sets
that variable, so the live WebUI should show `foundry-toolbox-mcp` tool events.
""")
    write_text(PROJECT_ROOT / "PHASE12_VALIDATION.md", """# Phase 12 Validation

## Expected Result

```text
Hosted agent has MAZE_TOOL_MCP_ENDPOINT configured.
Live WebUI /api/run returns source=foundry-hosted-agent.
Trace summary shows foundry_toolbox_mcp_calls > 0.
Trace summary shows direct_http_tool_calls == 0.
Maze tool boundary is FoundryToolboxMCPMazeToolProgram.
```

## Command

```bash
python3 scripts/phase12_foundry_toolbox_mcp_runtime.py --apply
```

## Generated Artifacts

```text
runs/phase12_foundry_toolbox_mcp_runtime.json
visuals/PHASE12_VISUAL.html
PHASE12_FOUNDRY_TOOLBOX_MCP_RUNTIME.md
PHASE12_VALIDATION.md
PROGRESS.html
```
""")


def main() -> int:
    parser = argparse.ArgumentParser(description="Switch hosted PydanticAI runtime to Foundry toolbox MCP Maze Tool calls.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    write_docs()
    report = build_report(apply=args.apply)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    VISUALS_DIR.mkdir(parents=True, exist_ok=True)
    write_text(RUNS_DIR / "phase12_foundry_toolbox_mcp_runtime.json", json.dumps(report, indent=2, default=str) + "\n")
    write_text(VISUALS_DIR / "PHASE12_VISUAL.html", render_phase_html(report))
    write_text(PROGRESS_PATH, render_progress_html(report))
    print(f"phase={report['phase']}")
    print(f"status={report['status']}")
    print(f"mcp_calls={report['summary']['foundry_toolbox_mcp_calls_observed']}")
    print(f"direct_http_calls={report['summary']['direct_http_tool_calls_observed']}")
    print(f"llm_calls={report['summary']['llm_calls_observed']}")
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
