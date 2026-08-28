#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = PROJECT_ROOT / "runs"
VISUALS_DIR = PROJECT_ROOT / "visuals"
PROGRESS_PATH = PROJECT_ROOT / "PROGRESS.html"
TARGET_TENANT_HINT = "cciepraveenyahoo.onmicrosoft.com"
TARGET_SUBSCRIPTION_HINT = "Visual Studio Enterprise Subscription"


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    returncode: int | None
    stdout: str
    stderr: str


def run_command(args: list[str], timeout: int = 30) -> CommandResult:
    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return CommandResult(False, None, "", "command not found")
    except subprocess.TimeoutExpired as exc:
        return CommandResult(False, None, exc.stdout or "", "command timed out")
    return CommandResult(
        ok=completed.returncode == 0,
        returncode=completed.returncode,
        stdout=sanitize_output(completed.stdout),
        stderr=sanitize_output(completed.stderr),
    )


def sanitize_output(value: str) -> str:
    sanitized = value.replace(str(Path.home()), "~")
    lines = []
    for line in sanitized.splitlines():
        if "Token" in line or "token" in line:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def parse_json(result: CommandResult) -> Any | None:
    if not result.ok or not result.stdout:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def mask_id(value: str | None) -> str | None:
    if not value:
        return value
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def account_summary(account: dict[str, Any] | None) -> dict[str, Any] | None:
    if not account:
        return None
    return {
        "name": account.get("name"),
        "state": account.get("state"),
        "is_default": account.get("isDefault"),
        "subscription_id_masked": mask_id(account.get("id")),
        "tenant_id_masked": mask_id(account.get("tenantId")),
        "user_type": (account.get("user") or {}).get("type"),
    }


