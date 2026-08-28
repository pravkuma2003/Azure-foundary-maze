#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.foundry_provider_adapter import FoundryProviderConfig, call_foundry_responses


RUNS_DIR = PROJECT_ROOT / "runs"
VISUALS_DIR = PROJECT_ROOT / "visuals"
PROGRESS_PATH = PROJECT_ROOT / "PROGRESS.html"
PHASE4_REPORT = RUNS_DIR / "phase4_foundry_project_model.json"
PROMPT = "Reply with exactly: foundry adapter ready"


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_phase5_report() -> dict[str, Any]:
    phase4 = load_json(PHASE4_REPORT)
    if not phase4 or phase4.get("status") != "complete":
        raise RuntimeError("Phase 4 report is missing or incomplete; run Phase 4 first.")

    project_endpoint = phase4["resources"]["project"]["endpoint"]
    deployment_name = phase4["resources"]["model_deployment"]["name"]
    config = FoundryProviderConfig(
        project_endpoint=project_endpoint,
        deployment_name=deployment_name,
        temperature=0.0,
        max_output_tokens=24,
    )

    error = ""
    result_payload: dict[str, Any] | None = None
    try:
        result = call_foundry_responses(config, PROMPT)
        result_payload = {
            "provider": result.provider,
            "deployment_name": result.deployment_name,
            "response_id": result.response_id,
            "output_text": result.output_text,
            "usage": result.usage,
            "request_path": result.request_path,
            "auth_mode": result.auth_mode,
        }
    except Exception as exc:
        error = str(exc)

    success = bool(result_payload and result_payload.get("output_text"))
    usage = (result_payload or {}).get("usage") or {}
    return {
        "course": "Azure Foundry Maze Migration From Scratch",
        "phase": 5,
        "phase_name": "Model Provider Adapter",
        "status": "complete" if success else "action_required",
        "local_code_location": "Mac/Linux",
        "provider_boundary": {
            "local_provider": "Pydantic AI -> local OpenAI-compatible LiteLLM/Ollama endpoint",
            "foundry_provider": "Pydantic AI -> local adapter -> Foundry project endpoint -> deployed model",
            "agent_code_deployed_to_azure": False,
            "hosted_agents_created": 0,
        },
        "foundry_target": {
            "project_endpoint": project_endpoint,
            "deployment_name": deployment_name,
            "auth_mode": "Azure CLI Entra ID token",
            "api_path": "/openai/v1/responses",
        },
        "rbac": {
            "project_scope_role": "Foundry User",
            "account_scope_role": "Cognitive Services OpenAI User",
            "why": "Project endpoint access and model inference data actions are separate checks.",
            "subscription_scope_role_added": False,
        },
        "test_call": {
            "prompt": PROMPT,
            "max_output_tokens": config.max_output_tokens,
            "temperature": config.temperature,
            "made": True,
            "success": success,
            "response": result_payload,
            "error": error,
        },
        "summary": {
            "model_backend": "Azure Foundry",
            "local_maze_code_changed": False,
            "provider_adapter_added": True,
            "inference_calls_made": 1,
            "hosted_agents_created": 0,
            "estimated_cost": "tiny pay-per-token test call",
            "total_tokens": usage.get("total_tokens") or usage.get("total_tokens_details") or "not_reported",
            "next_phase": "Run the Analyst role through the Foundry provider while keeping the maze tools local.",
        },
    }


