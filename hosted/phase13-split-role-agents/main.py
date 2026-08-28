#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import sys
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.provider_config import build_provider_config
from src.reasoning_curriculum import (
    MAZE_A_ROWS,
    MAZE_B_ROWS,
    _maze_tool_for_rows,
    _run_phase7_worker_sync_decision,
)


ROLE_ALIASES = {
    "analyst": "analyst",
    "analyst_agent": "analyst",
    "maze-analyst-agent": "analyst",
    "worker_a": "worker_a",
    "worker-agent-a": "worker_a",
    "maze-worker-agent-a": "worker_a",
    "worker_b": "worker_b",
    "worker-agent-b": "worker_b",
    "maze-worker-agent-b": "worker_b",
}


def normalize_role(role: str | None) -> str:
    selected = (role or os.environ.get("MAZE_HOSTED_ROLE") or "analyst").strip().lower()
    normalized = ROLE_ALIASES.get(selected)
    if not normalized:
        raise ValueError(f"unknown MAZE_HOSTED_ROLE={selected!r}; expected analyst, worker_a, or worker_b")
    return normalized


def parse_payload(request: dict[str, Any] | str | None) -> dict[str, Any]:
    if isinstance(request, str):
        try:
            payload = json.loads(request)
        except json.JSONDecodeError:
            payload = {"prompt": request}
    else:
        payload = request or {}
    return payload if isinstance(payload, dict) else {"prompt": str(payload)}


def provider_config_for(provider: str, model: str | None):
    return None if provider == "test" else build_provider_config(provider, model)


def find_marker(rows: list[str], marker: str) -> tuple[int, int]:
    for row_index, row in enumerate(rows):
        col_index = row.find(marker)
        if col_index >= 0:
            return row_index, col_index
    raise ValueError(f"maze does not contain marker {marker!r}")


def valid_maze_rows(rows: Any) -> bool:
    if not isinstance(rows, list) or len(rows) != 5:
        return False
    if not all(isinstance(row, str) and len(row) == 5 and re.fullmatch(r"[SG.#]+", row) for row in rows):
        return False
    joined = "".join(rows)
    return joined.count("S") == 1 and joined.count("G") == 1


def open_neighbors(position: tuple[int, int], rows: list[str]) -> list[tuple[str, tuple[int, int]]]:
    moves = {
        "north": (-1, 0),
        "south": (1, 0),
        "west": (0, -1),
        "east": (0, 1),
    }
    result: list[tuple[str, tuple[int, int]]] = []
    for move, (dr, dc) in moves.items():
        candidate = (position[0] + dr, position[1] + dc)
        row, col = candidate
        if 0 <= row < len(rows) and 0 <= col < len(rows[0]) and rows[row][col] != "#":
            result.append((move, candidate))
    return result


def manhattan(position: tuple[int, int], goal: tuple[int, int]) -> int:
    return abs(position[0] - goal[0]) + abs(position[1] - goal[1])


def normalize_position_list(value: Any) -> list[tuple[int, int]]:
    positions: list[tuple[int, int]] = []
    if not isinstance(value, list):
        return positions
    for item in value:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            positions.append((int(item[0]), int(item[1])))
    return positions


def move_between(before: tuple[int, int], after: tuple[int, int]) -> str:
    delta = (after[0] - before[0], after[1] - before[1])
    for move, move_delta in {"north": (-1, 0), "south": (1, 0), "west": (0, -1), "east": (0, 1)}.items():
        if delta == move_delta:
            return move
    return ""


def make_random_maze(seed: str, *, wall_count: int) -> dict[str, Any]:
    rng = random.Random(seed)
    cells = [(row, col) for row in range(5) for col in range(5) if (row, col) not in {(0, 0), (4, 4)}]
    selected = set(rng.sample(cells, wall_count))
    grid = [["." for _ in range(5)] for _ in range(5)]
    for row, col in selected:
        grid[row][col] = "#"
    grid[0][0] = "S"
    grid[4][4] = "G"
    rows = ["".join(row) for row in grid]
    return {"seed": seed, "rows": rows, "wall_count": wall_count, "solvability_prechecked": False}


def build_dynamic_mazes() -> dict[str, dict[str, Any]]:
    run_seed = os.environ.get("MAZE_RUN_SEED") or uuid.uuid4().hex[:12]
    return {
        "maze_a": make_random_maze(f"{run_seed}:maze_a", wall_count=6),
        "maze_b": make_random_maze(f"{run_seed}:maze_b", wall_count=7),
    }