def build_readiness() -> dict[str, Any]:
    az_path = shutil.which("az")
    azd_path = shutil.which("azd")

    az_version_result = run_command(["az", "version", "--output", "json"]) if az_path else None
    az_version = parse_json(az_version_result) if az_version_result else None

    az_account_result = run_command(["az", "account", "show", "--output", "json"]) if az_path else None
    az_account = parse_json(az_account_result) if az_account_result else None

    az_accounts_result = run_command(["az", "account", "list", "--output", "json"]) if az_path else None
    az_accounts_raw = parse_json(az_accounts_result) if az_accounts_result else None
    az_accounts = az_accounts_raw if isinstance(az_accounts_raw, list) else []
    all_visible_subscriptions = [account_summary(account) for account in az_accounts]
    all_visible_subscriptions = [item for item in all_visible_subscriptions if item]
    target_matches = [
        item for item in all_visible_subscriptions if TARGET_SUBSCRIPTION_HINT.lower() in (item.get("name") or "").lower()
    ]
    selected = account_summary(az_account)
    visible_subscriptions = target_matches or ([selected] if selected else [])

    budget_help_result = (
        run_command(["az", "consumption", "budget", "--help"], timeout=20)
        if az_path and az_account
        else None
    )

    azd_version_result = run_command(["azd", "version"]) if azd_path else None
    azd_status_result = run_command(["azd", "auth", "status"], timeout=20) if azd_path else None

    az_logged_in = bool(az_account)
    azd_installed = bool(azd_path)
    azd_logged_in = bool(azd_status_result and azd_status_result.ok)
    target_subscription_visible = bool(target_matches)

    readiness_gates = [
        {
            "name": "Azure CLI installed",
            "status": "pass" if az_path else "action_required",
            "detail": az_path or "Install Azure CLI before login.",
        },
        {
            "name": "Azure CLI authenticated",
            "status": "pass" if az_logged_in else "action_required",
            "detail": "az account show returned an account." if az_logged_in else "Run az login --use-device-code.",
        },
        {
            "name": "Personal subscription visible",
            "status": "pass" if target_subscription_visible else "review",
            "detail": f"Subscription name containing {TARGET_SUBSCRIPTION_HINT!r} found."
            if target_subscription_visible
            else f"Run device-code login for tenant {TARGET_TENANT_HINT!r}, then select the personal subscription.",
        },
        {
            "name": "Azure Developer CLI installed",
            "status": "pass" if azd_installed else "action_required",
            "detail": azd_path or "Install azd before Foundry Toolkit deployment phases.",
        },
        {
            "name": "Azure Developer CLI authenticated",
            "status": "pass" if azd_logged_in else "action_required",
            "detail": "azd auth status is authenticated." if azd_logged_in else "Run azd auth login --use-device-code after azd is installed.",
        },
        {
            "name": "Budget command available",
            "status": "pass" if budget_help_result and budget_help_result.ok else "review",
            "detail": "az consumption budget command group is available."
            if budget_help_result and budget_help_result.ok
            else "Budget command was not verified; use Azure portal budget alert if CLI preview command is unavailable.",
        },
        {
            "name": "Azure resources created",
            "status": "pass",
            "detail": "None. Phase 3 is readiness only.",
        },
    ]

    blocking = [
        gate for gate in readiness_gates if gate["status"] == "action_required"
    ]
    status = "complete" if not blocking else "action_required"

    return {
        "course": "Azure Foundry Maze Migration From Scratch",
        "phase": 3,
        "phase_name": "Azure Login and Subscription Readiness",
        "status": status,
        "target_tenant_hint": TARGET_TENANT_HINT,
        "target_subscription_hint": TARGET_SUBSCRIPTION_HINT,
        "summary": {
            "azure_cli_installed": bool(az_path),
            "azure_cli_logged_in": az_logged_in,
            "azd_installed": azd_installed,
            "azd_logged_in": azd_logged_in,
            "visible_subscription_count": len(all_visible_subscriptions),
            "relevant_subscription_count": len(visible_subscriptions),
            "target_subscription_visible": target_subscription_visible,
            "azure_resources_created": 0,
            "estimated_azure_cost": "$0",
            "next_phase": "Create or select one Foundry project and one model deployment only after readiness gates pass.",
        },
        "selected_account": selected,
        "visible_subscriptions": visible_subscriptions,
        "readiness_gates": readiness_gates,
        "commands": {
            "azure_login": f"az login --tenant {TARGET_TENANT_HINT} --use-device-code",
            "select_subscription": f'az account set --subscription "{TARGET_SUBSCRIPTION_HINT}"',
            "azd_login": "azd auth login --use-device-code",
            "azd_status": "azd auth status",
            "budget_review": "az consumption budget list --output table",
        },
        "tool_versions": {
            "az": az_version,
            "azd": azd_version_result.stdout if azd_version_result and azd_version_result.ok else None,
        },
        "command_errors": {
            "az_version": az_version_result.stderr if az_version_result and not az_version_result.ok else "",
            "az_account_show": az_account_result.stderr if az_account_result and not az_account_result.ok else "",
            "az_account_list": az_accounts_result.stderr if az_accounts_result and not az_accounts_result.ok else "",
            "azd_version": "command not found" if not azd_path else (azd_version_result.stderr if azd_version_result and not azd_version_result.ok else ""),
            "azd_auth_status": azd_status_result.stderr if azd_status_result and not azd_status_result.ok else "",
        },
    }


