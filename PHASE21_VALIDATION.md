# Phase 21 Validation

## Expected Result

```text
ACR builds maze-role-agent:phase21-github-main from the public GitHub repo.
Foundry Docker-backed agents are redeployed to use that image.
Source remote_build agents remain unchanged.
No local Docker engine is required.
```

## Validation Plan

```text
1. Commit and push the Phase 21 deployment files to GitHub.
2. Run scripts/phase21_github_acr_image_build.py --apply.
3. Confirm ACR reports the phase21-github-main tag.
4. Confirm all three Docker-backed Foundry agents are active.
5. Confirm each Docker-backed agent reports definition.container_configuration.image
   as the phase21 GitHub-built image.
6. Invoke one Docker-backed agent to prove runtime startup and model access.
```

## Validation Artifact

```text
runs/phase21_github_acr_image_build.json
```

## Observed Result

```text
Status:
  complete

GitHub source:
  https://github.com/pravkuma2003/Azure-foundary-maze.git#main:hosted/maze-role-agents

GitHub commit built after stable folder rename:
  f79ab1563d74f17e238a509123fb38a8b80ac1d0

ACR build run:
  ch3

ACR image:
  mazefoundryacrpravada483.azurecr.io/maze-role-agent:phase21-github-main

Image digest:
  sha256:f4f0bcd66054950fb0bde455fb5143f1fc1d807babaf2b5422a2a790b7a2a642

Foundry Docker-backed agents:
  maze-analyst-agent-docker     version 2 active
  maze-worker-agent-a-docker    version 2 active
  maze-worker-agent-b-docker    version 2 active
```

All three Docker-backed hosted agents report:

```text
definition.container_configuration.image =
  mazefoundryacrpravada483.azurecr.io/maze-role-agent:phase21-github-main
```

The post-deploy invoke test against `maze-analyst-agent-docker` completed
successfully and returned dynamic mission-design JSON with one Foundry model
call.

## Notes

The GitHub source URL is public in this lab:

```text
https://github.com/pravkuma2003/Azure-foundary-maze.git#main:hosted/maze-role-agents
```

For a customer non-prod Azure tenant, prefer a customer-approved branch, tag, or
commit SHA so the image build can be tied to an immutable source reference.

The hosted role-agent package now lives under `hosted/maze-role-agents`. It was
renamed from the original phase-numbered folder so future GitHub build URLs do
not imply that the current app runtime is still tied to Phase 13.
