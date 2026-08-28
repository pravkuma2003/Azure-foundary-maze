# Phase 20 Validation

## Expected Result

```text
ACR image exists.
Foundry deploys three Docker-backed hosted agents.
Docker-backed agents use image runtime, not source codeConfiguration.
Existing source-deployed Phase 18 agents remain unchanged.
```

## Observed Result

```text
ACR image:
  mazefoundryacrpravada483.azurecr.io/maze-role-agent:phase19

Docker-backed agents:
  maze-analyst-agent-docker     active
  maze-worker-agent-a-docker    active
  maze-worker-agent-b-docker    active

Source-built agents:
  maze-analyst-agent
  maze-worker-agent-a
  maze-worker-agent-b
  unchanged
```

Foundry reports the Docker-backed agents with:

```text
definition.container_configuration.image =
  mazefoundryacrpravada483.azurecr.io/maze-role-agent:phase19
```

That confirms Foundry is using the ACR image runtime rather than source
`remote_build`.

## Validation Plan

```text
1. Confirm ACR contains maze-role-agent:phase19.
2. Set PHASE20_AGENT_IMAGE to the full ACR image URL.
3. Deploy maze-analyst-agent-docker.
4. Deploy maze-worker-agent-a-docker.
5. Deploy maze-worker-agent-b-docker.
6. Inspect all three agents with azd ai agent show.
7. Confirm the original non-docker agent names still exist and are not redeployed.
8. Confirm the Foundry project managed identity has AcrPull on ACR.
9. Confirm each Docker-backed agent identity has Cognitive Services OpenAI User
   on the Foundry account before live model invocation.
```

## Validation Artifact

```text
runs/phase20_foundry_acr_image_runtime.json
```

## Runtime Finding

The first invoke reached the Docker container, but model invocation failed until
the new Docker-backed agent identity received model access. This was expected
once the agent split was understood: a new hosted-agent runtime gets a new
identity, even when it runs the same container image.

After assigning `Foundry User` at the Maze Foundry project scope, the
Docker-backed Analyst Agent completed a live invocation and returned a dynamic
mission-design JSON response. This confirms the Phase 20 answer:

```text
Yes, Foundry can run the hosted agent from the ACR image instead of source
remote_build.
```

The live WebUI was not switched to the Docker-backed agents in this phase. The
Docker agents were deployed side by side so the image runtime boundary could be
validated without disrupting the existing learner-facing app.
