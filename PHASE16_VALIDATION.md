# Phase 16 Validation

## Expected Result

```text
Analyst produces dynamic Maze A and Maze B rows without pre-solving them.
Team Memory stores maze.maze_a.rows and maze.maze_b.rows.
Workers solve those rows or report blocked/impossible instead of package-fixed mazes.
Maze Tool validates inspect/move against request-provided rows.
WebUI renders the generated layouts.
Run Fresh Maze does not run Worker agents.
Play runs Worker agents against the already displayed Team Memory run.
Play immediately shows Worker dispatch events while the hosted Worker calls are active.
Worker playback uses repeated one-step Worker calls so decisions/moves render incrementally.
```

## Live Result

```text
status: complete
webui_url: https://maze-webui-func-prav-ada483.azurewebsites.net/
mission_source: foundry-analyst-mission
mission_elapsed_s: 13.3
mission_workflow_stage: mission_ready
mission_llm_calls: 1
mission_worker_a_outcome: pending
mission_worker_b_outcome: pending
mission_maze_count: 2
workers_source: foundry-workers
workers_elapsed_s: 12.1
workers_workflow_stage: workers_complete
workers_same_team_memory_run: true
worker_step_endpoint: /api/worker-step
worker_a_first_step_elapsed_s: 12.2
worker_b_first_step_elapsed_s: 9.6
worker_a_first_step_outcome: running
worker_b_first_step_outcome: reported_stuck
visible_moves_after_first_worker_steps: 1
workers_llm_calls_after_first_worker_steps: 2
worker_a_outcome: running
worker_b_outcome: reported_stuck
worker_invalid_moves: 0
worker_side_path_rescue: false
guardrail_corrections: 0
```
