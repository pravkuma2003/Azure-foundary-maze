# Roadmap

## Theme

Move from:

```text
local Pydantic AI agents + local OpenAI-compatible model + local Python tools
```

to:

```text
Microsoft Foundry hosted agents + Azure-native tools, memory, tracing, and deployment
```

Cost rule:

```text
Use the minimum Azure resources that teach the phase.
Start with one Foundry project, one model deployment, and one hosted agent.
Do not add Azure-native storage, functions, monitoring, or extra hosted agents
until the phase objective requires them.
```

## Phases

```text
Phase 1   Portability Inventory
Phase 2   Public Repo and Secret Hygiene
Phase 3   Azure Login and Subscription Readiness
Phase 4   Foundry Project and Model Deployment
Phase 5   Model Provider Adapter
Phase 6   Pydantic AI Analyst Agent on Foundry Model
Phase 7   Monolithic Foundry-Hosted Maze Runtime
Phase 8   Azure-Hosted WebUI Adapter
Phase 9   Maze Tool Boundary without New Azure Service
Phase 10  External Azure Function Maze Tool
Phase 11  Foundry-Registered Maze Tool
Phase 12  PydanticAI Runtime Uses Foundry Toolbox MCP
Phase 13  Independent Foundry-Hosted Role Agents
Phase 14  Azure Durable Team Memory
Phase 15  Trace, Evaluation, and Cost Accounting
Phase 16  Portability Review and Cleanup
```

## Current Status

```text
Deployment complete through Phase 13.
Phase 12 routes Worker Maze Tool calls through the Foundry toolbox MCP endpoint.
Phase 13 splits Analyst, Worker A, and Worker B into independent Foundry-hosted
role agents while keeping Team Memory request-scoped.
```

## Phase Intent

Phase 1: Portability Inventory

Inventory local components, generated artifacts, machine-specific values, and
the first Azure equivalent for each construct.

Phase 2: Public Repo and Secret Hygiene

Create a clean standalone copy that can safely become public on GitHub.

Phase 3: Azure Login and Subscription Readiness

Use device-code login, select the Personnel subscription, and verify roles.

Phase 4: Foundry Project and Model Deployment

Create or select one Foundry project and one compatible chat model deployment.

Phase 5: Model Provider Adapter

Add an Azure/Foundry provider path while preserving the local provider interface.

Phase 6: Pydantic AI Analyst Agent on Foundry Model

Run one local Pydantic AI Analyst Agent against the Foundry model backend.
No Foundry-hosted agent is created yet.

Phase 7: Monolithic Foundry-Hosted Maze Runtime

Package the full local maze runtime as one hosted-agent source bundle. This
moves the runtime boundary without splitting tools, memory, or workers yet.

Phase 8: Azure-Hosted WebUI Adapter

Deploy a low-cost Azure Functions WebUI that renders the maze timeline and calls
the monolithic hosted agent through a server-side managed identity. Browser
playback works from the packaged sample trace before live hosted-agent RBAC is
granted.

Phase 9: Maze Tool Boundary without New Azure Service

Keep the Maze Tool in the Azure-hosted package, but reshape it into a separate
program interface with typed inspect/move requests and typed results. This
creates the boundary before adding another Azure service.

Phase 10: External Azure Function Maze Tool

Move the Maze Tool into an Azure Function while keeping the agent contract stable.

Phase 11: Foundry-Registered Maze Tool

Register the Azure Function Maze Tool as a Foundry toolbox OpenAPI tool.

Phase 12: PydanticAI Runtime Uses Foundry Toolbox MCP

Switch the hosted PydanticAI runtime from direct HTTP tool calls to the Foundry
toolbox MCP endpoint.

Phase 13: Independent Foundry-Hosted Role Agents

Split the monolithic runtime into three Foundry-hosted agents: Analyst, Worker
A, and Worker B. Keep Team Memory request-scoped so the phase teaches only the
hosted-agent boundary.

Phase 14: Azure Durable Team Memory

Move Team Memory from request-scoped JSON to a low-cost Azure durable store.

Phase 15: Trace, Evaluation, and Cost Accounting

Compare local traces, Foundry traces, latency, and model-call counts.

Phase 16: Portability Review and Cleanup

Document what stayed portable, what changed, and what should be abstracted.
