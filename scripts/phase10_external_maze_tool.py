#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOL_ROOT = PROJECT_ROOT / "tools" / "phase10-maze-tool-function"
HOSTED_ROOT = PROJECT_ROOT / "hosted" / "phase7-monolithic-maze-agent"
RUNS_DIR = PROJECT_ROOT / "runs"
VISUALS_DIR = PROJECT_ROOT / "visuals"
PROGRESS_PATH = PROJECT_ROOT / "PROGRESS.html"
WEBUI_SAMPLE_TRACE = PROJECT_ROOT / "webui" / "phase8-azure-webui" / "static" / "sample_trace.json"
RESOURCE_GROUP = "rg-maze-foundry-lab"
FUNCTION_LOCATION = "eastus2"
TOOL_STORAGE_ACCOUNT = "mazetoolpravada483"
TOOL_FUNCTION_APP_NAME = "maze-tool-func-prav-ada483"
WEBUI_FUNCTION_APP_NAME = "maze-webui-func-prav-ada483"
TOOL_BASE_URL = f"https://{TOOL_FUNCTION_APP_NAME}.azurewebsites.net"
PACKAGE_CONTAINER = "packages"
PACKAGE_BLOB = "phase10_maze_tool_function.zip"


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_command(args: list[str], cwd: Path, timeout: int = 300, redact_stdout: bool = False) -> dict[str, Any]:
    try:
        completed = subprocess.run(args, cwd=cwd, check=False, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return {"command": args[:1], "returncode": 127, "stdout": "", "stderr": f"{args[0]} not found"}
    except subprocess.TimeoutExpired as exc:
        return {"command": args[:1], "returncode": 124, "stdout": exc.stdout or "", "stderr": exc.stderr or "timed out"}
    stdout = "[redacted]" if redact_stdout and completed.stdout else completed.stdout.strip()
    return {
        "command": _safe_command(args),
        "returncode": completed.returncode,
        "stdout": stdout,
        "stderr": completed.stderr.strip(),
    }


def _safe_command(args: list[str]) -> list[str]:
    safe = []
    hide_next = False
    for arg in args:
        if hide_next:
            safe.append("[redacted]")
            hide_next = False
            continue
        safe.append(arg)
        if arg in {"--account-key", "--settings", "MAZE_TOOL_KEY"}:
            hide_next = True
    return safe


def summarize(result: dict[str, Any]) -> dict[str, Any]:
    stdout = _redact_sensitive_text(result["stdout"])
    stderr = _redact_sensitive_text(result["stderr"])
    return {
        "returncode": result["returncode"],
        "stdout_tail": stdout[-1200:],
        "stderr_tail": stderr[-1200:],
        "command": result["command"],
    }


def _redact_sensitive_text(text: str) -> str:
    redacted = re.sub(r'("MAZE_TOOL_KEY"\s*:\s*")[^"]+(")', r"\1[redacted]\2", text)
    redacted = re.sub(r'(MAZE_TOOL_KEY[=:]\s*)[^\s,}]+', r"\1[redacted]", redacted)
    redacted = re.sub(r'(sig=)[^"&\s]+', r"\1[redacted]", redacted)
    return redacted


def vendor_dependencies() -> dict[str, Any]:
    target = TOOL_ROOT / ".python_packages" / "lib" / "site-packages"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    return run_command(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--target",
            str(target),
            "-r",
            str(TOOL_ROOT / "requirements.txt"),
        ],
        TOOL_ROOT,
        timeout=300,
    )


def zip_tool() -> Path:
    zip_path = RUNS_DIR / "phase10_maze_tool_function.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in TOOL_ROOT.rglob("*"):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts:
                continue
            if path.suffix == ".pyc":
                continue
            zf.write(path, path.relative_to(TOOL_ROOT))
    return zip_path


