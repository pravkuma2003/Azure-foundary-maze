#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPORT_ROOT = PROJECT_ROOT / "exports" / "multi-agent-reasoning-from-scratch-public"
HOSTED_ROOT = PROJECT_ROOT / "hosted" / "phase7-monolithic-maze-agent"
RUNS_DIR = PROJECT_ROOT / "runs"
VISUALS_DIR = PROJECT_ROOT / "visuals"
PROGRESS_PATH = PROJECT_ROOT / "PROGRESS.html"
PHASE4_REPORT = RUNS_DIR / "phase4_foundry_project_model.json"
PHASE7_DEPLOYMENT_OBSERVATION = RUNS_DIR / "phase7_hosted_deployment_observation.json"


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_command(args: list[str], cwd: Path, timeout: int = 90) -> dict[str, Any]:
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


def build_provider_config_source() -> str:
    return """#!/usr/bin/env python3
from __future__ import annotations

import os
from dataclasses import dataclass


TOKEN_RESOURCE = "https://ai.azure.com"
LOCAL_BASE_URL = "http://localhost:4000/v1"


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    base_url: str
    api_key: str
    model: str
    model_note: str
    temperature: float


def build_provider_config(provider: str, model: str | None = None) -> ProviderConfig:
    normalized = provider.strip().lower()
    if normalized == "local":
        selected_model = model or "fast"
        return ProviderConfig(
            provider="local",
            base_url=os.environ.get("OPENAI_BASE_URL") or LOCAL_BASE_URL,
            api_key=os.environ.get("OPENAI_API_KEY") or "anything",
            model=selected_model,
            model_note=_local_model_note(selected_model),
            temperature=0.2,
        )
    if normalized == "foundry":
        deployment = model or os.environ.get("FOUNDRY_MODEL_DEPLOYMENT") or "gpt41mini-maze"
        project_endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "").rstrip("/")
        base_url = os.environ.get("FOUNDRY_OPENAI_BASE_URL") or (f"{project_endpoint}/openai/v1" if project_endpoint else "")
        if not base_url:
            raise ValueError("FOUNDRY_PROJECT_ENDPOINT or FOUNDRY_OPENAI_BASE_URL is required for provider='foundry'")
        return ProviderConfig(
            provider="foundry",
            base_url=base_url,
            api_key=os.environ.get("FOUNDRY_API_KEY") or _get_azure_ai_token(),
            model=deployment,
            model_note="Azure Foundry project model deployment",
            temperature=0.0,
        )
    raise ValueError(f"unknown provider: {provider!r}; expected 'local' or 'foundry'")


def _get_azure_ai_token() -> str:
    try:
        from azure.identity import DefaultAzureCredential
    except Exception as exc:
        raise RuntimeError("azure-identity is required for Foundry provider authentication when FOUNDRY_API_KEY is not set") from exc

    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    return credential.get_token(f"{TOKEN_RESOURCE}/.default").token


def _local_model_note(model: str) -> str:
    notes = {
        "fast": "LiteLLM alias for qwen3:14b on a local model host",
        "reasoner": "LiteLLM alias for deepseek-r1:14b on a local model host",
        "research": "LiteLLM alias for qwen3.6:27b on a local model host",
    }
    return notes.get(model, "custom local OpenAI-compatible model name")
"""


