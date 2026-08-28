#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.foundry_provider_adapter import TOKEN_RESOURCE, get_azure_ai_token


RUNS_DIR = PROJECT_ROOT / "runs"
VISUALS_DIR = PROJECT_ROOT / "visuals"
PROGRESS_PATH = PROJECT_ROOT / "PROGRESS.html"
PHASE4_REPORT = RUNS_DIR / "phase4_foundry_project_model.json"


class AnalystMigrationOutput(BaseModel):
    mission_summary: str = Field(description="One sentence summary of what Phase 6 proves.")
    agent_runtime_boundary: str = Field(description="Where the Analyst Agent code runs in this phase.")
    model_backend_boundary: str = Field(description="Where model inference runs in this phase.")
    local_components_remaining: list[str] = Field(description="Local components that have not moved to Azure yet.")
    next_migration_step: str = Field(description="The next smallest migration step.")
    confidence: float = Field(ge=0.0, le=1.0)


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def usage_to_dict(result: Any) -> dict[str, Any]:
    usage_attr = getattr(result, "usage", None)
    usage = usage_attr() if callable(usage_attr) else usage_attr
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        return json_safe(usage.model_dump())
    if hasattr(usage, "__dict__"):
        return json_safe(dict(usage.__dict__))
    return {}


def run_pydantic_ai_analyst(project_endpoint: str, deployment_name: str) -> tuple[AnalystMigrationOutput, dict[str, Any]]:
    try:
        from pydantic_ai import Agent, PromptedOutput
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.usage import UsageLimits
    except Exception as exc:
        raise RuntimeError("Pydantic AI is not installed in this environment.") from exc

    token = get_azure_ai_token(TOKEN_RESOURCE)
    provider = OpenAIProvider(
        base_url=f"{project_endpoint.rstrip('/')}/openai/v1",
        api_key=token,
    )
    model = OpenAIChatModel(deployment_name, provider=provider)
    agent = Agent(
        model,
        output_type=PromptedOutput(AnalystMigrationOutput),
        instructions=(
            "You are the Analyst Agent in a migration curriculum. Return concise, "
            "structured output. Do not claim any agent code is hosted in Azure yet. "
            "Do not introduce new Azure services. Keep the phase focused on the "
            "Pydantic AI agent runtime using a Foundry model backend."
        ),
    )
    prompt = """
Phase 6 migration checkpoint:
- The local multi-agent maze curriculum already uses Pydantic AI for reasoning agents.
- Azure Foundry already has a project and a gpt-4.1-mini deployment named gpt41mini-maze.
- The model provider adapter can reach the Foundry project endpoint with Azure CLI Entra ID.
- In this phase, run the Analyst Agent locally through Pydantic AI while the model call goes to Foundry.
- Maze tools, worker agents, orchestrator, and team memory remain local.
- No Foundry-hosted agents should be created in this phase.
- The next smallest migration step is to create a minimal Foundry-hosted Analyst
  Agent while maze tools, workers, orchestrator, and memory remain local.
- Do not recommend migrating worker agents next.

Explain the boundary this proves and the next smallest migration step.
"""
    result = agent.run_sync(prompt, usage_limits=UsageLimits(request_limit=3, output_tokens_limit=600))
    return result.output, usage_to_dict(result)