def create_or_update_tool_function(zip_path: Path) -> dict[str, Any]:
    storage = run_command(
        [
            "az",
            "storage",
            "account",
            "create",
            "--resource-group",
            RESOURCE_GROUP,
            "--name",
            TOOL_STORAGE_ACCOUNT,
            "--location",
            FUNCTION_LOCATION,
            "--sku",
            "Standard_LRS",
            "--output",
            "json",
        ],
        PROJECT_ROOT,
        timeout=300,
    )
    create = run_command(
        [
            "az",
            "functionapp",
            "create",
            "--resource-group",
            RESOURCE_GROUP,
            "--consumption-plan-location",
            FUNCTION_LOCATION,
            "--runtime",
            "python",
            "--runtime-version",
            "3.12",
            "--functions-version",
            "4",
            "--os-type",
            "Linux",
            "--storage-account",
            TOOL_STORAGE_ACCOUNT,
            "--name",
            TOOL_FUNCTION_APP_NAME,
            "--output",
            "json",
        ],
        PROJECT_ROOT,
        timeout=300,
    )
    settings = run_command(
        [
            "az",
            "functionapp",
            "config",
            "appsettings",
            "set",
            "--resource-group",
            RESOURCE_GROUP,
            "--name",
            TOOL_FUNCTION_APP_NAME,
            "--settings",
            "FUNCTIONS_WORKER_RUNTIME=python",
            "SCM_DO_BUILD_DURING_DEPLOYMENT=false",
            "--output",
            "json",
        ],
        PROJECT_ROOT,
        timeout=300,
    )
    deploy = deploy_run_from_package(zip_path)
    restart = run_command(
        [
            "az",
            "functionapp",
            "restart",
            "--resource-group",
            RESOURCE_GROUP,
            "--name",
            TOOL_FUNCTION_APP_NAME,
            "--output",
            "json",
        ],
        PROJECT_ROOT,
        timeout=300,
    )
    return {
        "storage": summarize(storage),
        "functionapp_create": summarize(create),
        "settings": summarize(settings),
        "package_deploy": deploy,
        "restart": summarize(restart),
        "status": "deployed" if storage["returncode"] == 0 and create["returncode"] == 0 and settings["returncode"] == 0 and deploy["status"] == "deployed" and restart["returncode"] == 0 else "action_required",
    }


