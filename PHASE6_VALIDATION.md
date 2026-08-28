# Phase 6 Validation

## Expected Result

```text
Pydantic AI Analyst Agent runs locally.
Model inference runs in Azure Foundry.
Structured output is parsed successfully.
Hosted agents created: 0.
Azure resources created: 0.
```

## Validation Command

```bash
.venv-phase6/bin/python scripts/phase6_foundry_analyst_agent.py
```

## Generated Artifacts

```text
runs/phase6_foundry_analyst_agent.json
visuals/PHASE6_VISUAL.html
PROGRESS.html
```

## Validation Notes

This phase is intentionally not a maze execution trace. It validates the
reasoning-agent provider boundary before any worker, tool, memory, or hosted
agent migration.

## Observed Result

```text
Status: complete
Pydantic AI agents run: 1
Foundry model calls: 1
Hosted agents created: 0
Azure resources created: 0
Input tokens: 479
Output tokens: 160
Reported cost: 0.0004476
```

One compatibility issue was found during validation: the Pydantic AI Responses
model wrapper sent a message shape this Foundry endpoint rejected. The Phase 6
runner now uses Pydantic AI's OpenAI-compatible Chat Completions model wrapper
against the same Foundry project endpoint and deployment.
