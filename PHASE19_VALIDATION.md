# Phase 19 Validation

## Expected Result

```text
Dockerfile exists beside the hosted role-agent source.
.dockerignore excludes Azure state, virtual environments, caches, and docs.
ACR Basic can be created or reused.
az acr build can build the hosted-agent image in Azure.
Local Docker is not required.
Agent behavior remains unchanged.
```

## Validation Plan

```text
1. Verify Dockerfile and .dockerignore exist.
2. Run the Phase 19 script without --apply to validate source files and planned Azure values.
3. Run the script with --apply to create/reuse ACR and build the image.
4. Confirm the image tag exists in ACR.
5. Confirm no Phase 18 hosted-agent deployment was modified.
```

## Notes

The Docker image is a packaging artifact. It is not a separate agent and it does
not add LLM calls.

The current known-good Foundry deployment remains Python source remote-build
until a later phase explicitly switches hosted agents to consume the ACR image.

## Live Validation

```text
Date: 2026-08-28
Subscription: Visual Studio Enterprise Subscription
Resource group: rg-maze-foundry-lab
ACR: mazefoundryacrpravada483
ACR SKU: Basic
Local Docker required: false
Image built: mazefoundryacrpravada483.azurecr.io/maze-role-agent:phase19
Digest: sha256:71ef95507e86e9b8198fdb5e195d6994590a8489c6a0dd9b36106de82e3eac1f
ACR build run: ch1
ACR build duration: 1m1s
Agent behavior changed: false
Current Foundry hosted agents modified: false
```

Validation artifact:

```text
runs/phase19_docker_packaging_boundary.json
```
