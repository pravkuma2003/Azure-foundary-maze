# Phase 24 Validation

## Expected Result

```text
Hosted agents:
  maze-analyst-agent-docker
  maze-worker-agent-a-docker
  maze-worker-agent-b-docker
  maze-reviewer-agent-docker

WebUI:
  calls Analyst to generate mazes
  calls Workers in parallel ticks after Play
  calls Reviewer after both Workers are terminal
  renders review score, status, and findings
```

## Validation Checks

Local checks:

```bash
python3 -m py_compile \
  hosted/maze-role-agents/main.py \
  webui/phase8-azure-webui/function_app.py \
  scripts/phase20_foundry_acr_image_runtime.py \
  scripts/phase22_acr_task_build_trigger.py \
  scripts/phase23_validate_candidate_before_promotion.py
```

Reviewer test-provider smoke:

```bash
cd hosted/maze-role-agents
python3 main.py --once --provider test --role reviewer
```

Candidate image gate:

```bash
python3 scripts/phase23_validate_candidate_before_promotion.py --apply
```

Promotion after passing validation:

```bash
python3 scripts/phase23_validate_candidate_before_promotion.py --apply --promote-if-valid
```

WebUI runtime setting:

```text
FOUNDRY_REVIEWER_AGENT_ENDPOINT is configured on the WebUI Function App.
```

Browser validation:

```text
1. Open the Maze Foundry WebUI.
2. Click Run Fresh Maze.
3. Confirm Maze A and Maze B appear before Worker execution.
4. Click Play.
5. Confirm Worker A and Worker B make parallel progress.
6. Wait for both Workers to finish or report terminal outcomes.
7. Confirm a Review panel appears with score, status, and findings.
8. Confirm Timeline includes a Reviewer Agent review event after the Worker ticks.
```

## Acceptance Criteria

```text
[ ] Reviewer role starts locally with provider=test
[ ] ACR validation gate includes analyst, worker_a, worker_b, and reviewer
[ ] Reviewer Docker-backed hosted agent exists in Foundry
[ ] WebUI has FOUNDRY_REVIEWER_AGENT_ENDPOINT configured
[ ] Reviewer runs only after both Workers are terminal
[ ] Review output is written to Team Memory under review.latest
[ ] WebUI renders review score/status/findings
[ ] Reviewer does not control movement or retry execution
```

## Notes

Reviewer evaluation spends a small number of model calls after the maze run
finishes. The low-cost validation gate still uses `--provider test`, so package
validation does not spend Foundry model tokens.

## Current Lab Result

Phase 24 was deployed in the Visual Studio Enterprise Subscription on
2026-09-01.

```text
Git commit:
  24d4d2670f248387b78be5a3ca62b1f8533fb4c9

ACR Task run:
  chh

Validated image:
  mazefoundryacrpravada483.azurecr.io/maze-role-agent:phase22-chh

Image digest:
  sha256:89f5028714f6be250645516a77f7793ee5e591e0b86e0508bdd6028e4f97bca6
```

The Phase 23 validation gate passed for all four role entrypoints:

```text
analyst: passed
worker_a: passed
worker_b: passed
reviewer: passed
```

Foundry hosted agent deployed:

```text
maze-reviewer-agent-docker
status: active
version: 1
image: maze-role-agent:phase22-chh
```

Reviewer runtime identity was granted the same scoped access pattern as the
Docker Worker agents:

```text
Cognitive Services OpenAI User:
  Foundry account scope

Foundry User:
  Foundry project scope
```

WebUI setting configured:

```text
FOUNDRY_REVIEWER_AGENT_ENDPOINT
```

Minimal live Reviewer validation:

```text
Command:
  azd ai agent invoke maze-reviewer-agent-docker '<compact completed Team Memory payload>'

Result:
  status: complete
  phase: 24
  score: 100
  threshold: 90
  review_status: approved_for_learning_review
  llm_calls: 1
```

WebUI health validation:

```text
https://maze-webui-func-prav-ada483.azurewebsites.net/api/health
-> {"status":"ok"}
```
