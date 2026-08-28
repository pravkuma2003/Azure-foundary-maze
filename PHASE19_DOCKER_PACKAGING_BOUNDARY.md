# Phase 19 - Docker Packaging Boundary

## Objective

Package the existing Foundry-hosted role-agent code as a Docker image using
Azure Container Registry remote build.

This phase does not change agent reasoning:

```text
same Analyst code
same Worker Agent A code
same Worker Agent B code
same Pydantic AI runtime
same Foundry model deployment
same Maze Tool
same Team Memory
same WebUI behavior
```

Only the packaging boundary changes.

## Option B Flow

This phase uses Azure to build the image. Local Docker Desktop is not required.

```text
Mac/Git working tree
  -> hosted/maze-role-agents/Dockerfile
  -> az acr build
  -> Azure Container Registry image
  -> later Foundry hosted-agent image runtime
```

For reproducible promotion, use Git as the source of truth:

```text
edit on Mac
commit changes
push to GitHub
ACR builds from the committed source or from the checked-out source folder
Foundry consumes the resulting image tag
```

During development, `az acr build` can build from the local checked-out folder.
For customer redeployment, prefer a pinned Git tag or commit so the image can be
traced back to source.

## What Docker Adds

Docker does not make the agent smarter. It makes the runtime package explicit:

```text
Python version
OS base image
pip dependency install
application files included in the image
startup entrypoint
image tag and registry location
```

This helps when a tenant requires:

```text
approved base images
image scanning
private registry governance
repeatable dependency builds
OS-level packages
CI/CD artifact promotion
```

## Implementation

Added:

```text
hosted/maze-role-agents/Dockerfile
hosted/maze-role-agents/.dockerignore
scripts/phase19_docker_packaging_boundary.py
```

The Dockerfile builds one shared image. The same image can run any role because
the existing `main.py` already selects behavior from `--role` or
`MAZE_HOSTED_ROLE`:

```text
analyst
worker_a
worker_b
```

## Commands

Dry run:

```bash
python3 scripts/phase19_docker_packaging_boundary.py
```

Create/reuse ACR and build the image in Azure:

```bash
python3 scripts/phase19_docker_packaging_boundary.py --apply
```

Optional environment overrides:

```bash
export PHASE19_ACR_NAME="mazefoundryacrpravada483"
export PHASE19_IMAGE_REPOSITORY="maze-role-agent"
export PHASE19_IMAGE_TAG="phase19"
export AZURE_RESOURCE_GROUP="rg-maze-foundry-lab"
export AZURE_LOCATION="eastus2"
```

## Boundary Decision

Phase 19 proves the Docker image build boundary first. It does not immediately
replace the currently working Phase 18 hosted-agent deployment.

The next deployment step, if we choose to continue, is:

```text
Foundry hosted agents run from the ACR image instead of source remote_build.
```

Important schema distinction:

```text
Source deploy:
  codeConfiguration.runtime = python_3_13
  codeConfiguration.dependencyResolution = remote_build

Image deploy:
  image = <acr>.azurecr.io/maze-role-agent:<tag>
```

Do not combine `codeConfiguration` with image-based container configuration.
When we switch hosted agents to consume the ACR image, `language: docker` should
select the container build/deploy path and `image` should identify the image
that Foundry pulls.
