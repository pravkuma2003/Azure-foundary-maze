# Phase 5 Validation: Model Provider Adapter

## Validation Goal

Confirm that local Mac/Linux code can call the Phase 4 Foundry model deployment
through a provider adapter.

## Expected Artifacts

```text
src/foundry_provider_adapter.py
runs/phase5_model_provider_adapter.json
visuals/PHASE5_VISUAL.html
PROGRESS.html
```

## Checks

- Phase 4 report is complete.
- Project endpoint is loaded from the Phase 4 report.
- Model deployment name is loaded from the Phase 4 report.
- Azure CLI Entra ID auth is used.
- `Foundry User` is assigned at project scope.
- `Cognitive Services OpenAI User` is assigned at Foundry account scope.
- No API key is written to disk.
- Exactly one Foundry inference call is made.
- Deployment capacity is `50`, but Phase 5 still makes exactly one official
  adapter validation call.
- Hosted agents created remains `0`.
- Local maze code is not deployed to Azure.
- The generated HTML records the provider flow.
- The next phase points to running the Analyst role through the Foundry provider.

## Result

Validated by `scripts/phase5_model_provider_adapter.py`.
