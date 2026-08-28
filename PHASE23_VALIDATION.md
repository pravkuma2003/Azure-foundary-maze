# Phase 23 Validation

## Expected Result

```text
Candidate image:
  latest successful ACR Task run-specific image

Validation:
  image tag exists
  analyst role smoke test passes
  worker_a role smoke test passes
  worker_b role smoke test passes

Promotion:
  allowed only when all validation checks pass
```

## Validation Artifact

```text
runs/phase23_validate_candidate_before_promotion.json
```

## Validation Command

```bash
python3 scripts/phase23_validate_candidate_before_promotion.py --apply
```

## Promote After Validation

```bash
python3 scripts/phase23_validate_candidate_before_promotion.py --apply --promote-if-valid
```

## Acceptance Criteria

```text
[ ] latest_successful_run resolves to an ACR run id
[ ] candidate_image points to maze-role-agent:phase22-<run-id>
[ ] image_tag status is passed
[ ] Analyst smoke test status is passed
[ ] Worker A smoke test status is passed
[ ] Worker B smoke test status is passed
[ ] promotion does not run unless validation status is passed
```

## Notes

The role smoke tests use `--provider test`, so they do not spend Foundry model
tokens. This phase validates the candidate runtime package before promotion,
not the final quality of LLM reasoning.

## Current Lab Result

Phase 23 was validated in the Visual Studio Enterprise Subscription on
2026-08-28.

```text
Validation command:
  python3 scripts/phase23_validate_candidate_before_promotion.py --apply

Result:
  status: passed
  candidate run: ch9
  run type: AutoRun
  source commit: 1811b91599507ba94a8334a479adacc4d721ddd4
  image: mazefoundryacrpravada483.azurecr.io/maze-role-agent:phase22-ch9
  digest: sha256:a7f330cb31a865dbb83d6ee63f30018f002ebbab6c74b35ad047d7a2feef4358
```

Checks that passed:

```text
image_tag:
  phase22-ch9 exists in ACR

role smoke tests:
  analyst passed
  worker_a passed
  worker_b passed

model calls:
  0, because validation used provider=test
```

The gated promote path was then tested:

```text
Command:
  python3 scripts/phase23_validate_candidate_before_promotion.py --apply --promote-if-valid

Promotion result:
  complete

Promoted image:
  mazefoundryacrpravada483.azurecr.io/maze-role-agent:phase22-ch9

Docker-backed Foundry agents:
  maze-analyst-agent-docker
  maze-worker-agent-a-docker
  maze-worker-agent-b-docker

Active Docker-backed agent version:
  version 4
```

This proves the Phase 23 gate: Foundry promotion happens only after the
candidate image passes automated validation.
