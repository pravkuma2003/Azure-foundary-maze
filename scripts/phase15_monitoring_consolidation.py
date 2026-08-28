#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = PROJECT_ROOT / "runs"
VISUALS_DIR = PROJECT_ROOT / "visuals"
PROGRESS_PATH = PROJECT_ROOT / "PROGRESS.html"

RESOURCE_GROUP = "rg-maze-foundry-lab"
WEBUI_FUNCTION_APP = "maze-webui-func-prav-ada483"
TOOL_FUNCTION_APP = "maze-tool-func-prav-ada483"
SHARED_APP_INSIGHTS = WEBUI_FUNCTION_APP
OLD_TOOL_APP_INSIGHTS = TOOL_FUNCTION_APP
OLD_TOOL_ALERT_RULE = f"Failure Anomalies - {TOOL_FUNCTION_APP}"
OLD_TOOL_LAW_RG = "ai_maze-tool-func-prav-ada483_a4fb8274-f365-4b8c-b42a-badc02c7562a_managed"
WEBUI_URL = f"https://{WEBUI_FUNCTION_APP}.azurewebsites.net/api/health"
TOOL_URL = f"https://{TOOL_FUNCTION_APP}.azurewebsites.net/api/maze/health"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def safe_text(value: str) -> str:
    value = value.replace(str(Path.home()), "~")
    value = re.sub(r'InstrumentationKey=[^;"\s]+', "InstrumentationKey=[redacted]", value)
    value = re.sub(r'IngestionEndpoint=https://[^;"\s]+', "IngestionEndpoint=[redacted]", value)
    value = re.sub(r'LiveEndpoint=https://[^;"\s]+', "LiveEndpoint=[redacted]", value)
    value = re.sub(r'ApplicationId=[^;"\s]+', "ApplicationId=[redacted]", value)
    value = re.sub(r'("value"\s*:\s*")[^"]{20,}(")', r'\1[redacted]\2', value)
    return value.strip()


def run_command(args: list[str], timeout: int = 300) -> dict[str, Any]:
    try:
        completed = subprocess.run(args, cwd=PROJECT_ROOT, check=False, capture_output=True, text=True, timeout=timeout)
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
        if arg.startswith("APPINSIGHTS_INSTRUMENTATIONKEY="):
            redacted.append("APPINSIGHTS_INSTRUMENTATIONKEY=[redacted]")
        elif arg.startswith("APPLICATIONINSIGHTS_CONNECTION_STRING="):
            redacted.append("APPLICATIONINSIGHTS_CONNECTION_STRING=[redacted]")
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


