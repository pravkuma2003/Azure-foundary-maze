# Phase 16 - Dynamic Mission Design

## Objective

Make the Analyst do meaningful mission design instead of assigning the same
fixed mazes every run.

## What Changed

Before:

```text
Analyst -> assign fixed Maze A to Worker A, fixed Maze B to Worker B
Workers -> solve the same layouts each run
```

After:

```text
Analyst -> generate fresh maze rows
Analyst -> store maze rows and task profiles in Team Memory
Workers -> read assigned rows from Team Memory
Workers -> solve or report blocked/impossible through their own reasoning
```

The WebUI now separates mission design from execution:

```text
Run Fresh Maze -> call Analyst only -> display Maze A and Maze B
Play           -> call Worker A and Worker B for the displayed Team Memory run
Replay         -> replay the loaded trace without any new agent calls
```

When Play is pressed, the browser immediately shows Worker dispatch events so
the learner can see execution has started. The WebUI then calls each Worker in
one-step mode and renders each completed decision/move before requesting the
next step.

## Analyst Intelligence Added

The Analyst now contributes useful reasoning at the mission-design level:

```text
create varied per-run tasks
decide wall counts and mission framing
avoid handing Workers a known route
avoid claiming the generated maze is solvable
publish only layouts/profiles/assignments, not step-by-step moves
explain why the generated work is suitable for the learning objective
```

The platform validates only the grid shape and legal moves. It does not solve
the Worker path or rescue Worker decisions with a deterministic shortest path.
If a generated maze is impossible, the Worker should discover and report that.

## Why This Matters

The learner can now see the Analyst-generated work product before any Worker
reasoning starts. That keeps the phase focused on role boundaries:

```text
Analyst owns task generation and assignment.
Team Memory owns durable handoff.
Workers own local maze attempts after the learner presses Play.
```
