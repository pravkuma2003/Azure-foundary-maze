# Phase 13 Split Role Agents

This package splits the Phase 12 monolithic hosted runtime into independent
Foundry-hosted role agents.

It deploys the same source package three times with different role entrypoints:

```text
maze-analyst-agent
maze-worker-agent-a
maze-worker-agent-b
```

Each role still uses Pydantic AI internally. Worker agents keep using the
Foundry toolbox MCP endpoint for Maze Tool calls.

## Local Package Validation

```bash
python3 main.py --once --provider test --role analyst
python3 main.py --once --provider test --role worker_a
python3 main.py --once --provider test --role worker_b
```

## Foundry Runtime Target

```text
Project endpoint: https://maze-foundry-prav-ada483.services.ai.azure.com/api/projects/maze-migration-lab
Model deployment: gpt41mini-maze
Provider: foundry
```

Authentication uses Azure identity in hosted/runtime environments. No API keys
are checked into this package.

## Memory Boundary

Phase 13 uses request-scoped Team Memory passed by the coordinator. Durable
Azure shared memory is intentionally left for the next phase so this phase
teaches only the hosted-agent split.
