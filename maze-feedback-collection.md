# Maze Feedback Collection

## Purpose

This document explains the simple human-feedback mechanism added to the Azure
Foundry maze learning app. The goal is to capture learner judgment about each
agent outcome without immediately changing agent behavior.

The same pattern can be reused for another agent application in a different
customer tenant:

```text
User observes agent behavior
-> User gives thumbs up or thumbs down
-> Web UI posts structured feedback
-> API validates and normalizes the feedback
-> Application Insights records telemetry
-> Log Analytics Workspace makes it queryable
-> Optional durable app memory stores the event with the run
```

For this phase, feedback is observational only. It does not call an LLM, alter
the prompt, rewrite Team Memory, change the route, or retry the run.

## Implemented User Experience

Each maze card has feedback controls next to the maze title:

```text
Maze A
Worker Agent A
[thumbs up] [thumbs down]
Optional note

Maze B
Worker Agent B
[thumbs up] [thumbs down]
Optional note
```

The mapping is intentionally simple:

```text
maze_a -> Worker Agent A
maze_b -> Worker Agent B
```

This lets the learner say:

```text
Maze A / Worker Agent A: good result
Maze B / Worker Agent B: poor result
```

The optional note is useful when a thumbs-down needs context, for example:

```text
Worker B repeated between (0,2) and (0,3) several times before finding the route.
```

## Why Thumbs Up / Thumbs Down

The first feedback interface should be low-friction. A richer taxonomy is useful
later, but early feedback capture should not interrupt the learning workflow.

The current schema captures:

```text
rating: up | down
target worker
target maze
optional note
run id
worker LLM call counts
worker outcomes
workflow stage
timestamp
```

This gives enough signal to answer questions such as:

```text
Which worker gets the most thumbs down?
Are thumbs-down events correlated with high LLM call counts?
Are users downvoting runs that reached the goal but took a poor path?
Are users downvoting impossible-maze detection failures?
```

## Frontend Flow

The WebUI keeps feedback state in browser memory for the currently loaded trace.
When the learner clicks thumbs up or thumbs down, the UI posts to `/api/feedback`.

Representative frontend payload:

```json
{
  "run_id": "phase18-fabbcfd6b0b84331",
  "phase": 18,
  "maze_id": "maze_b",
  "rating": "down",
  "note": "Worker B repeated between (0,2) and (0,3) before finding the route.",
  "summary": {
    "worker_a_llm_calls": 8,
    "worker_b_llm_calls": 14,
    "worker_a_outcome": "goal_reached",
    "worker_b_outcome": "goal_reached",
    "workflow_stage": "workers_complete"
  }
}
```

Important frontend behaviors:

```text
The feedback button is selected locally after submission.
The note is capped at 500 characters.
The page shows "Feedback saved" after successful persistence.
The feedback call is independent of Play/Pause/Replay.
The feedback call does not increment agent LLM call counters.
```

Minimal frontend pattern:

```javascript
async function submitFeedback(mazeId, rating, note, trace) {
  const summary = trace.summary || {};
  const response = await fetch('/api/feedback', {
    method: 'POST',
    cache: 'no-store',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      run_id: summary.team_memory_run_id || '',
      phase: trace.phase || 18,
      maze_id: mazeId,
      rating,
      note,
      summary
    })
  });
  return response.json();
}
```

## Backend Flow

The Azure WebUI Function exposes:

```text
POST /api/feedback
```

The backend does three things:

```text
1. Validate the feedback.
2. Log a structured event to Application Insights.
3. Append the event to durable Team Memory when run_id exists.
```

Validation rules:

```text
rating must be: up or down
maze_id must be: maze_a or maze_b
note is trimmed and truncated to 500 characters
run_id is trimmed and truncated to 256 characters
```

The API response confirms whether telemetry and Team Memory persistence worked:

```json
{
  "source": "maze-human-feedback",
  "status": "recorded",
  "event_name": "MazeFeedback",
  "app_insights_logged": true,
  "team_memory_persisted": true,
  "team_memory_error": null
}
```