def run_dynamic_analyst_mission(provider: str, provider_config: Any | None) -> dict[str, Any]:
    mazes = build_dynamic_mazes()
    if provider == "test":
        return {
            "agent": "Analyst Agent v7",
            "headline": "Analyst generates fresh maze layouts and assigns ownership.",
            "multi_worker_assignment": "Assign the generated Maze A to Worker Agent A and generated Maze B to Worker Agent B. Do not provide routes.",
            "maze_design_rationale": "Walls are randomized per run without route or solvability pre-screening.",
            "coordination_boundary": "Analyst owns mission design and assignment; Workers own route discovery, movement, and impossible-maze reporting.",
            "confidence": 0.91,
            "llm_call_count": 0,
            "mazes": mazes,
        }

    try:
        from pydantic import BaseModel, Field
        from pydantic_ai import Agent, PromptedOutput
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.usage import UsageLimits
    except Exception as exc:
        raise RuntimeError("Pydantic AI is not installed in the hosted role-agent package.") from exc

    class DynamicMissionOutput(BaseModel):
        headline: str = Field(description="One sentence summary of the dynamic mission.")
        multi_worker_assignment: str = Field(description="Assign Maze A to Worker A and Maze B to Worker B without route steps.")
        maze_design_rationale: str = Field(description="Why the generated mazes are useful learning tasks.")
        coordination_boundary: str = Field(description="What Analyst owns and what Workers own.")
        confidence: float = Field(ge=0.0, le=1.0)

    assert provider_config is not None
    pydantic_model = OpenAIChatModel(
        provider_config.model,
        provider=OpenAIProvider(base_url=provider_config.base_url, api_key=provider_config.api_key),
    )
    agent = Agent(
        pydantic_model,
        output_type=PromptedOutput(DynamicMissionOutput),
        instructions=(
            "You are the Analyst Agent for a maze multi-agent lab. "
            "Use the generated maze layouts as mission inputs, assign each maze to the correct worker, "
            "and do not reveal step-by-step routes or claim the mazes are solvable."
        ),
    )
    prompt = f"""
Create the mission assignment for two generated 5x5 mazes.

Maze A rows: {mazes['maze_a']['rows']}
Maze A wall_count: {mazes['maze_a']['wall_count']}
Maze A solvability_prechecked: {mazes['maze_a']['solvability_prechecked']}

Maze B rows: {mazes['maze_b']['rows']}
Maze B wall_count: {mazes['maze_b']['wall_count']}
Maze B solvability_prechecked: {mazes['maze_b']['solvability_prechecked']}

Rules:
- Assign Maze A to Worker Agent A.
- Assign Maze B to Worker Agent B.
- Do not provide a route or next moves.
- Do not claim the mazes are solvable.
- State that Workers must either reach the goal or report blocked/impossible.
- Explain why randomizing walls makes the Workers perform real local reasoning.
/no_think
"""
    result = agent.run_sync(prompt, usage_limits=UsageLimits(request_limit=3))
    usage = getattr(result, "usage", None)
    calls = getattr(usage, "requests", 0)
    return {
        "agent": "Analyst Agent v7",
        "headline": result.output.headline,
        "multi_worker_assignment": result.output.multi_worker_assignment,
        "maze_design_rationale": result.output.maze_design_rationale,
        "coordination_boundary": result.output.coordination_boundary,
        "confidence": result.output.confidence,
        "llm_call_count": calls if isinstance(calls, int) else 0,
        "mazes": mazes,
    }


def memory_rows(team_memory: dict[str, Any], maze_id: str, fallback: list[str]) -> list[str]:
    rows = team_memory.get(f"maze.{maze_id}.rows")
    if valid_maze_rows(rows):
        return list(rows)
    return list(fallback)


def memory_position(value: Any, fallback: tuple[int, int]) -> tuple[int, int]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return int(value[0]), int(value[1])
    return fallback


def memory_visited(value: Any) -> list[tuple[int, int]]:
    visited: list[tuple[int, int]] = []
    if not isinstance(value, list):
        return visited
    for item in value:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            visited.append((int(item[0]), int(item[1])))
    return visited