def render_phase_html(readiness: dict[str, Any]) -> str:
    summary = readiness["summary"]
    gate_cards = []
    for gate in readiness["readiness_gates"]:
        gate_cards.append(
            "<article class='gate'>"
            f"<span>{html.escape(gate['status'])}</span>"
            f"<strong>{html.escape(gate['name'])}</strong>"
            f"<p>{html.escape(gate['detail'])}</p>"
            "</article>"
        )
    subscription_rows = []
    for subscription in readiness["visible_subscriptions"]:
        subscription_rows.append(
            "<tr>"
            f"<td>{html.escape(str(subscription.get('name')))}</td>"
            f"<td>{html.escape(str(subscription.get('state')))}</td>"
            f"<td>{html.escape(str(subscription.get('is_default')))}</td>"
            f"<td>{html.escape(str(subscription.get('subscription_id_masked')))}</td>"
            "</tr>"
        )
    command_rows = []
    for label, command in readiness["commands"].items():
        command_rows.append(
            "<tr>"
            f"<td>{html.escape(label.replace('_', ' ').title())}</td>"
            f"<td><code>{html.escape(command)}</code></td>"
            "</tr>"
        )
    data = html.escape(json.dumps(readiness, indent=2))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Azure Foundry Maze Migration - Phase 3</title>
  <style>
    :root {{ --bg:#f7f8fa; --panel:#fff; --text:#17202a; --muted:#5f6b7a; --line:#d9dee7; --blue:#285da8; --green:#1f6f5b; --amber:#a86a00; --red:#b91c1c; --shadow:0 10px 28px rgba(28,36,48,.08); }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:var(--text); background:var(--bg); line-height:1.5; }}
    main {{ width:min(1180px, calc(100% - 32px)); margin:0 auto; padding:32px 0 48px; }}
    header {{ display:grid; grid-template-columns:minmax(0,1fr) 280px; gap:20px; border-bottom:1px solid var(--line); padding-bottom:20px; margin-bottom:22px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(28px,4vw,42px); line-height:1.08; }}
    h2 {{ margin:0 0 12px; font-size:20px; }}
    p {{ margin:0; color:var(--muted); }}
    .panel,.summary,.gate {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; box-shadow:var(--shadow); }}
    .summary,.panel {{ padding:16px; }}
    .summary strong {{ display:block; font-size:30px; text-transform:capitalize; }}
    .metrics,.gates {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }}
    .metric {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fff; }}
    .metric span,.gate span {{ display:block; color:var(--muted); font-size:12px; font-weight:800; text-transform:uppercase; }}
    .metric strong {{ display:block; margin-top:6px; font-size:26px; }}
    .gate {{ padding:14px; box-shadow:none; border-left:5px solid var(--blue); }}
    .gate span {{ color:var(--blue); }}
    .gate span:first-child {{ margin-bottom:4px; }}
    .gate:has(span:first-child:not(:only-child)) {{ border-left-color:var(--blue); }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th,td {{ padding:9px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-size:12px; text-transform:uppercase; }}
    code {{ color:#111827; background:#eef2f7; padding:2px 5px; border-radius:4px; }}
    pre {{ overflow:auto; max-height:420px; padding:12px; background:#111827; color:#e5e7eb; border-radius:8px; font-size:12px; }}
    .stack {{ display:grid; gap:14px; }}
    @media (max-width:900px) {{ header,.metrics,.gates {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Phase 3 - Azure Login and Subscription Readiness</h1>
        <p>Verify local Azure auth and tooling before creating any Foundry resources.</p>
      </div>
      <aside class="summary">
        <span>Status</span>
        <strong>{html.escape(readiness['status'])}</strong>
        <p>Azure resources created: {summary['azure_resources_created']}. Cost: {html.escape(summary['estimated_azure_cost'])}.</p>
      </aside>
    </header>
    <div class="stack">
      <section class="panel">
        <h2>Readiness Metrics</h2>
        <div class="metrics">
          <div class="metric"><span>Azure CLI</span><strong>{'yes' if summary['azure_cli_installed'] else 'no'}</strong></div>
          <div class="metric"><span>az login</span><strong>{'yes' if summary['azure_cli_logged_in'] else 'no'}</strong></div>
          <div class="metric"><span>azd installed</span><strong>{'yes' if summary['azd_installed'] else 'no'}</strong></div>
          <div class="metric"><span>azd login</span><strong>{'yes' if summary['azd_logged_in'] else 'no'}</strong></div>
          <div class="metric"><span>Subscriptions</span><strong>{summary['visible_subscription_count']}</strong></div>
          <div class="metric"><span>Azure Cost</span><strong>{html.escape(summary['estimated_azure_cost'])}</strong></div>
        </div>
      </section>
      <section class="panel">
        <h2>Readiness Gates</h2>
        <div class="gates">{''.join(gate_cards)}</div>
      </section>
      <section class="panel">
        <h2>Visible Subscriptions</h2>
        <table>
          <thead><tr><th>Name</th><th>State</th><th>Default</th><th>Subscription ID</th></tr></thead>
          <tbody>{''.join(subscription_rows) if subscription_rows else '<tr><td colspan="4">No subscriptions visible yet.</td></tr>'}</tbody>
        </table>
      </section>
      <section class="panel">
        <h2>Commands</h2>
        <table>
          <thead><tr><th>Purpose</th><th>Command</th></tr></thead>
          <tbody>{''.join(command_rows)}</tbody>
        </table>
      </section>
      <section class="panel">
        <h2>Next Phase</h2>
        <p>{html.escape(summary['next_phase'])}</p>
      </section>
      <section class="panel">
        <h2>Readiness JSON</h2>
        <details><summary>Open generated readiness report</summary><pre>{data}</pre></details>
      </section>
    </div>
  </main>
</body>
</html>
"""


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def render_progress_html(readiness: dict[str, Any]) -> str:
    phase1 = load_json(RUNS_DIR / "phase1_inventory.json")
    phase2 = load_json(RUNS_DIR / "phase2_public_repo_hygiene.json")
    cards = []
    if phase1:
        s = phase1["summary"]
        cards.append(
            f"""<section class="card">
      <h2>Phase 1: Portability Inventory</h2>
      <p>Status: complete. Files scanned: {s['files_scanned']}. Findings: {s['findings']}.</p>
      <p><a href="visuals/PHASE1_VISUAL.html">Open visual</a> | <a href="PHASE1_PORTABILITY_INVENTORY.md">Notes</a> | <a href="PHASE1_VALIDATION.md">Validation</a></p>
    </section>"""
        )
    if phase2:
        s = phase2["summary"]
        cards.append(
            f"""<section class="card">
      <h2>Phase 2: Public Repo and Secret Hygiene</h2>
      <p>Status: {html.escape(phase2['status'])}. Copied: {s['files_copied']}. Excluded: {s['files_excluded']}. Redacted: {s['files_redacted']}. Blocking findings: {s['blocking_findings_after_export']}.</p>
      <p><a href="visuals/PHASE2_VISUAL.html">Open visual</a> | <a href="PHASE2_PUBLIC_REPO_HYGIENE.md">Notes</a> | <a href="PHASE2_VALIDATION.md">Validation</a></p>
    </section>"""
        )
    s = readiness["summary"]
    cards.append(
        f"""<section class="card">
      <h2>Phase 3: Azure Login and Subscription Readiness</h2>
      <p>Status: {html.escape(readiness['status'])}. Azure CLI logged in: {s['azure_cli_logged_in']}. azd installed: {s['azd_installed']}. Azure resources created: {s['azure_resources_created']}. Cost: {html.escape(s['estimated_azure_cost'])}.</p>
      <p><a href="visuals/PHASE3_VISUAL.html">Open visual</a> | <a href="PHASE3_AZURE_LOGIN_READINESS.md">Notes</a> | <a href="PHASE3_VALIDATION.md">Validation</a></p>
    </section>"""
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
    <section class="card">
      <h2>Cost Policy</h2>
      <p>Personal-subscription learning lab: one Foundry project, one model deployment, one hosted agent first, short traces, and no extra Azure services until a phase teaches them.</p>
    </section>
    {''.join(cards)}
    <section class="card">
      <h2>Next: Phase 4</h2>
      <p>{html.escape(s['next_phase'])}</p>
    </section>
  </main>
</body>
</html>
"""


def main() -> int:
    readiness = build_readiness()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    VISUALS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "phase3_azure_login_readiness.json").write_text(
        json.dumps(readiness, indent=2) + "\n",
        encoding="utf-8",
    )
    (VISUALS_DIR / "PHASE3_VISUAL.html").write_text(render_phase_html(readiness), encoding="utf-8")
    PROGRESS_PATH.write_text(render_progress_html(readiness), encoding="utf-8")
    print(f"phase={readiness['phase']}")
    print(f"status={readiness['status']}")
    print(f"azure_cli_installed={readiness['summary']['azure_cli_installed']}")
    print(f"azure_cli_logged_in={readiness['summary']['azure_cli_logged_in']}")
    print(f"azd_installed={readiness['summary']['azd_installed']}")
    print(f"azd_logged_in={readiness['summary']['azd_logged_in']}")
    print(f"visible_subscription_count={readiness['summary']['visible_subscription_count']}")
    print(f"azure_resources_created={readiness['summary']['azure_resources_created']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
