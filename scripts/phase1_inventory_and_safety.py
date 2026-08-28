#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_APP = PROJECT_ROOT.parent / "multi-agent-reasoning-from-scratch"
RUNS_DIR = PROJECT_ROOT / "runs"
VISUALS_DIR = PROJECT_ROOT / "visuals"
PROGRESS_PATH = PROJECT_ROOT / "PROGRESS.html"

PATTERNS = {
    "private_ip": re.compile(r"\b(?:10|172\.(?:1[6-9]|2\d|3[0-1])|192\.168)\.\d{1,3}\.\d{1,3}\b"),
    "local_home_path": re.compile(r"(/Users/[^\\s\"'<>]+|/home/[^\\s\"'<>]+)"),
    "credential_name": re.compile(r"(api[_-]?key|secret|token|password|OPENAI_API_KEY|AZURE_[A-Z0-9_]+)", re.IGNORECASE),
}

AZURE_MAPPING = [
    {
        "local": "Pydantic AI Analyst Agent",
        "azure": "Foundry-hosted agent",
        "migration_note": "Keep instructions and output schema stable; swap provider/hosting first.",
    },
    {
        "local": "Pydantic AI Worker Agent A/B",
        "azure": "Foundry-hosted worker agents introduced one at a time",
        "migration_note": "Preserve role boundaries while avoiding multiple hosted agents until the lesson needs them.",
    },
    {
        "local": "Maze Tool Python functions",
        "azure": "In-process module first; Azure-hosted tool boundary later",
        "migration_note": "Keep the tool contract stable before paying for a separate hosted tool surface.",
    },
    {
        "local": "Team Memory in trace/state",
        "azure": "In-process memory first; Azure-native state later",
        "migration_note": "Introduce a memory interface before selecting a paid durable backend.",
    },
    {
        "local": "Generated HTML trace",
        "azure": "Foundry traces plus optional static HTML artifact",
        "migration_note": "Keep local HTML for learning while adding Foundry trace correlation.",
    },
]

COST_GUARDRAILS = [
    "Use one resource group, one Foundry project, and one model deployment at first.",
    "Deploy one Foundry-hosted agent before introducing multiple hosted agents.",
    "Keep maze traces short and preserve the 25-call learning budget.",
    "Prefer source-code hosted-agent deployment before container deployment unless the lesson requires containers.",
    "Use minimum practical hosted-agent CPU and memory sizing.",
    "Do not add Azure Functions, Cosmos DB, Storage, or extra monitoring services until a phase explicitly needs that construct.",
    "Clean up lab resources when they are no longer needed.",
]


def classify_file(path: Path) -> str:
    if path.suffix == ".py":
        return "python_source"
    if path.suffix == ".md":
        return "curriculum_doc"
    if path.suffix == ".json":
        return "generated_trace"
    if path.suffix == ".html":
        return "generated_html"
    if path.name.startswith("."):
        return "config"
    return "other"


def scan_file(path: Path) -> list[dict[str, Any]]:
    findings = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [{"type": "binary_or_non_utf8", "line": None, "match": path.name}]
    for line_number, line in enumerate(text.splitlines(), start=1):
        for finding_type, pattern in PATTERNS.items():
            for match in pattern.finditer(line):
                findings.append(
                    {
                        "type": finding_type,
                        "line": line_number,
                        "match": match.group(0),
                    }
                )
    return findings


def build_inventory() -> dict[str, Any]:
    files = []
    findings = []
    if not SOURCE_APP.exists():
        raise FileNotFoundError(f"source app not found: {SOURCE_APP}")

    for path in sorted(SOURCE_APP.rglob("*")):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(SOURCE_APP)
        file_findings = scan_file(path)
        category = classify_file(path)
        public_action = "keep"
        if category in {"generated_trace", "generated_html"}:
            public_action = "exclude or regenerate with sanitized provider metadata"
        if file_findings:
            public_action = "sanitize before public repo"
        record = {
            "path": str(relative),
            "category": category,
            "public_action": public_action,
            "finding_count": len(file_findings),
        }
        files.append(record)
        for finding in file_findings:
            findings.append({"path": str(relative), **finding})

    counts: dict[str, int] = {}
    for record in files:
        counts[record["category"]] = counts.get(record["category"], 0) + 1

    return {
        "course": "Azure Foundry Maze Migration From Scratch",
        "phase": 1,
        "phase_name": "Portability Inventory",
        "source_app": str(SOURCE_APP.relative_to(PROJECT_ROOT.parent)),
        "status": "complete",
        "summary": {
            "files_scanned": len(files),
            "categories": counts,
            "findings": len(findings),
            "public_repo_blocked_until_sanitized": bool(findings),
            "next_phase": "Create a public-safe standalone repo copy and remove generated local-provider metadata.",
        },
        "files": files,
        "findings": findings,
        "azure_mapping": AZURE_MAPPING,
        "cost_guardrails": COST_GUARDRAILS,
    }


