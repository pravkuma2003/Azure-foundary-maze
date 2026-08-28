# Phase 23 - Automated Validation Before Promotion

## Objective

Validate the newest ACR-built candidate image before it is promoted to the
Docker-backed Foundry hosted agents.

Phase 22 proved this flow:

```text
GitHub push -> ACR candidate image -> manual Foundry promotion
```

Phase 23 inserts a validation gate:

```text
GitHub push
  -> ACR candidate image
  -> automated validation
  -> manual promotion only if validation passes
```

## Why This Matters

A successful Docker build only proves the image packages. It does not prove the
agent code is runnable or that each role entrypoint still works.

Examples of failures a build may miss:

```text
Analyst role no longer starts
Worker A role has an import error
Worker B role returns invalid JSON
shared role image contains stale source
wrong image tag is about to be promoted
```

## Validation Strategy

The validation gate is intentionally low cost. It does not create new Azure
resources and does not invoke the Foundry model by default.

The script checks:

```text
1. latest successful ACR Task run exists
2. run-specific image tag exists in ACR
3. Analyst container starts with test provider
4. Worker A container starts with test provider
5. Worker B container starts with test provider
6. each role returns structured JSON with status=complete
```

The smoke tests run inside ACR with:

```text
python main.py --once --provider test --role analyst
python main.py --once --provider test --role worker_a
python main.py --once --provider test --role worker_b
```

This verifies the same image that Foundry would run, without changing the live
Foundry agents.

## Commands

Plan only:

```bash
python3 scripts/phase23_validate_candidate_before_promotion.py
```

Validate the latest candidate image:

```bash
python3 scripts/phase23_validate_candidate_before_promotion.py --apply
```

Validate and promote only if validation passes:

```bash
python3 scripts/phase23_validate_candidate_before_promotion.py --apply --promote-if-valid
```

The promote path delegates to the existing Phase 22 command:

```bash
python3 scripts/phase22_acr_task_build_trigger.py --promote-latest-run
```

## Lesson Boundary

Phase 23 validates packaging, role entrypoints, and structured output shape.

It does not yet prove model-quality behavior, route optimality, or WebUI
end-to-end trace quality. Those belong in a later evaluation phase because they
require live Foundry calls and clear scoring rules.
