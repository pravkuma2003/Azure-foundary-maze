#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_APP = PROJECT_ROOT.parent / "multi-agent-reasoning-from-scratch"
EXPORTS_DIR = PROJECT_ROOT / "exports"
PUBLIC_EXPORT = EXPORTS_DIR / "multi-agent-reasoning-from-scratch-public"
RUNS_DIR = PROJECT_ROOT / "runs"
VISUALS_DIR = PROJECT_ROOT / "visuals"
PROGRESS_PATH = PROJECT_ROOT / "PROGRESS.html"

EXCLUDED_DIRS = {".git", "__pycache__", "runs", "visuals"}
EXCLUDED_FILES = {"PROGRESS.html"}

BLOCKING_PATTERNS = {
    "private_ip": re.compile(r"\b(?:10|172\.(?:1[6-9]|2\d|3[0-1])|192\.168)\.\d{1,3}\.\d{1,3}\b"),
    "local_home_path": re.compile(r"(/Users/[^\\s\"'<>]+|/home/[^\\s\"'<>]+)"),
}

REDACTIONS = [
    (re.compile(r"http://172\.29\.1\.233:4000/v1"), "http://localhost:4000/v1"),
    (re.compile(r"http://172\.29\.1\.233:8766"), "http://localhost:8766"),
    (
        re.compile(r"/home/prav/orb-execute/orb-execute/learn-agent/multi-agent-reasoning-from-scratch"),
        "/path/to/multi-agent-reasoning-from-scratch",
    ),
    (
        re.compile(r"/Users/[^\\s\"'<>]+/orb-execute/learn-agent/multi-agent-reasoning-from-scratch"),
        "/path/to/multi-agent-reasoning-from-scratch",
    ),
    (re.compile(r"linux-research/nuc12"), "your local model host"),
    (re.compile(r"linux-research"), "your local model host"),
    (re.compile(r"nuc12"), "your local model host"),
]


def should_copy(path: Path) -> bool:
    relative = path.relative_to(SOURCE_APP)
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        return False
    if path.name in EXCLUDED_FILES:
        return False
    return path.is_file()


def sanitize_text(text: str) -> tuple[str, list[str]]:
    changes = []
    sanitized = text
    for pattern, replacement in REDACTIONS:
        sanitized, count = pattern.subn(replacement, sanitized)
        if count:
            changes.append(f"{pattern.pattern} -> {replacement} ({count})")
    return sanitized, changes


def copy_public_files() -> list[dict[str, Any]]:
    if not SOURCE_APP.exists():
        raise FileNotFoundError(f"source app not found: {SOURCE_APP}")

    if PUBLIC_EXPORT.exists():
        shutil.rmtree(PUBLIC_EXPORT)
    PUBLIC_EXPORT.mkdir(parents=True)

    copied: list[dict[str, Any]] = []
    for source_path in sorted(SOURCE_APP.rglob("*")):
        if not should_copy(source_path):
            continue
        relative = source_path.relative_to(SOURCE_APP)
        target_path = PUBLIC_EXPORT / relative
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            text = source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            shutil.copy2(source_path, target_path)
            copied.append({"path": str(relative), "action": "copied binary", "redactions": []})
            continue
        sanitized, changes = sanitize_text(text)
        target_path.write_text(sanitized, encoding="utf-8")
        copied.append(
            {
                "path": str(relative),
                "action": "copied sanitized" if changes else "copied",
                "redactions": changes,
            }
        )

    for directory in ("runs", "visuals"):
        keep = PUBLIC_EXPORT / directory / ".gitkeep"
        keep.parent.mkdir(parents=True, exist_ok=True)
        keep.write_text("", encoding="utf-8")

    env_example = """# Local OpenAI-compatible model endpoint for the public learning repo.
# Do not commit real keys or personal endpoint values.
OPENAI_BASE_URL=http://localhost:4000/v1
OPENAI_API_KEY=local-placeholder
MAZE_MODEL=fast
"""
    (PUBLIC_EXPORT / ".env.example").write_text(env_example, encoding="utf-8")

    public_gitignore = """__pycache__/
*.pyc
.env
runs/*.json
runs/*.tmp
visuals/*.html
"""
    (PUBLIC_EXPORT / ".gitignore").write_text(public_gitignore, encoding="utf-8")

    return copied


