# Phase 20 - Foundry Hosted Agents From ACR Image

## Objective

Run Foundry-hosted role agents from the Phase 19 ACR image instead of source
`remote_build`.

This phase tests the question:

```text
Can Foundry run the same Analyst and Worker agent code from a prebuilt ACR image?
```

## Boundary

Phase 19 built this image:

```text
mazefoundryacrpravada483.azurecr.io/maze-role-agent:phase19
```

Phase 20 deploys new Docker-backed Foundry agents from that image:

```text
maze-analyst-agent-docker
maze-worker-agent-a-docker
maze-worker-agent-b-docker
```

The existing source-deployed agents remain untouched:

```text
maze-analyst-agent
maze-worker-agent-a
maze-worker-agent-b
```

## Learning Point

Source deploy and image deploy are different packaging paths:

```text
Source remote_build:
  Foundry receives source ZIP, restores dependencies, and starts Python.

ACR image runtime:
  ACR stores a prebuilt image; Foundry starts that image directly.
```

The agent logic should not change. The runtime package changes.

## Implementation

Added:

```text
hosted/phase20-docker-image-runtime/azure.yaml
scripts/phase20_foundry_acr_image_runtime.py
```

The Phase 20 `azure.yaml` uses:

```yaml
language: docker
image: ${PHASE20_AGENT_IMAGE}
docker:
  remoteBuild: true
startupCommand: python main.py --provider foundry --role analyst
```

It intentionally does not use `codeConfiguration`, because Microsoft Foundry
documents `codeConfiguration` for source ZIP deployment and `image` for
prebuilt container deployment.

## Azure Permissions Learned

Image-backed hosted agents introduce two separate Azure permissions:

```text
Foundry project managed identity
  -> needs AcrPull on the ACR registry so Foundry can pull the image.

Each Docker-backed hosted agent identity
  -> needs Cognitive Services OpenAI User on the Foundry account so the
     PydanticAI runtime can call the deployed model.
```

These are separate from the original source-built agent identities. Creating
`maze-analyst-agent-docker`, `maze-worker-agent-a-docker`, and
`maze-worker-agent-b-docker` creates new identities, so model access must be
granted again.

## Configuration Note

For Docker-backed hosted agents, keep environment variables role-specific and
runtime-specific:

```text
AZURE_AI_MODEL_DEPLOYMENT_NAME
MAZE_HOSTED_ROLE
MAZE_PROVIDER
MAZE_TOOL_MCP_ENDPOINT
```

The source-built agents still carry `FOUNDRY_PROJECT_ENDPOINT` and
`FOUNDRY_MODEL_DEPLOYMENT`. The Docker image runtime receives project context
from Foundry, so Phase 20 keeps the manifest focused on the image and role
settings.

## Commands

Dry run:

```bash
python3 scripts/phase20_foundry_acr_image_runtime.py
```

Deploy the Docker-backed agents:

```bash
python3 scripts/phase20_foundry_acr_image_runtime.py --apply
```

Optional image override:

```bash
export PHASE20_AGENT_IMAGE="mazefoundryacrpravada483.azurecr.io/maze-role-agent:phase19"
```

## Next Phase

Phase 21 should move the image build source from the local checked-out folder to
GitHub:

```text
edit on Mac
  -> commit/push to GitHub
  -> ACR builds from GitHub source/ref
  -> Foundry deploys the Git-built image
```
