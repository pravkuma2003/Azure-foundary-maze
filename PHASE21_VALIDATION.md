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

## Notes

The GitHub source URL is public in this lab:

```text
https://github.com/pravkuma2003/Azure-foundary-maze.git#main:hosted/phase13-split-role-agents
```

For a customer non-prod Azure tenant, prefer a customer-approved branch, tag, or
commit SHA so the image build can be tied to an immutable source reference.
