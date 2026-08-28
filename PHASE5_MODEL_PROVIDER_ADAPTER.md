# Phase 5: Model Provider Adapter

## Learning Objective

Make the model backend replaceable while keeping the maze code local.

## New Concept

Provider boundary.

```text
provider=local
  Mac/Linux Python -> local OpenAI-compatible LiteLLM/Ollama endpoint

provider=foundry
  Mac/Linux Python -> Foundry project endpoint -> Azure model deployment
```

## What "Local Code" Means

In this phase, local code means code running on the Mac or Linux machine. The
maze code is not deployed into Azure yet.

```text
Still local:
  Pydantic AI role definitions
  maze tools
  orchestration
  traces
  HTML review artifacts

Moved to Azure:
  model backend only
```

## What Phase 5 Does

```text
Adds a small Foundry provider adapter.
Uses Azure CLI Entra ID authentication.
Calls the Foundry project endpoint.
Uses the Phase 4 model deployment.
Makes exactly one short test inference call.
Records token usage if Azure returns it.
```

## RBAC Requirement Observed

The first Foundry call reached the endpoint but returned `403`. The project
needed data-plane access for the signed-in user.

```text
Project role:
  Foundry User

Foundry account role:
  Cognitive Services OpenAI User
```

Both assignments were scoped to the lab project/account, not the whole
subscription.

## What Phase 5 Does Not Do

```text
No maze run yet.
No hosted agents yet.
No agent code deployed to Azure.
No API keys stored in files.
No Azure Functions, Cosmos DB, Storage, or extra monitoring.
```

## Cost Impact

```text
Azure cost: tiny pay-per-token inference cost
Calls made: 1
Hosted-agent runtime cost: 0
```

The deployment capacity was increased to `50` after repeated manual validation
calls hit a rate limit. This increases allowed requests/tokens per minute. It
does not increase the number of LLM calls made by the curriculum code.

## Deliverable

```text
src/foundry_provider_adapter.py
runs/phase5_model_provider_adapter.json
visuals/PHASE5_VISUAL.html
PHASE5_VALIDATION.md
```

## Knowledge Check

1. What moved to Azure in this phase?
2. What still runs locally?
3. Why is a provider adapter useful before hosted agents?
4. Why do we use Entra ID instead of an API key?
5. Why is the cost non-zero but tiny?
