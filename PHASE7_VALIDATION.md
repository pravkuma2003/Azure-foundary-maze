# Phase 7 Validation

## Expected Result

```text
Hosted package is created.
The package runs locally with provider=test.
The package includes agents, tools, worker logic, orchestrator, and memory state.
No Foundry model calls are made during package validation.
No hosted agent is created until Foundry hosted-agent tooling is active.
```

## Validation Command

```bash
python3 scripts/phase7_monolithic_hosted_runtime.py
```

## Generated Artifacts

```text
runs/phase7_monolithic_hosted_runtime.json
runs/phase7_hosted_package_validation/
visuals/PHASE7_VISUAL.html
hosted/phase7-monolithic-maze-agent/
PROGRESS.html
```
