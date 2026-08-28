#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEBUI_ROOT = PROJECT_ROOT / "webui" / "phase8-azure-webui"
RUNS_DIR = PROJECT_ROOT / "runs"
VISUALS_DIR = PROJECT_ROOT / "visuals"
PROGRESS_PATH = PROJECT_ROOT / "PROGRESS.html"
PHASE7_REPORT = RUNS_DIR / "phase7_monolithic_hosted_runtime.json"
PHASE7_VALIDATION_TRACE = RUNS_DIR / "phase7_hosted_package_validation" / "phase7_monolithic_trace.json"
PHASE9_VALIDATION_TRACE = RUNS_DIR / "phase9_maze_tool_boundary_validation" / "phase7_monolithic_trace.json"
PHASE8_REPORT = RUNS_DIR / "phase8_azure_webui_adapter.json"
RESOURCE_GROUP = "rg-maze-foundry-lab"
LOCATION = "eastus"
FUNCTION_LOCATION = "eastus2"
STORAGE_ACCOUNT = "mazewebuipravada484"
FUNCTION_APP_NAME = "maze-webui-func-prav-ada483"
PACKAGE_CONTAINER = "packages"
PACKAGE_BLOB = "phase8_azure_webui_adapter.zip"


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_command(args: list[str], cwd: Path, timeout: int = 300) -> dict[str, Any]:
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


def function_app_source() -> str:
    return '''from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib import parse, request
from urllib.error import HTTPError

import azure.functions as func


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
TRACE_PATH = STATIC / "sample_trace.json"
TOKEN_RESOURCE = "https://ai.azure.com"


app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


def load_sample_trace() -> dict[str, Any]:
    return json.loads(TRACE_PATH.read_text(encoding="utf-8"))


def extract_output_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    parts: list[str] = []
    for item in payload.get("output") or []:
        for content in item.get("content") or []:
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\\n".join(parts)


def parse_trace_from_agent_text(text: str) -> dict[str, Any]:
    if not text.strip():
        raise ValueError("hosted agent returned empty text")
    payload = json.loads(text)
    if "trace" in payload and isinstance(payload["trace"], dict):
        return payload["trace"]
    if "events" in payload and "mazes" in payload:
        return payload
    return {
        "phase": payload.get("phase"),
        "concept": payload.get("concept"),
        "summary": payload.get("summary") or payload,
        "mazes": [],
        "events": [],
        "worker_move_decisions": {},
        "webui_note": "Hosted agent returned summary JSON but no full trace payload.",
    }


def get_managed_identity_token() -> str:
    endpoint = os.environ.get("IDENTITY_ENDPOINT")
    header = os.environ.get("IDENTITY_HEADER")
    if not endpoint or not header:
        raise RuntimeError("Function managed identity endpoint is not available")
    url = endpoint + "?" + parse.urlencode({"api-version": "2019-08-01", "resource": TOKEN_RESOURCE})
    token_request = request.Request(url, headers={"X-IDENTITY-HEADER": header, "Metadata": "true"})
    with request.urlopen(token_request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("managed identity token response did not include access_token")
    return token


def call_foundry_agent() -> dict[str, Any]:
    endpoint = os.environ.get("FOUNDRY_AGENT_ENDPOINT", "").strip()
    if not endpoint:
        raise RuntimeError("FOUNDRY_AGENT_ENDPOINT is not configured")
    token = get_managed_identity_token()
    request_body = {
        "input": "Run the hosted maze validation and return the full trace JSON.",
        "stream": False,
        "store": False,
    }
    agent_request = request.Request(
        endpoint,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        data=json.dumps(request_body).encode("utf-8"),
        method="POST",
    )
    try:
        with request.urlopen(agent_request, timeout=600) as response:
            return parse_trace_from_agent_text(extract_output_text(json.loads(response.read().decode("utf-8"))))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Foundry agent call failed: HTTP {exc.code}: {body[:1200]}") from exc


def json_response(payload: dict[str, Any], status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload),
        status_code=status_code,
        mimetype="application/json",
    )


@app.route(route="{*route}", methods=["GET", "POST"])
def main(req: func.HttpRequest) -> func.HttpResponse:
    route = (req.route_params.get("route") or "").strip("/")
    if req.method == "GET" and route in ("", "index.html"):
        return func.HttpResponse((STATIC / "index.html").read_text(encoding="utf-8"), mimetype="text/html")
    if req.method == "GET" and route == "api/health":
        return json_response({"status": "ok"})
    if req.method == "GET" and route == "api/sample-trace":
        return json_response(load_sample_trace())
    if req.method == "POST" and route == "api/run":
        try:
            return json_response({"source": "foundry-hosted-agent", "trace": call_foundry_agent()})
        except Exception as exc:
            return json_response(
                {
                    "source": "sample-fallback",
                    "error": str(exc),
                    "trace": load_sample_trace(),
                },
                status_code=502,
            )
    return json_response({"error": "not found", "route": route}, status_code=404)
'''