def run_dynamic_worker_move_decisions(
    provider: str,
    provider_config: Any | None,
    *,
    worker_name: str,
    maze_id: str,
    maze_label: str,
    rows: list[str],
    max_steps: int = 11,
    initial_position: tuple[int, int] | None = None,
    initial_visited: list[tuple[int, int]] | None = None,
    initial_path_stack: list[tuple[int, int]] | None = None,
    initial_dead_ends: list[tuple[int, int]] | None = None,
    initial_step: int = 1,
    remaining_call_budget: int | None = None,
) -> tuple[list[dict[str, Any]], tuple[int, int], bool, int, str, list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]], int]:
    if provider != "test":
        try:
            from pydantic import BaseModel, Field
            from pydantic_ai import Agent, PromptedOutput
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider
            from pydantic_ai.usage import UsageLimits
        except Exception as exc:
            raise RuntimeError("Pydantic AI is not installed in the hosted role-agent package.") from exc

        class MoveDecisionOutput(BaseModel):
            action: str = Field(description="One of: move, report_impossible, report_stuck.")
            chosen_move: str = Field(description="If action is move, one legal move: north, south, west, or east. Otherwise empty.")
            rationale: str = Field(description="Short reason using the assigned maze, current position, legal moves, goal, and visited cells.")
            confidence: float = Field(ge=0.0, le=1.0)

    position = initial_position or find_marker(rows, "S")
    goal = find_marker(rows, "G")
    visited: list[tuple[int, int]] = list(initial_visited or [])
    if position not in visited:
        visited.append(position)
    path_stack: list[tuple[int, int]] = list(initial_path_stack or [])
    if not path_stack:
        path_stack = [position]
    elif path_stack[-1] != position:
        path_stack.append(position)
    dead_ends: list[tuple[int, int]] = list(initial_dead_ends or [])
    decisions: list[dict[str, Any]] = []
    invalid_moves = 0
    guardrail_corrections = 0
    outcome = "budget_exhausted"
    maze_tool = _maze_tool_for_rows(maze_id, maze_label, rows)
    pydantic_model = None
    if provider != "test":
        assert provider_config is not None
        pydantic_model = OpenAIChatModel(
            provider_config.model,
            provider=OpenAIProvider(base_url=provider_config.base_url, api_key=provider_config.api_key),
        )

    for step in range(initial_step, initial_step + max_steps):
        if position == goal:
            outcome = "goal_reached"
            break
        inspection = maze_tool.inspect(position)
        legal_moves = inspection.legal_moves
        neighbors = open_neighbors(position, rows)
        neighbor_by_move = {move: candidate for move, candidate in neighbors}
        explored = set(visited)
        blocked_or_exhausted = set(dead_ends)
        available = [
            (move, candidate)
            for move, candidate in neighbors
            if candidate not in explored and candidate not in blocked_or_exhausted
        ]
        available_moves = [move for move, _ in sorted(available, key=lambda item: manhattan(item[1], goal))]
        backtrack_target = path_stack[-2] if len(path_stack) >= 2 else None
        backtrack_move = move_between(position, backtrack_target) if backtrack_target is not None else ""
        if backtrack_move not in legal_moves:
            backtrack_target = None
            backtrack_move = ""
        if not legal_moves:
            outcome = "reported_impossible" if len(path_stack) <= 1 else "reported_stuck"
            if position not in dead_ends:
                dead_ends.append(position)
            decisions.append(
                {
                    "step": step,
                    "position": position,
                    "action": outcome.replace("reported_", "report_"),
                    "chosen_move": "",
                    "raw_move": "",
                    "rationale": f"{worker_name} inspected {position} and found no legal moves; it reports the assigned maze path is blocked from the current state.",
                    "legal_moves_seen": legal_moves,
                    "new_position": position,
                    "confidence": 1.0,
                    "llm_call_count": 0,
                    "maze_tool_call_count": 1,
                    "available_unvisited_moves": available_moves,
                    "backtrack_move": backtrack_move,
                    "dead_ends": list(dead_ends),
                    "guardrail_corrections": guardrail_corrections,
                    "move_applied": False,
                    "tool_runtime": getattr(maze_tool, "runtime_name", "in-process"),
                }
            )
            break
        if available_moves:
            raw_move = available_moves[0]
            action = "move"
            rationale = f"{worker_name} test mode chooses an unvisited legal move from {position}; no route solver is used."
        elif backtrack_move:
            raw_move = backtrack_move
            action = "move"
            rationale = f"{worker_name} test mode marks {position} exhausted and backtracks to {backtrack_target}."
        else:
            raw_move = ""
            action = "report_impossible"
            rationale = f"{worker_name} exhausted all reachable positions from the start without reaching {goal}."
        confidence = 0.72
        llm_calls = 0
        if provider != "test" and pydantic_model is not None:
            request_limit = 3 if remaining_call_budget is None else max(0, min(3, int(remaining_call_budget)))
            if request_limit <= 0:
                outcome = "budget_exhausted"
                decisions.append(
                    {
                        "step": step,
                        "position": position,
                        "action": "budget_exhausted",
                        "chosen_move": "",
                        "raw_move": "",
                        "rationale": f"{worker_name} has no remaining LLM call budget for this step.",
                        "legal_moves_seen": legal_moves,
                        "new_position": position,
                        "confidence": 1.0,
                        "llm_call_count": 0,
                        "maze_tool_call_count": 1,
                        "move_applied": False,
                        "tool_runtime": getattr(maze_tool, "runtime_name", "in-process"),
                    }
                )
                break
            agent = Agent(
                pydantic_model,
                output_type=PromptedOutput(MoveDecisionOutput),
                instructions=(
                    "You are a Worker Agent that owns maze reasoning for one assigned maze. "
                    "Use the assigned maze layout, current position, legal moves, goal, visited cells, path stack, and dead ends. "
                    "Choose exactly one productive unvisited legal move when one exists. "
                    "If no productive unvisited move exists but backtrack_move is provided, choose that backtrack move. "
                    "Do not oscillate between the same cells. Do not choose a visited/dead-end cell while any unvisited legal move remains. "
                    "Report_impossible only when no productive move and no backtrack move remain. "
                    "Do not output a full route."
                ),
            )
            prompt = (
                f"Worker={worker_name}; maze={maze_label}; rows={rows}; position={position}; "
                f"goal={goal}; visited={visited}; path_stack={path_stack}; dead_ends={dead_ends}; "
                f"legal_moves={legal_moves}; productive_unvisited_moves={available_moves}; "
                f"backtrack_move={backtrack_move or 'none'}; backtrack_target={backtrack_target or 'none'}. "
                "Return action, chosen_move, rationale, confidence. "
                "Use action=move only when chosen_move is one of the legal_moves. "
                "If productive_unvisited_moves is non-empty, chosen_move must be one of them. "
                "If productive_unvisited_moves is empty and backtrack_move is not none, chosen_move must equal backtrack_move. "
                "If productive_unvisited_moves is empty and backtrack_move is none, use report_impossible. /no_think"
            )
            try:
                result = agent.run_sync(prompt, usage_limits=UsageLimits(request_limit=request_limit))
            except Exception as exc:
                if "UsageLimit" not in exc.__class__.__name__ and "usage limit" not in str(exc).lower():
                    raise
                outcome = "budget_exhausted"
                decisions.append(
                    {
                        "step": step,
                        "position": position,
                        "action": "budget_exhausted",
                        "chosen_move": "",
                        "raw_move": "",
                        "rationale": f"{worker_name} reached its remaining LLM call budget before a valid move could be produced.",
                        "legal_moves_seen": legal_moves,
                        "new_position": position,
                        "confidence": 1.0,
                        "llm_call_count": request_limit,
                        "maze_tool_call_count": 1,
                        "move_applied": False,
                        "tool_runtime": getattr(maze_tool, "runtime_name", "in-process"),
                    }
                )
                break
            usage = getattr(result, "usage", None)
            calls = getattr(usage, "requests", 0)
            llm_calls = calls if isinstance(calls, int) else 0
            action = result.output.action.strip().lower()
            raw_move = result.output.chosen_move.strip().lower()
            rationale = result.output.rationale
            confidence = result.output.confidence

        if available_moves:
            chosen_candidate = neighbor_by_move.get(raw_move)
            if action != "move" or raw_move not in available_moves or chosen_candidate in blocked_or_exhausted:
                guardrail_corrections += 1
                original_action = action
                original_move = raw_move
                action = "move"
                raw_move = available_moves[0]
                rationale = (
                    f"Loop guard corrected {worker_name}'s raw output "
                    f"action={original_action}, move={original_move or 'none'} because productive unvisited moves remain. "
                    f"Choosing {raw_move} from {position}; visited={visited}; dead_ends={dead_ends}."
                )
                confidence = min(float(confidence), 0.8)
        elif backtrack_move:
            if position not in dead_ends:
                dead_ends.append(position)
            if action != "move" or raw_move != backtrack_move:
                guardrail_corrections += 1
                original_action = action
                original_move = raw_move
                action = "move"
                raw_move = backtrack_move
                rationale = (
                    f"Loop guard corrected {worker_name}'s raw output "
                    f"action={original_action}, move={original_move or 'none'} because every non-backtrack exit from {position} is exhausted. "
                    f"Backtracking to {backtrack_target} instead of looping."
                )
                confidence = min(float(confidence), 0.8)
            elif "backtrack" not in rationale.lower() and "exhaust" not in rationale.lower():
                rationale = f"{rationale} Local memory marks {position} exhausted, so this move backtracks to {backtrack_target}."
        else:
            if action == "move":
                guardrail_corrections += 1
                rationale = (
                    f"Loop guard stopped {worker_name}'s raw move={raw_move or 'none'} because all reachable cells are exhausted "
                    f"and no backtrack target remains. Reporting the maze impossible from explored local state."
                )
            action = "report_impossible"
            raw_move = ""

        if action != "move":
            outcome = "reported_impossible" if action == "report_impossible" else "reported_stuck"
            decisions.append(
                {
                    "step": step,
                    "position": position,
                    "action": action,
                    "chosen_move": "",
                    "raw_move": raw_move,
                    "rationale": rationale,
                    "legal_moves_seen": legal_moves,
                    "new_position": position,
                    "confidence": confidence,
                    "llm_call_count": llm_calls,
                    "maze_tool_call_count": 1,
                    "available_unvisited_moves": available_moves,
                    "backtrack_move": backtrack_move,
                    "dead_ends": list(dead_ends),
                    "guardrail_corrections": guardrail_corrections,
                    "move_applied": False,
                    "tool_runtime": getattr(maze_tool, "runtime_name", "in-process"),
                }
            )
            break

        chosen_move = raw_move
        if raw_move not in legal_moves:
            invalid_moves += 1
            outcome = "invalid_move"
            decisions.append(
                {
                    "step": step,
                    "position": position,
                    "action": action,
                    "chosen_move": chosen_move,
                    "raw_move": raw_move,
                    "rationale": f"Maze Tool rejected raw move '{raw_move}' at {position}. {rationale}",
                    "legal_moves_seen": legal_moves,
                    "new_position": position,
                    "confidence": confidence,
                    "llm_call_count": llm_calls,
                    "maze_tool_call_count": 1,
                    "available_unvisited_moves": available_moves,
                    "backtrack_move": backtrack_move,
                    "dead_ends": list(dead_ends),
                    "guardrail_corrections": guardrail_corrections,
                    "move_applied": False,
                    "tool_runtime": getattr(maze_tool, "runtime_name", "in-process"),
                }
            )
            break

        try:
            move_result = maze_tool.move(position, chosen_move)
        except Exception as exc:
            invalid_moves += 1
            outcome = "tool_rejected_move"
            decisions.append(
                {
                    "step": step,
                    "position": position,
                    "action": action,
                    "chosen_move": chosen_move,
                    "raw_move": raw_move,
                    "rationale": f"Maze Tool rejected {chosen_move} at {position}: {exc}",
                    "legal_moves_seen": legal_moves,
                    "new_position": position,
                    "confidence": confidence,
                    "llm_call_count": llm_calls,
                    "maze_tool_call_count": 2,
                    "available_unvisited_moves": available_moves,
                    "backtrack_move": backtrack_move,
                    "dead_ends": list(dead_ends),
                    "guardrail_corrections": guardrail_corrections,
                    "move_applied": False,
                    "tool_runtime": getattr(maze_tool, "runtime_name", "in-process"),
                }
            )
            break

        if not move_result.ok:
            invalid_moves += 1
            outcome = "tool_rejected_move"
            decisions.append(
                {
                    "step": step,
                    "position": position,
                    "action": action,
                    "chosen_move": chosen_move,
                    "raw_move": raw_move,
                    "rationale": f"Maze Tool rejected {chosen_move} at {position}: {move_result.error}",
                    "legal_moves_seen": legal_moves,
                    "new_position": position,
                    "confidence": confidence,
                    "llm_call_count": llm_calls,
                    "maze_tool_call_count": 2,
                    "move_applied": False,
                    "tool_runtime": getattr(maze_tool, "runtime_name", "in-process"),
                }
            )
            break

        next_position = move_result.new_position or move_result.position
        decisions.append(
            {
                "step": step,
                "position": position,
                "action": action,
                "chosen_move": chosen_move,
                "raw_move": raw_move,
                "rationale": rationale,
                "legal_moves_seen": legal_moves,
                "new_position": next_position,
                "confidence": confidence,
                "llm_call_count": llm_calls,
                "maze_tool_call_count": 2,
                "available_unvisited_moves": available_moves,
                "backtrack_move": backtrack_move,
                "dead_ends": list(dead_ends),
                "guardrail_corrections": guardrail_corrections,
                "move_applied": True,
                "tool_runtime": getattr(maze_tool, "runtime_name", "in-process"),
            }
        )
        if position not in visited:
            visited.append(position)
        position = next_position
        if position not in visited:
            visited.append(position)
        if backtrack_target is not None and position == backtrack_target and len(path_stack) >= 2:
            path_stack.pop()
        elif path_stack[-1] != position:
            path_stack.append(position)

    if position == goal:
        outcome = "goal_reached"
    elif max_steps == 1 and decisions and decisions[-1].get("move_applied"):
        outcome = "running"
    return decisions, position, position == goal, invalid_moves, outcome, visited, path_stack, dead_ends, guardrail_corrections


