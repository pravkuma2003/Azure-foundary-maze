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

The GitHub-triggered ACR Task was created successfully after
`PHASE22_GIT_ACCESS_TOKEN` was exported on the Mac:

```text
Task:
  maze-role-agent-github-build

GitHub context:
  https://github.com/pravkuma2003/Azure-foundary-maze.git#main:hosted/maze-role-agents

Trigger:
  GitHub commit trigger enabled on main
```

The first manual `--run-once` attempt created ACR run `ch4`, but that run failed
after source download:

```text
when specifying push, at least one credential is required
```

Root cause: the task had been created with `--auth-mode None` while also pushing
image tags back into ACR. `None` is correct only for no-push validation tasks or
source contexts that do not need registry credentials. Phase 22 now uses ACR
Task default registry authentication for push-enabled builds.

After the script fix, the task was updated and a manual validation run
succeeded:

```text
Command:
  python3 scripts/phase22_acr_task_build_trigger.py --apply --run-once

Result:
  status: complete
  successful ACR run: ch7
  git-head-revision: 93ff0ef3950dffc8d9f68f963544d07933a471f2
  duration: 53s

Images pushed:
  mazefoundryacrpravada483.azurecr.io/maze-role-agent:phase22-latest
  mazefoundryacrpravada483.azurecr.io/maze-role-agent:phase22-ch7

Digest:
  sha256:4f758f4a513622ceb1fe5778b147b17233eabb68224baf0263aa4c64dbb69110
```

The next GitHub commit triggered an automatic ACR run, proving the webhook path:

```text
Automatic run:
  ch8

Trigger:
  GitHub commit on main

Git commit:
  fc141eabc2378136b586acadbd89942b1851b020

Images pushed:
  mazefoundryacrpravada483.azurecr.io/maze-role-agent:phase22-latest
  mazefoundryacrpravada483.azurecr.io/maze-role-agent:phase22-ch8

Digest:
  sha256:742677f9cf04edbdf16afa425fb0ae49d8fad0c204e9b7f412ef17147ed1fce7
```

The manual promotion command then promoted `phase22-ch8` to all three
Docker-backed Foundry hosted agents:

```text
Command:
  python3 scripts/phase22_acr_task_build_trigger.py --promote-latest-run

Promoted image:
  mazefoundryacrpravada483.azurecr.io/maze-role-agent:phase22-ch8

Deployed agents:
  maze-analyst-agent-docker
  maze-worker-agent-a-docker
  maze-worker-agent-b-docker

Deployment result:
  all three agents deployed successfully

Active Docker-backed agent version:
  version 3
```

Future manual promotion still uses the same command:

```text
python3 scripts/phase22_acr_task_build_trigger.py --promote-latest-run
```
