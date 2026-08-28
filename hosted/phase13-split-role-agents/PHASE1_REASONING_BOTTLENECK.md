# Phase 1: Why Another Reasoning Agent?

## Learning Objective

Show why a second LLM reasoning agent is justified.

## Starting Architecture

```text
Analyst Agent
  LLM
  owns all reasoning

Orchestrator
  deterministic
  dispatches prepared work

Worker Programs
  deterministic
  execute Maze tool calls

Team Memory
  deterministic
  stores shared facts
```

## Concept

Reasoning bottleneck.

The Analyst is not wrong. It is overloaded.

It owns:

```text
global mission interpretation
both maze route plans
worker instructions
local obstacle interpretation
progress interpretation
next limitation diagnosis
```

The Workers own only execution.

## What This Phase Should Teach

Another LLM agent is justified only when a different role needs its own
reasoning responsibility.

For this curriculum, that next responsibility is:

```text
local navigation reasoning near execution
```

That belongs to a future Worker Agent, not to the Analyst.

## What This Phase Should Not Do

```text
Do not introduce Worker Agent yet.
Do not introduce two Worker Agents at once.
Do not make Orchestrator intelligent.
Do not change the maze.
Do not change the budget.
```

## Result Observed

```text
Reasoning agents: 1
Analyst LLM calls: 1
Worker LLM calls: 0
Orchestrator LLM calls: 0
Bottleneck: Analyst owns global and local reasoning
Next phase: introduce one Worker Agent
```

## Knowledge Check

1. Which component is the only LLM reasoning agent?
2. What reasoning responsibility is missing near execution?
3. Why should Phase 2 introduce one Worker Agent instead of two?
4. Why should Orchestrator remain deterministic?