def render_phase_html(inventory: dict[str, Any]) -> str:
    finding_rows = []
    for finding in inventory["findings"]:
        finding_rows.append(
            "<tr>"
            f"<td>{html.escape(finding['path'])}</td>"
            f"<td>{html.escape(finding['type'])}</td>"
            f"<td>{html.escape(str(finding['line']))}</td>"
            f"<td><code>{html.escape(finding['match'])}</code></td>"
            "</tr>"
        )
    file_rows = []
    for record in inventory["files"]:
        file_rows.append(
            "<tr>"
            f"<td>{html.escape(record['path'])}</td>"
            f"<td>{html.escape(record['category'])}</td>"
            f"<td>{html.escape(record['public_action'])}</td>"
            f"<td>{record['finding_count']}</td>"
            "</tr>"
        )
    mapping_cards = []
    for item in inventory["azure_mapping"]:
        mapping_cards.append(
            "<article>"
            f"<span>{html.escape(item['local'])}</span>"
            f"<strong>{html.escape(item['azure'])}</strong>"
            f"<p>{html.escape(item['migration_note'])}</p>"
            "</article>"
        )
    cost_items = "".join(f"<li>{html.escape(item)}</li>" for item in inventory["cost_guardrails"])

    summary = inventory["summary"]
    data = html.escape(json.dumps(inventory, indent=2))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Azure Foundry Maze Migration - Phase 1</title>
  <style>
    :root {{ --bg:#f7f8fa; --panel:#fff; --text:#17202a; --muted:#5f6b7a; --line:#d9dee7; --blue:#285da8; --green:#1f6f5b; --red:#b91c1c; --shadow:0 10px 28px rgba(28,36,48,.08); }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:var(--text); background:var(--bg); line-height:1.5; }}
    main {{ width:min(1200px, calc(100% - 32px)); margin:0 auto; padding:32px 0 48px; }}
    header {{ display:grid; grid-template-columns:minmax(0,1fr) 280px; gap:20px; border-bottom:1px solid var(--line); padding-bottom:20px; margin-bottom:22px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(28px,4vw,42px); line-height:1.08; }}
    h2 {{ margin:0 0 12px; font-size:20px; }}
    p {{ margin:0; color:var(--muted); }}
    .panel,.summary,article {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; box-shadow:var(--shadow); }}
    .summary,.panel {{ padding:16px; }}
    .summary strong {{ display:block; font-size:30px; }}
    .grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }}
    article {{ padding:14px; box-shadow:none; border-left:5px solid var(--blue); }}
    article span {{ display:block; color:var(--muted); font-size:12px; font-weight:800; text-transform:uppercase; }}
    article strong {{ display:block; margin:4px 0; }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th,td {{ padding:9px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-size:12px; text-transform:uppercase; }}
    li {{ margin:7px 0; color:var(--muted); }}
    code {{ color:var(--red); }}
    pre {{ overflow:auto; max-height:420px; padding:12px; background:#111827; color:#e5e7eb; border-radius:8px; font-size:12px; }}
    .stack {{ display:grid; gap:14px; }}
    @media (max-width:900px) {{ header,.grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Phase 1 - Portability Inventory</h1>
        <p>Inventory the local maze app before GitHub publishing or Azure Foundry migration.</p>
      </div>
      <aside class="summary">
        <span>Files Scanned</span>
        <strong>{summary['files_scanned']}</strong>
        <p>{summary['findings']} public-safety findings require review.</p>
      </aside>
    </header>
    <div class="stack">
      <section class="panel">
        <h2>Azure Migration Map</h2>
        <div class="grid">{''.join(mapping_cards)}</div>
      </section>
      <section class="panel">
        <h2>Cost Guardrails</h2>
        <ul>{cost_items}</ul>
      </section>
      <section class="panel">
        <h2>Public Repo Findings</h2>
        <table>
          <thead><tr><th>File</th><th>Type</th><th>Line</th><th>Match</th></tr></thead>
          <tbody>{''.join(finding_rows) if finding_rows else '<tr><td colspan="4">No findings</td></tr>'}</tbody>
        </table>
      </section>
      <section class="panel">
        <h2>File Inventory</h2>
        <table>
          <thead><tr><th>File</th><th>Category</th><th>Public Action</th><th>Findings</th></tr></thead>
          <tbody>{''.join(file_rows)}</tbody>
        </table>
      </section>
      <section class="panel">
        <h2>Next Phase</h2>
        <p>{html.escape(summary['next_phase'])}</p>
      </section>
      <section class="panel">
        <h2>Inventory JSON</h2>
        <details><summary>Open generated inventory</summary><pre>{data}</pre></details>
      </section>
    </div>
  </main>
</body>
</html>
"""


def render_progress_html(inventory: dict[str, Any]) -> str:
    summary = inventory["summary"]
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
    <section class="card">
      <h2>Phase 1: Portability Inventory</h2>
      <p>Status: complete. Files scanned: {summary['files_scanned']}. Findings: {summary['findings']}.</p>
      <p><a href="visuals/PHASE1_VISUAL.html">Open visual</a> | <a href="PHASE1_PORTABILITY_INVENTORY.md">Notes</a> | <a href="PHASE1_VALIDATION.md">Validation</a></p>
    </section>
    <section class="card">
      <h2>Next: Phase 2</h2>
      <p>{html.escape(summary['next_phase'])}</p>
    </section>
  </main>
</body>
</html>
"""


def main() -> int:
    inventory = build_inventory()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    VISUALS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "phase1_inventory.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    (VISUALS_DIR / "PHASE1_VISUAL.html").write_text(render_phase_html(inventory), encoding="utf-8")
    PROGRESS_PATH.write_text(render_progress_html(inventory), encoding="utf-8")
    print(f"phase={inventory['phase']}")
    print(f"files_scanned={inventory['summary']['files_scanned']}")
    print(f"findings={inventory['summary']['findings']}")
    print(f"public_repo_blocked_until_sanitized={inventory['summary']['public_repo_blocked_until_sanitized']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
