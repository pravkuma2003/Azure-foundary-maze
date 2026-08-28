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
Phase 15  Monitoring Consolidation
Phase 16  Dynamic Mission Design
Phase 17  Parallel Worker Step Execution
Phase 18  Human Feedback Telemetry
Phase 19  Docker Packaging Boundary
Phase 20  Foundry Hosted Agents From ACR Image
Phase 21  GitHub Source to ACR Image Build
Phase 22  Automated Build Trigger with Manual Foundry Promotion
```

## Current Status

```text
Deployment complete through Phase 18.
Phase 18 records per-worker thumbs feedback in Application Insights and durable
Team Memory. Phase 19 introduces Docker packaging through Azure Container
Registry remote build without changing agent behavior.
Phase 20 deploys side-by-side Docker-backed Foundry hosted agents from the ACR
image so Foundry runs a prebuilt container instead of source remote_build.
Phase 21 moves the ACR build source from the local folder to GitHub so the image
runtime can be rebuilt from a public repo branch, tag, or commit.
Phase 22 adds and validates a GitHub-triggered ACR Task so pushes create
candidate images automatically. Manual run `ch7` produced
`maze-role-agent:phase22-ch7`; Foundry promotion remains an explicit manual
step.
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

Phase 15: Monitoring Consolidation

Use one shared Application Insights component and Log Analytics workspace for
the Maze WebUI and Maze Tool Function Apps.

Phase 16: Dynamic Mission Design

Have the Analyst generate fresh Maze A and Maze B layouts before Worker
execution. Workers reason only after the learner clicks Play.

Phase 17: Parallel Worker Step Execution

Run Worker Agent A and Worker Agent B in parallel ticks with independent
per-worker call limits and partial-failure isolation.

Phase 18: Human Feedback Telemetry

Capture simple thumbs-up/thumbs-down feedback per maze and store it in
Application Insights plus durable Team Memory.

Phase 19: Docker Packaging Boundary

Build the same hosted-agent Python code as an Azure Container Registry image
using Azure remote build. Local Docker is not required, and agent behavior does
not change.

Phase 20: Foundry Hosted Agents From ACR Image

Deploy side-by-side Docker-backed Foundry hosted agents that use the Phase 19
ACR image as their runtime package. This proves the runtime can come from ACR
without replacing the existing source-built agents.

Phase 21: GitHub Source to ACR Image Build

Move the image-build input from the local checked-out folder to the GitHub repo:
edit on Mac, commit/push to GitHub, let ACR build from the GitHub ref, and point
Foundry at that image tag or digest.

Phase 22: Automated Build Trigger with Manual Foundry Promotion

Create an ACR Task wired to the GitHub repo. A push to `main` automatically
builds candidate image tags, but Docker-backed Foundry hosted agents change only
when the operator runs the manual promotion command.