def build_main_source() -> str:
    return """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.reasoning_curriculum import run_phase


def run_monolithic_maze(*, provider: str, model: str | None, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    return run_phase(
        phase_number=7,
        provider=provider,
        model=model,
        trace_path=output_dir / "phase7_monolithic_trace.json",
        html_path=output_dir / "PHASE7_MONOLITHIC_VISUAL.html",
        progress_path=output_dir / "PROGRESS.html",
    )


def default_output_dir() -> Path:
    return Path(os.environ.get("MAZE_OUTPUT_DIR") or "/tmp/maze-agent-artifacts")


def invoke(request: dict[str, Any] | str | None = None) -> dict[str, Any]:
    payload: dict[str, Any]
    if isinstance(request, str):
        try:
            payload = json.loads(request)
        except json.JSONDecodeError:
            payload = {"prompt": request}
    else:
        payload = request or {}

    provider = payload.get("provider") or os.environ.get("MAZE_PROVIDER") or "foundry"
    model = payload.get("model") or os.environ.get("FOUNDRY_MODEL_DEPLOYMENT") or os.environ.get("MAZE_MODEL")
    output_dir = Path(payload.get("output_dir") or str(default_output_dir()))
    trace = run_monolithic_maze(provider=provider, model=model, output_dir=output_dir)
    return {
        "status": "complete",
        "phase": trace.get("phase"),
        "concept": trace.get("concept"),
        "trace": trace,
        "summary": trace.get("summary"),
        "artifacts": {
            "trace": str(output_dir / "phase7_monolithic_trace.json"),
            "visual": str(output_dir / "PHASE7_MONOLITHIC_VISUAL.html"),
            "progress": str(output_dir / "PROGRESS.html"),
        },
    }


def extract_text(request: Any, current_input: str) -> str:
    if current_input:
        return current_input
    return "Run the Phase 7 monolithic maze validation and return the summary."


def run_server() -> None:
    from azure.ai.agentserver.responses import (
        CreateResponse,
        ResponseContext,
        ResponsesAgentServerHost,
        ResponsesServerOptions,
        TextResponse,
    )

    app = ResponsesAgentServerHost(
        options=ResponsesServerOptions(default_fetch_history_count=5),
    )

    @app.response_handler
    async def handler(
        request: CreateResponse,
        context: ResponseContext,
        _cancellation_signal: asyncio.Event,
    ):
        user_input = await context.get_input_text() or ""
        payload = {
            "prompt": extract_text(request, user_input),
            "provider": os.environ.get("MAZE_PROVIDER", "foundry"),
            "model": os.environ.get("FOUNDRY_MODEL_DEPLOYMENT") or os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
            "output_dir": str(default_output_dir()),
        }
        result = await asyncio.get_running_loop().run_in_executor(None, lambda: invoke(payload))
        summary = result.get("summary") or {}
        response = {
            "status": result.get("status"),
            "phase": result.get("phase"),
            "concept": result.get("concept"),
            "trace": result.get("trace"),
            "llm_call_budget_used": summary.get("llm_call_budget_used"),
            "agent_count": summary.get("agent_count"),
            "maze_tool_calls": summary.get("maze_tool_calls"),
            "artifacts": result.get("artifacts"),
            "note": "Monolithic hosted runtime executed agents, worker logic, orchestrator, maze tools, and in-process memory together.",
        }
        return TextResponse(context, request, text=json.dumps(response, indent=2))

    app.run()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the monolithic hosted maze-agent package.")
    parser.add_argument("--once", action="store_true", help="Run once as a CLI command instead of starting the hosted-agent server.")
    parser.add_argument("--provider", default=os.environ.get("MAZE_PROVIDER", "foundry"), choices=["test", "local", "foundry"])
    parser.add_argument("--model", default=os.environ.get("FOUNDRY_MODEL_DEPLOYMENT") or os.environ.get("MAZE_MODEL"))
    parser.add_argument("--output-dir", default=str(default_output_dir()))
    args = parser.parse_args()
    if not args.once:
        run_server()
        return 0
    result = invoke({"provider": args.provider, "model": args.model, "output_dir": args.output_dir})
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


def build_azure_yaml(project_endpoint: str, deployment_name: str) -> str:
    return f"""name: phase7-monolithic-maze-agent
metadata:
  template: phase7-monolithic-maze-agent@0.1.0
services:
  maze-migration-lab:
    host: azure.ai.project
    endpoint: {project_endpoint}
  maze-monolithic-agent:
    project: .
    host: azure.ai.agent
    language: python
    uses:
      - maze-migration-lab
    env:
      AZURE_AI_MODEL_DEPLOYMENT_NAME: {deployment_name}
      FOUNDRY_MODEL_DEPLOYMENT: {deployment_name}
      FOUNDRY_PROJECT_ENDPOINT: {project_endpoint}
      MAZE_PROVIDER: foundry
    codeConfiguration:
      dependencyResolution: remote_build
      entryPoint: main.py
      runtime: python_3_13
    container:
      resources:
        cpu: "0.5"
        memory: "1Gi"
    kind: hosted
    name: maze-monolithic-agent
    protocols:
      - protocol: responses
        version: 2.0.0
    startupCommand: python main.py --provider foundry
