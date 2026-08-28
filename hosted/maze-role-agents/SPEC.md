# Spec

## Curriculum

```text
Name: Multi-Agent Reasoning From Scratch
Role: Part II after Multi-Agent From Scratch
Framework: Pydantic AI from Phase 1
Model: local-LLM, default alias fast
Execution host: Linux
Review host: Mac / HTML
```

## Goal

Teach when and how to introduce multiple LLM reasoning agents.

Part I already established deterministic orchestration, deterministic workers,
Team Memory, planning, delegation, and scheduling.

Part II only promotes a deterministic component into an LLM reasoning agent when
that component has a unique reasoning responsibility.

## Persistent Roles

```text
Analyst Agent
  LLM reasoning agent
  Owns global mission understanding and global planning

Worker Agent
  LLM reasoning agent, introduced in Phase 2
  Owns local navigation and local tool use

Orchestrator
  Deterministic coordinator
  Owns scheduling, lifecycle, routing, synchronization

Team Memory
  Deterministic shared state
  Owns shared facts and discoveries

Maze Tool
  Deterministic environment
  Owns move validation and wall checks
```

## Roadmap

| Phase | Concept | New architectural component |
| --- | --- | --- |
| 1 | Reasoning Bottleneck | Justify why a Worker Agent is needed |
| 2 | LLM + Tool = Agent | Convert one worker into a reasoning agent |
| 3 | Planning Boundaries | Separate global and local planning |
| 4 | Role-Specific Tools | Give each reasoning agent different tools |
| 5 | Local vs Shared Memory | Add Worker local memory |
| 6 | Synchronization | Publish only useful local discoveries |
| 7 | Multiple Reasoning Workers | Introduce second Worker Agent |
| 8 | Collaboration | Workers cooperate on shared work |
| 9 | Disagreement Handling | Resolve conflicting recommendations |
| 10 | Work Stealing | Dynamically rebalance work |
| 11 | Reflection | Agents evaluate performance |
| 12 | Runtime Escalation | Harness retries, escalates, restarts, aborts |
| 13 | Graph Intelligence | Visualize the full agent graph |
| 14 | Architecture Transfer | Generalize environment without architecture change |

## Metrics

Every phase should report:

```text
mission success
LLM calls used / remaining
number of LLM reasoning agents
which roles used Pydantic AI
which roles were deterministic
global planning owner
local planning owner
memory writes / reads
tool calls
conflicts
retries
handoffs
result observed
next limitation
```

## Phase 1 Scope

Phase 1 does not introduce a Worker Agent yet.

It proves the need for one:

```text
Analyst owns all reasoning.
Workers execute instructions only.
Local navigation reasoning has no owner near execution.
```

Expected Phase 1 result:

```text
One LLM reasoning agent is not enough once local execution needs judgment.
Phase 2 should introduce exactly one Worker Agent.
```

## Phase 2 Scope

Phase 2 introduces one Worker Agent only:

```text
Analyst Agent uses Pydantic AI for global assignment.
Worker Agent A uses Pydantic AI for local navigation.
Worker Program B remains deterministic.
Orchestrator remains deterministic.
```

Expected Phase 2 result:

```text
LLM + Maze Tool creates a real Worker Agent.
Global assignment and local navigation are now owned by different reasoning roles.
Phase 3 should make that global/local planning boundary explicit.
```

## Phase 3 Scope

Phase 3 makes the planning boundary explicit:

```text
Analyst Agent owns global mission constraints.
Worker Agent A owns local Maze A route planning.
Analyst does not provide step-by-step Maze A moves.
Worker Agent A does not assign workers or change the mission.
```

Expected Phase 3 result:

```text
Global planning owner: Analyst Agent.
Local planning owner: Worker Agent A.
The next missing boundary is tool ownership.
```

## Phase 4 Scope

Phase 4 makes role-specific tools explicit:

```text
Analyst Agent owns planning tools:
  read_team_memory
  write_global_plan
  estimate_workload
  assign_task

Worker Agent A owns Maze A tools:
  inspect_maze_cell
  list_legal_moves
  move
  report_local_result

The runtime blocks tools outside each role's allowlist.
```

Expected Phase 4 result:

```text
Tool ownership becomes an enforced runtime boundary.
The Analyst can plan and assign, but cannot move in the maze.
Worker Agent A can inspect and move in Maze A, but cannot assign global work.
The next missing capability is independent local memory.
```

## Phase 5 Scope

Phase 5 adds Worker Agent A private local memory:

```text
Worker Local Memory stores:
  visited cells
  inspected legal moves
  rejected local options
  route candidates
  current local progress

Team Memory stores:
  assignment
  goal
  completion summary
  blocked/escalation facts
```

Expected Phase 5 result:

```text
Worker Agent A can remember detailed local execution state without cluttering
Team Memory.

The next missing capability is synchronization: deciding when a local discovery
should be promoted into shared Team Memory.
```

## Phase 6 Scope

Phase 6 adds synchronization policy:

```text
Worker Agent A evaluates local observations before publishing.

Retain local:
  visited cells
  rejected backtracks
  routine legal move checks

Promote shared:
  assignment acceptance
  route viability checkpoint
  blocked/escalation state
  completion summary
```

Expected Phase 6 result:

```text
Worker Agent A does not publish everything.
It promotes only discoveries that affect team-level understanding.

The next missing capability is a second Worker Agent, introduced only after one
Worker Agent's tools, memory, and synchronization responsibilities are clear.
```

## Phase 7 Scope

Phase 7 introduces Worker Agent B:

```text
Analyst Agent assigns:
  Maze A -> Worker Agent A
  Maze B -> Worker Agent B

Worker Agent A owns:
  Maze A tools
  Worker Local Memory A
  Maze A synchronization decisions
  one LLM decision call per Maze A move

Worker Agent B owns:
  Maze B tools
  Worker Local Memory B
  Maze B synchronization decisions
  one LLM decision call per Maze B move

Orchestrator remains deterministic.
```

Expected Phase 7 result:

```text
There are now three LLM reasoning agents:
  Analyst Agent
  Worker Agent A
  Worker Agent B

Each Worker Agent owns one independent local reasoning domain.
Worker execution is counted as fresh per-move LLM decisions:
  Analyst: 1 call
  Worker Agent A: 8 calls
  Worker Agent B: 8 calls
  Total: 17 / 25 calls

The next missing capability is collaboration between Workers.
```
