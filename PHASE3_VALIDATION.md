# Phase 3 Validation: Azure Login and Subscription Readiness

## Validation Goal

Confirm that Azure authentication and subscription readiness are known before
any Foundry resource is created.

## Expected Artifacts

```text
runs/phase3_azure_login_readiness.json
visuals/PHASE3_VISUAL.html
PROGRESS.html
```

## Checks

- Azure CLI installation status is recorded.
- Azure CLI login status is recorded.
- Visible subscription count is recorded.
- Subscription IDs and tenant IDs are masked.
- Azure Developer CLI installation status is recorded.
- Azure Developer CLI login status is recorded.
- Device-code login commands are documented.
- Budget-readiness command is documented.
- Azure resource creation count is zero.
- Estimated Azure cost is `$0`.
- The next phase points to one Foundry project and one model deployment only
  after readiness gates pass.

## Result

Validated by `scripts/phase3_azure_login_readiness.py`.