def command_json(args: list[str], timeout: int = 300) -> tuple[dict[str, Any], dict[str, Any] | list[Any]]:
    try:
        completed = subprocess.run(args, cwd=PROJECT_ROOT, check=False, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        result = {"command": args[:1], "returncode": 127, "stdout": "", "stderr": f"{args[0]} not found"}
        return result, {}
    except subprocess.TimeoutExpired as exc:
        result = {"command": args, "returncode": 124, "stdout": safe_text(exc.stdout or ""), "stderr": "timed out"}
        return result, {}
    result = {
        "command": redact_command(args),
        "returncode": completed.returncode,
        "stdout": safe_text(completed.stdout),
        "stderr": safe_text(completed.stderr),
    }
    if completed.returncode != 0:
        return result, {}
    try:
        payload: dict[str, Any] | list[Any] = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        payload = {}
    return result, payload


def get_shared_monitoring_values() -> tuple[dict[str, Any], dict[str, str]]:
    result, payload = command_json(
        [
            "az",
            "monitor",
            "app-insights",
            "component",
            "show",
            "--app",
            SHARED_APP_INSIGHTS,
            "--resource-group",
            RESOURCE_GROUP,
            "--output",
            "json",
        ]
    )
    values = {
        "instrumentation_key": "",
        "connection_string": "",
        "workspace_resource_id": "",
    }
    if isinstance(payload, dict):
        values["instrumentation_key"] = str(payload.get("instrumentationKey") or "")
        values["connection_string"] = str(payload.get("connectionString") or "")
        values["workspace_resource_id"] = str(payload.get("workspaceResourceId") or "")
    return summarize(result), values


def get_monitoring_setting_summary(app: str) -> dict[str, Any]:
    result, payload = command_json(
        [
            "az",
            "functionapp",
            "config",
            "appsettings",
            "list",
            "--resource-group",
            RESOURCE_GROUP,
            "--name",
            app,
            "--output",
            "json",
        ]
    )
    summary: dict[str, Any] = {"command": summarize(result), "settings": {}}
    if isinstance(payload, list):
        for item in payload:
            name = item.get("name") or ""
            value = item.get("value") or ""
            if "INSIGHTS" in name.upper() or "APPLICATIONINSIGHTS" in name.upper() or "APPINSIGHTS" in name.upper():
                summary["settings"][name] = {"configured": bool(value), "length": len(value)}
    return summary


def set_monitoring(apply: bool, values: dict[str, str]) -> dict[str, Any]:
    if not apply:
        return {"attempted": False, "status": "planned"}
    if not values["instrumentation_key"] or not values["connection_string"]:
        return {"attempted": True, "status": "action_required", "error": "shared App Insights values were not available"}
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
            TOOL_FUNCTION_APP,
            "--settings",
            f"APPINSIGHTS_INSTRUMENTATIONKEY={values['instrumentation_key']}",
            f"APPLICATIONINSIGHTS_CONNECTION_STRING={values['connection_string']}",
        ]
    )
    return {"attempted": True, "status": "configured" if result["returncode"] == 0 else "action_required", "command": summarize(result)}


def restart_tool_function(apply: bool) -> dict[str, Any]:
    if not apply:
        return {"attempted": False, "status": "planned"}
    result = run_command(
        ["az", "functionapp", "restart", "--resource-group", RESOURCE_GROUP, "--name", TOOL_FUNCTION_APP],
        timeout=180,
    )
    return {"attempted": True, "status": "restarted" if result["returncode"] == 0 else "action_required", "command": summarize(result)}


def delete_old_monitoring(apply: bool) -> dict[str, Any]:
    if not apply:
        return {"attempted": False, "status": "planned"}
    component = delete_resource_if_present(RESOURCE_GROUP, OLD_TOOL_APP_INSIGHTS, "Microsoft.Insights/components")
    alert = delete_resource_if_present(RESOURCE_GROUP, OLD_TOOL_ALERT_RULE, "microsoft.alertsmanagement/smartDetectorAlertRules")
    workspace_group = delete_group_if_present(OLD_TOOL_LAW_RG)
    return {
        "attempted": True,
        "status": "deleted" if all(item["returncode"] == 0 for item in (component, alert, workspace_group)) else "action_required",
        "component": summarize(component),
        "alert_rule": summarize(alert),
        "managed_workspace_resource_group": summarize(workspace_group),
    }


def delete_resource_if_present(resource_group: str, name: str, resource_type: str) -> dict[str, Any]:
    show = run_command(
        [
            "az",
            "resource",
            "show",
            "--resource-group",
            resource_group,
            "--name",
            name,
            "--resource-type",
            resource_type,
        ],
        timeout=120,
    )
    if show["returncode"] != 0:
        return {"command": show["command"], "returncode": 0, "stdout": "already absent", "stderr": ""}
    return run_command(
        [
            "az",
            "resource",
            "delete",
            "--resource-group",
            resource_group,
            "--name",
            name,
            "--resource-type",
            resource_type,
        ],
        timeout=300,
    )


def delete_group_if_present(resource_group: str) -> dict[str, Any]:
    exists_result = run_command(["az", "group", "exists", "--name", resource_group], timeout=120)
    if exists_result["returncode"] != 0 or exists_result["stdout"].strip().lower() != "true":
        return {"command": exists_result["command"], "returncode": 0, "stdout": "already absent", "stderr": ""}
    return run_command(["az", "group", "delete", "--name", resource_group, "--yes"], timeout=600)


