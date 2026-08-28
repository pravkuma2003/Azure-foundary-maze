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

## Current Lab Status

The Phase 22 code and documentation are in place, but the ACR Task was not
created during the first apply attempt because no GitHub token was available on
this machine:

```text
PHASE22_GIT_ACCESS_TOKEN: not set
GITHUB_TOKEN: not set
GH_TOKEN: not set
gh CLI: not installed
```

Azure requires `--git-access-token` when creating a GitHub source trigger
because ACR must register a GitHub webhook. The repo can remain public and the
ACR source auth mode can stay `None`; the token is for trigger/webhook setup.

To complete provisioning:

```bash
export PHASE22_GIT_ACCESS_TOKEN="<github-token-with-repo-webhook-access>"
python3 scripts/phase22_acr_task_build_trigger.py --apply --run-once
```

After the task has at least one successful run:

```bash
python3 scripts/phase22_acr_task_build_trigger.py --promote-latest-run
```