Minimal backend pattern:

```python
def build_feedback_event(payload: dict[str, Any]) -> dict[str, Any]:
    rating = str(payload.get("rating") or "").strip().lower()
    maze_id = str(payload.get("maze_id") or "").strip().lower()
    if rating not in {"up", "down"}:
        raise ValueError("rating must be up or down")
    if maze_id not in {"maze_a", "maze_b"}:
        raise ValueError("maze_id must be maze_a or maze_b")

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "event_name": "MazeFeedback",
        "feedback_schema": "thumbs_v1",
        "run_id": str(payload.get("run_id") or "").strip()[:256],
        "maze_id": maze_id,
        "worker": "Worker Agent A" if maze_id == "maze_a" else "Worker Agent B",
        "rating": rating,
        "note": str(payload.get("note") or "").strip()[:500],
        "worker_a_calls": int(summary.get("worker_a_llm_calls") or 0),
        "worker_b_calls": int(summary.get("worker_b_llm_calls") or 0),
        "worker_a_outcome": str(summary.get("worker_a_outcome") or "unknown")[:80],
        "worker_b_outcome": str(summary.get("worker_b_outcome") or "unknown")[:80],
        "workflow_stage": str(summary.get("workflow_stage") or "unknown")[:80],
        "created_at": utc_now(),
    }
```

Logging pattern:

```python
event = build_feedback_event(payload)
logging.info("MazeFeedback %s", json.dumps(event, separators=(",", ":")))
```

The string prefix `MazeFeedback ` is intentional. It makes the event easy to
find in both Application Insights and Log Analytics Workspace.

## Captured Fields

| Field | Meaning |
| --- | --- |
| `event_name` | Constant value: `MazeFeedback`. |
| `feedback_schema` | Current schema version: `thumbs_v1`. |
| `phase` | Curriculum phase where feedback was captured. |
| `run_id` | Durable Team Memory run id. |
| `maze_id` | `maze_a` or `maze_b`. |
| `maze_label` | Human-readable label such as `Maze A`. |
| `worker` | Worker being evaluated. |
| `rating` | `up` or `down`. |
| `note` | Optional user note, max 500 characters. |
| `worker_a_calls` | Worker A LLM calls at feedback time. |
| `worker_b_calls` | Worker B LLM calls at feedback time. |
| `worker_a_outcome` | Worker A outcome at feedback time. |
| `worker_b_outcome` | Worker B outcome at feedback time. |
| `workflow_stage` | Current run stage, for example `mission_ready`, `workers_running`, or `workers_complete`. |
| `created_at` | UTC timestamp generated by the API. |

## Application Insights vs Log Analytics Workspace

The same telemetry is visible from both places, but table and column names differ
depending on query scope.

When querying from Application Insights Logs:

```text
table: traces
timestamp column: timestamp
message column: message
```

When querying from Log Analytics Workspace Logs:

```text
table: AppTraces
timestamp column: TimeGenerated
message column: Message
```

If you run an Application Insights query from the LAW blade, you may see:

```text
'where' operator: Failed to resolve table or column expression named 'traces'
```

Use `AppTraces` in LAW.

## Log Analytics Workspace Queries

Use this when you are in the workspace Logs blade.

Recent feedback:

```kusto
AppTraces
| where TimeGenerated > ago(24h)
| where Message startswith "MazeFeedback "
| extend payload = parse_json(substring(Message, strlen("MazeFeedback ")))
| project TimeGenerated,
          run_id=tostring(payload.run_id),
          maze_id=tostring(payload.maze_id),
          worker=tostring(payload.worker),
          rating=tostring(payload.rating),
          note=tostring(payload.note),
          worker_a_calls=toint(payload.worker_a_calls),
          worker_b_calls=toint(payload.worker_b_calls),
          worker_a_outcome=tostring(payload.worker_a_outcome),
          worker_b_outcome=tostring(payload.worker_b_outcome),
          workflow_stage=tostring(payload.workflow_stage)
| order by TimeGenerated desc
```