def deploy_run_from_package(zip_path: Path) -> dict[str, Any]:
    key = run_command(
        [
            "az",
            "storage",
            "account",
            "keys",
            "list",
            "--resource-group",
            RESOURCE_GROUP,
            "--account-name",
            TOOL_STORAGE_ACCOUNT,
            "--query",
            "[0].value",
            "--output",
            "tsv",
        ],
        PROJECT_ROOT,
        timeout=300,
        redact_stdout=True,
    )
    actual_key = subprocess.run(
        [
            "az",
            "storage",
            "account",
            "keys",
            "list",
            "--resource-group",
            RESOURCE_GROUP,
            "--account-name",
            TOOL_STORAGE_ACCOUNT,
            "--query",
            "[0].value",
            "--output",
            "tsv",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    ).stdout.strip()
    if key["returncode"] != 0 or not actual_key:
        return {"status": "action_required", "storage_key": summarize(key), "error": "could not read storage key"}
    container = run_command(
        [
            "az",
            "storage",
            "container",
            "create",
            "--account-name",
            TOOL_STORAGE_ACCOUNT,
            "--account-key",
            actual_key,
            "--name",
            PACKAGE_CONTAINER,
            "--output",
            "json",
        ],
        PROJECT_ROOT,
        timeout=300,
    )
    upload = run_command(
        [
            "az",
            "storage",
            "blob",
            "upload",
            "--account-name",
            TOOL_STORAGE_ACCOUNT,
            "--account-key",
            actual_key,
            "--container-name",
            PACKAGE_CONTAINER,
            "--name",
            PACKAGE_BLOB,
            "--file",
            str(zip_path),
            "--overwrite",
            "--output",
            "json",
        ],
        PROJECT_ROOT,
        timeout=300,
    )
    expiry = (datetime.now(timezone.utc) + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sas = run_command(
        [
            "az",
            "storage",
            "blob",
            "generate-sas",
            "--account-name",
            TOOL_STORAGE_ACCOUNT,
            "--account-key",
            actual_key,
            "--container-name",
            PACKAGE_CONTAINER,
            "--name",
            PACKAGE_BLOB,
            "--permissions",
            "r",
            "--expiry",
            expiry,
            "--output",
            "tsv",
        ],
        PROJECT_ROOT,
        timeout=300,
        redact_stdout=True,
    )
    actual_sas = subprocess.run(
        [
            "az",
            "storage",
            "blob",
            "generate-sas",
            "--account-name",
            TOOL_STORAGE_ACCOUNT,
            "--account-key",
            actual_key,
            "--container-name",
            PACKAGE_CONTAINER,
            "--name",
            PACKAGE_BLOB,
            "--permissions",
            "r",
            "--expiry",
            expiry,
            "--output",
            "tsv",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    ).stdout.strip()
    if sas["returncode"] != 0 or not actual_sas:
        return {"status": "action_required", "storage_key": summarize(key), "container": summarize(container), "upload": summarize(upload), "sas": summarize(sas), "error": "could not create package SAS"}
    package_url = f"https://{TOOL_STORAGE_ACCOUNT}.blob.core.windows.net/{PACKAGE_CONTAINER}/{PACKAGE_BLOB}?{actual_sas}"
    app_settings = run_command(
        [
            "az",
            "functionapp",
            "config",
            "appsettings",
            "set",
            "--resource-group",
            RESOURCE_GROUP,
            "--name",
            TOOL_FUNCTION_APP_NAME,
            "--settings",
            f"WEBSITE_RUN_FROM_PACKAGE={package_url}",
            "FUNCTIONS_WORKER_RUNTIME=python",
            "SCM_DO_BUILD_DURING_DEPLOYMENT=false",
            "--output",
            "json",
        ],
        PROJECT_ROOT,
        timeout=300,
    )
    return {
        "status": "deployed" if all(item["returncode"] == 0 for item in (key, container, upload, sas, app_settings)) else "action_required",
        "storage_key": summarize(key),
        "container": summarize(container),
        "upload": summarize(upload),
        "sas": summarize(sas),
        "settings": summarize(app_settings),
        "package_blob": f"https://{TOOL_STORAGE_ACCOUNT}.blob.core.windows.net/{PACKAGE_CONTAINER}/{PACKAGE_BLOB}",
    }


def get_function_key() -> tuple[str, dict[str, Any]]:
    result = run_command(
        [
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
        ],
        PROJECT_ROOT,
        timeout=300,
        redact_stdout=True,
    )
    actual = subprocess.run(
        [
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
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return actual.stdout.strip(), summarize(result)


def post_json(url: str, payload: dict[str, Any], key: str | None = None) -> tuple[int, dict[str, Any]]:
    headers = {"Content-Type": "application/json"}
    if key:
        headers["x-functions-key"] = key
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body[:1200]}
        return int(exc.code), parsed


def get_json(url: str) -> tuple[int, dict[str, Any]]:
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body[:1200]}
        return int(exc.code), parsed


def validate_tool_function(function_key: str) -> dict[str, Any]:
    health_status, health = get_json(f"{TOOL_BASE_URL}/api/maze/health")
    openapi_status, openapi = get_json(f"{TOOL_BASE_URL}/api/maze/openapi.json")
    inspect_status, inspect = post_json(
        f"{TOOL_BASE_URL}/api/maze/inspect",
        {"maze_id": "maze_a", "position": [0, 0]},
        function_key,
    )
    move_status, move = post_json(
        f"{TOOL_BASE_URL}/api/maze/move",
        {"maze_id": "maze_a", "position": [0, 0], "move": "east"},
        function_key,
    )
    return {
        "health_status": health_status,
        "health": health,
        "openapi_status": openapi_status,
        "openapi_title": ((openapi.get("info") or {}).get("title") if isinstance(openapi, dict) else None),
        "inspect_status": inspect_status,
        "inspect": inspect,
        "move_status": move_status,
        "move": move,
        "passed": (
            health_status == 200
            and openapi_status == 200
            and inspect_status == 200
            and move_status == 200
            and inspect.get("legal_moves") == ["east"]
            and move.get("new_position") == [0, 1]
        ),
    }


def configure_hosted_agent_env(function_key: str) -> dict[str, Any]:
    base = run_command(["azd", "env", "set", "MAZE_TOOL_BASE_URL", TOOL_BASE_URL], HOSTED_ROOT, timeout=300)
    key = run_command(["azd", "env", "set", "MAZE_TOOL_KEY", function_key], HOSTED_ROOT, timeout=300, redact_stdout=True)
    return {"base_url": summarize(base), "function_key": summarize(key), "status": "configured" if base["returncode"] == 0 and key["returncode"] == 0 else "action_required"}


def deploy_hosted_agent() -> dict[str, Any]:
    deploy = run_command(["azd", "deploy", "maze-monolithic-agent", "--no-prompt", "--timeout", "1200"], HOSTED_ROOT, timeout=1500)
    show = run_command(["azd", "ai", "agent", "show", "maze-monolithic-agent", "--output", "json"], HOSTED_ROOT, timeout=300)
    agent_status: dict[str, Any] = {}
    try:
        agent_status = json.loads(show["stdout"])
    except json.JSONDecodeError:
        agent_status = {}
    return {
        "deploy": summarize(deploy),
        "show": summarize(show),
        "active_version": agent_status.get("version"),
        "status": "deployed" if deploy["returncode"] == 0 and agent_status.get("status") == "active" else "action_required",
    }


def validate_live_webui() -> dict[str, Any]:
    status, payload = post_json(f"https://{WEBUI_FUNCTION_APP_NAME}.azurewebsites.net/api/run", {}, None)
    trace = payload.get("trace") or {}
    summary = trace.get("summary") or {}
    events = trace.get("events") or []
    return {
        "status_code": status,
        "source": payload.get("source"),
        "provider": (trace.get("provider") or {}).get("provider"),
        "model": (trace.get("provider") or {}).get("model"),
        "llm_calls": summary.get("llm_call_budget_used"),
        "external_maze_tool_enabled": summary.get("external_maze_tool_enabled"),
        "external_maze_tool_calls": summary.get("external_maze_tool_calls"),
        "external_event_count": sum(1 for event in events if event.get("tool_runtime") == "external-http"),
        "maze_tool_boundary": summary.get("maze_tool_boundary_name"),
        "events": len(events),
        "passed": status == 200 and payload.get("source") == "foundry-hosted-agent" and summary.get("external_maze_tool_enabled") is True,
    }


def rebuild_webui_sample_from_external_tool(function_key: str) -> dict[str, Any]:
    env = {
        "MAZE_TOOL_BASE_URL": TOOL_BASE_URL,
        "MAZE_TOOL_KEY": function_key,
    }
    command = [
        sys.executable,
        "main.py",
        "--once",
        "--provider",
        "test",
        "--output-dir",
        str(RUNS_DIR / "phase10_external_tool_sample"),
    ]
    completed = subprocess.run(
        command,
        cwd=HOSTED_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
        env={**dict(**__import__("os").environ), **env},
    )
    trace_path = RUNS_DIR / "phase10_external_tool_sample" / "phase7_monolithic_trace.json"
    trace = load_json(trace_path) or {}
    if trace_path.exists():
        WEBUI_SAMPLE_TRACE.parent.mkdir(parents=True, exist_ok=True)
        WEBUI_SAMPLE_TRACE.write_text(trace_path.read_text(encoding="utf-8"), encoding="utf-8")
    return {
        "returncode": completed.returncode,
        "trace_created": trace_path.exists(),
        "external_event_count": sum(1 for event in trace.get("events", []) if event.get("tool_runtime") == "external-http"),
        "summary": trace.get("summary", {}),
        "sample_trace_refreshed": WEBUI_SAMPLE_TRACE.exists() and trace_path.exists(),
    }


def build_report(deploy: bool, deploy_hosted: bool, update_sample: bool) -> dict[str, Any]:
    py_files = [
        str(path.relative_to(TOOL_ROOT))
        for path in TOOL_ROOT.rglob("*.py")
        if ".python_packages" not in path.parts and "__pycache__" not in path.parts
    ]
    compile_tool = run_command([sys.executable, "-m", "py_compile", *py_files], TOOL_ROOT)
    vendor = vendor_dependencies()
    zip_path = zip_tool()
    deployment: dict[str, Any] = {"attempted": False, "status": "not_attempted"}
    key_result: dict[str, Any] = {"attempted": False}
    tool_validation: dict[str, Any] = {"attempted": False, "passed": False}
    hosted_env: dict[str, Any] = {"attempted": False, "status": "not_attempted"}
    hosted_deploy: dict[str, Any] = {"attempted": False, "status": "not_attempted"}
    sample_update: dict[str, Any] = {"attempted": False}
    live_validation: dict[str, Any] = {"attempted": False, "passed": False}
    function_key = ""

    if deploy:
        deployment = create_or_update_tool_function(zip_path)
        function_key, key_result = get_function_key()
        tool_validation = validate_tool_function(function_key) if function_key else {"attempted": True, "passed": False, "error": "function key unavailable"}
        if update_sample and function_key:
            sample_update = rebuild_webui_sample_from_external_tool(function_key)
        if deploy_hosted and function_key:
            hosted_env = configure_hosted_agent_env(function_key)
            hosted_deploy = deploy_hosted_agent()
            live_validation = validate_live_webui()

    passed = compile_tool["returncode"] == 0 and (not deploy or (deployment.get("status") == "deployed" and tool_validation.get("passed")))
    if deploy_hosted:
        passed = passed and hosted_deploy.get("status") == "deployed" and live_validation.get("passed")
    return {
        "course": "Azure Foundry Maze Migration From Scratch",
        "phase": 10,
        "phase_name": "External Azure Function Maze Tool",
        "status": "complete" if passed else "action_required",
        "learning_objective": "Move the Maze Tool from an in-package program boundary to a separately hosted Azure Function tool while keeping the agent contract stable.",
        "architecture": {
            "before": "Foundry hosted agent imported MazeToolProgram from its own source package.",
            "after": "Foundry hosted agent calls Maze Tool over HTTP using the same inspect/move contract.",
            "external_tool_service": TOOL_FUNCTION_APP_NAME,
            "webui_service": WEBUI_FUNCTION_APP_NAME,
            "auth": "Azure Functions function key stored outside source and passed to hosted agent as an environment variable.",
        },
        "tool_contract": {
            "openapi": f"{TOOL_BASE_URL}/api/maze/openapi.json",
            "health": f"{TOOL_BASE_URL}/api/maze/health",
            "inspect": f"{TOOL_BASE_URL}/api/maze/inspect",
            "move": f"{TOOL_BASE_URL}/api/maze/move",
        },
        "package": {
            "source": str(TOOL_ROOT.relative_to(PROJECT_ROOT)),
            "zip": str(zip_path.relative_to(PROJECT_ROOT)),
            "compile": summarize(compile_tool),
            "vendor_dependencies": summarize(vendor),
        },
        "deployment": deployment,
        "function_key": key_result,
        "tool_validation": tool_validation,
        "hosted_agent_environment": hosted_env,
        "hosted_agent_deployment": hosted_deploy,
        "webui_sample_update": sample_update,
        "live_webui_validation": live_validation,
        "summary": {
            "external_maze_tool_created": deploy and deployment.get("status") == "deployed",
            "external_maze_tool_validated": bool(tool_validation.get("passed")),
            "hosted_agent_uses_external_tool": bool(live_validation.get("external_maze_tool_enabled")),
            "external_maze_tool_calls_observed": live_validation.get("external_maze_tool_calls") or live_validation.get("external_event_count") or 0,
            "new_azure_resources_created": 2 if deploy else 0,
            "new_function_apps_created": 1 if deploy else 0,
            "new_storage_accounts_created": 1 if deploy else 0,
            "llm_calls_observed": live_validation.get("llm_calls") or 0,
            "additional_idle_cost": "Function App Consumption execution remains near zero at lab scale; new Standard_LRS storage adds small storage cost.",
            "next_phase": "Move Worker Agent A into its own Foundry-hosted agent and keep it calling the external Maze Tool contract.",
        },
    }


def table_rows(mapping: dict[str, Any]) -> str:
    rows = []
    for key, value in mapping.items():
        rendered = json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value)
        rows.append(
            "<tr>"
            f"<td>{html.escape(key.replace('_', ' ').title())}</td>"
            f"<td>{html.escape(rendered)}</td>"
            "</tr>"
        )
    return "".join(rows)


def render_phase_html(report: dict[str, Any]) -> str:
    data = html.escape(json.dumps(report, indent=2, default=str))
    summary = report["summary"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Azure Foundry Maze Migration - Phase 10</title>
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
        <h1>Phase 10 - External Azure Function Maze Tool</h1>
        <p>{html.escape(report['learning_objective'])}</p>
      </div>
      <aside class="summary">
        <span>Status</span>
        <strong>{html.escape(report['status'].replace('_', ' '))}</strong>
        <p>External tool calls observed: {summary['external_maze_tool_calls_observed']}.</p>
      </aside>
    </header>
    <div class="stack">
      <section class="panel">
        <h2>Phase Metrics</h2>
        <div class="metrics">
          <div class="metric"><span>Function Apps Added</span><strong>{summary['new_function_apps_created']}</strong></div>
          <div class="metric"><span>Storage Added</span><strong>{summary['new_storage_accounts_created']}</strong></div>
          <div class="metric"><span>LLM Calls</span><strong>{summary['llm_calls_observed']}</strong></div>
          <div class="metric"><span>External Tool Calls</span><strong>{summary['external_maze_tool_calls_observed']}</strong></div>
        </div>
      </section>
      <section class="panel">
        <h2>External Tool Flow</h2>
        <div class="flow">
          <article class="step"><span>1. Foundry Agent</span><h3>Reasoning stays hosted</h3><p>The agent decides it needs maze state or a move validation.</p></article>
          <article class="step tool"><span>2. HTTP Tool</span><h3>Azure Function</h3><p>The agent calls the Maze Tool over HTTP with a typed request.</p></article>
          <article class="step"><span>3. Tool Result</span><h3>Typed JSON</h3><p>The Function returns legal moves, new position, or validation error.</p></article>
          <article class="step note"><span>4. Trace</span><h3>Observable boundary</h3><p>The WebUI shows external-http tool events separately from LLM calls.</p></article>
        </div>
      </section>
      <section class="panel"><h2>Architecture</h2><table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{table_rows(report['architecture'])}</tbody></table></section>
      <section class="panel"><h2>Tool Contract</h2><table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{table_rows(report['tool_contract'])}</tbody></table></section>
      <section class="panel"><h2>Tool Validation</h2><table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{table_rows(report['tool_validation'])}</tbody></table></section>
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
    ]
    cards = []
    for title, path, visual, notes, validation in phase_files:
        item = load_json(path)
        if not item:
            continue
        summary = item.get("summary", {})
        detail = ", ".join(
            f"{key}: {summary[key]}"
            for key in ("foundry_model_calls", "hosted_agents_created", "azure_webui_deployed", "azure_resources_created", "new_azure_resources_created", "maze_tool_boundary_extracted")
            if key in summary
        )
        cards.append(
            f"""<section class="card"><h2>{html.escape(title)}</h2><p>Status: {html.escape(str(item.get('status')))}. {html.escape(detail)}</p><p><a href="{visual}">Open visual</a> | <a href="{notes}">Notes</a> | <a href="{validation}">Validation</a></p></section>"""
        )
    s = report["summary"]
    cards.append(
        f"""<section class="card current"><h2>Phase 10: External Azure Function Maze Tool</h2><p>Status: {html.escape(report['status'])}. External tool created: {s['external_maze_tool_created']}. Hosted agent uses tool: {s['hosted_agent_uses_external_tool']}. External calls: {s['external_maze_tool_calls_observed']}.</p><p><a href="visuals/PHASE10_VISUAL.html">Open visual</a> | <a href="PHASE10_EXTERNAL_MAZE_TOOL.md">Notes</a> | <a href="PHASE10_VALIDATION.md">Validation</a></p></section>"""
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Azure Foundry Maze Migration - Progress</title><style>body{{margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f7f8fa;color:#17202a}}main{{width:min(960px,calc(100% - 32px));margin:0 auto;padding:32px 0}}.card{{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:16px;margin:12px 0}}.current{{border-left:5px solid #1f6f5b}}a{{color:#285da8;font-weight:800;text-decoration:none}}p{{color:#5f6b7a}}</style></head><body><main><h1>Azure Foundry Maze Migration From Scratch</h1><p>Step-by-step migration of the local multi-agent maze program to Microsoft Foundry-hosted agents.</p><section class="card"><h2>Cost Policy</h2><p>Personal-subscription learning lab: add Azure-native pieces only when a phase teaches the implementation boundary.</p></section>{''.join(cards)}<section class="card"><h2>Next</h2><p>{html.escape(s['next_phase'])}</p></section></main></body></html>"""


def write_docs() -> None:
    write_text(PROJECT_ROOT / "PHASE10_EXTERNAL_MAZE_TOOL.md", """# Phase 10 - External Azure Function Maze Tool

## Objective

Move the Maze Tool from an in-package program boundary to a separately hosted
Azure Function tool while keeping the agent contract stable.

## Architecture

```text
Azure WebUI Function
  -> Foundry hosted agent
       -> Pydantic AI reasoning agents
       -> ExternalMazeToolProgram HTTP client
            -> Azure Function Maze Tool
                 -> /api/maze/inspect
                 -> /api/maze/move
```

## What Changed

Phase 9 created a clean in-process `MazeToolProgram` boundary. Phase 10 keeps
that boundary but swaps the implementation to an external HTTP tool when
`MAZE_TOOL_BASE_URL` is configured.

## Security

The Maze Tool uses Azure Functions function-level auth for `inspect` and
`move`. The function key is not committed to source or exposed to browser code.

## Cost

This phase adds one Azure Function App and one Standard_LRS storage account for
the Maze Tool service. Function execution remains consumption-based.
""")
    write_text(PROJECT_ROOT / "PHASE10_VALIDATION.md", """# Phase 10 Validation

## Expected Result

```text
Maze Tool is visible as a separate Azure Function App.
/api/maze/health returns HTTP 200 without a key.
/api/maze/openapi.json returns the OpenAPI contract.
/api/maze/inspect and /api/maze/move require function auth.
Hosted agent receives MAZE_TOOL_BASE_URL and MAZE_TOOL_KEY through environment configuration.
Live WebUI /api/run returns external-http MazeTool events.
```

## Command

```bash
python3 scripts/phase10_external_maze_tool.py --deploy --deploy-hosted-agent --update-webui-sample
```

## Generated Artifacts

```text
tools/phase10-maze-tool-function/
runs/phase10_external_maze_tool.json
runs/phase10_maze_tool_function.zip
runs/phase10_external_tool_sample/
visuals/PHASE10_VISUAL.html
PHASE10_EXTERNAL_MAZE_TOOL.md
PHASE10_VALIDATION.md
PROGRESS.html
```
""")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy and validate Phase 10 external Azure Function Maze Tool.")
    parser.add_argument("--deploy", action="store_true")
    parser.add_argument("--deploy-hosted-agent", action="store_true")
    parser.add_argument("--update-webui-sample", action="store_true")
    args = parser.parse_args()
    write_docs()
    report = build_report(args.deploy, args.deploy_hosted_agent, args.update_webui_sample)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    VISUALS_DIR.mkdir(parents=True, exist_ok=True)
    write_text(RUNS_DIR / "phase10_external_maze_tool.json", json.dumps(report, indent=2, default=str) + "\n")
    write_text(VISUALS_DIR / "PHASE10_VISUAL.html", render_phase_html(report))
    write_text(PROGRESS_PATH, render_progress_html(report))
    print(f"phase={report['phase']}")
    print(f"status={report['status']}")
    print(f"external_maze_tool_created={report['summary']['external_maze_tool_created']}")
    print(f"hosted_agent_uses_external_tool={report['summary']['hosted_agent_uses_external_tool']}")
    print(f"external_maze_tool_calls_observed={report['summary']['external_maze_tool_calls_observed']}")
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
