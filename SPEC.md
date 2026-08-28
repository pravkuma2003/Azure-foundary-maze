# Spec

## Curriculum

```text
Name: Azure Foundry Maze Migration From Scratch
Source: Multi-Agent Reasoning From Scratch
Framework baseline: Pydantic AI
Azure target: Microsoft Foundry
Agent hosting target: Foundry-hosted agents
Primary tooling: Microsoft Foundry Toolkit, Azure Developer CLI
Auth: device-code login for local development
Tenant target: cciepraveenyahoo.onmicrosoft.com
Subscription target: Visual Studio Enterprise Subscription
Cost posture: personal subscription / minimum viable Azure resources
```

## Goal

Learn how to migrate the local maze agents to Microsoft Foundry while preserving
the architecture as much as practical.

The migration should keep local development viable:

```text
Same agent roles
Same maze domain
Same call accounting idea
Same trace-first learning style
Provider and hosting boundaries become replaceable
```

## Non-Goals

```text
Do not publish private IPs, local usernames, private paths, or credentials.
Do not rewrite the local curriculum from scratch.
Do not make Azure-specific code the only runnable path.
Do not provision Azure resources before login, role, region, and cost readiness.
Do not add redundant Azure services for performance or production hardening.
Do not optimize for throughput, concurrency, or scale before portability is proven.
```

## Migration Principles

```text
Separate provider from agent behavior.
Separate tool interface from tool hosting.
Separate memory interface from memory backend.
Keep traces comparable between local and Azure runs.
Prefer Foundry Toolkit and azd for provisioning/deployment workflow.
Use Azure identity, managed identity, or Key Vault instead of checked-in secrets.
Prefer source-code hosted-agent deployment before container deployment unless a
phase explicitly needs container behavior.
Use the smallest hosted-agent resource sizing that is practical for the lab.
Defer Azure memory, storage, functions, monitoring, and evaluation services until
they teach a specific phase concept.
```

## Local to Azure Mapping

| Local construct | Azure migration target |
| --- | --- |
| Pydantic AI role function | Foundry-hosted agent wrapper |
| Local OpenAI-compatible model | Single Foundry model deployment first |
| LiteLLM endpoint | Foundry project endpoint / model client |
| Maze Tool function | In-process module first; Azure-hosted tool boundary later |
| Team Memory dict/trace | In-process memory first; Azure-native state later |
| Static HTML trace | Foundry tracing plus generated artifact |
| Shell runner | azd / Foundry Toolkit workflow command |

## Phase 1 Scope

Phase 1 does not log in to Azure or provision resources.

It inventories the current local maze app and identifies public-repo blockers:

```text
hardcoded private IPs
local filesystem paths
generated traces with provider metadata
generated HTML with provider metadata
credential-looking strings
Azure environment variable assumptions
```

Expected Phase 1 result:

```text
We know which local files are portable.
We know which values must be sanitized before GitHub.
We have an initial local-to-Azure component map.
Phase 2 should create a clean public-safe repo copy.
```

## Phase 2 Scope

Phase 2 stays local and creates a public-safe export candidate:

```text
copy source code, scripts, and curriculum docs
exclude generated traces and generated visual HTML
redact private IP addresses and local filesystem paths
add .env.example
add .gitignore protections
scan the exported candidate for blocking machine-specific values
```

Expected Phase 2 result:

```text
The public export is safe enough to review before GitHub publishing.
No Azure resources have been created.
Phase 3 should use device-code login and verify the Azure subscription.
```

## Phase 3 Scope

Phase 3 verifies Azure control-plane readiness:

```text
check Azure CLI installation
use device-code login when authentication is missing
verify visible subscriptions
select the intended personal subscription
check Azure Developer CLI installation/auth readiness
record budget-readiness command availability
confirm zero Azure resources are created
```

Expected Phase 3 result:

```text
We know whether the machine can authenticate to Azure.
We know whether the personal subscription is visible.
We know whether azd must be installed before Foundry Toolkit phases.
Phase 4 should create or select one Foundry project and one model deployment.
```

## Phase 4 Scope

Phase 4 creates the minimum Azure resource base:

```text
one resource group
one Foundry AIServices resource
one Foundry project
one low-capacity gpt-4.1-mini model deployment
zero hosted agents
zero inference calls
```

Expected Phase 4 result:

```text
The Foundry project exists and has a model deployment.
The local maze code has not been changed yet.
Phase 5 should add a provider adapter that can target this deployment.
```

## Phase 5 Scope

Phase 5 moves only the model backend:

```text
local Mac/Linux code still owns the maze program
local Pydantic AI agent behavior remains unchanged
provider=foundry targets the Foundry project endpoint
Azure CLI Entra ID token is used instead of an API key
one tiny inference call validates the deployment
zero Foundry-hosted agents are created
```

Expected Phase 5 result:

```text
The local code can call the Azure Foundry model deployment.
The model provider boundary is explicit.
Phase 6 should run the Analyst role through this Foundry provider.
```