def run_role_agent(*, role: str, provider: str, model: str | None, team_memory: dict[str, Any]) -> dict[str, Any]:
    provider_config = provider_config_for(provider, model)
    if role == "analyst":
        output = run_dynamic_analyst_mission(provider, provider_config)
        mazes = output["mazes"]
        shared_writes = [
            {"key": "mission", "value": "Solve generated Maze A and generated Maze B independently."},
            {"key": "maze.maze_a.rows", "value": mazes["maze_a"]["rows"]},
            {"key": "maze.maze_b.rows", "value": mazes["maze_b"]["rows"]},
            {"key": "maze.maze_a.profile", "value": {key: value for key, value in mazes["maze_a"].items() if key != "rows"}},
            {"key": "maze.maze_b.profile", "value": {key: value for key, value in mazes["maze_b"].items() if key != "rows"}},
            {"key": "assignment.maze_a", "value": "Worker Agent A owns generated Maze A. Route is not provided."},
            {"key": "assignment.maze_b", "value": "Worker Agent B owns generated Maze B. Route is not provided."},
            {"key": "analyst.maze_design_rationale", "value": output["maze_design_rationale"]},
            {"key": "coordination_boundary", "value": output["coordination_boundary"]},
        ]
        return {
            "status": "complete",
            "phase": 16,
            "role": "analyst",
            "hosted_agent_name": "maze-analyst-agent",
            "agent": output["agent"],
            "output": output,
            "team_memory_reads": list(team_memory.keys()),
            "team_memory_writes": shared_writes,
            "events": [
                {
                    "type": "plan",
                    "actor": "Analyst Agent",
                    "target": "Team Memory",
                    "label": "global assignment",
                    "detail": f"{output['multi_worker_assignment']} Generated wall layouts are persisted to Team Memory.",
                    "llm_call_count": output["llm_call_count"],
                }
            ],
            "summary": {
                "llm_calls": output["llm_call_count"],
                "maze_tool_calls": 0,
                "uses_pydantic_ai": True,
                "owns": "dynamic mission design and global multi-worker assignment",
            },
        }

    worker_specs = {
        "worker_a": {
            "agent_name": "maze-worker-agent-a",
            "worker_name": "Worker Agent A",
            "maze_id": "maze_a",
            "maze_label": "Maze A",
            "rows": memory_rows(team_memory, "maze_a", MAZE_A_ROWS),
            "assignment_key": "assignment.maze_a",
        },
        "worker_b": {
            "agent_name": "maze-worker-agent-b",
            "worker_name": "Worker Agent B",
            "maze_id": "maze_b",
            "maze_label": "Maze B",
            "rows": memory_rows(team_memory, "maze_b", MAZE_B_ROWS),
            "assignment_key": "assignment.maze_b",
        },
    }
    spec = worker_specs[role]
    state_key = f"worker_state.{spec['maze_id']}"
    worker_state = team_memory.get(state_key) if isinstance(team_memory.get(state_key), dict) else {}
    start_position = find_marker(spec["rows"], "S")
    current_position = memory_position(worker_state.get("position") if isinstance(worker_state, dict) else None, start_position)
    visited = memory_visited(worker_state.get("visited") if isinstance(worker_state, dict) else None)
    path_stack = normalize_position_list(worker_state.get("path_stack") if isinstance(worker_state, dict) else None)
    dead_ends = normalize_position_list(worker_state.get("dead_ends") if isinstance(worker_state, dict) else None)
    next_step = int(worker_state.get("next_step") or 1) if isinstance(worker_state, dict) else 1
    max_worker_steps = int(team_memory.get("_control.worker_max_steps") or 11)
    max_worker_steps = max(1, min(11, max_worker_steps))
    remaining_call_budget_key = f"_control.worker_remaining_llm_calls.{role}"
    remaining_call_budget_value = team_memory.get(remaining_call_budget_key)
    remaining_call_budget = int(remaining_call_budget_value) if remaining_call_budget_value is not None else None
    step_mode = max_worker_steps == 1 or bool(team_memory.get("_control.worker_step_mode"))
    if step_mode:
        sync = {
            "agent": f"{spec['worker_name']} vStep",
            "llm_call_count": 0,
            "decision": "Continue one visible step from stored Team Memory state.",
        }
    else:
        sync = _run_phase7_worker_sync_decision(
            provider,
            provider_config,
            worker_name=spec["worker_name"],
            maze_label=spec["maze_label"],
        )
    decisions, final_position, reached_goal, invalid_moves, outcome, visited, path_stack, dead_ends, guardrail_corrections = run_dynamic_worker_move_decisions(
        provider,
        provider_config,
        worker_name=spec["worker_name"],
        maze_id=spec["maze_id"],
        maze_label=spec["maze_label"],
        rows=spec["rows"],
        max_steps=max_worker_steps,
        initial_position=current_position,
        initial_visited=visited,
        initial_path_stack=path_stack,
        initial_dead_ends=dead_ends,
        initial_step=next_step,
        remaining_call_budget=remaining_call_budget,
    )
    llm_calls = sync["llm_call_count"] + sum(int(decision.get("llm_call_count") or 0) for decision in decisions)
    events: list[dict[str, Any]] = [
        {
            "type": "memory",
            "actor": spec["worker_name"],
            "target": "Team Memory",
            "label": "read assignment",
            "detail": f"{spec['worker_name']} reads {spec['assignment_key']} and ignores the other maze assignment.",
            "memory_scope": "shared",
            "llm_call_count": 0,
        }
    ]
    for decision in decisions:
        after_position = tuple(decision.get("new_position") or decision["position"])
        event_type = "decision" if decision.get("action") == "move" else "result"
        events.append(
            {
                "type": event_type,
                "actor": spec["worker_name"],
                "target": spec["maze_label"],
                "maze_id": spec["maze_id"],
                "label": f"choose {decision['chosen_move']}" if decision.get("action") == "move" else str(decision.get("action") or "stop"),
                "detail": decision["rationale"],
                "position": decision["position"],
                "llm_call_count": decision.get("llm_call_count", 0),
            }
        )
        if not decision.get("move_applied"):
            continue
        events.append(
            {
                "type": "move",
                "actor": spec["worker_name"],
                "target": spec["maze_label"],
                "maze_id": spec["maze_id"],
                "label": f"move {decision['chosen_move']}",
                "detail": f"{spec['worker_name']} applied {decision['chosen_move']} through Maze Tool: {tuple(decision['position'])} -> {after_position}.",
                "position": after_position,
                "tool_runtime": decision.get("tool_runtime", "in-process"),
                "llm_call_count": 0,
            }
        )
    events.append(
        {
            "type": "result",
            "actor": spec["worker_name"],
            "target": "Team Memory",
            "maze_id": spec["maze_id"],
            "label": "publish completion",
            "detail": f"{spec['worker_name']} {'completed' if reached_goal else 'stopped before completing'} {spec['maze_label']} at {final_position}.",
            "memory_scope": "shared",
            "llm_call_count": 0,
        }
    )
    return {
        "status": "complete",
        "phase": 16,
        "role": role,
        "hosted_agent_name": spec["agent_name"],
        "agent": sync["agent"],
        "maze_id": spec["maze_id"],
        "maze_label": spec["maze_label"],
        "output": sync,
        "move_decisions": decisions,
        "team_memory_reads": [spec["assignment_key"], state_key],
        "team_memory_writes": [
            {"key": f"result.{spec['maze_id']}", "value": f"{spec['maze_label']} {'complete' if reached_goal else 'incomplete'} at {final_position}."},
            {
                "key": state_key,
                "value": {
                    "position": list(final_position),
                    "visited": [list(item) for item in visited],
                    "path_stack": [list(item) for item in path_stack],
                    "dead_ends": [list(item) for item in dead_ends],
                    "next_step": next_step + len(decisions),
                    "outcome": outcome,
                    "goal_reached": reached_goal,
                    "guardrail_corrections": guardrail_corrections,
                    "updated_by": spec["worker_name"],
                },
            },
        ],
        "events": events,
        "summary": {
            "llm_calls": llm_calls,
            "maze_tool_calls": sum(int(decision.get("maze_tool_call_count") or 0) for decision in decisions),
            "uses_pydantic_ai": True,
            "owns": f"{spec['maze_label']} local reasoning, Maze Tool calls, and local memory",
            "goal_reached": reached_goal,
            "outcome": outcome,
            "invalid_moves": invalid_moves,
            "worker_side_path_rescue": False,
            "guardrail_corrections": guardrail_corrections,
        },
    }


