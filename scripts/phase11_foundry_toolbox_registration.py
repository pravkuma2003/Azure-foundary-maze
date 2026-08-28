#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOSTED_ROOT = PROJECT_ROOT / "hosted" / "phase7-monolithic-maze-agent"
RUNS_DIR = PROJECT_ROOT / "runs"
VISUALS_DIR = PROJECT_ROOT / "visuals"
PROGRESS_PATH = PROJECT_ROOT / "PROGRESS.html"
TOOLBOX_DIR = PROJECT_ROOT / "tools" / "phase11-foundry-toolbox"

RESOURCE_GROUP = "rg-maze-foundry-lab"
PROJECT_ENDPOINT = "https://maze-foundry-prav-ada483.services.ai.azure.com/api/projects/maze-migration-lab"
TOOL_FUNCTION_APP_NAME = "maze-tool-func-prav-ada483"
TOOL_BASE_URL = f"https://{TOOL_FUNCTION_APP_NAME}.azurewebsites.net"
OPENAPI_URL = f"{TOOL_BASE_URL}/api/maze/openapi.json"
CONNECTION_NAME = "maze-tool-function-key"
TOOLBOX_NAME = "maze-toolbox"
OPENAPI_TOOL_NAME = "maze_tool_api"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def safe_text(value: str) -> str:
    value = value.replace(str(Path.home()), "~")
    value = re.sub(r'(x-functions-key=)[^\s"]+', r"\1[redacted]", value)
    value = re.sub(r'("key"\s*:\s*")[^"]+(")', r"\1[redacted]\2", value)
    value = re.sub(r'("secret"\s*:\s*")[^"]+(")', r"\1[redacted]\2", value)
    value = re.sub(r'("credential"\s*:\s*")[^"]+(")', r"\1[redacted]\2", value)
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
        safe.append(arg if not arg.startswith("x-functions-key=") else "x-functions-key=[redacted]")
        if arg in {"--custom-key", "--key", "--client-secret"}:
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


def get_function_key() -> tuple[str, dict[str, Any]]:
    command = [
        "az",
        "functionapp",
        "keys",
        "list",
        "--resource-group",
        RESOURCE_GROUP,
        "--name",
        TOOL_FUNCTION_APP_NAME,
        "--query",
        "functionKeys.default",
        "--output",
        "tsv",
    ]
    safe = run_command(command, PROJECT_ROOT, timeout=300, redact_stdout=True)
    actual = subprocess.run(command, cwd=PROJECT_ROOT, check=False, capture_output=True, text=True, timeout=300)
    return actual.stdout.strip(), summarize(safe)