def render_phase_html(report: dict[str, Any]) -> str:
    summary = report["summary"]
    boundary = report["provider_boundary"]
    target = report["foundry_target"]
    rbac = report["rbac"]
    test = report["test_call"]
    response = test.get("response") or {}
    boundary_rows = "".join(
        "<tr>"
        f"<td>{html.escape(key.replace('_', ' ').title())}</td>"
        f"<td>{html.escape(str(value))}</td>"
        "</tr>"
        for key, value in boundary.items()
    )
    target_rows = "".join(
        "<tr>"
        f"<td>{html.escape(key.replace('_', ' ').title())}</td>"
        f"<td>{html.escape(str(value))}</td>"
        "</tr>"
        for key, value in target.items()
    )
    rbac_rows = "".join(
        "<tr>"
        f"<td>{html.escape(key.replace('_', ' ').title())}</td>"
        f"<td>{html.escape(str(value))}</td>"
        "</tr>"
        for key, value in rbac.items()
    )
    data = html.escape(json.dumps(report, indent=2))
    output_text = response.get("output_text") or test.get("error") or "No response text"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Azure Foundry Maze Migration - Phase 5</title>
  <style>
    :root {{ --bg:#f7f8fa; --panel:#fff; --text:#17202a; --muted:#5f6b7a; --line:#d9dee7; --blue:#285da8; --green:#1f6f5b; --shadow:0 10px 28px rgba(28,36,48,.08); }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:var(--text); background:var(--bg); line-height:1.5; }}
    main {{ width:min(1180px, calc(100% - 32px)); margin:0 auto; padding:32px 0 48px; }}
    header {{ display:grid; grid-template-columns:minmax(0,1fr) 280px; gap:20px; border-bottom:1px solid var(--line); padding-bottom:20px; margin-bottom:22px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(28px,4vw,42px); line-height:1.08; }}
    h2 {{ margin:0 0 12px; font-size:20px; }}
    p {{ margin:0; color:var(--muted); }}
    .panel,.summary,.step {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; box-shadow:var(--shadow); padding:16px; }}
    .summary strong {{ display:block; font-size:30px; text-transform:capitalize; }}
    .metrics {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }}
    .metric {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fff; }}
    .metric span {{ display:block; color:var(--muted); font-size:12px; font-weight:800; text-transform:uppercase; }}
    .metric strong {{ display:block; margin-top:6px; font-size:26px; }}
    .flow {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; }}
    .step {{ box-shadow:none; min-height:125px; border-left:5px solid var(--blue); }}
    .step:nth-child(4) {{ border-left-color:var(--green); }}
    .step span {{ display:block; color:var(--muted); font-size:12px; font-weight:800; text-transform:uppercase; }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th,td {{ padding:9px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-size:12px; text-transform:uppercase; }}
    code {{ color:#111827; background:#eef2f7; padding:2px 5px; border-radius:4px; }}
    pre {{ overflow:auto; max-height:420px; padding:12px; background:#111827; color:#e5e7eb; border-radius:8px; font-size:12px; }}
    .answer {{ border-left:5px solid var(--green); padding:14px; background:#eef8f3; border-radius:8px; color:#17202a; }}
    .stack {{ display:grid; gap:14px; }}
    @media (max-width:900px) {{ header,.metrics,.flow {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Phase 5 - Model Provider Adapter</h1>
        <p>Keep the maze code local while switching the model backend to Azure Foundry.</p>
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
          <div class="metric"><span>Local Code</span><strong>yes</strong></div>
          <div class="metric"><span>Foundry Calls</span><strong>{summary['inference_calls_made']}</strong></div>
          <div class="metric"><span>Hosted Agents</span><strong>{summary['hosted_agents_created']}</strong></div>
          <div class="metric"><span>Token Cost</span><strong>tiny</strong></div>
        </div>
      </section>
      <section class="panel">
        <h2>Provider Flow</h2>
        <div class="flow">
          <article class="step"><span>1. Local Python</span><strong>Mac/Linux code</strong><p>The maze program still runs outside Azure.</p></article>
          <article class="step"><span>2. Adapter</span><strong>foundry provider</strong><p>The provider boundary chooses Azure instead of LiteLLM.</p></article>
          <article class="step"><span>3. Endpoint</span><strong>Foundry project</strong><p>The call uses Entra ID, not a checked-in key.</p></article>
          <article class="step"><span>4. Deployment</span><strong>{html.escape(target['deployment_name'])}</strong><p>The model returns the first tiny response.</p></article>
        </div>
      </section>
      <section class="panel">
        <h2>Test Response</h2>
        <p class="answer">{html.escape(output_text)}</p>
      </section>
      <section class="panel">
        <h2>Provider Boundary</h2>
        <table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{boundary_rows}</tbody></table>
      </section>
      <section class="panel">
        <h2>Foundry Target</h2>
        <table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{target_rows}</tbody></table>
      </section>
      <section class="panel">
        <h2>RBAC Lesson</h2>
        <table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{rbac_rows}</tbody></table>
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
    ]
    cards = []
    for title, path, visual, notes, validation in phase_files:
        item = load_json(path)
        if not item:
            continue
        summary = item.get("summary", {})
        detail = ", ".join(f"{key}: {value}" for key, value in summary.items() if key in {
            "files_scanned",
            "blocking_findings_after_export",
            "azure_resources_created",
            "new_resources_created",
            "inference_calls_made",
            "hosted_agents_created",
        })
        cards.append(
            f"""<section class="card"><h2>{html.escape(title)}</h2><p>Status: {html.escape(str(item.get('status')))}. {html.escape(detail)}</p><p><a href="{visual}">Open visual</a> | <a href="{notes}">Notes</a> | <a href="{validation}">Validation</a></p></section>"""
        )
    s = report["summary"]
    cards.append(
        f"""<section class="card"><h2>Phase 5: Model Provider Adapter</h2><p>Status: {html.escape(report['status'])}. Foundry calls: {s['inference_calls_made']}. Hosted agents: {s['hosted_agents_created']}. Estimated cost: {html.escape(s['estimated_cost'])}.</p><p><a href="visuals/PHASE5_VISUAL.html">Open visual</a> | <a href="PHASE5_MODEL_PROVIDER_ADAPTER.md">Notes</a> | <a href="PHASE5_VALIDATION.md">Validation</a></p></section>"""
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
    <section class="card"><h2>Next: Phase 6</h2><p>{html.escape(s['next_phase'])}</p></section>
  </main>
</body>
</html>
"""


def main() -> int:
    report = build_phase5_report()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    VISUALS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "phase5_model_provider_adapter.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (VISUALS_DIR / "PHASE5_VISUAL.html").write_text(render_phase_html(report), encoding="utf-8")
    PROGRESS_PATH.write_text(render_progress_html(report), encoding="utf-8")
    print(f"phase={report['phase']}")
    print(f"status={report['status']}")
    print(f"local_code_location={report['local_code_location']}")
    print(f"inference_calls_made={report['summary']['inference_calls_made']}")
    print(f"hosted_agents_created={report['summary']['hosted_agents_created']}")
    print(f"output_text={report['test_call']['response']['output_text'] if report['test_call']['response'] else ''}")
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
