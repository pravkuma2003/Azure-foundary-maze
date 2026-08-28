# Phase 1 Validation: Portability Inventory

## Validation Goal

Confirm that the local maze app has been inventoried before any public GitHub or
Azure Foundry migration work starts.

## Expected Artifacts

```text
runs/phase1_inventory.json
visuals/PHASE1_VISUAL.html
PROGRESS.html
```

## Checks

- Source app exists.
- Python source files are identified.
- Markdown curriculum files are identified.
- Generated trace files are identified.
- Generated HTML files are identified.
- Machine-specific values are flagged.
- Credential-looking strings are flagged for review.
- Azure migration targets are documented as Foundry-hosted agents.
- Personal-subscription cost guardrails are documented.
- Phase 2 points to public repo and secret hygiene.

## Result

Validated by `scripts/phase1_inventory_and_safety.py`.