def fetch_openapi_spec() -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        with urllib.request.urlopen(OPENAPI_URL, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload, {"status_code": response.status, "url": OPENAPI_URL, "title": payload.get("info", {}).get("title")}
    except Exception as exc:
        return {}, {"status_code": 0, "url": OPENAPI_URL, "error": str(exc)}


def write_toolbox_file(openapi_spec: dict[str, Any]) -> Path:
    toolbox = {
        "description": "Maze Tool OpenAPI toolbox for the Azure Foundry migration learning lab.",
        "tools": [
            {
                "type": "openapi",
                "name": OPENAPI_TOOL_NAME,
                "openapi": {
                    "name": OPENAPI_TOOL_NAME,
                    "spec": openapi_spec,
                    "auth": {
                        "type": "project_connection",
                        "security_scheme": {
                            "project_connection_id": CONNECTION_NAME,
                        },
                    },
                },
            }
        ],
    }
    path = TOOLBOX_DIR / "maze_toolbox.json"
    write_text(path, json.dumps(toolbox, indent=2) + "\n")
    return path


def create_connection(function_key: str, apply: bool) -> dict[str, Any]:
    if not apply:
        return {"attempted": False, "status": "planned", "name": CONNECTION_NAME}
    result = run_command(
        [
            "azd",
            "ai",
            "connection",
            "create",
            CONNECTION_NAME,
            "--kind",
            "remote-tool",
            "--target",
            TOOL_BASE_URL,
            "--auth-type",
            "custom-keys",
            "--custom-key",
            f"x-functions-key={function_key}",
            "--force",
            "-p",
            PROJECT_ENDPOINT,
            "--output",
            "json",
        ],
        HOSTED_ROOT,
        timeout=300,
    )
    return {
        "attempted": True,
        "status": "created_or_updated" if result["returncode"] == 0 else "action_required",
        "name": CONNECTION_NAME,
        "target": TOOL_BASE_URL,
        "auth": "custom-keys: x-functions-key",
        "command": summarize(result),
    }


def show_toolbox() -> dict[str, Any]:
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
    return {
        "exists": result["returncode"] == 0,
        "command": summarize(result),
        "payload": payload,
    }


def create_toolbox(toolbox_file: Path, apply: bool) -> dict[str, Any]:
    existing = show_toolbox()
    if existing["exists"]:
        return {
            "attempted": False,
            "status": "reused",
            "name": TOOLBOX_NAME,
            "show": existing,
        }
    if not apply:
        return {"attempted": False, "status": "planned", "name": TOOLBOX_NAME}
    result = run_command(
        [
            "azd",
            "ai",
            "toolbox",
            "create",
            TOOLBOX_NAME,
            "--from-file",
            str(toolbox_file),
            "--project-endpoint",
            PROJECT_ENDPOINT,
            "--output",
            "json",
        ],
        HOSTED_ROOT,
        timeout=300,
    )
    after = show_toolbox()
    payload = parse_json_result(result)
    return {
        "attempted": True,
        "status": "created" if result["returncode"] == 0 and after["exists"] else "action_required",
        "name": TOOLBOX_NAME,
        "tool": OPENAPI_TOOL_NAME,
        "create": summarize(result),
        "create_payload": payload,
        "show": after,
    }


def list_toolboxes(apply: bool) -> dict[str, Any]:
    if not apply:
        return {"attempted": False}
    result = run_command(
        [
            "azd",
            "ai",
            "toolbox",
            "list",
            "--project-endpoint",
            PROJECT_ENDPOINT,
            "--output",
            "json",
        ],
        HOSTED_ROOT,
        timeout=300,
    )
    payload = parse_json_result(result)
    toolboxes = payload.get("toolboxes") if isinstance(payload.get("toolboxes"), list) else []
    return {
        "attempted": True,
        "status": "listed" if result["returncode"] == 0 else "action_required",
        "toolbox_names": [item.get("name") for item in toolboxes if isinstance(item, dict)],
        "contains_maze_toolbox": any(item.get("name") == TOOLBOX_NAME for item in toolboxes if isinstance(item, dict)),
        "command": summarize(result),
    }


def extract_mcp_endpoint(toolbox: dict[str, Any]) -> str:
    payload = toolbox.get("show", {}).get("payload", {}) if toolbox else {}
    for key in ("mcp_endpoint", "mcpEndpoint", "endpoint", "runtime_mcp_endpoint"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    text = json.dumps(payload)
    match = re.search(r"https://[^\" ]+/mcp[^\" ]*", text)
    return match.group(0) if match else ""


def build_report(apply: bool) -> dict[str, Any]:
    openapi_spec, openapi_validation = fetch_openapi_spec()
    toolbox_file = write_toolbox_file(openapi_spec) if openapi_spec else TOOLBOX_DIR / "maze_toolbox.json"
    function_key, key_result = get_function_key() if apply else ("", {"attempted": False})
    connection = create_connection(function_key, apply) if function_key or not apply else {
        "attempted": True,
        "status": "action_required",
        "error": "Function key unavailable",
        "function_key": key_result,
    }
    toolbox = create_toolbox(toolbox_file, apply)
    toolbox_list = list_toolboxes(apply)
    mcp_endpoint = extract_mcp_endpoint(toolbox)
    passed = (
        bool(openapi_spec)
        and (not apply or connection.get("status") == "created_or_updated")
        and (not apply or toolbox.get("status") in {"created", "reused"})
        and (not apply or toolbox_list.get("contains_maze_toolbox") is True)
    )
    return {
        "course": "Azure Foundry Maze Migration From Scratch",
        "phase": 11,
        "phase_name": "Foundry-Registered Maze Tool",
        "status": "complete" if passed else "action_required",
        "mode": "apply" if apply else "plan",
        "learning_objective": "Register the external Azure Function Maze Tool as a Foundry-managed OpenAPI tool through a toolbox and project connection.",
        "documentation_basis": {
            "microsoft_learn_openapi_tools": "https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/openapi",
            "toolbox_concept": "OpenAPI tools are embedded under tools[].openapi.spec; project_connection auth references a project connection.",
        },
        "foundry_project": {
            "project_endpoint": PROJECT_ENDPOINT,
            "toolbox_name": TOOLBOX_NAME,
            "openapi_tool_name": OPENAPI_TOOL_NAME,
            "connection_name": CONNECTION_NAME,
            "external_service": TOOL_FUNCTION_APP_NAME,
        },
        "openapi_contract": {
            "source_url": OPENAPI_URL,
            "local_toolbox_file": str(toolbox_file.relative_to(PROJECT_ROOT)),
            "validation": openapi_validation,
            "operation_ids": sorted(
                operation.get("operationId")
                for path in openapi_spec.get("paths", {}).values()
                for operation in path.values()
                if isinstance(operation, dict) and operation.get("operationId")
            ) if openapi_spec else [],
        },
        "function_key": key_result,
        "connection": connection,
        "toolbox": toolbox,
        "toolbox_list": toolbox_list,
        "runtime_usage": {
            "phase10_live_runtime": "Hosted PydanticAI agent still calls the external Maze Tool through ExternalMazeToolProgram.",
            "phase11_registration": "Foundry now has a managed toolbox/tool registration for the same Maze Tool contract.",
            "next_runtime_step": "Switch the PydanticAI runtime from direct HTTP client to the Foundry toolbox MCP endpoint.",
            "mcp_endpoint_observed": bool(mcp_endpoint),
            "mcp_endpoint": mcp_endpoint or "not returned by current CLI output",
        },
        "summary": {
            "foundry_toolbox_registered": toolbox.get("status") in {"created", "reused"},
            "foundry_tool_connection_created": connection.get("status") == "created_or_updated",
            "portal_expected_location": "Foundry project > Tools > Toolboxes tab; the individual OpenAPI tool is inside maze-toolbox.",
            "new_azure_compute_resources": 0,
            "new_toolboxes_created_or_reused": 1 if toolbox.get("status") in {"created", "reused"} else 0,
            "llm_calls_made": 0,
            "external_maze_function_reused": True,
            "next_phase": "Use the Foundry toolbox MCP endpoint from the hosted PydanticAI runtime instead of the direct ExternalMazeToolProgram HTTP client.",
        },
    }


def table_rows(mapping: dict[str, Any]) -> str:
    rows = []
    for key, value in mapping.items():
        rendered = json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value)
        rows.append(f"<tr><td>{html.escape(key.replace('_', ' ').title())}</td><td>{html.escape(rendered)}</td></tr>")
    return "".join(rows)


def render_phase_html(report: dict[str, Any]) -> str:
    data = html.escape(json.dumps(report, indent=2, default=str))
    summary = report["summary"]
    status = report["status"].replace("_", " ")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Azure Foundry Maze Migration - Phase 11</title>
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
        <h1>Phase 11 - Foundry-Registered Maze Tool</h1>
        <p>{html.escape(report['learning_objective'])}</p>
      </div>
      <aside class="summary">
        <span>Status</span>
        <strong>{html.escape(status)}</strong>
        <p>{html.escape(summary['portal_expected_location'])}</p>
      </aside>
    </header>
    <div class="stack">
      <section class="panel">
        <h2>Phase Metrics</h2>
        <div class="metrics">
          <div class="metric"><span>New Compute</span><strong>{summary['new_azure_compute_resources']}</strong></div>
          <div class="metric"><span>Toolboxes</span><strong>{summary['new_toolboxes_created_or_reused']}</strong></div>
          <div class="metric"><span>LLM Calls</span><strong>{summary['llm_calls_made']}</strong></div>
          <div class="metric"><span>Function Reused</span><strong>{'yes' if summary['external_maze_function_reused'] else 'no'}</strong></div>
        </div>
      </section>
      <section class="panel">
        <h2>Foundry Registration Flow</h2>
        <div class="flow">
          <article class="step"><span>1. Azure Function</span><h3>Existing Maze Tool</h3><p>Phase 10 Function remains the external implementation.</p></article>
          <article class="step tool"><span>2. Project Connection</span><h3>Function Key</h3><p>Foundry stores the key as a project connection, outside source and browser code.</p></article>
          <article class="step tool"><span>3. Toolbox</span><h3>OpenAPI Tool</h3><p>The OpenAPI spec is registered as <code>{html.escape(OPENAPI_TOOL_NAME)}</code> inside <code>{html.escape(TOOLBOX_NAME)}</code>.</p></article>
          <article class="step note"><span>4. Runtime</span><h3>Next Boundary</h3><p>PydanticAI still uses direct HTTP today; next phase can consume the toolbox MCP endpoint.</p></article>
        </div>
      </section>
      <section class="panel"><h2>Foundry Project</h2><table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{table_rows(report['foundry_project'])}</tbody></table></section>
      <section class="panel"><h2>OpenAPI Contract</h2><table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{table_rows(report['openapi_contract'])}</tbody></table></section>
      <section class="panel"><h2>Connection</h2><table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{table_rows(report['connection'])}</tbody></table></section>
      <section class="panel"><h2>Toolbox</h2><table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{table_rows({'status': report['toolbox'].get('status'), 'name': report['toolbox'].get('name'), 'tool': report['toolbox'].get('tool'), 'listed_in_project': report['toolbox_list'].get('contains_maze_toolbox'), 'mcp_endpoint_observed': report['runtime_usage'].get('mcp_endpoint_observed')})}</tbody></table></section>
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
            "maze_tool_boundary_extracted",
        )
        detail = ", ".join(f"{key}: {summary[key]}" for key in interesting if key in summary)
        cards.append(f"""<section class="card"><h2>{html.escape(title)}</h2><p>Status: {html.escape(str(item.get('status')))}. {html.escape(detail)}</p><p><a href="{visual}">Open visual</a> | <a href="{notes}">Notes</a> | <a href="{validation}">Validation</a></p></section>""")
    s = report["summary"]
    cards.append(f"""<section class="card current"><h2>Phase 11: Foundry-Registered Maze Tool</h2><p>Status: {html.escape(report['status'])}. Toolbox registered: {s['foundry_toolbox_registered']}. Connection created: {s['foundry_tool_connection_created']}. LLM calls: {s['llm_calls_made']}.</p><p><a href="visuals/PHASE11_VISUAL.html">Open visual</a> | <a href="PHASE11_FOUNDRY_TOOLBOX_REGISTRATION.md">Notes</a> | <a href="PHASE11_VALIDATION.md">Validation</a></p></section>""")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Azure Foundry Maze Migration - Progress</title><style>body{{margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f7f8fa;color:#17202a}}main{{width:min(960px,calc(100% - 32px));margin:0 auto;padding:32px 0}}.card{{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:16px;margin:12px 0}}.current{{border-left:5px solid #1f6f5b}}a{{color:#285da8;font-weight:800;text-decoration:none}}p{{color:#5f6b7a}}</style></head><body><main><h1>Azure Foundry Maze Migration From Scratch</h1><p>Step-by-step migration of the local multi-agent maze program to Microsoft Foundry-hosted agents and Azure-native tool boundaries.</p><section class="card"><h2>Cost Policy</h2><p>Personal-subscription learning lab: Phase 11 reuses existing Function and Foundry resources and adds only metadata-level Foundry registration.</p></section>{''.join(cards)}<section class="card"><h2>Next</h2><p>{html.escape(s['next_phase'])}</p></section></main></body></html>"""


def write_docs() -> None:
    write_text(PROJECT_ROOT / "PHASE11_FOUNDRY_TOOLBOX_REGISTRATION.md", """# Phase 11 - Foundry-Registered Maze Tool

## Objective

Register the external Azure Function Maze Tool as a Foundry-managed OpenAPI
tool through a toolbox and project connection.

## Why This Phase Exists

Phase 10 made the Maze Tool a real external Azure Function. Foundry could not
show it as a Foundry tool because only our Python code knew about the HTTP
endpoint.

Phase 11 adds the Foundry-native registration:

```text
Azure Function Maze Tool
  -> OpenAPI contract
  -> Foundry project connection for x-functions-key
  -> Foundry toolbox
  -> OpenAPI tool inside toolbox
```

## What Should Be Visible In Foundry

Look under the Foundry project Tools area, especially the Toolboxes tab:

```text
Toolbox: maze-toolbox
Tool:    maze_tool_api
Auth:    maze-tool-function-key project connection
```

The individual Azure Function App still appears under Azure resources, not as
an agent by itself.

## Runtime Boundary

The live maze WebUI still uses the Phase 10 runtime path:

```text
PydanticAI hosted agent -> ExternalMazeToolProgram -> Azure Function
```

The next phase can switch the PydanticAI runtime to consume the toolbox MCP
endpoint instead of the direct HTTP client.

## Auth Shape Note

The toolbox file uses the runtime-compatible project connection shape:

```json
{
  "type": "project_connection",
  "security_scheme": {
    "project_connection_id": "maze-tool-function-key"
  }
}
```
""")
    write_text(PROJECT_ROOT / "PHASE11_VALIDATION.md", """# Phase 11 Validation

## Expected Result

```text
OpenAPI contract is reachable from the Maze Function.
Foundry project connection stores x-functions-key auth outside source.
Foundry toolbox maze-toolbox exists.
OpenAPI tool maze_tool_api is registered inside the toolbox.
No LLM calls are required for this registration phase.
```

## Command

```bash
python3 scripts/phase11_foundry_toolbox_registration.py --apply
```

## Generated Artifacts

```text
tools/phase11-foundry-toolbox/maze_toolbox.json
runs/phase11_foundry_toolbox_registration.json
visuals/PHASE11_VISUAL.html
PHASE11_FOUNDRY_TOOLBOX_REGISTRATION.md
PHASE11_VALIDATION.md
PROGRESS.html
```
""")


def main() -> int:
    parser = argparse.ArgumentParser(description="Register the Maze Tool as a Foundry OpenAPI toolbox tool.")
    parser.add_argument("--apply", action="store_true", help="Create/update the Foundry connection and toolbox.")
    args = parser.parse_args()
    write_docs()
    report = build_report(apply=args.apply)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    VISUALS_DIR.mkdir(parents=True, exist_ok=True)
    write_text(RUNS_DIR / "phase11_foundry_toolbox_registration.json", json.dumps(report, indent=2, default=str) + "\n")
    write_text(VISUALS_DIR / "PHASE11_VISUAL.html", render_phase_html(report))
    write_text(PROGRESS_PATH, render_progress_html(report))
    print(f"phase={report['phase']}")
    print(f"status={report['status']}")
    print(f"toolbox_registered={report['summary']['foundry_toolbox_registered']}")
    print(f"connection_created={report['summary']['foundry_tool_connection_created']}")
    print(f"llm_calls={report['summary']['llm_calls_made']}")
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
