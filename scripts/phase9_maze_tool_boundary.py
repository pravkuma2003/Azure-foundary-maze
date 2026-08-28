#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOSTED_ROOT = PROJECT_ROOT / "hosted" / "phase7-monolithic-maze-agent"
RUNS_DIR = PROJECT_ROOT / "runs"
VISUALS_DIR = PROJECT_ROOT / "visuals"
PROGRESS_PATH = PROJECT_ROOT / "PROGRESS.html"
WEBUI_SAMPLE_TRACE = PROJECT_ROOT / "webui" / "phase8-azure-webui" / "static" / "sample_trace.json"
PHASE9_RUN_DIR = RUNS_DIR / "phase9_maze_tool_boundary_validation"
LIVE_VALIDATION = RUNS_DIR / "phase9_live_hosted_validation.json"


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_command(args: list[str], cwd: Path, timeout: int = 180) -> dict[str, Any]:
    try:
        completed = subprocess.run(args, cwd=cwd, check=False, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return {"command": args, "returncode": 127, "stdout": "", "stderr": f"{args[0]} not found"}
    except subprocess.TimeoutExpired as exc:
        return {"command": args, "returncode": 124, "stdout": exc.stdout or "", "stderr": exc.stderr or "timed out"}
    return {
        "command": args,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def validate_boundary() -> dict[str, Any]:
    command = [sys.executable, "main.py", "--once", "--provider", "test", "--output-dir", str(PHASE9_RUN_DIR)]
    result = run_command(command, cwd=HOSTED_ROOT)
    trace_path = PHASE9_RUN_DIR / "phase7_monolithic_trace.json"
    visual_path = PHASE9_RUN_DIR / "PHASE7_MONOLITHIC_VISUAL.html"
    trace = load_json(trace_path) or {}
    tool_events = [event for event in trace.get("events", []) if event.get("type") == "tool_call"]
    boundary_events = [event for event in tool_events if event.get("tool_boundary") == "MazeToolProgram"]
    result_events = [event for event in boundary_events if isinstance(event.get("tool_result"), dict)]
    all_tool_results_ok = all((event.get("tool_result") or {}).get("ok") is True for event in result_events)
    if trace_path.exists():
        WEBUI_SAMPLE_TRACE.parent.mkdir(parents=True, exist_ok=True)
        WEBUI_SAMPLE_TRACE.write_text(trace_path.read_text(encoding="utf-8"), encoding="utf-8")
    if visual_path.exists():
        phase9_visual = VISUALS_DIR / "PHASE9_VISUAL.html"
        phase9_visual.parent.mkdir(parents=True, exist_ok=True)
        phase9_visual.write_text(visual_path.read_text(encoding="utf-8"), encoding="utf-8")
    return {
        "command": command,
        "returncode": result["returncode"],
        "stdout_tail": result["stdout"][-1200:],
        "stderr_tail": result["stderr"][-1200:],
        "trace_created": trace_path.exists(),
        "tool_events": len(tool_events),
        "boundary_events": len(boundary_events),
        "tool_results": len(result_events),
        "all_tool_results_ok": all_tool_results_ok,
        "maze_tool_module": str((HOSTED_ROOT / "src" / "maze_tool_boundary.py").relative_to(PROJECT_ROOT)),
        "trace_summary": trace.get("summary", {}),
        "sample_trace_refreshed": WEBUI_SAMPLE_TRACE.exists() and trace_path.exists(),
    }


def build_report() -> dict[str, Any]:
    validation = validate_boundary()
    live_validation = load_json(LIVE_VALIDATION) or {"status": "not_run"}
    passed = (
        validation["returncode"] == 0
        and validation["trace_created"]
        and validation["tool_events"] > 0
        and validation["tool_events"] == validation["boundary_events"]
        and validation["tool_results"] == validation["tool_events"]
        and validation["all_tool_results_ok"]
    )
    return {
        "course": "Azure Foundry Maze Migration From Scratch",
        "phase": 9,
        "phase_name": "Maze Tool Boundary without New Azure Service",
        "status": "complete" if passed else "action_required",
        "learning_objective": "Split maze inspection and movement execution out of direct agent runtime logic and behind a stable MazeTool program interface.",
        "boundary": {
            "before": "Agents and trace code called maze helper functions directly inside the hosted monolith.",
            "after": "Agents call MazeToolProgram inspect/move operations through typed request/result payloads.",
            "tool_runtime_location": "still in the same Azure-hosted package",
            "new_azure_service_created": False,
            "why_no_new_service": "The lesson is program boundary extraction first; separate Azure deployment comes after the interface is stable.",
        },
        "maze_tool_contract": {
            "program": "MazeToolProgram",
            "operations": ["inspect", "move"],
            "request_fields": ["operation", "maze_id", "position", "move"],
            "result_fields": ["ok", "maze_id", "position", "legal_moves", "new_position", "error"],
            "trace_fields_added": ["tool_boundary", "tool_request", "tool_result"],
        },
        "validation": validation,
        "live_hosted_validation": live_validation,
        "summary": {
            "maze_tool_boundary_extracted": passed,
            "hosted_agent_count_changed": 0,
            "azure_resources_created": 0,
            "new_function_apps_created": 0,
            "additional_idle_cost": "$0",
            "llm_calls_during_validation": 0,
            "tool_events_through_boundary": validation["boundary_events"],
            "webui_sample_trace_refreshed": validation["sample_trace_refreshed"],
            "live_hosted_validation": live_validation.get("status"),
            "next_phase": "Move Worker Agent A into its own hosted boundary while reusing the MazeTool contract.",
        },
    }


def table_rows(mapping: dict[str, Any]) -> str:
    rows = []
    for key, value in mapping.items():
        if isinstance(value, (dict, list)):
            rendered = json.dumps(value, default=str)
        else:
            rendered = str(value)
        rows.append(
            "<tr>"
            f"<td>{html.escape(key.replace('_', ' ').title())}</td>"
            f"<td>{html.escape(rendered)}</td>"
            "</tr>"
        )
    return "".join(rows)


def render_phase_html(report: dict[str, Any]) -> str:
    boundary = report["boundary"]
    contract = report["maze_tool_contract"]
    validation = report["validation"]
    live_validation = report.get("live_hosted_validation") or {}
    data = html.escape(json.dumps(report, indent=2, default=str))
    operations = "".join(f"<li>{html.escape(item)}</li>" for item in contract["operations"])
    trace_fields = "".join(f"<li>{html.escape(item)}</li>" for item in contract["trace_fields_added"])
    live_section = ""
    if live_validation.get("status") != "not_run":
        live_section = f"""
      <section class="panel">
        <h2>Live Azure Validation</h2>
        <table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{table_rows(live_validation)}</tbody></table>
      </section>"""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Azure Foundry Maze Migration - Phase 9</title>
  <style>
    :root {{ --bg:#f7f8fa; --panel:#fff; --text:#17202a; --muted:#5f6b7a; --line:#d9dee7; --blue:#285da8; --green:#1f6f5b; --amber:#9a6500; --shadow:0 10px 28px rgba(28,36,48,.08); }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--text); background:var(--bg); line-height:1.5; }}
    main {{ width:min(1180px,calc(100% - 32px)); margin:0 auto; padding:32px 0 48px; }}
    header {{ display:grid; grid-template-columns:minmax(0,1fr) 330px; gap:20px; border-bottom:1px solid var(--line); padding-bottom:20px; margin-bottom:22px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(28px,4vw,42px); line-height:1.08; }}
    h2 {{ margin:0 0 12px; font-size:20px; }}
    h3 {{ margin:0 0 8px; font-size:16px; }}
    p {{ margin:0; color:var(--muted); }}
    a {{ color:var(--blue); font-weight:800; text-decoration:none; }}
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
    .two {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th,td {{ padding:9px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-size:12px; text-transform:uppercase; }}
    code {{ color:#111827; background:#eef2f7; padding:2px 5px; border-radius:4px; }}
    pre {{ overflow:auto; max-height:420px; padding:12px; background:#111827; color:#e5e7eb; border-radius:8px; font-size:12px; }}
    ul {{ margin:8px 0 0; padding-left:20px; }}
    @media (max-width:980px) {{ header,.metrics,.flow,.two {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Phase 9 - Maze Tool Boundary</h1>
        <p>{html.escape(report['learning_objective'])}</p>
      </div>
      <aside class="summary">
        <span>Status</span>
        <strong>{html.escape(report['status'].replace('_', ' '))}</strong>
        <p>No new Azure service was created in this phase.</p>
      </aside>
    </header>
    <div class="stack">
      <section class="panel">
        <h2>Phase Metrics</h2>
        <div class="metrics">
          <div class="metric"><span>Boundary Events</span><strong>{validation['boundary_events']}</strong></div>
          <div class="metric"><span>Tool Results</span><strong>{validation['tool_results']}</strong></div>
          <div class="metric"><span>New Azure Services</span><strong>0</strong></div>
          <div class="metric"><span>Validation LLM Calls</span><strong>0</strong></div>
        </div>
      </section>
      <section class="panel">
        <h2>Boundary Flow</h2>
        <div class="flow">
          <article class="step"><span>1. Worker Agent</span><h3>Reasoning owner</h3><p>Chooses what operation it needs: inspect or move.</p></article>
          <article class="step tool"><span>2. MazeTool Program</span><h3>Callable boundary</h3><p>Receives typed request fields and returns typed result fields.</p></article>
          <article class="step"><span>3. Maze Engine</span><h3>Rule owner</h3><p>Knows grid bounds, walls, legal moves, and validation.</p></article>
          <article class="step note"><span>4. Later Phase</span><h3>Deployment split</h3><p>The same contract can become an Azure Function or hosted tool later.</p></article>
        </div>
      </section>
      <section class="two">
        <article class="panel">
          <h2>Tool Contract</h2>
          <p><code>{html.escape(contract['program'])}</code></p>
          <h3>Operations</h3>
          <ul>{operations}</ul>
        </article>
        <article class="panel">
          <h2>Trace Additions</h2>
          <p>Every maze operation now records request and result payloads.</p>
          <ul>{trace_fields}</ul>
        </article>
      </section>
      <section class="panel">
        <h2>Boundary Summary</h2>
        <table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{table_rows(boundary)}</tbody></table>
      </section>
      <section class="panel">
        <h2>Validation</h2>
        <table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{table_rows(validation)}</tbody></table>
      </section>
      {live_section}
      <section class="panel">
        <h2>Report JSON</h2>
        <details><summary>Open generated report</summary><pre>{data}</pre></details>
      </section>
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
    ]
    cards = []
    for title, path, visual, notes, validation in phase_files:
        item = load_json(path)
        if not item:
            continue
        summary = item.get("summary", {})
        detail = ", ".join(
            f"{key}: {summary[key]}"
            for key in ("foundry_model_calls", "hosted_agents_created", "azure_webui_deployed", "azure_resources_created")
            if key in summary
        )
        cards.append(
            f"""<section class="card"><h2>{html.escape(title)}</h2><p>Status: {html.escape(str(item.get('status')))}. {html.escape(detail)}</p><p><a href="{visual}">Open visual</a> | <a href="{notes}">Notes</a> | <a href="{validation}">Validation</a></p></section>"""
        )
    s = report["summary"]
    cards.append(
        f"""<section class="card current"><h2>Phase 9: Maze Tool Boundary without New Azure Service</h2><p>Status: {html.escape(report['status'])}. Boundary extracted: {s['maze_tool_boundary_extracted']}. New Azure services: {s['azure_resources_created']}. Additional idle cost: {html.escape(s['additional_idle_cost'])}.</p><p><a href="visuals/PHASE9_VISUAL.html">Open visual</a> | <a href="PHASE9_MAZE_TOOL_BOUNDARY.md">Notes</a> | <a href="PHASE9_VALIDATION.md">Validation</a></p></section>"""
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Azure Foundry Maze Migration - Progress</title><style>body{{margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f7f8fa;color:#17202a}}main{{width:min(960px,calc(100% - 32px));margin:0 auto;padding:32px 0}}.card{{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:16px;margin:12px 0}}.current{{border-left:5px solid #1f6f5b}}a{{color:#285da8;font-weight:800;text-decoration:none}}p{{color:#5f6b7a}}</style></head><body><main><h1>Azure Foundry Maze Migration From Scratch</h1><p>Step-by-step migration of the local multi-agent maze program to Microsoft Foundry-hosted agents.</p><section class="card"><h2>Cost Policy</h2><p>Personal-subscription learning lab: one Foundry project, one model deployment, one hosted runtime, and one small WebUI/proxy before adding Azure-native storage or tool services.</p></section>{''.join(cards)}<section class="card"><h2>Next</h2><p>{html.escape(s['next_phase'])}</p></section></main></body></html>"""


def write_docs() -> None:
    write_text(PROJECT_ROOT / "PHASE9_MAZE_TOOL_BOUNDARY.md", """# Phase 9 - Maze Tool Boundary without New Azure Service

## Objective

Split maze inspection and movement execution out of direct agent runtime logic
and behind a stable program interface.

The Maze Tool was already running in Azure as part of the monolithic hosted
agent package. This phase does not move the tool to Azure; it makes the tool a
separate callable program boundary inside that package.

## Before

```text
Worker Agent logic
  -> direct helper call for legal moves
  -> direct helper call for move validation
```

## After

```text
Worker Agent logic
  -> MazeToolProgram.inspect(request)
  -> MazeToolProgram.move(request)
  -> typed tool result
```

## Contract

```text
Request: operation, maze_id, position, optional move
Result: ok, maze_id, position, legal_moves, optional new_position, optional error
```

## Cost

No new Azure resource is created. The tool still runs inside the existing hosted
agent package, so the idle cost does not change.

## Why This Matters

Future phases can move the Maze Tool into an Azure Function, Container App, or
Foundry-connected tool without changing the agent reasoning contract.
""")
    write_text(PROJECT_ROOT / "PHASE9_VALIDATION.md", """# Phase 9 Validation

## Expected Result

```text
MazeToolProgram exists as its own source module.
Hosted package still runs with provider=test.
Every maze tool event includes tool_boundary=MazeToolProgram.
Every maze tool event includes tool_request and tool_result payloads.
No new Azure resource is created.
No LLM calls are made during validation.
```

## Command

```bash
python3 scripts/phase9_maze_tool_boundary.py
```

## Generated Artifacts

```text
hosted/phase7-monolithic-maze-agent/src/maze_tool_boundary.py
runs/phase9_maze_tool_boundary.json
runs/phase9_maze_tool_boundary_validation/
visuals/PHASE9_VISUAL.html
PHASE9_MAZE_TOOL_BOUNDARY.md
PHASE9_VALIDATION.md
PROGRESS.html
```
""")


def main() -> int:
    write_docs()
    report = build_report()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    VISUALS_DIR.mkdir(parents=True, exist_ok=True)
    write_text(RUNS_DIR / "phase9_maze_tool_boundary.json", json.dumps(report, indent=2, default=str) + "\n")
    write_text(VISUALS_DIR / "PHASE9_VISUAL.html", render_phase_html(report))
    write_text(PROGRESS_PATH, render_progress_html(report))
    print(f"phase={report['phase']}")
    print(f"status={report['status']}")
    print(f"maze_tool_boundary_extracted={report['summary']['maze_tool_boundary_extracted']}")
    print(f"tool_events_through_boundary={report['summary']['tool_events_through_boundary']}")
    print(f"azure_resources_created={report['summary']['azure_resources_created']}")
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
