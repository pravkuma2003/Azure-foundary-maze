# Phase 22 - Automated Build Trigger

## Objective

Automatically build a new ACR image when GitHub source changes, while keeping
Foundry agent redeployment manual.

This phase teaches the difference between:

```text
Build automation:
  GitHub push creates a new candidate container image.

Runtime promotion:
  A human explicitly chooses when Foundry should run that candidate image.
```

## Why Keep Foundry Redeploy Manual?

Automatic image build is low risk. It produces a new deployable artifact but
does not change running agents.

Automatic Foundry redeploy is higher risk. It changes the runtime used by the
hosted agents.

For the learning lab, the safer sequence is:

```text
1. Push code.
2. Let ACR automatically build a candidate image.
3. Review the build/run result.
4. Manually promote that image to Foundry.
5. Test the agent.
```

## Quick Example

Assume we change a Worker prompt locally.

```text
Mac:
  edit hosted/maze-role-agents/main.py
  git commit
  git push

GitHub:
  records the new commit on main

ACR Task:
  receives the GitHub commit event
  pulls hosted/maze-role-agents
  builds the Docker image
  pushes:
    maze-role-agent:phase22-latest
    maze-role-agent:phase22-<run-id>

Foundry:
  still runs the previous promoted image until we manually redeploy
```

Manual promotion:

```bash
python3 scripts/phase22_acr_task_build_trigger.py --promote-latest-run
```

That command finds the latest successful ACR Task run and points the
Docker-backed Foundry agents at the run-specific image tag:

```text
mazefoundryacrpravada483.azurecr.io/maze-role-agent:phase22-<run-id>
```

## What the Automated Trigger Accomplishes

It removes the manual build step from Phase 21.

Phase 21:

```text
git push
operator runs script
ACR builds image
operator promotes image to Foundry
```

Phase 22:

```text
git push
ACR automatically builds image
operator promotes image to Foundry
```

So Phase 22 saves the operator from remembering to run the build command after
every source change. It still prevents every commit from immediately changing
the running agents.

## Implementation

Added:

```text
scripts/phase22_acr_task_build_trigger.py
```

The script creates or updates this ACR Task:

```text
maze-role-agent-github-build
```

Default GitHub context:

```text
https://github.com/pravkuma2003/Azure-foundary-maze.git#main:hosted/maze-role-agents
```

Default output tags:

```text
maze-role-agent:phase22-latest
maze-role-agent:phase22-{{.Run.ID}}
```

The run-specific tag is preferred for manual Foundry promotion because it is
clear which ACR Task run produced the runtime image.

## Commands

Dry run:

```bash
python3 scripts/phase22_acr_task_build_trigger.py
```

Create or update the GitHub-triggered ACR Task:

```bash
python3 scripts/phase22_acr_task_build_trigger.py --apply
```

Create/update and run the task once immediately:

```bash
python3 scripts/phase22_acr_task_build_trigger.py --apply --run-once
```

Manually promote the latest successful task-run image to Foundry:

```bash
python3 scripts/phase22_acr_task_build_trigger.py --promote-latest-run
```

## GitHub Token

Creating the ACR Task GitHub webhook requires a GitHub access token. The script
does not print or persist the token in repo files.

It checks these sources in order:

```text
PHASE22_GIT_ACCESS_TOKEN
GITHUB_TOKEN
GH_TOKEN
gh auth token
```

For this public repo, the token only needs enough access for Azure Container
Registry to configure the GitHub source trigger/webhook.

## Lesson Boundary

This phase does not add GitHub Actions and does not automatically deploy to
Foundry.

A later phase can add a gated promotion workflow, such as:

```text
GitHub pull request
  -> ACR candidate image
  -> validation
  -> approval
  -> Foundry deploy
```
