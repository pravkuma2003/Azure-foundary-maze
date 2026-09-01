# Phase 24 - Post-Run Evaluation Agent

## Objective

Add a fourth independent Foundry-hosted role agent that evaluates a completed
maze run after Analyst and Worker agents finish.

The Reviewer Agent reads Team Memory and human feedback, produces a structured
quality review, and writes the review back to Team Memory. It does not choose
moves, retry workers, change prompts, or update deployment state.

## Why This Matters

Earlier phases focused on execution:

```text
Analyst creates work
Worker A solves Maze A
Worker B solves Maze B
WebUI captures thumbs feedback
```

Phase 24 adds a separate evaluation role:

```text
Completed run
  -> Reviewer Agent reads Team Memory and feedback
  -> Reviewer Agent scores run quality
  -> Reviewer Agent stores findings
  -> learner can inspect the review in the WebUI
```

This is the first phase where an agent evaluates other agents instead of
participating in the maze execution itself.

## Role Boundary

```text
Analyst Agent
  owns maze generation and assignment

Worker Agent A
  owns Maze A navigation

Worker Agent B
  owns Maze B navigation

Reviewer Agent
  owns post-run evaluation only

Azure WebUI Coordinator
  owns deterministic orchestration, durable memory writes, and trace assembly
```

## Reviewer Inputs

The Reviewer reads compact Team Memory:

```text
_role.worker_a
_role.worker_b
worker_state.maze_a
worker_state.maze_b
feedback.events
```

The WebUI invokes the Reviewer only after both Workers have terminal outcomes.

## Reviewer Output

The Reviewer returns structured JSON:

```text
overall_result: approved_for_learning_review | needs_review
score: 0-100
threshold: 90
findings:
  target
  category
  severity
  issue
  recommendation
retry_target
human_gate
review_summary
llm_call_count
```

The current score is intentionally simple:

```text
start at 100
penalize incomplete Worker outcomes
penalize guardrail corrections / loop symptoms
penalize exhausted Worker LLM budgets
penalize thumbs-down human feedback
```

This gives the learner a concrete evaluation artifact without yet introducing
automatic retries or prompt repair.

## Azure Runtime Change

Phase 24 adds a Docker-backed Foundry hosted agent:

```text
maze-reviewer-agent-docker
```

It uses the same shared `maze-role-agent` image as the Analyst and Workers, with:

```text
MAZE_HOSTED_ROLE=reviewer
```

The WebUI receives the Reviewer endpoint through:

```text
FOUNDRY_REVIEWER_AGENT_ENDPOINT
```

## Learning Boundary

Phase 24 teaches agentic evaluation.

It does not yet teach:

```text
automatic retry routing
prompt improvement
model grading against a golden answer
deployment promotion decisions based on live LLM quality
```

Those are later phases.
