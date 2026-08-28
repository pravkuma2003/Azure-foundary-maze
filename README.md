# Azure Foundry Maze Migration From Scratch

Step-by-step learning curriculum for moving the local Multi-Agent Maze program
to Microsoft Foundry.

The goal is portability first:

```text
Local Mac/Linux maze agents
  -> public-safe standalone repo
  -> Azure Foundry model backend
  -> Foundry-hosted agent workflow
  -> Azure-native tools, memory, tracing, and deployment
```

## Core Rule

Each phase introduces one Azure migration concept.

The local maze curriculum remains the reference implementation. This project
explains how to carry that implementation to Azure with minimal architectural
change.

## Current Status

```text
Status: Azure-native split-agent WebUI deployed through Phase 18, with Docker-backed Foundry agents rebuilt from GitHub source in Phase 21
Active phase: Phase 21 - GitHub Source to ACR Image Build
Source app: ../multi-agent-reasoning-from-scratch
Target platform: Microsoft Foundry
Primary tooling: Foundry Toolkit, Azure Developer CLI, Foundry-hosted agents
Cost posture: personal Azure subscription, minimum viable resources
```

## Intended Migration Shape

```text
Analyst Agent
  local: Pydantic AI + local OpenAI-compatible model
  azure: Foundry-hosted agent

Worker Agent A / B
  local: Pydantic AI + Maze tools + local memory
  azure: Foundry-hosted agents introduced one at a time

Maze Tool
  local: Python in-process validation
  azure: in-process first, then Azure-hosted tool only when the lesson needs it

Team Memory
  local: in-process trace/state
  azure: local/in-process first, then Azure-native state only when the lesson needs it

Trace HTML
  local: generated static HTML
  azure: Azure-hosted playback UI plus Foundry traces
```

## Cost Policy

This is a learning exercise on a personal Azure subscription. Each phase should
use the smallest Azure surface that teaches the concept:

```text
one resource group
one Foundry project
one model deployment at first
one hosted agent before multiple hosted agents
short maze traces and low call counts
minimum hosted-agent CPU/memory sizing
no Cosmos DB, durable databases, extra hosted agents, or monitoring/customization
until a phase explicitly teaches that component
```

Clean up Azure resources after labs that do not need to stay online.

## First Local Commands

```bash
python3 scripts/phase1_inventory_and_safety.py
python3 scripts/phase2_public_repo_hygiene.py
python3 scripts/phase3_azure_login_readiness.py
python3 scripts/phase4_foundry_project_model.py --apply
python3 scripts/phase5_model_provider_adapter.py
python3 -m venv .venv-phase6
.venv-phase6/bin/pip install -r requirements-phase6.txt
.venv-phase6/bin/python scripts/phase6_foundry_analyst_agent.py
python3 scripts/phase7_monolithic_hosted_runtime.py
python3 scripts/phase8_azure_webui_adapter.py --deploy
python3 scripts/phase9_maze_tool_boundary.py
python3 scripts/phase19_docker_packaging_boundary.py
open PROGRESS.html
```

## Azure Login Later

Use device-code authentication. Do not paste tokens into code or chat.

```bash
az login --use-device-code
az account set --subscription "Personnel"
azd auth login
azd ext install microsoft.foundry
```

## References

- Microsoft Foundry Toolkit hosted agent workflow
- Azure Developer CLI with Microsoft Foundry extension
- Microsoft Foundry SDK
- Hosted agent deployment from source code