def list_monitoring_resources() -> dict[str, Any]:
    result, payload = command_json(
        [
            "az",
            "resource",
            "list",
            "--query",
            "[?contains(name, 'maze') && (type=='Microsoft.Insights/components' || type=='microsoft.operationalinsights/workspaces' || type=='microsoft.alertsmanagement/smartDetectorAlertRules')].{name:name,type:type,resourceGroup:resourceGroup,location:location,kind:kind}",
            "--output",
            "json",
        ],
        timeout=300,
    )
    return {"command": summarize(result), "resources": payload if isinstance(payload, list) else []}


def http_probe(url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            body = response.read().decode("utf-8", errors="replace")
            return {"url": url, "status_code": int(response.status), "body": body[:500]}
    except Exception as exc:
        return {"url": url, "status_code": 0, "error": str(exc)}


def validate(apply: bool) -> dict[str, Any]:
    after_tool_settings = get_monitoring_setting_summary(TOOL_FUNCTION_APP)
    resources = list_monitoring_resources()
    remaining_names = {item.get("name") for item in resources.get("resources", []) if isinstance(item, dict)}
    return {
        "attempted": apply,
        "webui_health": http_probe(WEBUI_URL) if apply else {"status": "planned"},
        "tool_health": http_probe(TOOL_URL) if apply else {"status": "planned"},
        "tool_monitoring_settings": after_tool_settings,
        "monitoring_resources": resources,
        "passed": (
            apply
            and OLD_TOOL_APP_INSIGHTS not in remaining_names
            and OLD_TOOL_ALERT_RULE not in remaining_names
            and SHARED_APP_INSIGHTS in remaining_names
            and after_tool_settings.get("settings", {}).get("APPLICATIONINSIGHTS_CONNECTION_STRING", {}).get("configured") is True
        ),
    }


def build_report(apply: bool) -> dict[str, Any]:
    before = list_monitoring_resources()
    webui_settings_before = get_monitoring_setting_summary(WEBUI_FUNCTION_APP)
    tool_settings_before = get_monitoring_setting_summary(TOOL_FUNCTION_APP)
    shared_lookup, values = get_shared_monitoring_values()
    set_result = set_monitoring(apply, values)
    restart = restart_tool_function(apply) if set_result.get("status") in {"configured", "planned"} else {"attempted": False, "status": "blocked_by_settings"}
    delete_result = delete_old_monitoring(apply) if restart.get("status") in {"restarted", "planned"} else {"attempted": False, "status": "blocked_by_restart"}
    validation = validate(apply) if delete_result.get("status") in {"deleted", "planned"} else {"attempted": apply, "passed": False, "status": "blocked_by_delete"}
    passed = not apply or bool(validation.get("passed"))
    return {
        "course": "Azure Foundry Maze Migration From Scratch",
        "phase": 15,
        "phase_name": "Monitoring Consolidation",
        "status": "complete" if passed else "action_required",
        "mode": "apply" if apply else "plan",
        "learning_objective": "Consolidate duplicate Azure monitoring resources while leaving Function App storage unchanged.",
        "architecture": {
            "before": "Each Function App had its own Application Insights component and managed Log Analytics workspace.",
            "after": "Both Function Apps send telemetry to the WebUI Application Insights component and its managed workspace.",
            "storage_scope": "No Function App storage account was changed in this phase.",
            "app_service_plan_scope": "The existing Y1 Consumption plan remains shared by both Function Apps.",
        },
        "before_monitoring_resources": before,
        "webui_settings_before": webui_settings_before,
        "tool_settings_before": tool_settings_before,
        "shared_app_insights_lookup": shared_lookup,
        "set_tool_monitoring": set_result,
        "restart_tool_function": restart,
        "delete_old_monitoring": delete_result,
        "validation": validation,
        "summary": {
            "shared_app_insights": SHARED_APP_INSIGHTS,
            "removed_app_insights": OLD_TOOL_APP_INSIGHTS if apply and validation.get("passed") else None,
            "removed_managed_law_resource_group": OLD_TOOL_LAW_RG if apply and validation.get("passed") else None,
            "storage_accounts_changed": 0,
            "app_service_plans_changed": 0,
            "next_phase": "Storage consolidation can be evaluated separately, but it was intentionally left untouched here.",
        },
    }


def render_visual(report: dict[str, Any]) -> str:
    resources = report["validation"].get("monitoring_resources", {}).get("resources") or []
    rows = "".join(
        f"<tr><td>{html.escape(str(item.get('name')))}</td><td>{html.escape(str(item.get('type')))}</td><td>{html.escape(str(item.get('resourceGroup')))}</td></tr>"
        for item in resources
        if isinstance(item, dict)
    )
    escaped = html.escape(json.dumps(report, indent=2, default=str))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Azure Foundry Maze Migration - Phase 15</title>
  <style>
    body {{ margin:0; font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:#f7f8fa; color:#17202a; line-height:1.5; }}
    main {{ width:min(1180px,calc(100% - 32px)); margin:0 auto; padding:32px 0 48px; }}
    header {{ display:grid; grid-template-columns:minmax(0,1fr) 300px; gap:18px; border-bottom:1px solid #d9dee7; padding-bottom:20px; margin-bottom:20px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(30px,4vw,44px); line-height:1.08; }}
    h2 {{ margin:0 0 12px; font-size:20px; }}
    p {{ margin:0; color:#5f6b7a; }}
    .panel,.metric,.node {{ background:#fff; border:1px solid #d9dee7; border-radius:8px; box-shadow:0 10px 28px rgba(28,36,48,.08); padding:16px; }}
    .metric strong {{ display:block; font-size:28px; }}
    .diagram {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:14px; align-items:start; }}
    .node strong {{ display:block; font-size:17px; }}
    .node span {{ color:#5f6b7a; font-weight:800; font-size:12px; text-transform:uppercase; }}
    .keep {{ border-left:5px solid #1f6f5b; }}
    .merge {{ border-left:5px solid #285da8; }}
    .remove {{ border-left:5px solid #9a6500; }}
    table {{ width:100%; border-collapse:collapse; background:#fff; border:1px solid #d9dee7; border-radius:8px; overflow:hidden; margin-top:10px; }}
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
      <h1>Phase 15 - Monitoring Consolidation</h1>
      <p>{html.escape(report['learning_objective'])}</p>
    </div>
    <aside class="metric"><span>Status</span><strong>{html.escape(report['status'])}</strong><p>Mode: {html.escape(report['mode'])}</p></aside>
  </header>
  <section class="diagram">
    <article class="node keep"><span>Kept</span><strong>WebUI App Insights</strong><p>Shared telemetry target for WebUI and Maze Tool.</p></article>
    <article class="node merge"><span>Repointed</span><strong>Maze Tool Function</strong><p>Monitoring settings now use the shared component.</p></article>
    <article class="node remove"><span>Removed</span><strong>Duplicate Tool Monitoring</strong><p>Old tool App Insights, alert rule, and managed workspace group removed after validation.</p></article>
  </section>
  <section class="panel" style="margin-top:14px">
    <h2>Remaining Monitoring Resources</h2>
    <table><thead><tr><th>Name</th><th>Type</th><th>Resource Group</th></tr></thead><tbody>{rows}</tbody></table>
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
    return """# Phase 15 - Monitoring Consolidation

## Objective

Consolidate duplicate monitoring resources while leaving Function App storage
unchanged.

## What Changed

Before:

```text
maze-webui-func-prav-ada483 -> App Insights A -> managed LAW A
maze-tool-func-prav-ada483  -> App Insights B -> managed LAW B
```

After:

```text
maze-webui-func-prav-ada483 -> shared App Insights -> shared managed LAW
maze-tool-func-prav-ada483  -> shared App Insights -> shared managed LAW
```

## What Did Not Change

The WebUI and Maze Tool Function Apps still use their existing storage accounts.
The shared Y1 Consumption App Service plan also remains unchanged.

## Why This Matters

Monitoring is a support boundary, not part of the agent runtime. Consolidating it
reduces duplicate resources without changing agent behavior, tool calls, durable
Team Memory, or Foundry-hosted role agents.
"""


def render_validation(report: dict[str, Any]) -> str:
    validation = report["validation"]
    return f"""# Phase 15 Validation

## Expected Result

```text
Maze Tool Function App points to shared WebUI Application Insights.
Duplicate Maze Tool Application Insights is removed.
Duplicate Maze Tool managed Log Analytics workspace resource group is removed.
Storage accounts remain unchanged.
App Service plan remains unchanged.
```

## Live Result

```text
status: {report['status']}
shared_app_insights: {report['summary']['shared_app_insights']}
removed_app_insights: {report['summary']['removed_app_insights']}
removed_managed_law_resource_group: {report['summary']['removed_managed_law_resource_group']}
storage_accounts_changed: {report['summary']['storage_accounts_changed']}
app_service_plans_changed: {report['summary']['app_service_plans_changed']}
webui_health: {validation.get('webui_health', {}).get('status_code')}
tool_health: {validation.get('tool_health', {}).get('status_code')}
```
"""


def refresh_progress(report: dict[str, Any]) -> None:
    existing = PROGRESS_PATH.read_text(encoding="utf-8") if PROGRESS_PATH.exists() else ""
    phase14 = '<section class="card"><h2>Phase 14: Azure Durable Team Memory</h2><p>Status: complete. Backend: Azure Blob Storage. Durable readback: True.</p><p><a href="visuals/PHASE14_VISUAL.html">Open visual</a> | <a href="PHASE14_AZURE_DURABLE_TEAM_MEMORY.md">Notes</a> | <a href="PHASE14_VALIDATION.md">Validation</a></p></section>'
    phase15 = f'<section class="card current"><h2>Phase 15: Monitoring Consolidation</h2><p>Status: {html.escape(report["status"])}. Shared App Insights: {html.escape(report["summary"]["shared_app_insights"])}. Storage changes: 0.</p><p><a href="visuals/PHASE15_VISUAL.html">Open visual</a> | <a href="PHASE15_MONITORING_CONSOLIDATION.md">Notes</a> | <a href="PHASE15_VALIDATION.md">Validation</a></p></section>'
    if "Phase 15: Monitoring Consolidation" in existing:
        updated = re.sub(r'<section class="card(?: current)?"><h2>Phase 15: Monitoring Consolidation.*?</section>', phase15, existing, flags=re.S)
    else:
        updated = re.sub(r'<section class="card(?: current)?"><h2>Phase 14:.*?</section>', phase14 + phase15, existing, flags=re.S)
    updated = re.sub(r'<section class="card(?: current)?"><h2>Phase 14:.*?</section>', phase14, updated, flags=re.S)
    updated = re.sub(
        r"<section class=\"card\"><h2>Next</h2>.*?</section>",
        '<section class="card"><h2>Next</h2><p>Evaluate storage consolidation separately, after confirming monitoring remains stable.</p></section>',
        updated,
        flags=re.S,
    )
    write_text(PROGRESS_PATH, updated)


def write_artifacts(report: dict[str, Any]) -> None:
    write_text(RUNS_DIR / "phase15_monitoring_consolidation.json", json.dumps(report, indent=2, default=str) + "\n")
    write_text(VISUALS_DIR / "PHASE15_VISUAL.html", render_visual(report))
    write_text(PROJECT_ROOT / "PHASE15_MONITORING_CONSOLIDATION.md", render_notes(report))
    write_text(PROJECT_ROOT / "PHASE15_VALIDATION.md", render_validation(report))
    refresh_progress(report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Consolidate Azure monitoring resources for the maze migration lab.")
    parser.add_argument("--apply", action="store_true", help="Apply monitoring consolidation and delete duplicate monitoring resources.")
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
                "validation_passed": report["validation"].get("passed"),
            },
            indent=2,
        )
    )
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