def scan_export() -> list[dict[str, Any]]:
    findings = []
    for path in sorted(PUBLIC_EXPORT.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(PUBLIC_EXPORT)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for finding_type, pattern in BLOCKING_PATTERNS.items():
                for match in pattern.finditer(line):
                    findings.append(
                        {
                            "path": str(relative),
                            "type": finding_type,
                            "line": line_number,
                            "match": match.group(0),
                        }
                    )
    return findings


def build_manifest(copied: list[dict[str, Any]], findings: list[dict[str, Any]]) -> dict[str, Any]:
    excluded = []
    for source_path in sorted(SOURCE_APP.rglob("*")):
        if source_path.is_file() and not should_copy(source_path):
            excluded.append(str(source_path.relative_to(SOURCE_APP)))

    redacted_files = [item for item in copied if item["redactions"]]
    return {
        "course": "Azure Foundry Maze Migration From Scratch",
        "phase": 2,
        "phase_name": "Public Repo and Secret Hygiene",
        "status": "complete" if not findings else "blocked",
        "source_app": str(SOURCE_APP.relative_to(PROJECT_ROOT.parent)),
        "public_export": str(PUBLIC_EXPORT.relative_to(PROJECT_ROOT)),
        "summary": {
            "files_copied": len(copied),
            "files_excluded": len(excluded),
            "files_redacted": len(redacted_files),
            "blocking_findings_after_export": len(findings),
            "public_repo_candidate_ready": not findings,
            "next_phase": "Use device-code login and verify Azure subscription readiness before provisioning anything.",
        },
        "copied": copied,
        "excluded": excluded,
        "redacted_files": redacted_files,
        "blocking_findings": findings,
        "public_repo_rules": [
            "Generated traces and visual HTML are excluded from the public candidate and should be regenerated by the user.",
            "Local IP addresses are replaced with localhost examples.",
            "Local filesystem paths are replaced with generic /path/to examples.",
            "Secrets are not copied; .env is ignored and only .env.example is included.",
            "Azure resources are not provisioned in this phase.",
        ],
    }


def render_phase_html(manifest: dict[str, Any]) -> str:
    summary = manifest["summary"]
    rule_items = "".join(f"<li>{html.escape(rule)}</li>" for rule in manifest["public_repo_rules"])
    redaction_rows = []
    for item in manifest["redacted_files"]:
        redaction_rows.append(
            "<tr>"
            f"<td>{html.escape(item['path'])}</td>"
            f"<td>{html.escape(str(len(item['redactions'])))}</td>"
            f"<td>{html.escape('; '.join(item['redactions']))}</td>"
            "</tr>"
        )
    excluded_rows = "".join(f"<tr><td>{html.escape(path)}</td></tr>" for path in manifest["excluded"])
    finding_rows = []
    for finding in manifest["blocking_findings"]:
        finding_rows.append(
            "<tr>"
            f"<td>{html.escape(finding['path'])}</td>"
            f"<td>{html.escape(finding['type'])}</td>"
            f"<td>{html.escape(str(finding['line']))}</td>"
            f"<td><code>{html.escape(finding['match'])}</code></td>"
            "</tr>"
        )
    manifest_json = html.escape(json.dumps(manifest, indent=2))
    status_text = "ready" if summary["public_repo_candidate_ready"] else "blocked"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Azure Foundry Maze Migration - Phase 2</title>
  <style>
    :root {{ --bg:#f7f8fa; --panel:#fff; --text:#17202a; --muted:#5f6b7a; --line:#d9dee7; --blue:#285da8; --green:#1f6f5b; --amber:#a86a00; --red:#b91c1c; --shadow:0 10px 28px rgba(28,36,48,.08); }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:var(--text); background:var(--bg); line-height:1.5; }}
    main {{ width:min(1180px, calc(100% - 32px)); margin:0 auto; padding:32px 0 48px; }}
    header {{ display:grid; grid-template-columns:minmax(0,1fr) 260px; gap:20px; border-bottom:1px solid var(--line); padding-bottom:20px; margin-bottom:22px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(28px,4vw,42px); line-height:1.08; }}
    h2 {{ margin:0 0 12px; font-size:20px; }}
    p {{ margin:0; color:var(--muted); }}
    .panel,.summary,.step {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; box-shadow:var(--shadow); }}
    .summary,.panel {{ padding:16px; }}
    .summary strong {{ display:block; font-size:30px; text-transform:capitalize; }}
    .metrics {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }}
    .metric {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fff; }}
    .metric span {{ display:block; color:var(--muted); font-size:12px; font-weight:800; text-transform:uppercase; }}
    .metric strong {{ display:block; margin-top:6px; font-size:26px; }}
    .flow {{ display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:10px; align-items:stretch; }}
    .step {{ padding:14px; box-shadow:none; border-left:5px solid var(--blue); min-height:118px; }}
    .step:nth-child(3) {{ border-left-color:var(--amber); }}
    .step:nth-child(5) {{ border-left-color:var(--green); }}
    .step span {{ display:block; color:var(--muted); font-size:12px; font-weight:800; text-transform:uppercase; }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th,td {{ padding:9px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-size:12px; text-transform:uppercase; }}
    li {{ margin:7px 0; color:var(--muted); }}
    code {{ color:var(--red); }}
    pre {{ overflow:auto; max-height:420px; padding:12px; background:#111827; color:#e5e7eb; border-radius:8px; font-size:12px; }}
    .stack {{ display:grid; gap:14px; }}
    @media (max-width:900px) {{ header,.metrics,.flow {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Phase 2 - Public Repo and Secret Hygiene</h1>
        <p>Create a public-safe candidate copy before GitHub publishing or Azure provisioning.</p>
      </div>
      <aside class="summary">
        <span>Candidate Status</span>
        <strong>{status_text}</strong>
        <p>{summary['blocking_findings_after_export']} blocking findings after export.</p>
      </aside>
    </header>
    <div class="stack">
      <section class="panel">
        <h2>Export Metrics</h2>
        <div class="metrics">
          <div class="metric"><span>Copied</span><strong>{summary['files_copied']}</strong></div>
          <div class="metric"><span>Excluded</span><strong>{summary['files_excluded']}</strong></div>
          <div class="metric"><span>Redacted</span><strong>{summary['files_redacted']}</strong></div>
          <div class="metric"><span>Azure Cost</span><strong>$0</strong></div>
        </div>
      </section>
      <section class="panel">
        <h2>Hygiene Flow</h2>
        <div class="flow">
          <article class="step"><span>1. Source</span><strong>Local maze repo</strong><p>Start from the working learning app.</p></article>
          <article class="step"><span>2. Exclude</span><strong>Generated output</strong><p>Old traces and visuals are left out.</p></article>
          <article class="step"><span>3. Redact</span><strong>Machine details</strong><p>Private IPs and local paths become examples.</p></article>
          <article class="step"><span>4. Guard</span><strong>.gitignore + .env.example</strong><p>Real environment values stay local.</p></article>
          <article class="step"><span>5. Verify</span><strong>Public candidate</strong><p>The candidate is scanned before GitHub.</p></article>
        </div>
      </section>
      <section class="panel">
        <h2>Public Repo Rules</h2>
        <ul>{rule_items}</ul>
      </section>
      <section class="panel">
        <h2>Redacted Files</h2>
        <table>
          <thead><tr><th>File</th><th>Changes</th><th>Redactions</th></tr></thead>
          <tbody>{''.join(redaction_rows) if redaction_rows else '<tr><td colspan="3">No redactions needed</td></tr>'}</tbody>
        </table>
      </section>
      <section class="panel">
        <h2>Excluded Generated Files</h2>
        <table>
          <thead><tr><th>File</th></tr></thead>
          <tbody>{excluded_rows}</tbody>
        </table>
      </section>
      <section class="panel">
        <h2>Blocking Findings After Export</h2>
        <table>
          <thead><tr><th>File</th><th>Type</th><th>Line</th><th>Match</th></tr></thead>
          <tbody>{''.join(finding_rows) if finding_rows else '<tr><td colspan="4">No blocking findings</td></tr>'}</tbody>
        </table>
      </section>
      <section class="panel">
        <h2>Next Phase</h2>
        <p>{html.escape(summary['next_phase'])}</p>
      </section>
      <section class="panel">
        <h2>Manifest JSON</h2>
        <details><summary>Open generated manifest</summary><pre>{manifest_json}</pre></details>
      </section>
    </div>
  </main>
</body>
</html>
"""


def load_phase1_summary() -> dict[str, Any] | None:
    path = RUNS_DIR / "phase1_inventory.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def render_progress_html(manifest: dict[str, Any]) -> str:
    phase1 = load_phase1_summary()
    phase1_summary = phase1["summary"] if phase1 else None
    phase2_summary = manifest["summary"]
    phase1_card = ""
    if phase1_summary:
        phase1_card = f"""
    <section class="card">
      <h2>Phase 1: Portability Inventory</h2>
      <p>Status: complete. Files scanned: {phase1_summary['files_scanned']}. Findings: {phase1_summary['findings']}.</p>
      <p><a href="visuals/PHASE1_VISUAL.html">Open visual</a> | <a href="PHASE1_PORTABILITY_INVENTORY.md">Notes</a> | <a href="PHASE1_VALIDATION.md">Validation</a></p>
    </section>"""
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
    </section>{phase1_card}
    <section class="card">
      <h2>Phase 2: Public Repo and Secret Hygiene</h2>
      <p>Status: {html.escape(manifest['status'])}. Copied: {phase2_summary['files_copied']}. Excluded: {phase2_summary['files_excluded']}. Redacted: {phase2_summary['files_redacted']}. Blocking findings: {phase2_summary['blocking_findings_after_export']}.</p>
      <p><a href="visuals/PHASE2_VISUAL.html">Open visual</a> | <a href="PHASE2_PUBLIC_REPO_HYGIENE.md">Notes</a> | <a href="PHASE2_VALIDATION.md">Validation</a></p>
    </section>
    <section class="card">
      <h2>Next: Phase 3</h2>
      <p>{html.escape(phase2_summary['next_phase'])}</p>
    </section>
  </main>
</body>
</html>
"""


def main() -> int:
    copied = copy_public_files()
    findings = scan_export()
    manifest = build_manifest(copied, findings)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    VISUALS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "phase2_public_repo_hygiene.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    (VISUALS_DIR / "PHASE2_VISUAL.html").write_text(render_phase_html(manifest), encoding="utf-8")
    PROGRESS_PATH.write_text(render_progress_html(manifest), encoding="utf-8")
    print(f"phase={manifest['phase']}")
    print(f"files_copied={manifest['summary']['files_copied']}")
    print(f"files_excluded={manifest['summary']['files_excluded']}")
    print(f"files_redacted={manifest['summary']['files_redacted']}")
    print(f"blocking_findings_after_export={manifest['summary']['blocking_findings_after_export']}")
    print(f"public_repo_candidate_ready={manifest['summary']['public_repo_candidate_ready']}")
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
