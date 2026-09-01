# Phase 25 Validation

## Expected Result

```text
After Reviewer completes:
  Review panel shows score and threshold separately
  Review panel shows Accept Review
  Review panel shows Request Retry Planning
  selecting either button records a durable gate decision
```

## Validation Checks

Local syntax:

```bash
python3 -m py_compile webui/phase8-azure-webui/function_app.py
```

WebUI health:

```bash
curl https://maze-webui-func-prav-ada483.azurewebsites.net/api/health
```

Browser validation:

```text
1. Open the Maze Foundry WebUI.
2. Click Run Fresh Maze.
3. Click Play.
4. Wait for Reviewer output.
5. Confirm Score is shown as "N out of 100" and Threshold is shown separately.
6. Click Accept Review or Request Retry Planning.
7. Confirm the status bar says the Review Gate was recorded.
8. Confirm the learner timeline includes Azure WebUI Review Gate.
```

## Log Analytics Query

Use the WebUI Application Insights / Log Analytics workspace:

```kusto
AppTraces
| where Message startswith "MazeReviewGate "
| extend payload = parse_json(substring(Message, strlen("MazeReviewGate ")))
| project
    TimeGenerated,
    run_id=tostring(payload.run_id),
    decision=tostring(payload.decision),
    review_status=tostring(payload.review_status),
    review_score=toint(payload.review_score),
    review_threshold=toint(payload.review_threshold),
    retry_target=tostring(payload.retry_target),
    worker_a_outcome=tostring(payload.worker_a_outcome),
    worker_b_outcome=tostring(payload.worker_b_outcome)
| order by TimeGenerated desc
```

Some workspaces use `traces` instead of `AppTraces` depending on the query
surface. If `AppTraces` is unavailable, switch only the first line:

```kusto
traces
```

## Acceptance Criteria

```text
[ ] Review panel has human gate buttons
[ ] Review score and threshold are not ambiguous
[ ] /api/review-decision records accepted
[ ] /api/review-decision records retry_requested
[ ] Team Memory contains review.gate.latest
[ ] App Insights receives MazeReviewGate log records
[ ] No Worker retry is automatically triggered
```

## Current Lab Result

Phase 25 was deployed in the Visual Studio Enterprise Subscription on
2026-09-01.

```text
Commit:
  265071d Add phase 25 review gate

WebUI package:
  runs/phase25_webui.zip

WebUI:
  https://maze-webui-func-prav-ada483.azurewebsites.net/
```

Validation completed:

```text
Python compile:
  passed

Extracted browser JavaScript syntax:
  passed

WebUI health:
  {"status":"ok"}

Live HTML check:
  Accept Review button present
  Request Retry Planning button present
  /api/review-decision call present
```

API-level gate validation used a synthetic run id:

```text
POST /api/review-decision
run_id: phase25-validation
decision: accepted

Result:
  source: maze-review-gate
  status: recorded
  event_name: MazeReviewGate
  team_memory_persisted: true
  phase: 25
  workflow_stage: review_gate_recorded
  llm calls: 0
```