Count feedback by worker and rating:

```kusto
AppTraces
| where TimeGenerated > ago(7d)
| where Message startswith "MazeFeedback "
| extend payload = parse_json(substring(Message, strlen("MazeFeedback ")))
| summarize feedback_count=count()
    by worker=tostring(payload.worker),
       rating=tostring(payload.rating)
| order by worker asc, rating asc
```

Find thumbs-down notes:

```kusto
AppTraces
| where TimeGenerated > ago(7d)
| where Message startswith "MazeFeedback "
| extend payload = parse_json(substring(Message, strlen("MazeFeedback ")))
| where tostring(payload.rating) == "down"
| project TimeGenerated,
          run_id=tostring(payload.run_id),
          maze_id=tostring(payload.maze_id),
          worker=tostring(payload.worker),
          note=tostring(payload.note),
          worker_a_calls=toint(payload.worker_a_calls),
          worker_b_calls=toint(payload.worker_b_calls),
          workflow_stage=tostring(payload.workflow_stage)
| order by TimeGenerated desc
```

Find feedback correlated with high Worker call counts:

```kusto
AppTraces
| where TimeGenerated > ago(7d)
| where Message startswith "MazeFeedback "
| extend payload = parse_json(substring(Message, strlen("MazeFeedback ")))
| extend rating=tostring(payload.rating),
         worker=tostring(payload.worker),
         worker_a_calls=toint(payload.worker_a_calls),
         worker_b_calls=toint(payload.worker_b_calls)
| extend target_worker_calls = case(
    worker == "Worker Agent A", worker_a_calls,
    worker == "Worker Agent B", worker_b_calls,
    int(null)
)
| summarize feedback_count=count(),
            avg_target_worker_calls=avg(target_worker_calls),
            max_target_worker_calls=max(target_worker_calls)
    by worker, rating
| order by worker asc, rating asc
```

Daily feedback trend:

```kusto
AppTraces
| where TimeGenerated > ago(30d)
| where Message startswith "MazeFeedback "
| extend payload = parse_json(substring(Message, strlen("MazeFeedback ")))
| summarize up=countif(tostring(payload.rating) == "up"),
            down=countif(tostring(payload.rating) == "down"),
            total=count()
    by bin(TimeGenerated, 1d)
| extend down_rate = todouble(down) / todouble(total)
| order by TimeGenerated asc
```

## Application Insights Queries

Use this when you are in the Application Insights Logs blade for the WebUI app.

Recent feedback:

```kusto
traces
| where timestamp > ago(24h)
| where message startswith "MazeFeedback "
| extend payload = parse_json(substring(message, strlen("MazeFeedback ")))
| project timestamp,
          run_id=tostring(payload.run_id),
          maze_id=tostring(payload.maze_id),
          worker=tostring(payload.worker),
          rating=tostring(payload.rating),
          note=tostring(payload.note),
          worker_a_calls=toint(payload.worker_a_calls),
          worker_b_calls=toint(payload.worker_b_calls),
          worker_a_outcome=tostring(payload.worker_a_outcome),
          worker_b_outcome=tostring(payload.worker_b_outcome),
          workflow_stage=tostring(payload.workflow_stage)
| order by timestamp desc
```

Feedback summary:

```kusto
traces
| where timestamp > ago(7d)
| where message startswith "MazeFeedback "
| extend payload = parse_json(substring(message, strlen("MazeFeedback ")))
| summarize feedback_count=count()
    by worker=tostring(payload.worker),
       rating=tostring(payload.rating)
| order by worker asc, rating asc
```

## Team Memory Storage

Telemetry is the main reporting path. The app also appends each feedback event to
durable Team Memory when a `run_id` is available.

Current Team Memory key:

```text
feedback.events
```

Shape:

```json
[
  {
    "event_name": "MazeFeedback",
    "feedback_schema": "thumbs_v1",
    "run_id": "phase18-fabbcfd6b0b84331",
    "maze_id": "maze_b",
    "maze_label": "Maze B",
    "worker": "Worker Agent B",
    "rating": "up",
    "note": "",
    "worker_a_calls": 8,
    "worker_b_calls": 14,
    "worker_a_outcome": "goal_reached",
    "worker_b_outcome": "goal_reached",
    "workflow_stage": "workers_complete",
    "created_at": "2026-08-28T01:02:12.557723+00:00"
  }
]
```

Why store feedback in both places:

```text
Application Insights / LAW:
Best for cross-run metrics, dashboards, alerts, and trend analysis.

Team Memory:
Best for replaying or inspecting one specific run with its full context.
```

## Recommended Portal Navigation

Application Insights:

```text
Azure Portal
-> Application Insights resource for the WebUI Function App
-> Logs
-> use traces query
```

Log Analytics Workspace:

```text
Azure Portal
-> Log Analytics Workspace connected to the WebUI App Insights resource
-> Logs
-> use AppTraces query
```

In this lab, the LAW backing the WebUI App Insights resource is:

```text
managed-maze-webui-func-prav-ada483-ws
```

The workspace may appear under a managed resource group rather than the main lab
resource group.

## Tenant Portability Checklist

For another customer tenant, implement the same mechanism with these steps:

```text
1. Pick a simple feedback schema.
2. Add per-agent or per-task feedback controls in the UI.
3. POST feedback to a backend endpoint.
4. Validate rating, target id, note length, and run id.
5. Log one structured event with a stable prefix.
6. Send logs to Application Insights.
7. Confirm Application Insights is workspace-based.
8. Query feedback in LAW using AppTraces.
9. Optionally persist feedback to the app's durable run memory.
10. Keep feedback observational until you intentionally design adaptation.
```

Recommended minimum schema:

```json
{
  "event_name": "AgentFeedback",
  "feedback_schema": "thumbs_v1",
  "tenant_id": "customer-or-lab-tenant",
  "app": "agent-app-name",
  "environment": "dev",
  "run_id": "run-123",
  "agent": "agent-name",
  "task_id": "task-or-document-id",
  "rating": "up",
  "note": "",
  "created_at": "UTC timestamp"
}
```

Useful optional fields:

```text
model deployment
prompt version
agent version
tool version
workflow stage
task outcome
LLM call count
token count
latency
error code
user role
UI view
```

## Design Guidance

Use thumbs-only first when:

```text
The user is focused on reviewing agent behavior.
You want minimal friction.
You do not yet know the right failure taxonomy.
You mainly need enough data to identify patterns.
```

Add richer reason codes later when repeated feedback shows stable categories:

```text
suboptimal_path
wrong_answer
too_many_calls
missed_block
stale_memory
bad_tool_use
unclear_explanation
slow_response
```

Do not let feedback automatically modify agent behavior until you have:

```text
enough samples
clear review process
guardrails against bad feedback
separation between telemetry and training data
approval workflow for prompt or policy changes
```

## Privacy and Security Notes

Do not log secrets or raw credentials in feedback notes.

For customer tenants:

```text
Avoid collecting user email unless needed.
Prefer hashed or opaque user/session ids.
Limit free-text note length.
Sanitize or classify notes if they may contain sensitive data.
Set retention according to customer policy.
Use RBAC so only authorized operators can read feedback telemetry.
Keep production and dev feedback streams separable.
```

## Operational Notes

The feedback endpoint should be cheap:

```text
No LLM call.
No agent execution.
One API request.
One log event.
One optional durable memory write.
```

The feedback path should also be resilient:

```text
If Team Memory write fails, still log telemetry.
If telemetry is temporarily delayed, Team Memory can still hold run-local feedback.
If the user gives feedback before a durable run id exists, log telemetry with an empty or generated run id.
```

For dashboards and reports, prefer LAW queries because they can aggregate across
many runs and can later join with other App Insights tables such as requests,
exceptions, dependencies, and custom metrics.