"""


def build_readme(project_endpoint: str, deployment_name: str) -> str:
    return f"""# Phase 7 Monolithic Maze Agent

This package is the first hosted-runtime migration step.

It moves the app boundary as one unit:

```text
Pydantic AI Analyst
Pydantic AI worker logic
deterministic orchestrator
maze tools
team memory / trace state
```

The package intentionally does not split tools, memory, or workers into
separate Azure-native services yet.

## Local Package Validation

```bash
python3 main.py --provider test --output-dir artifacts
```

## Foundry Runtime Target

```text
Project endpoint: {project_endpoint}
Model deployment: {deployment_name}
Provider: foundry
```

Authentication uses Azure identity in hosted/runtime environments. No API keys
are checked into this package.
"""


def copy_exported_maze_runtime() -> None:
    if not EXPORT_ROOT.exists():
        raise RuntimeError(f"exported maze app is missing: {EXPORT_ROOT}")

    HOSTED_ROOT.mkdir(parents=True, exist_ok=True)
    for child in ("src", "scripts"):
        shutil.copytree(EXPORT_ROOT / child, HOSTED_ROOT / child, dirs_exist_ok=True)

    for name in (
        "README.md",
        "ROADMAP.md",
        "SPEC.md",
        "PHASE1_REASONING_BOTTLENECK.md",
        "PHASE2_WORKER_AGENT.md",
        "PHASE3_GLOBAL_LOCAL_PLANNING.md",
        "PHASE4_TOOL_OWNERSHIP.md",
        "PHASE5_INDEPENDENT_LOCAL_MEMORY.md",
        "PHASE6_SHARED_KNOWLEDGE_SYNCHRONIZATION.md",
        "PHASE7_SECOND_WORKER_AGENT.md",
    ):
        source = EXPORT_ROOT / name
        if source.exists():
            shutil.copy2(source, HOSTED_ROOT / name)


def build_hosted_package(project_endpoint: str, deployment_name: str) -> list[str]:
    copy_exported_maze_runtime()
    write_text(HOSTED_ROOT / "src" / "provider_config.py", build_provider_config_source())
    write_text(HOSTED_ROOT / "main.py", build_main_source())
    write_text(
        HOSTED_ROOT / "requirements.txt",
        "pydantic-ai-slim[openai]>=2.35.0\nazure-ai-agentserver-responses>=2.1.0b2\nazure-ai-projects>=2.0.1\nazure-identity>=1.23.0\n",
    )
    write_text(HOSTED_ROOT / "azure.yaml", build_azure_yaml(project_endpoint, deployment_name))
    write_text(HOSTED_ROOT / ".gitignore", "__pycache__/\n*.pyc\n.env\n.venv/\n.azure/\nartifacts/\n")
    write_text(HOSTED_ROOT / "README.md", build_readme(project_endpoint, deployment_name))
    return [
        "main.py",
        "requirements.txt",
        "azure.yaml",
        "src/reasoning_curriculum.py",
        "src/provider_config.py",
    ]


def validate_hosted_package() -> dict[str, Any]:
    output_dir = PROJECT_ROOT / "runs" / "phase7_hosted_package_validation"
    command = [sys.executable, "main.py", "--once", "--provider", "test", "--output-dir", str(output_dir)]
    result = run_command(command, cwd=HOSTED_ROOT, timeout=180)
    trace_path = output_dir / "phase7_monolithic_trace.json"
    trace = load_json(trace_path)
    return {
        "command": command,
        "returncode": result["returncode"],
        "stdout_tail": result["stdout"][-1200:],
        "stderr_tail": result["stderr"][-1200:],
        "trace_created": trace_path.exists(),
        "trace_summary": (trace or {}).get("summary", {}),
        "artifact_dir": str(output_dir.relative_to(PROJECT_ROOT)),
    }


def detect_deploy_tooling() -> dict[str, Any]:
    azd_version = run_command(["azd", "version"], cwd=PROJECT_ROOT)
    ai_help = run_command(["azd", "ai", "agent", "--help"], cwd=HOSTED_ROOT)
    extension_status = "available" if ai_help["returncode"] == 0 else "missing_or_inactive"
    return {
        "azd_version": azd_version,
        "azd_ai_agent_help": {
            "returncode": ai_help["returncode"],
            "stdout_tail": ai_help["stdout"][-1200:],
            "stderr_tail": ai_help["stderr"][-1200:],
        },
        "foundry_agent_command_status": extension_status,
    }


def build_phase7_report() -> dict[str, Any]:
    phase4 = load_json(PHASE4_REPORT)
    if not phase4 or phase4.get("status") != "complete":
        raise RuntimeError("Phase 4 report is missing or incomplete; run Phase 4 first.")

    project_endpoint = phase4["resources"]["project"]["endpoint"]
    deployment_name = phase4["resources"]["model_deployment"]["name"]
    packaged_files = build_hosted_package(project_endpoint, deployment_name)
    validation = validate_hosted_package()
    tooling = detect_deploy_tooling()
    validation_ok = validation["returncode"] == 0 and validation["trace_created"]
    deploy_ready = tooling["foundry_agent_command_status"] == "available"

    status = "deployable_package_ready" if validation_ok and not deploy_ready else ("complete" if validation_ok else "action_required")
    blocker = "" if deploy_ready else "azd Foundry hosted-agent command is not available locally yet."
    deployment_observation = load_json(PHASE7_DEPLOYMENT_OBSERVATION)
    deployment = {
        "attempted": False,
        "status": "not_attempted",
        "blocker": blocker,
        "next_command_when_tooling_is_available": "azd deploy maze-monolithic-agent",
    }
    invocation = {"attempted": False, "status": "not_attempted"}
    boundary_hosted_agents_created = 0
    summary_hosted_agents_created = 0
    hosted_agent_versions_deployed: int | str = 0
    foundry_model_calls = 0
    estimated_cost = "zero model cost for package validation; hosted deployment not attempted"
    next_phase = "Enable Foundry hosted-agent tooling and deploy the monolithic package, or split the maze tool boundary after this package is deployed."
    if deployment_observation:
        status = deployment_observation.get("phase_status") or status
        deployment = deployment_observation.get("deployment") or deployment
        invocation = deployment_observation.get("invocation") or invocation
        boundary_hosted_agents_created = 1
        summary_hosted_agents_created = 1
        hosted_agent_versions_deployed = deployment.get("active_version") or 1
        foundry_model_calls = 1 if invocation.get("attempted") else 0
        estimated_cost = "hosted runtime deployed; model-backed invocation blocked before successful completion by managed identity RBAC"
        next_phase = "Approve hosted-agent managed identity model-inference RBAC, then rerun the hosted invocation."

    return {
        "course": "Azure Foundry Maze Migration From Scratch",
        "phase": 7,
        "phase_name": "Monolithic Foundry-Hosted Maze Runtime",
        "status": status,
        "learning_objective": "Move the existing agents, tools, worker logic, orchestrator, and in-process memory together behind one Foundry-hosted agent boundary.",
        "runtime_boundary": {
            "packaging_style": "monolithic hosted-agent source package",
            "agent_framework": "Pydantic AI",
            "included_reasoning_roles": ["Analyst Agent", "Worker Agent A", "Worker Agent B"],
            "included_deterministic_roles": ["Orchestrator", "Maze Tool", "Team Memory / trace state"],
            "azure_native_splitting_done": False,
            "hosted_agents_created": boundary_hosted_agents_created,
            "azure_resources_created": 0,
        },
        "foundry_target": {
            "project_endpoint": project_endpoint,
            "deployment_name": deployment_name,
            "hosted_agent_name": "maze-monolithic-agent",
            "resource_size": "500m CPU / 1Gi memory in package metadata",
            "auth_mode": "Azure identity at runtime; no checked-in API keys",
        },
        "package": {
            "path": str(HOSTED_ROOT.relative_to(PROJECT_ROOT)),
            "packaged_files": packaged_files,
            "entry_point": "main.py",
            "local_validation_provider": "test",
        },
        "validation": validation,
        "deploy_tooling": tooling,
        "deployment": deployment,
        "invocation": invocation,
        "summary": {
            "hosted_package_created": validation_ok,
            "local_package_validation_passed": validation_ok,
            "hosted_agents_created": summary_hosted_agents_created,
            "hosted_agent_versions_deployed": hosted_agent_versions_deployed,
            "azure_resources_created": 0,
            "foundry_model_calls": foundry_model_calls,
            "llm_calls_during_package_validation": 0,
            "estimated_cost": estimated_cost,
            "next_phase": next_phase,
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
    boundary = report["runtime_boundary"]
    target = report["foundry_target"]
    package = report["package"]
    validation = report["validation"]
    deployment = report["deployment"]
    invocation = report.get("invocation", {})
    tooling = report["deploy_tooling"]
    data = html.escape(json.dumps(report, indent=2, default=str))
    included_roles = "".join(f"<li>{html.escape(role)}</li>" for role in boundary["included_reasoning_roles"] + boundary["included_deterministic_roles"])
    packaged_files = "".join(f"<li>{html.escape(item)}</li>" for item in package["packaged_files"])
    deploy_blocker = deployment.get("blocker") or "Hosted deployment completed; model-backed invocation still needs managed-identity model permission."
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Azure Foundry Maze Migration - Phase 7</title>
  <style>
    :root {{ --bg:#f7f8fa; --panel:#fff; --text:#17202a; --muted:#5f6b7a; --line:#d9dee7; --blue:#285da8; --green:#1f6f5b; --amber:#9a6500; --shadow:0 10px 28px rgba(28,36,48,.08); }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:var(--text); background:var(--bg); line-height:1.5; }}
    main {{ width:min(1180px, calc(100% - 32px)); margin:0 auto; padding:32px 0 48px; }}
    header {{ display:grid; grid-template-columns:minmax(0,1fr) 330px; gap:20px; border-bottom:1px solid var(--line); padding-bottom:20px; margin-bottom:22px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(28px,4vw,42px); line-height:1.08; }}
    h2 {{ margin:0 0 12px; font-size:20px; }}
    h3 {{ margin:0 0 8px; font-size:16px; }}
    p {{ margin:0; color:var(--muted); }}
    a {{ color:var(--blue); font-weight:800; text-decoration:none; }}
    .panel,.summary,.flow-step {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; box-shadow:var(--shadow); padding:16px; }}
    .summary strong {{ display:block; font-size:26px; text-transform:capitalize; }}
    .stack {{ display:grid; gap:14px; }}
    .metrics {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }}
    .metric {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fff; }}
    .metric span,.flow-step span {{ display:block; color:var(--muted); font-size:12px; font-weight:800; text-transform:uppercase; }}
    .metric strong {{ display:block; margin-top:6px; font-size:26px; }}
    .flow {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; }}
    .flow-step {{ box-shadow:none; min-height:130px; border-left:5px solid var(--blue); }}
    .flow-step.local {{ border-left-color:var(--amber); }}
    .flow-step.done {{ border-left-color:var(--green); }}
    .two {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
    ul {{ margin:8px 0 0; padding-left:20px; color:#17202a; }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th,td {{ padding:9px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-size:12px; text-transform:uppercase; }}
    code {{ color:#111827; background:#eef2f7; padding:2px 5px; border-radius:4px; }}
    pre {{ overflow:auto; max-height:420px; padding:12px; background:#111827; color:#e5e7eb; border-radius:8px; font-size:12px; }}
    .note {{ border-left:5px solid var(--amber); background:#fff8e7; }}
    .pass {{ border-left:5px solid var(--green); background:#eef8f3; }}
    @media (max-width:980px) {{ header,.metrics,.flow,.two {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Phase 7 - Monolithic Hosted Runtime</h1>
        <p>Move agents, worker logic, tools, orchestrator, and in-process memory together behind one Foundry-hosted boundary.</p>
      </div>
      <aside class="summary">
        <span>Status</span>
        <strong>{html.escape(report['status'].replace('_', ' '))}</strong>
        <p>Hosted agents created: {summary['hosted_agents_created']}.</p>
      </aside>
    </header>
    <div class="stack">
      <section class="panel">
        <h2>Phase Metrics</h2>
        <div class="metrics">
          <div class="metric"><span>Package Created</span><strong>{'yes' if summary['hosted_package_created'] else 'no'}</strong></div>
          <div class="metric"><span>Local Validation</span><strong>{'pass' if summary['local_package_validation_passed'] else 'fail'}</strong></div>
          <div class="metric"><span>Foundry Calls</span><strong>{summary['foundry_model_calls']}</strong></div>
          <div class="metric"><span>Hosted Agents</span><strong>{summary['hosted_agents_created']}</strong></div>
        </div>
      </section>
      <section class="panel">
        <h2>Hosted Boundary</h2>
        <div class="flow">
          <article class="flow-step local"><span>1. Existing App</span><h3>Maze runtime</h3><p>The exported local curriculum remains the source of truth.</p></article>
          <article class="flow-step"><span>2. Package</span><h3>One source bundle</h3><p>Agents, tools, workers, orchestrator, and memory are carried together.</p></article>
          <article class="flow-step"><span>3. Foundry Host</span><h3>One hosted agent</h3><p>The package is shaped for a minimal hosted-agent runtime.</p></article>
          <article class="flow-step done"><span>4. Later Split</span><h3>Azure-native pieces</h3><p>Tool, memory, and worker splitting are intentionally deferred.</p></article>
        </div>
      </section>
      <section class="two">
        <article class="panel pass">
          <h2>Included Together</h2>
          <ul>{included_roles}</ul>
        </article>
        <article class="panel">
          <h2>Package Files</h2>
          <p><code>{html.escape(package['path'])}</code></p>
          <ul>{packaged_files}</ul>
        </article>
      </section>
      <section class="panel">
        <h2>Local Package Validation</h2>
        <table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{table_rows(validation)}</tbody></table>
      </section>
      <section class="panel note">
        <h2>Deployment Status</h2>
        <p>{html.escape(deploy_blocker)}</p>
        <p>Command status: {html.escape(tooling['foundry_agent_command_status'])}. Deployment status: {html.escape(str(deployment.get('status')))}.</p>
      </section>
      <section class="panel note">
        <h2>Hosted Invocation</h2>
        <table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{table_rows(invocation)}</tbody></table>
      </section>
      <section class="panel">
        <h2>Runtime Boundary</h2>
        <table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{table_rows(boundary)}</tbody></table>
      </section>
      <section class="panel">
        <h2>Foundry Target</h2>
        <table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{table_rows(target)}</tbody></table>
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
        ("Phase 6: Pydantic AI Analyst Agent on Foundry Model", RUNS_DIR / "phase6_foundry_analyst_agent.json", "visuals/PHASE6_VISUAL.html", "PHASE6_FOUNDRY_ANALYST_AGENT.md", "PHASE6_VALIDATION.md"),
    ]
    cards = []
    for title, path, visual, notes, validation in phase_files:
        item = load_json(path)
        if not item:
            continue
        summary = item.get("summary", {})
        detail_parts = []
        for key in ("files_scanned", "blocking_findings_after_export", "new_resources_created", "inference_calls_made", "foundry_model_calls", "hosted_agents_created"):
            if key in summary:
                detail_parts.append(f"{key}: {summary[key]}")
        detail = ", ".join(detail_parts)
        cards.append(
            f"""<section class="card"><h2>{html.escape(title)}</h2><p>Status: {html.escape(str(item.get('status')))}. {html.escape(detail)}</p><p><a href="{visual}">Open visual</a> | <a href="{notes}">Notes</a> | <a href="{validation}">Validation</a></p></section>"""
        )

    s = report["summary"]
    cards.append(
        f"""<section class="card current"><h2>Phase 7: Monolithic Foundry-Hosted Maze Runtime</h2><p>Status: {html.escape(report['status'])}. Package created: {s['hosted_package_created']}. Local validation: {s['local_package_validation_passed']}. Hosted agents: {s['hosted_agents_created']}.</p><p><a href="visuals/PHASE7_VISUAL.html">Open visual</a> | <a href="PHASE7_MONOLITHIC_HOSTED_RUNTIME.md">Notes</a> | <a href="PHASE7_VALIDATION.md">Validation</a></p></section>"""
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
    <section class="card"><h2>Cost Policy</h2><p>Personal-subscription learning lab: one Foundry project, one model deployment, one hosted runtime first, short traces, and no extra Azure services until a phase teaches them.</p></section>
    {''.join(cards)}
    <section class="card"><h2>Next</h2><p>{html.escape(s['next_phase'])}</p></section>
  </main>
</body>
</html>
"""