def default_output_dir() -> Path:
    return Path(os.environ.get("MAZE_OUTPUT_DIR") or "/tmp/maze-agent-artifacts")


def invoke(request: dict[str, Any] | str | None = None) -> dict[str, Any]:
    payload = parse_payload(request)
    provider = payload.get("provider") or os.environ.get("MAZE_PROVIDER") or "foundry"
    model = payload.get("model") or os.environ.get("FOUNDRY_MODEL_DEPLOYMENT") or os.environ.get("MAZE_MODEL")
    role = normalize_role(payload.get("role"))
    team_memory = payload.get("team_memory") if isinstance(payload.get("team_memory"), dict) else {}
    result = run_role_agent(role=role, provider=provider, model=model, team_memory=team_memory)
    return {
        "status": "complete",
        "phase": 16,
        "concept": "Dynamic Mission Design",
        "role": role,
        "hosted_agent_name": result.get("hosted_agent_name"),
        "result": result,
        "summary": result.get("summary"),
    }


def extract_text(request: Any, current_input: str) -> str:
    if current_input:
        return current_input
    return "Run your configured maze role and return JSON."


def run_server() -> None:
    from azure.ai.agentserver.responses import (
        CreateResponse,
        ResponseContext,
        ResponsesAgentServerHost,
        ResponsesServerOptions,
        TextResponse,
    )

    app = ResponsesAgentServerHost(
        options=ResponsesServerOptions(default_fetch_history_count=5),
    )

    @app.response_handler
    async def handler(
        request: CreateResponse,
        context: ResponseContext,
        _cancellation_signal: asyncio.Event,
    ):
        user_input = await context.get_input_text() or ""
        payload = {
            **parse_payload(extract_text(request, user_input)),
            "provider": os.environ.get("MAZE_PROVIDER", "foundry"),
            "model": os.environ.get("FOUNDRY_MODEL_DEPLOYMENT") or os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
            "role": os.environ.get("MAZE_HOSTED_ROLE", "analyst"),
        }
        result = await asyncio.get_running_loop().run_in_executor(None, lambda: invoke(payload))
        summary = result.get("summary") or {}
        response = {
            "status": result.get("status"),
            "phase": result.get("phase"),
            "concept": result.get("concept"),
            "role": result.get("role"),
            "hosted_agent_name": result.get("hosted_agent_name"),
            "result": result.get("result"),
            "llm_calls": summary.get("llm_calls"),
            "maze_tool_calls": summary.get("maze_tool_calls"),
            "note": "This hosted runtime executes exactly one role. The coordinator combines role outputs outside the role agent.",
        }
        return TextResponse(context, request, text=json.dumps(response, indent=2))

    app.run()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one split hosted role-agent package.")
    parser.add_argument("--once", action="store_true", help="Run once as a CLI command instead of starting the hosted-agent server.")
    parser.add_argument("--role", default=os.environ.get("MAZE_HOSTED_ROLE", "analyst"), choices=["analyst", "worker_a", "worker_b"])
    parser.add_argument("--provider", default=os.environ.get("MAZE_PROVIDER", "foundry"), choices=["test", "local", "foundry"])
    parser.add_argument("--model", default=os.environ.get("FOUNDRY_MODEL_DEPLOYMENT") or os.environ.get("MAZE_MODEL"))
    args = parser.parse_args()
    if not args.once:
        run_server()
        return 0
    result = invoke({"provider": args.provider, "model": args.model, "role": args.role})
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
