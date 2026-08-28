# Phase 21 - GitHub Source to ACR Image Build

## Objective

Move the Docker image build input from the local Mac checkout to GitHub.

The target learning flow is:

```text
edit on Mac
  -> commit/push to GitHub
  -> ACR pulls source from GitHub
  -> ACR builds the image
  -> Foundry runs that image
```

## What Changes

Phase 19 built the image from the local checked-out folder.

Phase 20 proved Foundry can run hosted agents from an ACR image.

Phase 21 keeps the same Dockerfile and same Foundry hosted agents, but changes
the image-build source:

```text
Before:
  Mac local folder -> az acr build -> ACR image -> Foundry agent

Now:
  GitHub repo/ref -> az acr build -> ACR image -> Foundry agent
```

## Why This Helps

This creates the first real deployment handoff boundary.

The customer or lab Azure environment no longer needs to trust whatever happens
to be on one Mac filesystem. It can build from a specific GitHub repository,
branch, tag, or commit.

That gives us:

```text
Reproducibility:
  The source ref used for the image can be recorded.

Cleaner deployment:
  The Azure build does not depend on local Docker or local source state.

Rollback:
  Foundry can be pointed back to a previous ACR tag or digest.

Customer handoff:
  A customer machine only needs GitHub access and Azure permissions, not the
  broader local workspace.
```

## Implementation

Added:

```text
scripts/phase21_github_acr_image_build.py
```

The script builds this image tag by default:

```text
mazefoundryacrpravada483.azurecr.io/maze-role-agent:phase21-github-main
```

from this GitHub context:

```text
https://github.com/pravkuma2003/Azure-foundary-maze.git#main:hosted/phase13-split-role-agents
```

The context subfolder is important because the Dockerfile expects:

```text
Dockerfile
main.py
requirements.txt
src/
```

to be in the Docker build context root.

## Commands

Dry run:

```bash
python3 scripts/phase21_github_acr_image_build.py
```

Build from GitHub and redeploy Docker-backed Foundry agents:

```bash
python3 scripts/phase21_github_acr_image_build.py --apply
```

Build from GitHub but do not redeploy Foundry agents:

```bash
python3 scripts/phase21_github_acr_image_build.py --apply --skip-deploy
```

Build from a specific GitHub ref:

```bash
export PHASE21_GITHUB_REF="main"
export PHASE21_IMAGE_TAG="phase21-github-main"
python3 scripts/phase21_github_acr_image_build.py --apply
```

For a stricter release flow, use a tag or commit SHA instead of `main`.

## Validation

Success means:

```text
ACR contains maze-role-agent:phase21-github-main.
The image was built from the GitHub URL, not from the local folder.
Foundry Docker-backed agents point to the phase21 image tag.
The existing source remote_build agents remain unchanged.
```

## Lesson Boundary

This phase is still not a CI/CD trigger.

It is an explicit pull-build:

```text
operator runs az acr build with a GitHub source URL
```

A later phase can convert that into a GitHub-triggered ACR Task or GitHub
Actions workflow.
