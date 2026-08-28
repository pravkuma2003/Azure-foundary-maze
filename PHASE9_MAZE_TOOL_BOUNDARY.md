# Phase 9 - Maze Tool Boundary without New Azure Service

## Objective

Split maze inspection and movement execution out of direct agent runtime logic
and behind a stable program interface.

The Maze Tool was already running in Azure as part of the monolithic hosted
agent package. This phase does not move the tool to Azure; it makes the tool a
separate callable program boundary inside that package.

## Before

```text
Worker Agent logic
  -> direct helper call for legal moves
  -> direct helper call for move validation
```

## After

```text
Worker Agent logic
  -> MazeToolProgram.inspect(request)
  -> MazeToolProgram.move(request)
  -> typed tool result
```

## Contract

```text
Request: operation, maze_id, position, optional move
Result: ok, maze_id, position, legal_moves, optional new_position, optional error
```

## Cost

No new Azure resource is created. The tool still runs inside the existing hosted
agent package, so the idle cost does not change.

## Why This Matters

Future phases can move the Maze Tool into an Azure Function, Container App, or
Foundry-connected tool without changing the agent reasoning contract.
