# Phase 22 Validation

## Expected Result

```text
ACR Task exists:
  maze-role-agent-github-build

Source trigger:
  GitHub commit trigger enabled for main

Build context:
  https://github.com/pravkuma2003/Azure-foundary-maze.git#main:hosted/maze-role-agents

Output image tags:
  maze-role-agent:phase22-latest
  maze-role-agent:phase22-<acr-run-id>

Foundry promotion:
  manual only
```

## Validation Plan

```text
1. Create or update the ACR Task.
2. Run the task once manually to prove the build definition works.
3. Confirm a successful ACR Task run exists.
4. Confirm phase22-latest and phase22-<run-id> image tags exist.
5. Manually promote the latest successful run tag to Foundry.
6. Confirm Docker-backed Foundry agents point at the promoted phase22 run tag.
7. Invoke one Docker-backed agent after promotion.
```

## Validation Artifact

```text
runs/phase22_acr_task_build_trigger.json
```

## Manual Promotion Command

```bash
python3 scripts/phase22_acr_task_build_trigger.py --promote-latest-run
```

This keeps image creation automatic but runtime rollout controlled by the
operator.
