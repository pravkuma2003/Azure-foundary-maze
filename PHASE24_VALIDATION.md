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