## Phase 6 Scope

Phase 6 runs one Pydantic AI reasoning role against the Foundry model backend:

```text
Analyst Agent remains local Mac/Linux Python code
Pydantic AI remains the local agent framework
model inference goes to the Foundry project deployment
structured output is parsed into a Pydantic model
maze tools, workers, orchestrator, and team memory remain local/not invoked
zero Foundry-hosted agents are created
zero Azure resources are created
```

Expected Phase 6 result:

```text
The existing Pydantic AI role abstraction works with the Foundry model backend.
Agent hosting is still a separate migration boundary.
Phase 7 should create the first minimal Foundry-hosted Analyst Agent.
```

## Phase 7 Scope

Phase 7 changes the migration approach from a single Analyst-only hosted agent
to a monolithic hosted-runtime package:

```text
copy the public-safe local maze runtime into a hosted package
include Pydantic AI Analyst and Worker roles
include deterministic orchestrator, Maze Tool, Team Memory, and trace state
add a Foundry-oriented provider path for hosted/runtime authentication
add hosted-agent package metadata
validate the package locally with provider=test
make zero Foundry model calls during package validation
create zero hosted agents until Foundry hosted-agent tooling is active
```

Expected Phase 7 result:

```text
The full local app has a deployable hosted-runtime package.
The package validates locally without extra Azure cost.
The next step is deploying that package as one minimal hosted runtime, then
splitting tools, memory, and workers in later phases.
```

## Phase 8 Scope

Phase 8 hosts the maze playback UI in Azure:

```text
deploy one Azure Functions Consumption app
reuse the existing Foundry project and hosted maze agent endpoint
serve the same play/pause/replay maze timeline from Azure-hosted HTML
proxy /api/run through the Function App managed identity
keep Azure tokens and package SAS values out of browser code and docs
include a packaged sample trace so the UI is useful before live RBAC is granted
```

Expected Phase 8 result:

```text
The WebUI is reachable from an Azure URL.
Packaged trace playback works without secrets.
Live hosted-agent invocation is narrowed to managed-identity RBAC and hosted
agent model-access validation.
Phase 9 should continue splitting the runtime boundary inside the hosted
package, starting with the Maze Tool program interface.

## Phase 9 Scope

Phase 9 keeps the Maze Tool in the existing Azure-hosted package but extracts
it from direct helper calls into a separate program boundary:

```text
Worker Agent logic
  -> MazeToolProgram.inspect(request)
  -> MazeToolProgram.move(request)
  -> typed tool result
```

Expected Phase 9 result:

```text
No new Azure service is created.
Maze inspection and movement use a typed MazeToolProgram contract.
Trace events include tool_request and tool_result payloads.
The existing Azure WebUI can render the refreshed sample trace.
The next phase can move Worker Agent A behind its own hosted boundary while
reusing the same MazeTool contract.
```
```

## Phase 10 Scope

Phase 10 moves the Maze Tool implementation out of the hosted agent package and
into an Azure Function:

```text
hosted PydanticAI runtime
  -> external Maze Tool boundary
  -> Azure Function Maze Tool
```

Expected Phase 10 result:

```text
The Maze Tool is a real Azure-hosted program boundary.
The agent runtime does not need to change its inspect/move contract.
The WebUI trace can identify external Maze Tool calls.
```

## Phase 11 Scope

Phase 11 registers the Azure Function Maze Tool in Foundry as an OpenAPI tool
inside a toolbox:

```text
Azure Function OpenAPI document
  -> Foundry project connection
  -> Foundry toolbox
  -> OpenAPI tool
```

Expected Phase 11 result:

```text
The Maze Tool appears in Foundry as a toolbox-backed tool.
No runtime path changes yet.
The next phase can make the agent consume the toolbox MCP endpoint.
```

## Phase 12 Scope

Phase 12 switches the hosted PydanticAI runtime from direct HTTP tool calls to
the Foundry toolbox MCP endpoint:

```text
PydanticAI hosted agent
  -> Foundry toolbox MCP endpoint
  -> OpenAPI wrapper
  -> Azure Function Maze Tool
```

Expected Phase 12 result:

```text
Live WebUI traces show Foundry toolbox MCP calls.
Direct HTTP Maze Tool calls are zero.
The monolithic hosted agent still contains Analyst, Worker A, Worker B, and
request-scoped Team Memory.
```

## Phase 13 Scope

Phase 13 splits the monolithic role runtime into independent Foundry-hosted
role agents:

```text
maze-analyst-agent
maze-worker-agent-a
maze-worker-agent-b
```

Expected Phase 13 result:

```text
Analyst, Worker A, and Worker B are separately deployed hosted agents.
Each hosted role still uses Pydantic AI internally.
Worker agents keep using the Foundry toolbox MCP Maze Tool path.
Team Memory is request-scoped and passed by the coordinator.
No new storage resource, model deployment, or toolbox is created.
The next phase should move Team Memory to low-cost Azure durable storage.
```
