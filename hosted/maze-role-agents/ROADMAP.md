# Roadmap

## Part II Theme

Move from:

```text
one LLM Analyst + deterministic components
```

to:

```text
multiple LLM reasoning agents with separate responsibilities
```

## Phases

```text
Phase 1   Why Another Reasoning Agent?
Phase 2   Worker Agent
Phase 3   Global vs Local Planning
Phase 4   Tool Ownership
Phase 5   Independent Local Memory
Phase 6   Shared Knowledge Synchronization
Phase 7   Second Worker Agent
Phase 8   Worker Collaboration
Phase 9   Conflict Resolution
Phase 10  Dynamic Delegation
Phase 11  Reflection
Phase 12  Harness Intelligence
Phase 13  Agent Graph Visualization
Phase 14  Environment Generalization
```

## Current Status

```text
Starter deployment complete through Phase 7.
Pydantic AI is used from Phase 1 onward.
Phase 1 diagnoses the Analyst bottleneck.
Phase 2 introduces one Worker Agent.
Phase 3 separates global and local planning ownership.
Phase 4 enforces role boundaries with explicit tool allowlists.
Phase 5 separates Worker Agent A private local memory from Team Memory.
Phase 6 adds synchronization from Worker Local Memory to Team Memory.
Phase 7 promotes Worker Program B into Worker Agent B.
```

## Phase Intent

Phase 1: Why Another Reasoning Agent?

Diagnose the bottleneck in the Part I architecture. Analyst owns all reasoning;
deterministic workers execute but cannot reason locally.

Phase 2: Worker Agent

Convert one worker into an LLM reasoning agent with Maze tools. Analyst still
plans globally; Worker owns local navigation.

Phase 3: Global vs Local Planning

Separate mission planning from local execution planning.

Phase 4: Tool Ownership

Give Analyst and Worker different tools so responsibility is enforced by
capability, not just prompt text.

Phase 5: Independent Local Memory

Worker keeps temporary observations locally instead of writing everything to
Team Memory.

Phase 6: Shared Knowledge Synchronization

Worker decides what local discoveries should be published to shared memory.

Phase 7: Second Worker Agent

Introduce a second LLM Worker after one Worker Agent is understood.

Phase 8: Worker Collaboration

Workers cooperate on shared work.

Phase 9: Conflict Resolution

Resolve competing worker recommendations.

Phase 10: Dynamic Delegation

Reassign work when one worker finishes early.

Phase 11: Reflection

Agents evaluate local and team performance.

Phase 12: Harness Intelligence

Runtime decides when to retry, escalate, restart, or abort.

Phase 13: Agent Graph Visualization

Visualize the full reasoning graph.

Phase 14: Environment Generalization

Change maze size, goal, obstacles, or budget without changing the architecture.
