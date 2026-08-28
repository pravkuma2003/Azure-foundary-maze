# Phase 4 Validation: Foundry Project and Model Deployment

## Validation Goal

Confirm that the minimal Foundry resource base exists before changing the maze
agent code.

## Expected Artifacts

```text
runs/phase4_foundry_project_model.json
visuals/PHASE4_VISUAL.html
PROGRESS.html
```

## Checks

- Azure CLI is authenticated to the personal subscription from Phase 3.
- One learning resource group is created or reused.
- One Foundry `AIServices` resource is created or reused.
- The Foundry resource uses SKU `S0`.
- Project management is enabled on the Foundry resource.
- One Foundry project is created or reused.
- One `gpt-4.1-mini` deployment is created or reused with `GlobalStandard`
  capacity `50`.
- Hosted agents created is `0`.
- Inference calls made is `0`.
- Cleanup command is documented.
- The next phase points to adding a provider adapter, not rewriting agent logic.

## Result

Validated by `scripts/phase4_foundry_project_model.py --apply`.