def build_phase6_report() -> dict[str, Any]:
    phase4 = load_json(PHASE4_REPORT)
    if not phase4 or phase4.get("status") != "complete":
        raise RuntimeError("Phase 4 report is missing or incomplete; run Phase 4 first.")

    project_endpoint = phase4["resources"]["project"]["endpoint"]
    deployment_name = phase4["resources"]["model_deployment"]["name"]

    error = ""
    output: AnalystMigrationOutput | None = None
    usage: dict[str, Any] = {}
    try:
        output, usage = run_pydantic_ai_analyst(project_endpoint, deployment_name)
    except Exception as exc:
        error = str(exc)

    requests = usage.get("requests")
    inference_calls = requests if isinstance(requests, int) and requests > 0 else (1 if output else 0)
    success = output is not None and inference_calls > 0

    return {
        "course": "Azure Foundry Maze Migration From Scratch",
        "phase": 6,
        "phase_name": "Pydantic AI Analyst Agent on Foundry Model",
        "status": "complete" if success else "action_required",
        "learning_objective": "Run one local Pydantic AI Analyst Agent while using the Azure Foundry model deployment as its backend.",
        "boundary": {
            "agent_runtime": "local Mac/Linux Python process",
            "agent_framework": "Pydantic AI",
            "model_backend": "Azure Foundry project model deployment",
            "hosted_agents_created": 0,
            "azure_resources_created": 0,
            "maze_tools_location": "local Python",
            "worker_agents_location": "local curriculum code, not invoked in this phase",
            "team_memory_location": "local/in-process, not invoked in this phase",
        },
        "foundry_target": {
            "project_endpoint": project_endpoint,
            "deployment_name": deployment_name,
            "auth_mode": "Azure CLI Entra ID token",
            "api_family": "OpenAI-compatible Chat Completions API through Pydantic AI",
        },
        "analyst_agent": {
            "name": "Analyst Agent v1",
            "framework": "Pydantic AI",
            "structured_output_model": "AnalystMigrationOutput",
            "made_model_call": success,
            "output": output.model_dump() if output else None,
            "error": error,
            "usage": usage,
        },
        "summary": {
            "pydantic_ai_agents_run": 1 if success else 0,
            "foundry_model_calls": inference_calls,
            "hosted_agents_created": 0,
            "azure_resources_created": 0,
            "maze_tool_calls": 0,
            "worker_agents_run": 0,
            "estimated_cost": "one short gpt-4.1-mini call",
            "next_phase": "Create the first minimal Foundry-hosted Analyst Agent while keeping maze tools and workers local.",
        },
    }


def table_rows(mapping: dict[str, Any]) -> str:
    return "".join(
        "<tr>"
        f"<td>{html.escape(key.replace('_', ' ').title())}</td>"
        f"<td>{html.escape(json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value))}</td>"
        "</tr>"
        for key, value in mapping.items()
    )


