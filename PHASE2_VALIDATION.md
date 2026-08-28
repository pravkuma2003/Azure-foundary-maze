# Phase 2 Validation: Public Repo and Secret Hygiene

## Validation Goal

Confirm that the local maze app has a public-safe candidate export before any
GitHub publishing or Azure Foundry provisioning starts.

## Expected Artifacts

```text
exports/multi-agent-reasoning-from-scratch-public/
runs/phase2_public_repo_hygiene.json
visuals/PHASE2_VISUAL.html
PROGRESS.html
```

## Checks

- Source code, scripts, and curriculum docs are copied.
- Generated trace JSON files are excluded.
- Generated visual HTML files are excluded.
- Private IP addresses are redacted.
- Local filesystem paths are redacted.
- `.env.example` is included.
- `.env` is ignored.
- Blocking public-safety findings are zero after export.
- Azure cost remains zero because no Azure resources are created.
- The next phase points to device-code login and subscription readiness.

## Result

Validated by `scripts/phase2_public_repo_hygiene.py`.
