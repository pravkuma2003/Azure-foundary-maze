# Phase 10 - External Azure Function Maze Tool

## Objective

Move the Maze Tool from an in-package program boundary to a separately hosted
Azure Function tool while keeping the agent contract stable.

## Architecture

```text
Azure WebUI Function
  -> Foundry hosted agent
       -> Pydantic AI reasoning agents
       -> ExternalMazeToolProgram HTTP client
            -> Azure Function Maze Tool
                 -> /api/maze/inspect
                 -> /api/maze/move
```

## What Changed

Phase 9 created a clean in-process `MazeToolProgram` boundary. Phase 10 keeps
that boundary but swaps the implementation to an external HTTP tool when
`MAZE_TOOL_BASE_URL` is configured.

## Security

The Maze Tool uses Azure Functions function-level auth for `inspect` and
`move`. The function key is not committed to source or exposed to browser code.

## Cost

This phase adds one Azure Function App and one Standard_LRS storage account for
the Maze Tool service. Function execution remains consumption-based.