def write_docs() -> None:
    write_text(
        PROJECT_ROOT / "PHASE7_MONOLITHIC_HOSTED_RUNTIME.md",
        """# Phase 7 - Monolithic Foundry-Hosted Maze Runtime

## Objective

Move the local maze application's agent, tool, worker, orchestrator, and memory
logic together into one Foundry-hosted runtime package.

This phase teaches runtime migration, not Azure-native decomposition.

## What Moves Together

```text
Pydantic AI Analyst
Pydantic AI Worker Agent A
Pydantic AI Worker Agent B
deterministic orchestrator
Maze Tool validation
Team Memory / trace state
HTML/result generation
```

## What Does Not Move Yet

```text
Maze Tool is not a separate Foundry tool.
Team Memory is not Azure Storage or Cosmos DB.
Worker agents are not separate hosted agents.
Orchestrator is not an Azure workflow service.
```

## Why This Approach

The goal is to prove that the local app can cross the hosting boundary with
minimal architectural change. Once that works, later phases can split tools,
memory, and workers one at a time.

## Package

```text
hosted/phase7-monolithic-maze-agent
```

The package includes `azure.yaml`, `agent.yaml`, `main.py`, requirements, and a
copy of the public-safe maze runtime source.
""",
    )
    write_text(
        PROJECT_ROOT / "PHASE7_VALIDATION.md",
        """# Phase 7 Validation

## Expected Result

```text
Hosted package is created.
The package runs locally with provider=test.
The package includes agents, tools, worker logic, orchestrator, and memory state.
No Foundry model calls are made during package validation.
No hosted agent is created until Foundry hosted-agent tooling is active.
```

## Validation Command

```bash
python3 scripts/phase7_monolithic_hosted_runtime.py
```

## Generated Artifacts

```text
runs/phase7_monolithic_hosted_runtime.json
runs/phase7_hosted_package_validation/
visuals/PHASE7_VISUAL.html
hosted/phase7-monolithic-maze-agent/
PROGRESS.html
```
""",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and validate Phase 7 monolithic hosted maze runtime package.")
    parser.parse_args()
    write_docs()
    report = build_phase7_report()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    VISUALS_DIR.mkdir(parents=True, exist_ok=True)
    write_text(RUNS_DIR / "phase7_monolithic_hosted_runtime.json", json.dumps(report, indent=2, default=str) + "\n")
    write_text(VISUALS_DIR / "PHASE7_VISUAL.html", render_phase_html(report))
    write_text(PROGRESS_PATH, render_progress_html(report))
    print(f"phase={report['phase']}")
    print(f"status={report['status']}")
    print(f"hosted_package_created={report['summary']['hosted_package_created']}")
    print(f"local_package_validation_passed={report['summary']['local_package_validation_passed']}")
    print(f"foundry_agent_command_status={report['deploy_tooling']['foundry_agent_command_status']}")
    print(f"hosted_agents_created={report['summary']['hosted_agents_created']}")
    if report["deployment"].get("blocker"):
        print(f"deployment_blocker={report['deployment']['blocker']}")
    if report.get("invocation", {}).get("status"):
        print(f"invocation_status={report['invocation']['status']}")
    return 0 if report["summary"]["local_package_validation_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