def render_phase_html(report: dict[str, Any]) -> str:
    summary = report["summary"]
    boundary = report["boundary"]
    target = report["foundry_target"]
    analyst = report["analyst_agent"]
    output = analyst.get("output") or {}
    data = html.escape(json.dumps(report, indent=2, default=str))
    local_components = output.get("local_components_remaining") or [
        "Maze tools",
        "Worker agents",
        "Orchestrator",
        "Team memory",
    ]
    components_html = "".join(f"<li>{html.escape(str(item))}</li>" for item in local_components)
    output_cards = "".join(
        f"<article><span>{html.escape(key.replace('_', ' ').title())}</span><p>{html.escape(str(value))}</p></article>"
        for key, value in output.items()
        if key != "local_components_remaining"
    )
    if not output_cards:
        output_cards = f"<article><span>Validation Error</span><p>{html.escape(analyst.get('error') or 'No agent output returned.')}</p></article>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Azure Foundry Maze Migration - Phase 6</title>
  <style>
    :root {{ --bg:#f7f8fa; --panel:#fff; --text:#17202a; --muted:#5f6b7a; --line:#d9dee7; --blue:#285da8; --green:#1f6f5b; --amber:#9a6500; --shadow:0 10px 28px rgba(28,36,48,.08); }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:var(--text); background:var(--bg); line-height:1.5; }}
    main {{ width:min(1180px, calc(100% - 32px)); margin:0 auto; padding:32px 0 48px; }}
    header {{ display:grid; grid-template-columns:minmax(0,1fr) 300px; gap:20px; border-bottom:1px solid var(--line); padding-bottom:20px; margin-bottom:22px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(28px,4vw,42px); line-height:1.08; }}
    h2 {{ margin:0 0 12px; font-size:20px; }}
    h3 {{ margin:0 0 8px; font-size:16px; }}
    p {{ margin:0; color:var(--muted); }}
    a {{ color:var(--blue); font-weight:800; text-decoration:none; }}
    .panel,.summary,.flow-step,.answer article {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; box-shadow:var(--shadow); padding:16px; }}
    .summary strong {{ display:block; font-size:30px; text-transform:capitalize; }}
    .stack {{ display:grid; gap:14px; }}
    .metrics {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }}
    .metric {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fff; }}
    .metric span,.answer span,.flow-step span {{ display:block; color:var(--muted); font-size:12px; font-weight:800; text-transform:uppercase; }}
    .metric strong {{ display:block; margin-top:6px; font-size:26px; }}
    .flow {{ display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:10px; }}
    .flow-step {{ box-shadow:none; min-height:130px; border-left:5px solid var(--blue); }}
    .flow-step.local {{ border-left-color:var(--amber); }}
    .flow-step.done {{ border-left-color:var(--green); }}
    .answer {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }}
    .answer article {{ box-shadow:none; }}
    .answer p {{ color:#17202a; }}
    ul {{ margin:8px 0 0; padding-left:20px; color:#17202a; }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th,td {{ padding:9px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-size:12px; text-transform:uppercase; }}
    code {{ color:#111827; background:#eef2f7; padding:2px 5px; border-radius:4px; }}
    pre {{ overflow:auto; max-height:420px; padding:12px; background:#111827; color:#e5e7eb; border-radius:8px; font-size:12px; }}
    @media (max-width:980px) {{ header,.metrics,.flow,.answer {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Phase 6 - Pydantic AI Analyst Agent</h1>
        <p>Run the Analyst role locally through Pydantic AI while the model inference goes to Azure Foundry.</p>
      </div>
      <aside class="summary">
        <span>Status</span>
        <strong>{html.escape(report['status'])}</strong>
        <p>Hosted agents created: {summary['hosted_agents_created']}.</p>
      </aside>
    </header>
    <div class="stack">
      <section class="panel">
        <h2>Phase Metrics</h2>
        <div class="metrics">
          <div class="metric"><span>Pydantic AI Agents</span><strong>{summary['pydantic_ai_agents_run']}</strong></div>
          <div class="metric"><span>Foundry Calls</span><strong>{summary['foundry_model_calls']}</strong></div>
          <div class="metric"><span>Hosted Agents</span><strong>{summary['hosted_agents_created']}</strong></div>
          <div class="metric"><span>Maze Tool Calls</span><strong>{summary['maze_tool_calls']}</strong></div>
        </div>
      </section>
      <section class="panel">
        <h2>Runtime Flow</h2>
        <div class="flow">
          <article class="flow-step local"><span>1. Local Process</span><h3>Mac/Linux Python</h3><p>The agent code still runs where the curriculum runs today.</p></article>
          <article class="flow-step local"><span>2. Agent Framework</span><h3>Pydantic AI</h3><p>The Analyst is a typed Pydantic AI agent, not a raw HTTP call.</p></article>
          <article class="flow-step"><span>3. Provider</span><h3>Foundry endpoint</h3><p>The model backend is selected through the OpenAI-compatible provider boundary.</p></article>
          <article class="flow-step"><span>4. Model</span><h3>{html.escape(target['deployment_name'])}</h3><p>Inference runs in the Foundry project deployment.</p></article>
          <article class="flow-step done"><span>5. Output</span><h3>Typed Analyst result</h3><p>The response is parsed into <code>AnalystMigrationOutput</code>.</p></article>
        </div>
      </section>
      <section class="panel">
        <h2>Analyst Output</h2>
        <div class="answer">{output_cards}</div>
      </section>
      <section class="panel">
        <h2>Still Local</h2>
        <p>Phase 6 moves only the Analyst model backend. These pieces intentionally remain local:</p>
        <ul>{components_html}</ul>
      </section>
      <section class="panel">
        <h2>Boundary</h2>
        <table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{table_rows(boundary)}</tbody></table>
      </section>
      <section class="panel">
        <h2>Foundry Target</h2>
        <table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{table_rows(target)}</tbody></table>
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


def render_progress_html(report: dict[str, Any]) -> str:
    phase_files = [
        ("Phase 1: Portability Inventory", RUNS_DIR / "phase1_inventory.json", "visuals/PHASE1_VISUAL.html", "PHASE1_PORTABILITY_INVENTORY.md", "PHASE1_VALIDATION.md"),
        ("Phase 2: Public Repo and Secret Hygiene", RUNS_DIR / "phase2_public_repo_hygiene.json", "visuals/PHASE2_VISUAL.html", "PHASE2_PUBLIC_REPO_HYGIENE.md", "PHASE2_VALIDATION.md"),
        ("Phase 3: Azure Login and Subscription Readiness", RUNS_DIR / "phase3_azure_login_readiness.json", "visuals/PHASE3_VISUAL.html", "PHASE3_AZURE_LOGIN_READINESS.md", "PHASE3_VALIDATION.md"),
        ("Phase 4: Foundry Project and Model Deployment", RUNS_DIR / "phase4_foundry_project_model.json", "visuals/PHASE4_VISUAL.html", "PHASE4_FOUNDRY_PROJECT_MODEL.md", "PHASE4_VALIDATION.md"),
        ("Phase 5: Model Provider Adapter", RUNS_DIR / "phase5_model_provider_adapter.json", "visuals/PHASE5_VISUAL.html", "PHASE5_MODEL_PROVIDER_ADAPTER.md", "PHASE5_VALIDATION.md"),
    ]
    detail_keys = {
        "files_scanned",
        "blocking_findings_after_export",
        "azure_resources_created",
        "new_resources_created",
        "inference_calls_made",
        "foundry_model_calls",
        "hosted_agents_created",
    }
    cards = []
    for title, path, visual, notes, validation in phase_files:
        item = load_json(path)
        if not item:
            continue
        summary = item.get("summary", {})
        detail = ", ".join(f"{key}: {value}" for key, value in summary.items() if key in detail_keys)
        cards.append(
            f"""<section class="card"><h2>{html.escape(title)}</h2><p>Status: {html.escape(str(item.get('status')))}. {html.escape(detail)}</p><p><a href="{visual}">Open visual</a> | <a href="{notes}">Notes</a> | <a href="{validation}">Validation</a></p></section>"""
        )

    s = report["summary"]
    cards.append(
        f"""<section class="card current"><h2>Phase 6: Pydantic AI Analyst Agent on Foundry Model</h2><p>Status: {html.escape(report['status'])}. Pydantic AI agents run: {s['pydantic_ai_agents_run']}. Foundry calls: {s['foundry_model_calls']}. Hosted agents: {s['hosted_agents_created']}.</p><p><a href="visuals/PHASE6_VISUAL.html">Open visual</a> | <a href="PHASE6_FOUNDRY_ANALYST_AGENT.md">Notes</a> | <a href="PHASE6_VALIDATION.md">Validation</a></p></section>"""
    )
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
    .current {{ border-left:5px solid #1f6f5b; }}
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
    <section class="card"><h2>Next: Phase 7</h2><p>{html.escape(s['next_phase'])}</p></section>
  </main>
</body>
</html>
"""


def main() -> int:
    report = build_phase6_report()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    VISUALS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "phase6_foundry_analyst_agent.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    (VISUALS_DIR / "PHASE6_VISUAL.html").write_text(render_phase_html(report), encoding="utf-8")
    PROGRESS_PATH.write_text(render_progress_html(report), encoding="utf-8")
    print(f"phase={report['phase']}")
    print(f"status={report['status']}")
    print(f"pydantic_ai_agents_run={report['summary']['pydantic_ai_agents_run']}")
    print(f"foundry_model_calls={report['summary']['foundry_model_calls']}")
    print(f"hosted_agents_created={report['summary']['hosted_agents_created']}")
    agent_output = report["analyst_agent"].get("output") or {}
    print(f"mission_summary={agent_output.get('mission_summary', '')}")
    if report["analyst_agent"].get("error"):
        print(f"error={report['analyst_agent']['error']}")
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