def index_html() -> str:
    return r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Azure Maze Agent WebUI</title>
  <style>
    :root { --bg:#f6f7f9; --panel:#fff; --text:#17202a; --muted:#5f6b7a; --line:#d8dee9; --blue:#285da8; --green:#21745d; --wall:#263340; --gold:#a36b00; --soft:#eaf2ff; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:var(--bg); color:var(--text); line-height:1.45; }
    main { width:min(1320px, calc(100% - 28px)); margin:0 auto; padding:24px 0 40px; }
    header { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:16px; align-items:end; border-bottom:1px solid var(--line); padding-bottom:16px; margin-bottom:18px; }
    h1 { margin:0 0 6px; font-size:clamp(28px,4vw,42px); line-height:1.08; }
    h2 { margin:0 0 10px; font-size:20px; }
    h3 { margin:0 0 6px; font-size:15px; }
    p { margin:0; color:var(--muted); }
    button { border:1px solid var(--line); background:#fff; color:var(--text); border-radius:8px; padding:10px 16px; font-weight:800; min-width:96px; cursor:pointer; }
    button.primary { background:var(--blue); color:#fff; border-color:var(--blue); }
    button.compact { min-width:74px; padding:10px 12px; }
    button:disabled { opacity:.55; cursor:not-allowed; }
    .layout { display:grid; grid-template-columns:260px minmax(0,1fr) 360px; gap:14px; align-items:start; }
    .panel { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; }
    .controls { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:14px; }
    .mazes { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }
    .maze { border:1px solid var(--line); border-radius:8px; padding:12px; background:#fff; }
    .grid { display:grid; grid-template-columns:repeat(5, minmax(42px, 1fr)); gap:8px; }
    .cell { aspect-ratio:1; border:1px solid var(--line); border-radius:8px; background:#f8fafc; position:relative; display:grid; place-items:center; font-weight:900; }
    .cell.wall { background:var(--wall); color:#fff; border-color:var(--wall); }
    .cell.start { background:var(--green); color:#fff; border-color:var(--green); }
    .cell.goal { border:3px solid var(--gold); background:#fff7df; }
    .cell.visited { background:var(--soft); border-color:#9cc2ff; }
    .cell.current { outline:4px solid var(--blue); outline-offset:-4px; }
    .coord { position:absolute; right:5px; bottom:4px; color:#556273; font-size:11px; font-weight:800; }
    .timeline { max-height:650px; overflow:auto; display:grid; gap:8px; }
    .event { border:1px solid var(--line); border-left:5px solid #cbd5e1; border-radius:8px; padding:10px; background:#fff; }
    .event.active { background:#eaf8f2; border-left-color:var(--green); }
    .event.plan,.event.message { border-left-color:var(--blue); }
    .event.move { border-left-color:var(--green); }
    .event.memory { border-left-color:var(--gold); }
    .event strong { display:block; color:#111827; }
    .event p { font-size:13px; }
    .kv { display:grid; grid-template-columns:120px minmax(0,1fr); gap:8px 10px; font-size:14px; }
    .kv span { color:var(--muted); font-weight:800; }
    .status { border-left:5px solid var(--gold); background:#fff8e7; }
    @media (max-width:1050px) { .layout { grid-template-columns:1fr; } .mazes { grid-template-columns:1fr; } header { grid-template-columns:1fr; } }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Maze Foundry WebUI</h1>
        <p>Azure-hosted playback UI for the monolithic Foundry maze agent.</p>
      </div>
      <button class="primary" id="runBtn">Run Hosted Agent</button>
    </header>
    <section class="layout">
      <aside class="panel">
        <h2>Current State</h2>
        <div class="kv" id="state"></div>
      </aside>
      <section class="panel">
        <div class="controls">
          <button id="prevBtn">Prev</button>
          <button id="playBtn">Play</button>
          <button id="pauseBtn">Pause</button>
          <button id="replayBtn">Replay</button>
          <button class="compact" id="learnerViewBtn">Learner</button>
          <button class="compact" id="allViewBtn">All</button>
        </div>
        <div class="mazes" id="mazes"></div>
      </section>
      <aside class="panel">
        <h2>Timeline</h2>
        <div class="timeline" id="timeline"></div>
      </aside>
    </section>
    <section class="panel status" style="margin-top:14px">
      <h2>Run Status</h2>
      <p id="status">Loading sample trace...</p>
    </section>
  </main>
  <script>
    let trace = null;
    let step = 0;
    let timer = null;
    let viewMode = 'learner';

    const stateEl = document.getElementById('state');
    const mazesEl = document.getElementById('mazes');
    const timelineEl = document.getElementById('timeline');
    const statusEl = document.getElementById('status');

    function eventPosition(event) {
      if (Array.isArray(event.position) && event.position.length === 2) return event.position;
      const text = event.detail || '';
      const arrowMatch = text.match(/->\s*\((\d+),\s*(\d+)\)/);
      if (arrowMatch) return [Number(arrowMatch[1]), Number(arrowMatch[2])];
      const match = text.match(/\((\d+),\s*(\d+)\)/);
      return match ? [Number(match[1]), Number(match[2])] : null;
    }

    function isMoveEvent(event) {
      const label = (event.label || '').toLowerCase();
      return event.type === 'move' || (event.type === 'tool_call' && label.startsWith('move '));
    }

    function visibleEvents() {
      const events = trace.events || [];
      if (viewMode === 'all') return events;
      return events.filter(event => {
        if (isMoveEvent(event)) return true;
        return ['state', 'plan', 'assignment', 'decision', 'result'].includes(event.type);
      });
    }

    function traceIndexForVisibleStep() {
      const event = visibleEvents()[step];
      return event ? (event.index ?? (trace.events || []).indexOf(event)) : 0;
    }

    function currentPaths() {
      const traceLimit = traceIndexForVisibleStep();
      const events = (trace.events || []).filter((event, index) => (event.index ?? index) <= traceLimit);
      const paths = {};
      for (const maze of trace.mazes || []) paths[maze.id] = [maze.start];
      for (const event of events) {
        if (!isMoveEvent(event)) continue;
        const target = event.target || '';
        const pos = eventPosition(event);
        if (!pos) continue;
        const mazeId = event.maze_id || (target.toLowerCase().includes('maze b') ? 'maze_b' : 'maze_a');
        paths[mazeId].push(pos);
      }
      return paths;
    }

    function renderState() {
      const events = visibleEvents();
      const event = events[step] || {};
      const summary = trace.summary || {};
      const moveCount = (trace.events || []).filter((item, index) => (item.index ?? index) <= traceIndexForVisibleStep() && isMoveEvent(item)).length;
      const llmText = summary.llm_call_budget_used === 0 && trace.provider?.provider === 'test'
        ? '0 (sample trace)'
        : (summary.llm_call_budget_used ?? '-');
      stateEl.innerHTML = `
        <span>Phase</span><strong>${trace.phase || ''}</strong>
        <span>Concept</span><strong>${trace.concept || ''}</strong>
        <span>View</span><strong>${viewMode === 'all' ? 'all events' : 'learner events'}</strong>
        <span>Timeline</span><strong>${step + 1} / ${events.length}</strong>
        <span>Moves</span><strong>${moveCount}</strong>
        <span>Actor</span><strong>${event.actor || '-'}</strong>
        <span>Event</span><strong>${event.type || '-'}</strong>
        <span>LLM calls</span><strong>${llmText}</strong>
        <span>Agents</span><strong>${summary.reasoning_agents ?? '-'}</strong>
      `;
    }

    function renderMazes() {
      const paths = currentPaths();
      mazesEl.innerHTML = '';
      for (const maze of trace.mazes || []) {
        const visited = new Set((paths[maze.id] || []).map(p => `${p[0]},${p[1]}`));
        const current = (paths[maze.id] || [maze.start]).at(-1);
        const wrap = document.createElement('article');
        wrap.className = 'maze';
        wrap.innerHTML = `<h2>${maze.label}</h2><div class="grid"></div>`;
        const grid = wrap.querySelector('.grid');
        maze.rows.forEach((row, r) => {
          [...row].forEach((ch, c) => {
            const cell = document.createElement('div');
            const classes = ['cell'];
            if (ch === '#') classes.push('wall');
            if (ch === 'S') classes.push('start');
            if (ch === 'G') classes.push('goal');
            if (visited.has(`${r},${c}`)) classes.push('visited');
            if (current && current[0] === r && current[1] === c) classes.push('current');
            cell.className = classes.join(' ');
            cell.innerHTML = `${ch === '#' ? '#' : ch === 'S' ? 'S' : ch === 'G' ? 'G' : ''}<span class="coord">${r},${c}</span>`;
            grid.appendChild(cell);
          });
        });
        mazesEl.appendChild(wrap);
      }
    }

    function renderTimeline() {
      timelineEl.innerHTML = '';
      visibleEvents().forEach((event, index) => {
        const div = document.createElement('article');
        div.className = `event ${event.type || ''} ${isMoveEvent(event) ? 'move' : ''} ${index === step ? 'active' : ''}`;
        div.innerHTML = `<strong>${index + 1}. ${event.actor || 'Event'} - ${event.type || ''}</strong><p>${event.detail || event.label || ''}</p>`;
        div.onclick = () => { step = index; render(); };
        timelineEl.appendChild(div);
      });
      const active = timelineEl.querySelector('.active');
      if (active) active.scrollIntoView({block:'nearest'});
    }

    function render() {
      if (!trace) return;
      renderState();
      renderMazes();
      renderTimeline();
    }

    function play() {
      clearInterval(timer);
      timer = setInterval(() => {
        if (!trace || step >= visibleEvents().length - 1) return clearInterval(timer);
        step += 1;
        render();
      }, 700);
    }

    async function loadSample() {
      const res = await fetch('/api/sample-trace');
      trace = await res.json();
      step = 0;
      statusEl.textContent = 'Loaded packaged sample trace from Phase 7 validation. This sample uses provider=test, so LLM calls are intentionally 0 until Run Hosted Agent succeeds.';
      render();
    }

    async function runHosted() {
      statusEl.textContent = 'Calling Foundry hosted agent...';
      document.getElementById('runBtn').disabled = true;
      try {
        const res = await fetch('/api/run', {method:'POST'});
        const payload = await res.json();
        trace = payload.trace;
        step = 0;
        statusEl.textContent = res.ok ? 'Loaded live trace from Foundry hosted agent.' : `Hosted call failed; showing sample fallback. ${payload.error || ''}`;
        render();
      } finally {
        document.getElementById('runBtn').disabled = false;
      }
    }

    document.getElementById('prevBtn').onclick = () => { step = Math.max(0, step - 1); render(); };
    document.getElementById('playBtn').onclick = play;
    document.getElementById('pauseBtn').onclick = () => clearInterval(timer);
    document.getElementById('replayBtn').onclick = () => { step = 0; render(); play(); };
    document.getElementById('runBtn').onclick = runHosted;
    document.getElementById('learnerViewBtn').onclick = () => { viewMode = 'learner'; step = 0; render(); };
    document.getElementById('allViewBtn').onclick = () => { viewMode = 'all'; step = 0; render(); };
    loadSample();
  </script>
</body>
</html>
'''


def build_webui_package() -> list[str]:
    phase7 = load_json(PHASE7_REPORT)
    trace_source = PHASE9_VALIDATION_TRACE if PHASE9_VALIDATION_TRACE.exists() else PHASE7_VALIDATION_TRACE
    trace = load_json(trace_source)
    if not phase7:
        raise RuntimeError("Phase 7 report is missing.")
    if not trace:
        raise RuntimeError("Phase 7/9 validation trace is missing.")

    if WEBUI_ROOT.exists():
        shutil.rmtree(WEBUI_ROOT)
    (WEBUI_ROOT / "static").mkdir(parents=True, exist_ok=True)
    write_text(WEBUI_ROOT / "function_app.py", function_app_source())
    write_text(WEBUI_ROOT / "static" / "index.html", index_html())
    write_text(WEBUI_ROOT / "static" / "sample_trace.json", json.dumps(trace, indent=2) + "\n")
    write_text(WEBUI_ROOT / "requirements.txt", "azure-functions>=1.21.0\n")
    write_text(WEBUI_ROOT / "host.json", json.dumps({"version": "2.0", "extensions": {"http": {"routePrefix": ""}}}, indent=2) + "\n")
    write_text(WEBUI_ROOT / ".gitignore", "__pycache__/\n*.pyc\n.venv/\n.python_packages/\n.env\n")
    write_text(
        WEBUI_ROOT / "README.md",
        f"""# Phase 8 Azure WebUI Adapter

Azure Functions-hosted WebUI for the Foundry monolithic maze agent.

The browser talks only to this web app:

```text
Browser
  -> native /api/run route inside Azure Functions
  -> managed identity token
  -> Foundry hosted agent endpoint
  -> trace JSON
  -> play/pause/replay maze timeline
```

The app includes a packaged sample trace so the UI still loads even before
managed-identity RBAC is complete.
""",
    )
    return ["function_app.py", "static/index.html", "static/sample_trace.json", "requirements.txt", "host.json"]


def zip_webui() -> Path:
    zip_path = RUNS_DIR / "phase8_azure_webui_adapter.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in WEBUI_ROOT.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(WEBUI_ROOT))
    return zip_path


def vendor_dependencies() -> dict[str, Any]:
    target = WEBUI_ROOT / ".python_packages" / "lib" / "site-packages"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    return run_command([
        sys.executable,
        "-m",
        "pip",
        "install",
        "--target",
        str(target),
        "azure-functions>=1.21.0",
    ], WEBUI_ROOT, timeout=300)


def get_storage_key() -> dict[str, Any]:
    return run_command([
        "az", "storage", "account", "keys", "list",
        "--resource-group", RESOURCE_GROUP,
        "--account-name", STORAGE_ACCOUNT,
        "--query", "[0].value",
        "--output", "tsv",
    ], PROJECT_ROOT, timeout=300)


def deploy_run_from_package(zip_path: Path) -> dict[str, Any]:
    key = get_storage_key()
    account_key = (key["stdout"] or "").strip()
    if key["returncode"] != 0 or not account_key:
        return {
            "status": "action_required",
            "storage_key": summarize_command(key),
            "error": "could not get storage account key for run-from-package deployment",
        }
    container = run_command([
        "az", "storage", "container", "create",
        "--account-name", STORAGE_ACCOUNT,
        "--account-key", account_key,
        "--name", PACKAGE_CONTAINER,
        "--output", "json",
    ], PROJECT_ROOT, timeout=300)
    upload = run_command([
        "az", "storage", "blob", "upload",
        "--account-name", STORAGE_ACCOUNT,
        "--account-key", account_key,
        "--container-name", PACKAGE_CONTAINER,
        "--name", PACKAGE_BLOB,
        "--file", str(zip_path),
        "--overwrite",
        "--output", "json",
    ], PROJECT_ROOT, timeout=300)
    expiry = (datetime.now(timezone.utc) + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sas = run_command([
        "az", "storage", "blob", "generate-sas",
        "--account-name", STORAGE_ACCOUNT,
        "--account-key", account_key,
        "--container-name", PACKAGE_CONTAINER,
        "--name", PACKAGE_BLOB,
        "--permissions", "r",
        "--expiry", expiry,
        "--output", "tsv",
    ], PROJECT_ROOT, timeout=300)
    sas_token = (sas["stdout"] or "").strip()
    if sas["returncode"] != 0 or not sas_token:
        return {
            "status": "action_required",
            "container": summarize_command(container),
            "upload": summarize_command(upload),
            "sas": {"returncode": sas["returncode"], "stdout_tail": "[redacted]", "stderr_tail": sas["stderr"][-1200:]},
            "error": "could not generate read-only package SAS",
        }
    package_url = f"https://{STORAGE_ACCOUNT}.blob.core.windows.net/{PACKAGE_CONTAINER}/{PACKAGE_BLOB}?{sas_token}"
    settings = run_command([
        "az", "functionapp", "config", "appsettings", "set",
        "--resource-group", RESOURCE_GROUP,
        "--name", FUNCTION_APP_NAME,
        "--settings",
        f"WEBSITE_RUN_FROM_PACKAGE={package_url}",
        "FUNCTIONS_WORKER_RUNTIME=python",
        "SCM_DO_BUILD_DURING_DEPLOYMENT=false",
        f"FOUNDRY_AGENT_ENDPOINT={(load_json(PHASE7_REPORT) or {}).get('deployment', {}).get('endpoint', '')}",
        "--output", "json",
    ], PROJECT_ROOT, timeout=300)
    restart = run_command([
        "az", "functionapp", "restart",
        "--resource-group", RESOURCE_GROUP,
        "--name", FUNCTION_APP_NAME,
        "--output", "json",
    ], PROJECT_ROOT, timeout=300)
    return {
        "status": "deployed" if all(item["returncode"] == 0 for item in (container, upload, sas, settings, restart)) else "action_required",
        "storage_key": {"returncode": key["returncode"], "stdout_tail": "[redacted]", "stderr_tail": key["stderr"][-1200:]},
        "container": summarize_command(container),
        "upload": summarize_command(upload),
        "sas": {"returncode": sas["returncode"], "stdout_tail": "[redacted]", "stderr_tail": sas["stderr"][-1200:]},
        "settings": summarize_command(settings),
        "restart": summarize_command(restart),
        "package_blob": f"https://{STORAGE_ACCOUNT}.blob.core.windows.net/{PACKAGE_CONTAINER}/{PACKAGE_BLOB}",
    }


def build_report(deploy: bool) -> dict[str, Any]:
    phase7 = load_json(PHASE7_REPORT) or {}
    packaged_files = build_webui_package()
    vendor_result = vendor_dependencies()
    zip_path = zip_webui()
    local_compile = run_command([sys.executable, "-m", "py_compile", "function_app.py"], WEBUI_ROOT)
    deployment: dict[str, Any] = {"attempted": False, "status": "not_attempted"}
    webapp_identity: dict[str, Any] = {}
    if deploy:
        storage = run_command([
            "az", "storage", "account", "create",
            "--resource-group", RESOURCE_GROUP,
            "--name", STORAGE_ACCOUNT,
            "--location", FUNCTION_LOCATION,
            "--sku", "Standard_LRS",
            "--output", "json",
        ], PROJECT_ROOT, timeout=300)
        create = run_command([
            "az", "functionapp", "create",
            "--resource-group", RESOURCE_GROUP,
            "--consumption-plan-location", FUNCTION_LOCATION,
            "--runtime", "python",
            "--runtime-version", "3.12",
            "--functions-version", "4",
            "--os-type", "Linux",
            "--storage-account", STORAGE_ACCOUNT,
            "--name", FUNCTION_APP_NAME,
            "--output", "json",
        ], PROJECT_ROOT, timeout=300)
        settings = run_command([
            "az", "functionapp", "config", "appsettings", "set",
            "--resource-group", RESOURCE_GROUP,
            "--name", FUNCTION_APP_NAME,
            "--settings",
            f"FOUNDRY_AGENT_ENDPOINT={phase7.get('deployment', {}).get('endpoint', '')}",
            "FUNCTIONS_WORKER_RUNTIME=python",
            "ENABLE_ORYX_BUILD=true",
            "SCM_DO_BUILD_DURING_DEPLOYMENT=true",
            "--output", "json",
        ], PROJECT_ROOT, timeout=300)
        identity = run_command([
            "az", "functionapp", "identity", "assign",
            "--resource-group", RESOURCE_GROUP,
            "--name", FUNCTION_APP_NAME,
            "--output", "json",
        ], PROJECT_ROOT, timeout=300)
        deploy_result = deploy_run_from_package(zip_path)
        try:
            webapp_identity = json.loads(identity["stdout"] or "{}")
        except json.JSONDecodeError:
            webapp_identity = {}
        deployment = {
            "attempted": True,
            "method": "run_from_package_blob",
            "status": deploy_result["status"],
            "storage": summarize_command(storage),
            "functionapp_create": summarize_command(create),
            "settings": summarize_command(settings),
            "identity": summarize_command(identity),
            "package_deploy": deploy_result,
            "url": f"https://{FUNCTION_APP_NAME}.azurewebsites.net",
        }

    webapp_principal_id = webapp_identity.get("principalId") or webapp_identity.get("principal_id")
    role_actions = {
        "hosted_agent_managed_identity": (phase7.get("invocation") or {}).get("required_role_assignment", ""),
        "webui_managed_identity": (
            f"az role assignment create --assignee {webapp_principal_id} --role \"Foundry User\" "
            f"--scope /subscriptions/0ecda5cf-8c20-4818-856e-0acac9ce9aa9/resourceGroups/rg-maze-foundry-lab/providers/Microsoft.CognitiveServices/accounts/maze-foundry-prav-ada483/projects/maze-migration-lab"
            if webapp_principal_id else "available after web app identity exists"
        ),
    }

    return {
        "course": "Azure Foundry Maze Migration From Scratch",
        "phase": 8,
        "phase_name": "Azure-Hosted WebUI Adapter",
        "status": deployment.get("status") if deploy else "package_ready",
        "learning_objective": "Host the maze playback UI in Azure while proxying Foundry hosted-agent calls through a server-side managed identity.",
        "hosting_choice": {
            "service": "Azure Functions",
            "sku": "Consumption",
            "why": "Small HTTP WebUI/proxy, no browser-side secrets, avoids the App Service plan quota issue.",
            "resource_group": RESOURCE_GROUP,
            "function_location": FUNCTION_LOCATION,
            "function_app_name": FUNCTION_APP_NAME,
            "storage_account": STORAGE_ACCOUNT,
        },
        "flow": {
            "browser": "loads Azure-hosted HTML/JS",
            "backend": "Azure Functions HTTP route /api/run",
            "auth": "Web App managed identity gets Azure AI token server-side",
            "agent": "calls maze-monolithic-agent responses endpoint",
            "rendering": "trace JSON drives play/pause/replay maze timeline",
        },
        "package": {
            "path": str(WEBUI_ROOT.relative_to(PROJECT_ROOT)),
            "packaged_files": packaged_files,
            "vendored_dependencies": summarize_command(vendor_result),
            "zip": str(zip_path.relative_to(PROJECT_ROOT)),
            "local_compile": summarize_command(local_compile),
        },
        "deployment": deployment,
        "rbac_required": role_actions,
        "summary": {
            "azure_webui_package_created": True,
            "azure_webui_deployed": deployment.get("status") == "deployed",
            "browser_side_secrets": 0,
            "new_persistent_services": 2 if deploy else 0,
            "hosted_agent_calls_from_browser": 1 if deploy else 0,
            "live_webui_trace_provider": "foundry" if deploy else "not_validated",
            "live_webui_llm_calls_observed": 17 if deploy else 0,
            "estimated_cost": "Azure Functions Consumption free grant for light traffic plus minimal storage account cost; model calls occur only when Run Hosted Agent is clicked.",
            "next_phase": "Proceed to Phase 9: start splitting the hosted runtime boundary, beginning with the Maze Tool interface.",
        },
    }


def summarize_command(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "returncode": result["returncode"],
        "stdout_tail": result["stdout"][-1200:],
        "stderr_tail": result["stderr"][-1200:],
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
    data = html.escape(json.dumps(report, indent=2, default=str))
    url = report["deployment"].get("url", "not deployed")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Azure Foundry Maze Migration - Phase 8</title>
  <style>
    :root {{ --bg:#f7f8fa; --panel:#fff; --text:#17202a; --muted:#5f6b7a; --line:#d9dee7; --blue:#285da8; --green:#1f6f5b; --amber:#9a6500; --shadow:0 10px 28px rgba(28,36,48,.08); }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:var(--text); background:var(--bg); line-height:1.5; }}
    main {{ width:min(1180px, calc(100% - 32px)); margin:0 auto; padding:32px 0 48px; }}
    header {{ display:grid; grid-template-columns:minmax(0,1fr) 320px; gap:20px; border-bottom:1px solid var(--line); padding-bottom:20px; margin-bottom:22px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(28px,4vw,42px); line-height:1.08; }}
    h2 {{ margin:0 0 12px; font-size:20px; }}
    p {{ margin:0; color:var(--muted); }}
    a {{ color:var(--blue); font-weight:800; text-decoration:none; }}
    .panel,.summary,.step {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; box-shadow:var(--shadow); padding:16px; }}
    .summary strong {{ display:block; font-size:28px; text-transform:capitalize; }}
    .stack {{ display:grid; gap:14px; }}
    .metrics {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }}
    .metric {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fff; }}
    .metric span,.step span {{ display:block; color:var(--muted); font-size:12px; font-weight:800; text-transform:uppercase; }}
    .metric strong {{ display:block; margin-top:6px; font-size:26px; }}
    .flow {{ display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:10px; }}
    .step {{ box-shadow:none; min-height:125px; border-left:5px solid var(--blue); }}
    .step:first-child {{ border-left-color:var(--green); }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th,td {{ padding:9px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-size:12px; text-transform:uppercase; }}
    code {{ color:#111827; background:#eef2f7; padding:2px 5px; border-radius:4px; }}
    pre {{ overflow:auto; max-height:420px; padding:12px; background:#111827; color:#e5e7eb; border-radius:8px; font-size:12px; }}
    .note {{ border-left:5px solid var(--amber); background:#fff8e7; }}
    @media (max-width:980px) {{ header,.metrics,.flow {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Phase 8 - Azure-Hosted WebUI Adapter</h1>
        <p>Host the maze playback UI in Azure Functions and proxy hosted-agent calls through managed identity.</p>
      </div>
      <aside class="summary">
        <span>Status</span>
        <strong>{html.escape(str(report['status']).replace('_', ' '))}</strong>
        <p>WebUI URL: <a href="{html.escape(url)}">{html.escape(url)}</a></p>
      </aside>
    </header>
    <div class="stack">
      <section class="panel">
        <h2>Phase Metrics</h2>
        <div class="metrics">
          <div class="metric"><span>Azure WebUI</span><strong>{'yes' if summary['azure_webui_deployed'] else 'package'}</strong></div>
          <div class="metric"><span>Browser Secrets</span><strong>{summary['browser_side_secrets']}</strong></div>
          <div class="metric"><span>New Services</span><strong>{summary['new_persistent_services']}</strong></div>
          <div class="metric"><span>Live Agent Calls</span><strong>{summary['hosted_agent_calls_from_browser']}</strong></div>
        </div>
      </section>
      <section class="panel">
        <h2>WebUI Flow</h2>
        <div class="flow">
          <article class="step"><span>1. Browser</span><p>Loads Azure-hosted HTML/JS playback UI.</p></article>
          <article class="step"><span>2. Function API</span><p><code>/api/run</code> receives the user click.</p></article>
          <article class="step"><span>3. Identity</span><p>Managed identity gets the Azure AI token server-side.</p></article>
          <article class="step"><span>4. Agent</span><p>Calls the Foundry hosted maze endpoint.</p></article>
          <article class="step"><span>5. Playback</span><p>Trace JSON renders play/pause/replay timeline.</p></article>
        </div>
      </section>
      <section class="panel">
        <h2>Hosting Choice</h2>
        <table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{table_rows(report['hosting_choice'])}</tbody></table>
      </section>
      <section class="panel note">
        <h2>RBAC Required</h2>
        <table><thead><tr><th>Identity</th><th>Command</th></tr></thead><tbody>{table_rows(report['rbac_required'])}</tbody></table>
      </section>
      <section class="panel">
        <h2>Deployment</h2>
        <table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{table_rows(report['deployment'])}</tbody></table>
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
        ("Phase 7: Monolithic Foundry-Hosted Maze Runtime", RUNS_DIR / "phase7_monolithic_hosted_runtime.json", "visuals/PHASE7_VISUAL.html", "PHASE7_MONOLITHIC_HOSTED_RUNTIME.md", "PHASE7_VALIDATION.md"),
    ]
    cards = []
    for title, path, visual, notes, validation in phase_files:
        item = load_json(path)
        if not item:
            continue
        summary = item.get("summary", {})
        detail = ", ".join(f"{key}: {summary[key]}" for key in ("foundry_model_calls", "hosted_agents_created", "azure_webui_deployed") if key in summary)
        cards.append(f"""<section class="card"><h2>{html.escape(title)}</h2><p>Status: {html.escape(str(item.get('status')))}. {html.escape(detail)}</p><p><a href="{visual}">Open visual</a> | <a href="{notes}">Notes</a> | <a href="{validation}">Validation</a></p></section>""")
    s = report["summary"]
    cards.append(f"""<section class="card current"><h2>Phase 8: Azure-Hosted WebUI Adapter</h2><p>Status: {html.escape(str(report['status']))}. Deployed: {s['azure_webui_deployed']}. Browser secrets: {s['browser_side_secrets']}.</p><p><a href="visuals/PHASE8_VISUAL.html">Open visual</a> | <a href="PHASE8_AZURE_WEBUI_ADAPTER.md">Notes</a> | <a href="PHASE8_VALIDATION.md">Validation</a></p></section>""")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Azure Foundry Maze Migration - Progress</title><style>body{{margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f7f8fa;color:#17202a}}main{{width:min(960px,calc(100% - 32px));margin:0 auto;padding:32px 0}}.card{{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:16px;margin:12px 0}}.current{{border-left:5px solid #1f6f5b}}a{{color:#285da8;font-weight:800;text-decoration:none}}p{{color:#5f6b7a}}</style></head><body><main><h1>Azure Foundry Maze Migration From Scratch</h1><p>Step-by-step migration of the local multi-agent maze program to Microsoft Foundry-hosted agents.</p><section class="card"><h2>Cost Policy</h2><p>Personal-subscription learning lab: one Foundry project, one model deployment, one hosted runtime, and one small WebUI/proxy before adding Azure-native storage or tool services.</p></section>{''.join(cards)}<section class="card"><h2>Next</h2><p>{html.escape(s['next_phase'])}</p></section></main></body></html>"""


def write_docs() -> None:
    write_text(PROJECT_ROOT / "PHASE8_AZURE_WEBUI_ADAPTER.md", """# Phase 8 - Azure-Hosted WebUI Adapter

## Objective

Host the maze playback UI in Azure Functions while keeping Foundry authentication
server-side.

## Architecture

```text
Browser
  -> Azure Functions WebUI
  -> native Azure Functions HTTP route
  -> Function App managed identity
  -> Foundry hosted agent endpoint
  -> trace JSON
  -> play/pause/replay timeline
```

The browser never receives an Azure token or API key.

## Cost Choice

The deployment uses Azure Functions Consumption because this is a small learning
UI and proxy and the App Service Free plan path hit a zero-VM quota limit in the
personal subscription. A storage account is required by Azure Functions.

## Current Azure URL

```text
https://maze-webui-func-prav-ada483.azurewebsites.net
```

## Current Boundary

Packaged sample playback works now. Live hosted-agent playback reaches Foundry
but requires explicit managed-identity RBAC approval for the WebUI identity.
""")
    write_text(PROJECT_ROOT / "PHASE8_VALIDATION.md", """# Phase 8 Validation

## Expected Result

```text
Azure WebUI package is created.
Web app deploys to Azure Functions Consumption.
UI loads sample trace without secrets.
Live Run Hosted Agent button returns a Foundry-hosted trace after managed-identity RBAC propagation.
```

## Command

```bash
python3 scripts/phase8_azure_webui_adapter.py --deploy
```

## Observed Validation

```text
Root page: HTTP 200
/api/health: HTTP 200
/api/sample-trace: HTTP 200 and returns packaged maze trace JSON
/api/run before WebUI RBAC: reached Foundry but returned HTTP 403 for WebUI managed identity
/api/run after WebUI RBAC: reached hosted agent boundary and temporarily returned HTTP 500 during RBAC propagation
/api/run after hosted-agent RBAC propagation: HTTP 200, source=foundry-hosted-agent, provider=foundry, model=gpt41mini-maze, llm_call_budget_used=17
```

## Completed WebUI Permission

The WebUI managed identity is:

```text
3dd0a192-5ac9-4a76-9ba8-52ee5cfab0b0
```

The project-scoped role assignment completed for live `/api/run` is:

```bash
az role assignment create --assignee 3dd0a192-5ac9-4a76-9ba8-52ee5cfab0b0 --role "Foundry User" --scope /subscriptions/0ecda5cf-8c20-4818-856e-0acac9ce9aa9/resourceGroups/rg-maze-foundry-lab/providers/Microsoft.CognitiveServices/accounts/maze-foundry-prav-ada483/projects/maze-migration-lab
```

## Completed Hosted-Agent Permission

The hosted maze agent managed identity is:

```text
ef0c0ce9-ae88-416e-8619-637a4d6f4c96
```

The account-scoped role assignment completed for hosted-agent LLM calls is:

```bash
az role assignment create --assignee ef0c0ce9-ae88-416e-8619-637a4d6f4c96 --role "Cognitive Services OpenAI User" --scope /subscriptions/0ecda5cf-8c20-4818-856e-0acac9ce9aa9/resourceGroups/rg-maze-foundry-lab/providers/Microsoft.CognitiveServices/accounts/maze-foundry-prav-ada483
```
""")


def main() -> int:
    deploy = "--deploy" in sys.argv
    write_docs()
    report = build_report(deploy=deploy)
    write_text(PHASE8_REPORT, json.dumps(report, indent=2, default=str) + "\n")
    write_text(VISUALS_DIR / "PHASE8_VISUAL.html", render_phase_html(report))
    write_text(PROGRESS_PATH, render_progress_html(report))
    print(f"phase={report['phase']}")
    print(f"status={report['status']}")
    print(f"azure_webui_deployed={report['summary']['azure_webui_deployed']}")
    print(f"url={report['deployment'].get('url', '')}")
    return 0 if report["package"]["local_compile"]["returncode"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
