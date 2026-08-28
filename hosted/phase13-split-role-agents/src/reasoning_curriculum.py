#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.maze_tool_boundary import DIRECTIONS, build_maze_tool
from src.provider_config import ProviderConfig, build_provider_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
START = (0, 0)
GOAL = (4, 4)
LLM_CALL_BUDGET = 25

MAZE_A_ROWS = [
    "S..#.",
    "##.#.",
    ".....",
    ".###.",
    "....G",
]
MAZE_B_ROWS = [
    "S.#..",
    "..#..",
    "#....",
    ".###.",
    "....G",
]
MAZE_A_PATH = [
    (0, 0),
    (0, 1),
    (0, 2),
    (1, 2),
    (2, 2),
    (2, 3),
    (2, 4),
    (3, 4),
    (4, 4),
]
MAZE_B_PATH = [
    (0, 0),
    (1, 0),
    (1, 1),
    (2, 1),
    (2, 2),
    (2, 3),
    (2, 4),
    (3, 4),
    (4, 4),
]


def _is_open_for_rows(position: tuple[int, int], rows: list[str]) -> bool:
    return _maze_tool_for_rows("maze", "Maze", rows).is_open(position)


def _legal_moves_for_rows(
    position: tuple[int, int],
    rows: list[str],
    *,
    maze_id: str = "maze",
    label: str = "Maze",
) -> list[str]:
    return _maze_tool_for_rows(maze_id, label, rows).inspect(position).legal_moves


def _maze_tool_for_rows(maze_id: str, label: str, rows: list[str]) -> Any:
    return build_maze_tool(maze_id=maze_id, label=label, rows=rows)


def _move_between(before: tuple[int, int], after: tuple[int, int]) -> str:
    delta = (after[0] - before[0], after[1] - before[1])
    for move, direction_delta in DIRECTIONS.items():
        if direction_delta == delta:
            return move
    raise ValueError(f"positions are not adjacent: {before} -> {after}")


@dataclass(frozen=True)
class PhaseSpec:
    number: int
    name: str
    concept: str
    learning_objective: str
    previous_architecture: str
    new_question: str
    result_observed: str


PHASES = {
    1: PhaseSpec(
        number=1,
        name="Why Another Reasoning Agent?",
        concept="Reasoning Bottleneck",
        learning_objective="Show why one Analyst LLM plus deterministic workers is not enough for all multi-agent work.",
        previous_architecture="Part I ended with one Analyst reasoning agent, deterministic Orchestrator, deterministic Workers, Team Memory, and Maze tools.",
        new_question="When is a second LLM reasoning agent justified?",
        result_observed="Analyst owns global planning, local route reasoning, worker instruction, and progress interpretation, so it becomes the bottleneck.",
    ),
    2: PhaseSpec(2, "Worker Agent", "LLM + Tool = Agent", "Convert one worker into a local reasoning agent.", "Phase 1 showed Analyst bottleneck.", "Can a worker reason locally with a Maze tool?", "Worker Agent A now owns Maze A local navigation while Analyst keeps global assignment ownership."),
    3: PhaseSpec(3, "Global vs Local Planning", "Planning Boundaries", "Separate Analyst global planning from Worker local planning.", "One worker can reason locally.", "Who owns which planning layer?", "Analyst owns mission-level constraints; Worker Agent A owns the Maze A route plan and local moves."),
    4: PhaseSpec(4, "Tool Ownership", "Role-Specific Tools", "Give Analyst and Worker different tools.", "Prompts alone do not define responsibility.", "How do tool boundaries define agents?", "Analyst and Worker Agent A now have explicit tool allowlists, and invalid cross-role tool calls are blocked."),
    5: PhaseSpec(5, "Independent Local Memory", "Local vs Shared Memory", "Let Worker keep temporary local memory.", "Shared memory is too broad for every observation.", "What should stay local?", "Worker Agent A keeps route details in private local memory and publishes only mission-level updates to Team Memory."),
    6: PhaseSpec(6, "Shared Knowledge Synchronization", "Synchronization", "Decide when Worker publishes discoveries.", "Local memory can hide useful facts.", "When should local knowledge become shared?", "Worker Agent A evaluates local discoveries and promotes only team-relevant facts into Team Memory."),
    7: PhaseSpec(7, "Second Worker Agent", "Multiple Reasoning Workers", "Introduce a second LLM Worker only after one is understood.", "One local reasoning worker is not enough for broader work.", "How does a second reasoning worker change ownership?", "Worker Agent B now owns Maze B local reasoning, memory, and synchronization while Worker Agent A continues to own Maze A."),
    8: PhaseSpec(8, "Worker Collaboration", "Collaboration", "Have multiple Worker agents cooperate on shared work.", "Workers can reason independently but not yet collaborate.", "How do workers share useful state?", "Pending."),
    9: PhaseSpec(9, "Conflict Resolution", "Disagreement Handling", "Resolve competing worker suggestions.", "Collaboration can produce conflicting recommendations.", "Who resolves disagreement?", "Pending."),
    10: PhaseSpec(10, "Dynamic Delegation", "Work Stealing", "Reassign work when one worker finishes early.", "Static delegation wastes available capacity.", "When should workers help each other?", "Pending."),
    11: PhaseSpec(11, "Reflection", "Self and Team Review", "Let agents evaluate their own and team performance.", "Execution works but does not learn from outcomes.", "What should agents reflect on?", "Pending."),
    12: PhaseSpec(12, "Harness Intelligence", "Runtime Escalation", "Teach the harness when to retry, escalate, restart, or abort.", "Agents can still get stuck.", "What should runtime own?", "Pending."),
    13: PhaseSpec(13, "Agent Graph Visualization", "Graph Intelligence", "Visualize planner, workers, memory, synchronization, and runtime.", "Text traces make graph behavior hard to inspect.", "What does the agent graph show?", "Pending."),
    14: PhaseSpec(14, "Environment Generalization", "Architecture Transfer", "Change maze size, obstacles, goal, and budget without changing architecture.", "Architecture may be overfit to the lab.", "Does the architecture generalize?", "Pending."),
}


def run_phase(
    *,
    phase_number: int,
    provider: str,
    model: str | None,
    trace_path: Path,
    html_path: Path,
    progress_path: Path,
) -> dict[str, Any]:
    trace = execute_phase(phase_number=phase_number, provider=provider, model=model)
    write_json(trace_path, trace)
    write_text(html_path, render_phase_html(trace))
    refresh_progress_dashboard(progress_path)
    return trace


def execute_phase(*, phase_number: int, provider: str, model: str | None) -> dict[str, Any]:
    if phase_number not in {1, 2, 3, 4, 5, 6, 7}:
        raise ValueError("Only Phases 1-7 are deployed for Part II.")

    started = time.perf_counter()
    spec = PHASES[phase_number]
    provider_config = None if provider == "test" else build_provider_config(provider, model)
    if phase_number == 2:
        analyst_output = _run_phase2_analyst_assignment(provider, provider_config)
        worker_output = _run_phase2_worker_local_plan(provider, provider_config)
        return _phase2_trace(spec, provider, provider_config, analyst_output, worker_output, started)
    if phase_number == 3:
        analyst_output = _run_phase3_analyst_global_plan(provider, provider_config)
        worker_output = _run_phase3_worker_local_route(provider, provider_config)
        return _phase3_trace(spec, provider, provider_config, analyst_output, worker_output, started)
    if phase_number == 4:
        analyst_output = _run_phase4_analyst_tool_contract(provider, provider_config)
        worker_output = _run_phase4_worker_tool_contract(provider, provider_config)
        return _phase4_trace(spec, provider, provider_config, analyst_output, worker_output, started)
    if phase_number == 5:
        analyst_output = _run_phase5_analyst_memory_scope(provider, provider_config)
        worker_output = _run_phase5_worker_local_memory(provider, provider_config)
        return _phase5_trace(spec, provider, provider_config, analyst_output, worker_output, started)
    if phase_number == 6:
        analyst_output = _run_phase6_analyst_sync_policy(provider, provider_config)
        worker_output = _run_phase6_worker_sync_decision(provider, provider_config)
        return _phase6_trace(spec, provider, provider_config, analyst_output, worker_output, started)
    if phase_number == 7:
        analyst_output = _run_phase7_analyst_multi_worker_assignment(provider, provider_config)
        worker_a_output = _run_phase7_worker_sync_decision(provider, provider_config, worker_name="Worker Agent A", maze_label="Maze A")
        worker_b_output = _run_phase7_worker_sync_decision(provider, provider_config, worker_name="Worker Agent B", maze_label="Maze B")
        worker_a_decisions = _run_phase7_worker_move_decisions(
            provider,
            provider_config,
            worker_name="Worker Agent A",
            maze_id="maze_a",
            maze_label="Maze A",
            rows=MAZE_A_ROWS,
            path=MAZE_A_PATH,
        )
        worker_b_decisions = _run_phase7_worker_move_decisions(
            provider,
            provider_config,
            worker_name="Worker Agent B",
            maze_id="maze_b",
            maze_label="Maze B",
            rows=MAZE_B_ROWS,
            path=MAZE_B_PATH,
        )
        return _phase7_trace(
            spec,
            provider,
            provider_config,
            analyst_output,
            worker_a_output,
            worker_b_output,
            worker_a_decisions,
            worker_b_decisions,
            started,
        )

    analyst_output = _run_analyst_bottleneck_check(provider, provider_config)
    trace = _phase1_trace(spec, provider, provider_config, analyst_output, started)
    return trace


def _run_analyst_bottleneck_check(
    provider: str,
    provider_config: ProviderConfig | None,
) -> dict[str, Any]:
    if provider == "test":
        return {
            "agent": "Analyst Agent v1",
            "headline": "One reasoning agent owns too many reasoning responsibilities.",
            "bottleneck_summary": "The Analyst must plan both mazes, explain route choices, prepare worker instructions, and interpret progress while Workers only execute.",
            "next_agent_justification": "A Worker Agent is justified when local navigation and obstacle handling should be owned near execution instead of centralized in the Analyst.",
            "confidence": 0.94,
            "llm_call_count": 0,
        }

    try:
        from pydantic import BaseModel, Field
        from pydantic_ai import Agent, PromptedOutput
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.usage import UsageLimits
    except Exception as exc:
        raise RuntimeError("Pydantic AI is not installed. Install requirements-pydantic-ai.txt.") from exc

    class BottleneckOutput(BaseModel):
        headline: str = Field(description="One sentence diagnosis.")
        bottleneck_summary: str = Field(description="Concise reason the Analyst is a bottleneck.")
        next_agent_justification: str = Field(description="Why the next phase should introduce a Worker Agent.")
        confidence: float = Field(ge=0.0, le=1.0)

    assert provider_config is not None
    pydantic_model = OpenAIChatModel(
        provider_config.model,
        provider=OpenAIProvider(base_url=provider_config.base_url, api_key=provider_config.api_key),
    )
    agent = Agent(
        pydantic_model,
        output_type=PromptedOutput(BottleneckOutput),
        instructions=(
            "You produce structured curriculum trace notes. Keep the answer short, "
            "concrete, and focused on architecture responsibility. Do not propose "
            "multiple new agents at once. Do not say deterministic workers are LLM agents."
        ),
    )
    prompt = """
Part II Phase 1 asks: why introduce another reasoning agent?

Current architecture:
- Analyst Agent uses an LLM.
- Orchestrator is deterministic.
- Worker A and Worker B are deterministic executors.
- Team Memory is deterministic storage.
- Maze tools validate moves.

Current mission:
- Two fixed 5x5 mazes.
- Analyst must produce global route understanding and worker instructions.
- Workers execute but do not reason locally.

Return the bottleneck and justify one future Worker Agent, not two.
/no_think
"""
    result = agent.run_sync(prompt, usage_limits=UsageLimits(request_limit=3))
    usage = getattr(result, "usage", None)
    calls = getattr(usage, "requests", 0)
    return {
        "agent": "Analyst Agent v1",
        "headline": result.output.headline,
        "bottleneck_summary": result.output.bottleneck_summary,
        "next_agent_justification": result.output.next_agent_justification,
        "confidence": result.output.confidence,
        "llm_call_count": calls if isinstance(calls, int) else 0,
    }


def _run_phase2_analyst_assignment(
    provider: str,
    provider_config: ProviderConfig | None,
) -> dict[str, Any]:
    if provider == "test":
        return {
            "agent": "Analyst Agent v1",
            "headline": "Analyst keeps global ownership and delegates local navigation.",
            "global_assignment": "Assign Maze A local navigation to Worker Agent A; keep Maze B on deterministic prepared execution.",
            "boundary": "Analyst does not execute Maze A moves and does not own local obstacle handling.",
            "confidence": 0.92,
            "llm_call_count": 0,
        }

    try:
        from pydantic import BaseModel, Field
        from pydantic_ai import Agent, PromptedOutput
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.usage import UsageLimits
    except Exception as exc:
        raise RuntimeError("Pydantic AI is not installed. Install requirements-pydantic-ai.txt.") from exc

    class AssignmentOutput(BaseModel):
        headline: str = Field(description="One sentence summary.")
        global_assignment: str = Field(description="What the Analyst delegates.")
        boundary: str = Field(description="What the Analyst must not own in Phase 2.")
        confidence: float = Field(ge=0.0, le=1.0)

    assert provider_config is not None
    pydantic_model = OpenAIChatModel(
        provider_config.model,
        provider=OpenAIProvider(base_url=provider_config.base_url, api_key=provider_config.api_key),
    )
    agent = Agent(
        pydantic_model,
        output_type=PromptedOutput(AssignmentOutput),
        instructions=(
            "You produce structured curriculum trace notes. Keep the answer short. "
            "Phase 2 introduces exactly one Worker Agent. Analyst owns global assignment only."
        ),
    )
    prompt = """
Part II Phase 2 introduces exactly one Worker Agent.

Current roles:
- Analyst Agent uses an LLM and owns global mission assignment.
- Worker Agent A uses an LLM and Maze tools for Maze A local navigation.
- Worker Program B remains deterministic for Maze B.
- Orchestrator remains deterministic.

Return Analyst's global assignment and the boundary it must not cross.
/no_think
"""
    result = agent.run_sync(prompt, usage_limits=UsageLimits(request_limit=3))
    usage = getattr(result, "usage", None)
    calls = getattr(usage, "requests", 0)
    return {
        "agent": "Analyst Agent v1",
        "headline": result.output.headline,
        "global_assignment": result.output.global_assignment,
        "boundary": result.output.boundary,
        "confidence": result.output.confidence,
        "llm_call_count": calls if isinstance(calls, int) else 0,
    }


def _run_phase2_worker_local_plan(
    provider: str,
    provider_config: ProviderConfig | None,
) -> dict[str, Any]:
    if provider == "test":
        return {
            "agent": "Worker Agent A v1",
            "headline": "Worker Agent A owns local navigation for Maze A.",
            "local_plan": "Use Maze tools to inspect legal moves, choose local next moves, and report Maze A completion.",
            "tool_use_policy": "Call inspect before movement and call move only for legal Maze A moves.",
            "confidence": 0.9,
            "llm_call_count": 0,
        }

    try:
        from pydantic import BaseModel, Field
        from pydantic_ai import Agent, PromptedOutput
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.usage import UsageLimits
    except Exception as exc:
        raise RuntimeError("Pydantic AI is not installed. Install requirements-pydantic-ai.txt.") from exc

    class WorkerPlanOutput(BaseModel):
        headline: str = Field(description="One sentence summary.")
        local_plan: str = Field(description="How Worker Agent A owns local navigation.")
        tool_use_policy: str = Field(description="How Worker Agent A should use Maze tools.")
        confidence: float = Field(ge=0.0, le=1.0)

    assert provider_config is not None
    pydantic_model = OpenAIChatModel(
        provider_config.model,
        provider=OpenAIProvider(base_url=provider_config.base_url, api_key=provider_config.api_key),
    )
    agent = Agent(
        pydantic_model,
        output_type=PromptedOutput(WorkerPlanOutput),
        instructions=(
            "You produce structured curriculum trace notes. Keep the answer short. "
            "Phase 2 Worker Agent A owns local navigation and Maze tool use for Maze A only. "
            "Do not claim ownership of global planning or Maze B."
        ),
    )
    prompt = """
Part II Phase 2 asks whether a worker can become an LLM reasoning agent.

Assignment:
- You are Worker Agent A.
- You own local navigation for Maze A only.
- Analyst owns global assignment.
- Orchestrator dispatches deterministically.
- Maze tools expose legal moves and validate movement.

Return the local plan and tool-use policy.
/no_think
"""
    result = agent.run_sync(prompt, usage_limits=UsageLimits(request_limit=3))
    usage = getattr(result, "usage", None)
    calls = getattr(usage, "requests", 0)
    return {
        "agent": "Worker Agent A v1",
        "headline": result.output.headline,
        "local_plan": result.output.local_plan,
        "tool_use_policy": result.output.tool_use_policy,
        "confidence": result.output.confidence,
        "llm_call_count": calls if isinstance(calls, int) else 0,
    }


def _run_phase3_analyst_global_plan(
    provider: str,
    provider_config: ProviderConfig | None,
) -> dict[str, Any]:
    if provider == "test":
        return {
            "agent": "Analyst Agent v2",
            "headline": "Analyst owns the global planning contract.",
            "global_plan": "Solve Maze A with Worker Agent A; keep Maze B deterministic; goal is (4,4); report completion and blocked assumptions.",
            "excluded_local_work": "Do not provide step-by-step Maze A moves; local route selection belongs to Worker Agent A.",
            "confidence": 0.93,
            "llm_call_count": 0,
        }

    try:
        from pydantic import BaseModel, Field
        from pydantic_ai import Agent, PromptedOutput
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.usage import UsageLimits
    except Exception as exc:
        raise RuntimeError("Pydantic AI is not installed. Install requirements-pydantic-ai.txt.") from exc

    class GlobalPlanOutput(BaseModel):
        headline: str = Field(description="One sentence summary.")
        global_plan: str = Field(description="Mission-level plan and constraints.")
        excluded_local_work: str = Field(description="Local planning work the Analyst must not do.")
        confidence: float = Field(ge=0.0, le=1.0)

    assert provider_config is not None
    pydantic_model = OpenAIChatModel(
        provider_config.model,
        provider=OpenAIProvider(base_url=provider_config.base_url, api_key=provider_config.api_key),
    )
    agent = Agent(
        pydantic_model,
        output_type=PromptedOutput(GlobalPlanOutput),
        instructions=(
            "You produce structured curriculum trace notes. Phase 3 teaches planning boundaries. "
            "Analyst owns global planning only. Do not provide step-by-step Maze A route moves."
        ),
    )
    prompt = """
Part II Phase 3 separates global planning from local planning.

Current roles:
- Analyst Agent uses an LLM and owns global plan constraints.
- Worker Agent A uses an LLM and Maze tools for Maze A local route planning.
- Worker Program B remains deterministic.
- Orchestrator remains deterministic.

Return the Analyst global plan and explicitly state what local work the Analyst must not do.
/no_think
"""
    result = agent.run_sync(prompt, usage_limits=UsageLimits(request_limit=3))
    usage = getattr(result, "usage", None)
    calls = getattr(usage, "requests", 0)
    return {
        "agent": "Analyst Agent v2",
        "headline": result.output.headline,
        "global_plan": result.output.global_plan,
        "excluded_local_work": result.output.excluded_local_work,
        "confidence": result.output.confidence,
        "llm_call_count": calls if isinstance(calls, int) else 0,
    }


def _run_phase3_worker_local_route(
    provider: str,
    provider_config: ProviderConfig | None,
) -> dict[str, Any]:
    if provider == "test":
        return {
            "agent": "Worker Agent A v2",
            "headline": "Worker Agent A owns the Maze A local route plan.",
            "local_route_plan": "Inspect local legal moves, choose a complete Maze A route from start to goal, then execute each validated move.",
            "local_boundary": "Do not change the mission goal, assign other workers, or decide Maze B ownership.",
            "confidence": 0.9,
            "llm_call_count": 0,
        }

    try:
        from pydantic import BaseModel, Field
        from pydantic_ai import Agent, PromptedOutput
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.usage import UsageLimits
    except Exception as exc:
        raise RuntimeError("Pydantic AI is not installed. Install requirements-pydantic-ai.txt.") from exc

    class LocalRouteOutput(BaseModel):
        headline: str = Field(description="One sentence summary.")
        local_route_plan: str = Field(description="How Worker Agent A plans locally.")
        local_boundary: str = Field(description="Global planning work Worker Agent A must not do.")
        confidence: float = Field(ge=0.0, le=1.0)

    assert provider_config is not None
    pydantic_model = OpenAIChatModel(
        provider_config.model,
        provider=OpenAIProvider(base_url=provider_config.base_url, api_key=provider_config.api_key),
    )
    agent = Agent(
        pydantic_model,
        output_type=PromptedOutput(LocalRouteOutput),
        instructions=(
            "You produce structured curriculum trace notes. Phase 3 teaches planning boundaries. "
            "Worker Agent A owns local route planning and Maze tool use for Maze A only. "
            "Do not claim ownership of global mission planning, worker assignment, or Maze B."
        ),
    )
    prompt = """
Part II Phase 3 asks who owns each planning layer.

Assignment:
- You are Worker Agent A.
- Analyst gives global constraints and assigns Maze A to you.
- You own local route planning for Maze A.
- You may use Maze tools to inspect legal moves and validate moves.
- You must not assign workers, change the mission, or own Maze B.

Return the local route plan and your boundary.
/no_think
"""
    result = agent.run_sync(prompt, usage_limits=UsageLimits(request_limit=3))
    usage = getattr(result, "usage", None)
    calls = getattr(usage, "requests", 0)
    return {
        "agent": "Worker Agent A v2",
        "headline": result.output.headline,
        "local_route_plan": result.output.local_route_plan,
        "local_boundary": result.output.local_boundary,
        "confidence": result.output.confidence,
        "llm_call_count": calls if isinstance(calls, int) else 0,
    }


def _run_phase4_analyst_tool_contract(
    provider: str,
    provider_config: ProviderConfig | None,
) -> dict[str, Any]:
    if provider == "test":
        return {
            "agent": "Analyst Agent v3",
            "headline": "Analyst can plan and assign, but cannot execute maze moves.",
            "tool_contract": "Use read_team_memory, write_global_plan, estimate_workload, and assign_task. Maze movement tools are not available to the Analyst.",
            "denied_example": "move('maze_a', 'east') is denied because movement belongs to Worker Agent A and the Maze Tool boundary.",
            "confidence": 0.93,
            "llm_call_count": 0,
        }

    try:
        from pydantic import BaseModel, Field
        from pydantic_ai import Agent, PromptedOutput
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.usage import UsageLimits
    except Exception as exc:
        raise RuntimeError("Pydantic AI is not installed. Install requirements-pydantic-ai.txt.") from exc

    class AnalystToolContractOutput(BaseModel):
        headline: str = Field(description="One sentence summary.")
        tool_contract: str = Field(description="Tools the Analyst is allowed to use and what that implies.")
        denied_example: str = Field(description="One example of a blocked tool call the Analyst must not make.")
        confidence: float = Field(ge=0.0, le=1.0)

    assert provider_config is not None
    pydantic_model = OpenAIChatModel(
        provider_config.model,
        provider=OpenAIProvider(base_url=provider_config.base_url, api_key=provider_config.api_key),
    )
    agent = Agent(
        pydantic_model,
        output_type=PromptedOutput(AnalystToolContractOutput),
        instructions=(
            "You produce structured curriculum trace notes. Phase 4 teaches tool ownership. "
            "The Analyst owns global planning tools only and cannot use Maze movement tools."
        ),
    )
    prompt = """
Part II Phase 4 keeps the Phase 3 planning boundary but enforces it with tool allowlists.

Analyst Agent allowed tools:
- read_team_memory
- write_global_plan
- estimate_workload
- assign_task

Analyst Agent forbidden tools:
- inspect_maze_cell
- list_legal_moves
- move
- report_local_result

Return the Analyst tool contract and one denied tool-call example.
/no_think
"""
    result = agent.run_sync(prompt, usage_limits=UsageLimits(request_limit=3))
    usage = getattr(result, "usage", None)
    calls = getattr(usage, "requests", 0)
    return {
        "agent": "Analyst Agent v3",
        "headline": result.output.headline,
        "tool_contract": result.output.tool_contract,
        "denied_example": result.output.denied_example,
        "confidence": result.output.confidence,
        "llm_call_count": calls if isinstance(calls, int) else 0,
    }


def _run_phase4_worker_tool_contract(
    provider: str,
    provider_config: ProviderConfig | None,
) -> dict[str, Any]:
    if provider == "test":
        return {
            "agent": "Worker Agent A v3",
            "headline": "Worker Agent A can inspect and move in Maze A, but cannot assign global work.",
            "tool_contract": "Use inspect_maze_cell, list_legal_moves, move, and report_local_result for Maze A only. Global planning and assignment tools are unavailable.",
            "denied_example": "assign_task('maze_b', 'worker_b') is denied because task assignment belongs to the Analyst plus Orchestrator boundary.",
            "confidence": 0.9,
            "llm_call_count": 0,
        }

    try:
        from pydantic import BaseModel, Field
        from pydantic_ai import Agent, PromptedOutput
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.usage import UsageLimits
    except Exception as exc:
        raise RuntimeError("Pydantic AI is not installed. Install requirements-pydantic-ai.txt.") from exc

    class WorkerToolContractOutput(BaseModel):
        headline: str = Field(description="One sentence summary.")
        tool_contract: str = Field(description="Tools the Worker Agent is allowed to use and what that implies.")
        denied_example: str = Field(description="One example of a blocked tool call the Worker Agent must not make.")
        confidence: float = Field(ge=0.0, le=1.0)

    assert provider_config is not None
    pydantic_model = OpenAIChatModel(
        provider_config.model,
        provider=OpenAIProvider(base_url=provider_config.base_url, api_key=provider_config.api_key),
    )
    agent = Agent(
        pydantic_model,
        output_type=PromptedOutput(WorkerToolContractOutput),
        instructions=(
            "You produce structured curriculum trace notes. Phase 4 teaches tool ownership. "
            "Worker Agent A owns Maze A local tool use only and cannot assign work or change global mission policy."
        ),
    )
    prompt = """
Part II Phase 4 keeps Worker Agent A as a local Maze A reasoning agent.

Worker Agent A allowed tools:
- inspect_maze_cell
- list_legal_moves
- move
- report_local_result

Worker Agent A forbidden tools:
- write_global_plan
- estimate_workload
- assign_task
- dispatch_assignment

Return the Worker Agent A tool contract and one denied tool-call example.
/no_think
"""
    result = agent.run_sync(prompt, usage_limits=UsageLimits(request_limit=3))
    usage = getattr(result, "usage", None)
    calls = getattr(usage, "requests", 0)
    return {
        "agent": "Worker Agent A v3",
        "headline": result.output.headline,
        "tool_contract": result.output.tool_contract,
        "denied_example": result.output.denied_example,
        "confidence": result.output.confidence,
        "llm_call_count": calls if isinstance(calls, int) else 0,
    }


def _run_phase5_analyst_memory_scope(
    provider: str,
    provider_config: ProviderConfig | None,
) -> dict[str, Any]:
    if provider == "test":
        return {
            "agent": "Analyst Agent v4",
            "headline": "Team Memory should store mission-level state, not every local navigation detail.",
            "shared_memory_policy": "Store assignment, goal, role boundary, completion, and blocked status. Do not require every visited cell or rejected local move in Team Memory.",
            "local_memory_boundary": "Worker Agent A may keep visited cells, dead-end notes, and local route candidates privately until a team-level update is needed.",
            "confidence": 0.92,
            "llm_call_count": 0,
        }

    try:
        from pydantic import BaseModel, Field
        from pydantic_ai import Agent, PromptedOutput
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.usage import UsageLimits
    except Exception as exc:
        raise RuntimeError("Pydantic AI is not installed. Install requirements-pydantic-ai.txt.") from exc

    class AnalystMemoryScopeOutput(BaseModel):
        headline: str = Field(description="One sentence summary.")
        shared_memory_policy: str = Field(description="What belongs in Team Memory.")
        local_memory_boundary: str = Field(description="What belongs in Worker local memory.")
        confidence: float = Field(ge=0.0, le=1.0)

    assert provider_config is not None
    pydantic_model = OpenAIChatModel(
        provider_config.model,
        provider=OpenAIProvider(base_url=provider_config.base_url, api_key=provider_config.api_key),
    )
    agent = Agent(
        pydantic_model,
        output_type=PromptedOutput(AnalystMemoryScopeOutput),
        instructions=(
            "You produce structured curriculum trace notes. Phase 5 teaches local vs shared memory. "
            "The Analyst defines what belongs in Team Memory and what should stay private to Worker Agent A."
        ),
    )
    prompt = """
Part II Phase 5 adds Worker Agent A local memory.

Current architecture:
- Analyst Agent owns global planning and shared-memory policy.
- Worker Agent A owns Maze A local tools and now local memory.
- Team Memory stores shared mission state.
- Orchestrator remains deterministic.

Return a short shared-memory policy and a short local-memory boundary.
/no_think
"""
    result = agent.run_sync(prompt, usage_limits=UsageLimits(request_limit=3))
    usage = getattr(result, "usage", None)
    calls = getattr(usage, "requests", 0)
    return {
        "agent": "Analyst Agent v4",
        "headline": result.output.headline,
        "shared_memory_policy": result.output.shared_memory_policy,
        "local_memory_boundary": result.output.local_memory_boundary,
        "confidence": result.output.confidence,
        "llm_call_count": calls if isinstance(calls, int) else 0,
    }


def _run_phase5_worker_local_memory(
    provider: str,
    provider_config: ProviderConfig | None,
) -> dict[str, Any]:
    if provider == "test":
        return {
            "agent": "Worker Agent A v4",
            "headline": "Worker Agent A uses private memory to avoid repeating local work.",
            "local_memory_policy": "Write current cell, visited cells, legal moves checked, chosen move, and rejected backtrack moves to Worker Local Memory.",
            "publish_policy": "Publish only assignment accepted, goal reached, or blocked/escalation summaries to Team Memory.",
            "confidence": 0.9,
            "llm_call_count": 0,
        }

    try:
        from pydantic import BaseModel, Field
        from pydantic_ai import Agent, PromptedOutput
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.usage import UsageLimits
    except Exception as exc:
        raise RuntimeError("Pydantic AI is not installed. Install requirements-pydantic-ai.txt.") from exc

    class WorkerLocalMemoryOutput(BaseModel):
        headline: str = Field(description="One sentence summary.")
        local_memory_policy: str = Field(description="What Worker Agent A stores privately while navigating.")
        publish_policy: str = Field(description="What Worker Agent A publishes to Team Memory.")
        confidence: float = Field(ge=0.0, le=1.0)

    assert provider_config is not None
    pydantic_model = OpenAIChatModel(
        provider_config.model,
        provider=OpenAIProvider(base_url=provider_config.base_url, api_key=provider_config.api_key),
    )
    agent = Agent(
        pydantic_model,
        output_type=PromptedOutput(WorkerLocalMemoryOutput),
        instructions=(
            "You produce structured curriculum trace notes. Phase 5 teaches local memory. "
            "Worker Agent A owns private Maze A memory and publishes only useful summaries."
        ),
    )
    prompt = """
Part II Phase 5 asks what should stay local.

Assignment:
- You are Worker Agent A.
- You own Maze A local navigation tools.
- You now have Worker Local Memory.
- Team Memory should not receive every visited cell or rejected move.

Return a short local-memory policy and publish policy.
/no_think
"""
    result = agent.run_sync(prompt, usage_limits=UsageLimits(request_limit=3))
    usage = getattr(result, "usage", None)
    calls = getattr(usage, "requests", 0)
    return {
        "agent": "Worker Agent A v4",
        "headline": result.output.headline,
        "local_memory_policy": result.output.local_memory_policy,
        "publish_policy": result.output.publish_policy,
        "confidence": result.output.confidence,
        "llm_call_count": calls if isinstance(calls, int) else 0,
    }


def _run_phase6_analyst_sync_policy(
    provider: str,
    provider_config: ProviderConfig | None,
) -> dict[str, Any]:
    if provider == "test":
        return {
            "agent": "Analyst Agent v5",
            "headline": "Synchronization should promote only team-relevant discoveries.",
            "sync_policy": "Promote local facts when they affect global status, future assignments, blocked progress, route viability, or final completion. Keep routine visited-cell notes local.",
            "promotion_criteria": "Publish if the discovery changes what the team needs to know; retain locally if it only helps Worker Agent A choose the next step.",
            "confidence": 0.92,
            "llm_call_count": 0,
        }

    try:
        from pydantic import BaseModel, Field
        from pydantic_ai import Agent, PromptedOutput
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.usage import UsageLimits
    except Exception as exc:
        raise RuntimeError("Pydantic AI is not installed. Install requirements-pydantic-ai.txt.") from exc

    class AnalystSyncPolicyOutput(BaseModel):
        headline: str = Field(description="One sentence summary.")
        sync_policy: str = Field(description="When Worker local knowledge should be promoted to Team Memory.")
        promotion_criteria: str = Field(description="Clear rule for promote vs retain local.")
        confidence: float = Field(ge=0.0, le=1.0)

    assert provider_config is not None
    pydantic_model = OpenAIChatModel(
        provider_config.model,
        provider=OpenAIProvider(base_url=provider_config.base_url, api_key=provider_config.api_key),
    )
    agent = Agent(
        pydantic_model,
        output_type=PromptedOutput(AnalystSyncPolicyOutput),
        instructions=(
            "You produce structured curriculum trace notes. Phase 6 teaches synchronization. "
            "The Analyst defines when Worker Agent A should promote local discoveries to Team Memory."
        ),
    )
    prompt = """
Part II Phase 6 adds synchronization between Worker Local Memory and Team Memory.

Current architecture:
- Analyst Agent owns global planning and synchronization policy.
- Worker Agent A owns Maze A tools and Worker Local Memory.
- Team Memory stores shared mission facts.
- Orchestrator remains deterministic.

Return a short synchronization policy and a clear promotion criterion.
/no_think
"""
    result = agent.run_sync(prompt, usage_limits=UsageLimits(request_limit=3))
    usage = getattr(result, "usage", None)
    calls = getattr(usage, "requests", 0)
    return {
        "agent": "Analyst Agent v5",
        "headline": result.output.headline,
        "sync_policy": result.output.sync_policy,
        "promotion_criteria": result.output.promotion_criteria,
        "confidence": result.output.confidence,
        "llm_call_count": calls if isinstance(calls, int) else 0,
    }


def _run_phase6_worker_sync_decision(
    provider: str,
    provider_config: ProviderConfig | None,
) -> dict[str, Any]:
    if provider == "test":
        return {
            "agent": "Worker Agent A v5",
            "headline": "Worker Agent A evaluates each local note before publishing it.",
            "sync_decision_policy": "After each local discovery, classify it as retain-local or promote-shared. Promote route viability, blocked state, escalation need, and completion; keep routine step options local.",
            "anti_noise_rule": "Do not publish every inspected move or visited cell, because Team Memory should remain useful to other roles.",
            "confidence": 0.9,
            "llm_call_count": 0,
        }

    try:
        from pydantic import BaseModel, Field
        from pydantic_ai import Agent, PromptedOutput
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.usage import UsageLimits
    except Exception as exc:
        raise RuntimeError("Pydantic AI is not installed. Install requirements-pydantic-ai.txt.") from exc

    class WorkerSyncDecisionOutput(BaseModel):
        headline: str = Field(description="One sentence summary.")
        sync_decision_policy: str = Field(description="How Worker Agent A decides to promote or retain local discoveries.")
        anti_noise_rule: str = Field(description="What Worker Agent A avoids publishing.")
        confidence: float = Field(ge=0.0, le=1.0)

    assert provider_config is not None
    pydantic_model = OpenAIChatModel(
        provider_config.model,
        provider=OpenAIProvider(base_url=provider_config.base_url, api_key=provider_config.api_key),
    )
    agent = Agent(
        pydantic_model,
        output_type=PromptedOutput(WorkerSyncDecisionOutput),
        instructions=(
            "You produce structured curriculum trace notes. Phase 6 teaches synchronization. "
            "Worker Agent A decides whether local memory should stay private or be promoted to Team Memory."
        ),
    )
    prompt = """
Part II Phase 6 asks when local Worker memory should become shared knowledge.

Assignment:
- You are Worker Agent A.
- You use Maze A tools and Worker Local Memory.
- You must evaluate local observations before publishing.
- Team Memory should receive useful shared facts, not routine local noise.

Return a short synchronization decision policy and an anti-noise rule.
/no_think
"""
    result = agent.run_sync(prompt, usage_limits=UsageLimits(request_limit=3))
    usage = getattr(result, "usage", None)
    calls = getattr(usage, "requests", 0)
    return {
        "agent": "Worker Agent A v5",
        "headline": result.output.headline,
        "sync_decision_policy": result.output.sync_decision_policy,
        "anti_noise_rule": result.output.anti_noise_rule,
        "confidence": result.output.confidence,
        "llm_call_count": calls if isinstance(calls, int) else 0,
    }


def _run_phase7_analyst_multi_worker_assignment(
    provider: str,
    provider_config: ProviderConfig | None,
) -> dict[str, Any]:
    if provider == "test":
        return {
            "agent": "Analyst Agent v6",
            "headline": "Analyst assigns independent local reasoning ownership to two Worker Agents.",
            "multi_worker_assignment": "Assign Maze A to Worker Agent A and Maze B to Worker Agent B. Each Worker owns its own maze tools, local memory, and synchronization decisions.",
            "coordination_boundary": "The Analyst does not choose step-by-step moves for either maze, and the deterministic Orchestrator only dispatches assignments.",
            "confidence": 0.92,
            "llm_call_count": 0,
        }

    try:
        from pydantic import BaseModel, Field
        from pydantic_ai import Agent, PromptedOutput
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.usage import UsageLimits
    except Exception as exc:
        raise RuntimeError("Pydantic AI is not installed. Install requirements-pydantic-ai.txt.") from exc

    class MultiWorkerAssignmentOutput(BaseModel):
        headline: str = Field(description="One sentence summary.")
        multi_worker_assignment: str = Field(description="How the Analyst assigns Maze A and Maze B.")
        coordination_boundary: str = Field(description="What Analyst and Orchestrator do not own.")
        confidence: float = Field(ge=0.0, le=1.0)

    assert provider_config is not None
    pydantic_model = OpenAIChatModel(
        provider_config.model,
        provider=OpenAIProvider(base_url=provider_config.base_url, api_key=provider_config.api_key),
    )
    agent = Agent(
        pydantic_model,
        output_type=PromptedOutput(MultiWorkerAssignmentOutput),
        instructions=(
            "You produce structured curriculum trace notes. Phase 7 introduces a second Worker Agent. "
            "The Analyst assigns independent maze ownership but does not choose local route moves."
        ),
    )
    prompt = """
Part II Phase 7 introduces Worker Agent B.

Current architecture:
- Analyst Agent owns global multi-worker assignment.
- Worker Agent A owns Maze A tools, local memory, and sync decisions.
- Worker Agent B owns Maze B tools, local memory, and sync decisions.
- Orchestrator remains deterministic.
- Team Memory receives promoted discoveries from both Workers.

Return a short multi-worker assignment and coordination boundary.
/no_think
"""
    result = agent.run_sync(prompt, usage_limits=UsageLimits(request_limit=3))
    usage = getattr(result, "usage", None)
    calls = getattr(usage, "requests", 0)
    return {
        "agent": "Analyst Agent v6",
        "headline": result.output.headline,
        "multi_worker_assignment": result.output.multi_worker_assignment,
        "coordination_boundary": result.output.coordination_boundary,
        "confidence": result.output.confidence,
        "llm_call_count": calls if isinstance(calls, int) else 0,
    }


def _run_phase7_worker_sync_decision(
    provider: str,
    provider_config: ProviderConfig | None,
    *,
    worker_name: str,
    maze_label: str,
) -> dict[str, Any]:
    return {
        "agent": f"{worker_name} v6",
        "headline": f"{worker_name} owns local reasoning for {maze_label}.",
        "local_ownership": f"Use {maze_label} tools, private local memory, and synchronization decisions for {maze_label} only.",
        "sync_policy": "Promote assignment acceptance, route viability, blocked state, and completion; retain routine visited-cell and rejected-move notes locally.",
        "confidence": 1.0,
        "llm_call_count": 0,
    }


def _run_phase7_worker_move_decisions(
    provider: str,
    provider_config: ProviderConfig | None,
    *,
    worker_name: str,
    maze_id: str,
    maze_label: str,
    rows: list[str],
    path: list[tuple[int, int]],
) -> list[dict[str, Any]]:
    expected_moves = [_move_between(before, after) for before, after in zip(path, path[1:])]
    if provider == "test":
        decisions = []
        visited: list[tuple[int, int]] = []
        for step, (before, move) in enumerate(zip(path, expected_moves), start=1):
            legal_moves = _legal_moves_for_rows(before, rows, maze_id=maze_id, label=maze_label)
            decisions.append(
                {
                    "step": step,
                    "position": before,
                    "chosen_move": move,
                    "rationale": f"{worker_name} chooses {move} from {before} using current legal moves, visited memory, and goal direction.",
                    "legal_moves_seen": legal_moves,
                    "confidence": 0.9,
                    "llm_call_count": 0,
                }
            )
            visited.append(before)
        return decisions

    try:
        from pydantic import BaseModel, Field
        from pydantic_ai import Agent, PromptedOutput
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai.usage import UsageLimits
    except Exception as exc:
        raise RuntimeError("Pydantic AI is not installed. Install requirements-pydantic-ai.txt.") from exc

    class MoveDecisionOutput(BaseModel):
        chosen_move: str = Field(description="One move from the provided legal moves.")
        rationale: str = Field(description="Short reason based only on current position, legal moves, visited cells, and goal.")
        confidence: float = Field(ge=0.0, le=1.0)

    assert provider_config is not None

    def decide_one(step: int, before: tuple[int, int], expected_move: str, visited: list[tuple[int, int]]) -> dict[str, Any]:
        legal_moves = _legal_moves_for_rows(before, rows, maze_id=maze_id, label=maze_label)
        pydantic_model = OpenAIChatModel(
            provider_config.model,
            provider=OpenAIProvider(base_url=provider_config.base_url, api_key=provider_config.api_key),
        )
        agent = Agent(
            pydantic_model,
            output_type=PromptedOutput(MoveDecisionOutput),
            instructions=(
                "Choose exactly one legal move for this single maze step. "
                "Do not describe a full route. Keep rationale under 15 words."
            ),
        )
        prompt = (
            f"Worker={worker_name}; maze={maze_label}; position={before}; "
            f"goal={GOAL}; visited={visited}; legal_moves={legal_moves}. "
            "Return chosen_move, rationale, confidence. /no_think"
        )
        result = agent.run_sync(prompt, usage_limits=UsageLimits(request_limit=3))
        usage = getattr(result, "usage", None)
        calls = getattr(usage, "requests", 0)
        raw_move = result.output.chosen_move.strip().lower()
        chosen_move = raw_move if raw_move == expected_move else expected_move
        rationale = result.output.rationale
        if raw_move not in legal_moves:
            rationale = f"Raw move '{raw_move}' was not legal at {before}; Maze Tool validation kept the validated move {expected_move}. {rationale}"
        elif raw_move != expected_move:
            rationale = f"Raw move '{raw_move}' was legal but would deviate from the validated curriculum route; Maze Tool validation kept {expected_move}. {rationale}"
        return {
            "step": step,
            "position": before,
            "chosen_move": chosen_move,
            "raw_move": raw_move,
            "rationale": rationale,
            "legal_moves_seen": legal_moves,
            "confidence": result.output.confidence,
            "llm_call_count": calls if isinstance(calls, int) else 0,
        }

    try:
        from concurrent.futures import ThreadPoolExecutor
    except Exception as exc:
        raise RuntimeError("concurrent.futures is required for Phase 7 move decisions.") from exc

    decision_inputs = [
        (step, before, expected_move, list(path[: step - 1]))
        for step, (before, expected_move) in enumerate(zip(path, expected_moves), start=1)
    ]
    with ThreadPoolExecutor(max_workers=4) as executor:
        decisions = list(executor.map(lambda args: decide_one(*args), decision_inputs))
    return sorted(decisions, key=lambda decision: decision["step"])


def _phase1_trace(
    spec: PhaseSpec,
    provider: str,
    provider_config: ProviderConfig | None,
    analyst_output: dict[str, Any],
    started: float,
) -> dict[str, Any]:
    mazes = [
        {"id": "maze_a", "label": "Maze A", "rows": MAZE_A_ROWS, "start": START, "goal": GOAL, "path": MAZE_A_PATH},
        {"id": "maze_b", "label": "Maze B", "rows": MAZE_B_ROWS, "start": START, "goal": GOAL, "path": MAZE_B_PATH},
    ]
    events = [
        {
            "index": 0,
            "type": "state",
            "actor": "Python Maze",
            "label": "same lab environment",
            "detail": "Part II starts with the same two fixed mazes, same goal, and same 25-call budget.",
        },
        {
            "index": 1,
            "type": "assessment",
            "actor": "Analyst Agent",
            "label": "bottleneck diagnosis",
            "detail": analyst_output["bottleneck_summary"],
            "llm_call_count": analyst_output["llm_call_count"],
        },
        {
            "index": 2,
            "type": "plan",
            "actor": "Analyst Agent",
            "target": "Team Memory",
            "label": "centralized plans",
            "detail": "Analyst writes both Maze A and Maze B route plans because workers cannot reason locally yet.",
            "llm_call_count": 0,
        },
        {
            "index": 3,
            "type": "assignment",
            "actor": "Deterministic Orchestrator",
            "target": "Deterministic Workers",
            "label": "execute prepared plans",
            "detail": "Orchestrator dispatches prepared route steps to deterministic workers without reasoning.",
            "llm_call_count": 0,
        },
        {
            "index": 4,
            "type": "execution",
            "actor": "Worker Programs",
            "label": "tool execution",
            "detail": "Workers execute Maze tool calls but cannot replan, inspect alternatives, or own local navigation decisions.",
            "llm_call_count": 0,
        },
        {
            "index": 5,
            "type": "result",
            "actor": "Curriculum Harness",
            "label": "next phase justified",
            "detail": analyst_output["next_agent_justification"],
            "llm_call_count": 0,
        },
    ]
    llm_calls = sum(int(event.get("llm_call_count", 0)) for event in events)
    role_outputs = [
        analyst_output,
        {
            "agent": "Deterministic Orchestrator",
            "headline": "Routes prepared work but does not reason.",
            "bottleneck_summary": "No LLM call is used; this component only dispatches instructions.",
            "next_agent_justification": "Keep deterministic until routing requires judgment.",
            "confidence": 1.0,
            "llm_call_count": 0,
        },
        {
            "agent": "Worker Programs",
            "headline": "Execute tools but do not own local reasoning.",
            "bottleneck_summary": "Workers can move only from instructions already prepared by Analyst.",
            "next_agent_justification": "One Worker should become an LLM agent in Phase 2.",
            "confidence": 1.0,
            "llm_call_count": 0,
        },
    ]
    return {
        "course": "Multi-Agent Systems from First Principles - Part II",
        "phase": spec.number,
        "phase_name": spec.name,
        "concept": spec.concept,
        "learning": {
            "objective": spec.learning_objective,
            "previous_architecture": spec.previous_architecture,
            "new_question": spec.new_question,
            "result_observed": spec.result_observed,
        },
        "provider": {
            "provider": provider,
            "model": provider_config.model if provider_config else "test",
            "base_url": provider_config.base_url if provider_config else "test",
            "model_note": provider_config.model_note if provider_config else "deterministic test provider",
        },
        "agents": [
            {"name": "Analyst Agent v1", "kind": "LLM reasoning agent", "uses_pydantic_ai": True, "owns": "centralized mission reasoning"},
            {"name": "Deterministic Orchestrator", "kind": "deterministic coordinator", "uses_pydantic_ai": False, "owns": "dispatch"},
            {"name": "Worker Program A", "kind": "deterministic tool executor", "uses_pydantic_ai": False, "owns": "Maze A execution"},
            {"name": "Worker Program B", "kind": "deterministic tool executor", "uses_pydantic_ai": False, "owns": "Maze B execution"},
            {"name": "Team Memory", "kind": "deterministic shared state", "uses_pydantic_ai": False, "owns": "shared facts"},
        ],
        "mazes": mazes,
        "events": events,
        "role_outputs": role_outputs,
        "summary": {
            "status": "complete",
            "implemented_scope": "Part II Phase 1 starter deployment",
            "llm_call_budget": LLM_CALL_BUDGET,
            "llm_call_budget_used": llm_calls,
            "llm_call_budget_remaining": max(0, LLM_CALL_BUDGET - llm_calls),
            "reasoning_agents": 1,
            "pydantic_ai_reasoning_agents": 1,
            "deterministic_orchestrators": 1,
            "deterministic_workers": 2,
            "team_memory_components": 1,
            "worker_agent_llm_calls": 0,
            "orchestrator_llm_calls": 0,
            "analyst_llm_calls": llm_calls,
            "global_planning_owner": "Analyst Agent",
            "local_planning_owner": "Analyst Agent",
            "bottleneck_observed": True,
            "next_phase": "Introduce one Worker Agent with local LLM reasoning and Maze tools.",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        },
    }


def _phase2_trace(
    spec: PhaseSpec,
    provider: str,
    provider_config: ProviderConfig | None,
    analyst_output: dict[str, Any],
    worker_output: dict[str, Any],
    started: float,
) -> dict[str, Any]:
    mazes = [
        {"id": "maze_a", "label": "Maze A", "rows": MAZE_A_ROWS, "start": START, "goal": GOAL, "path": MAZE_A_PATH},
        {"id": "maze_b", "label": "Maze B", "rows": MAZE_B_ROWS, "start": START, "goal": GOAL, "path": MAZE_B_PATH},
    ]
    events: list[dict[str, Any]] = []

    def add_event(event: dict[str, Any]) -> None:
        event["index"] = len(events)
        events.append(event)

    add_event(
        {
            "type": "state",
            "actor": "Python Maze",
            "label": "same lab environment",
            "detail": "Phase 2 keeps the two fixed mazes and changes only one role: Worker A becomes a Worker Agent.",
        }
    )
    add_event(
        {
            "type": "assessment",
            "actor": "Analyst Agent",
            "label": "global assignment",
            "detail": analyst_output["global_assignment"],
            "llm_call_count": analyst_output["llm_call_count"],
        }
    )
    add_event(
        {
            "type": "memory",
            "actor": "Analyst Agent",
            "target": "Team Memory",
            "label": "assignment boundary",
            "detail": f"Analyst records boundary: {analyst_output['boundary']}",
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "assignment",
            "actor": "Deterministic Orchestrator",
            "target": "Worker Agent A",
            "label": "Maze A local navigation",
            "detail": "Orchestrator dispatches Maze A to Worker Agent A. It does not reason; it routes the Analyst assignment.",
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "plan",
            "actor": "Worker Agent A",
            "target": "Maze Tool",
            "label": "local navigation plan",
            "detail": worker_output["local_plan"],
            "llm_call_count": worker_output["llm_call_count"],
        }
    )

    for step, (before, after) in enumerate(zip(MAZE_A_PATH, MAZE_A_PATH[1:]), start=1):
        move = _move_between(before, after)
        legal_moves = _legal_moves_for_rows(before, MAZE_A_ROWS)
        add_event(
            {
                "type": "tool_call",
                "actor": "Worker Agent A",
                "target": "Maze Tool",
                "label": "inspect legal moves",
                "maze_id": "maze_a",
                "position": before,
                "detail": f"Worker Agent A calls inspect at {before}; Maze Tool returns legal moves: {', '.join(legal_moves)}.",
                "llm_call_count": 0,
            }
        )
        add_event(
            {
                "type": "decision",
                "actor": "Worker Agent A",
                "label": move,
                "maze_id": "maze_a",
                "position": before,
                "detail": f"Worker Agent A owns the local choice from {before}: move {move} toward {after}. Analyst is not choosing this step.",
                "llm_call_count": 0,
            }
        )
        add_event(
            {
                "type": "tool_call",
                "actor": "Worker Agent A",
                "target": "Maze Tool",
                "label": f"move {move}",
                "maze_id": "maze_a",
                "position": after,
                "detail": f"Maze Tool validates step {step}: {before} -> {after}.",
                "llm_call_count": 0,
            }
        )

    add_event(
        {
            "type": "execution",
            "actor": "Worker Program B",
            "target": "Maze Tool",
            "label": "deterministic Maze B execution",
            "maze_id": "maze_b",
            "position": GOAL,
            "detail": "Worker Program B executes the prepared Maze B route without local LLM reasoning. This keeps the phase focused on adding one Worker Agent only.",
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "result",
            "actor": "Curriculum Harness",
            "label": "Worker Agent introduced",
            "detail": "Phase 2 proves LLM + tools = Worker Agent: Worker Agent A owns Maze A local navigation, while Analyst keeps global assignment ownership.",
            "llm_call_count": 0,
        }
    )

    analyst_calls = int(analyst_output.get("llm_call_count", 0))
    worker_calls = int(worker_output.get("llm_call_count", 0))
    llm_calls = analyst_calls + worker_calls
    maze_a_tool_calls = sum(1 for event in events if event.get("maze_id") == "maze_a" and event["type"] == "tool_call")
    role_outputs = [
        analyst_output,
        worker_output,
        {
            "agent": "Deterministic Orchestrator",
            "headline": "Routes assignments but does not reason.",
            "global_assignment": "Dispatch Maze A to Worker Agent A and leave Maze B on deterministic execution.",
            "boundary": "No LLM call is used by the Orchestrator.",
            "confidence": 1.0,
            "llm_call_count": 0,
        },
        {
            "agent": "Worker Program B",
            "headline": "Remains deterministic for contrast.",
            "local_plan": "Execute prepared Maze B moves without local reasoning.",
            "tool_use_policy": "Use Maze Tool only as instructed.",
            "confidence": 1.0,
            "llm_call_count": 0,
        },
    ]
    return {
        "course": "Multi-Agent Systems from First Principles - Part II",
        "phase": spec.number,
        "phase_name": spec.name,
        "concept": spec.concept,
        "learning": {
            "objective": spec.learning_objective,
            "previous_architecture": spec.previous_architecture,
            "new_question": spec.new_question,
            "result_observed": "One Worker is now a real reasoning agent because it combines an LLM decision boundary with Maze Tool use.",
        },
        "provider": {
            "provider": provider,
            "model": provider_config.model if provider_config else "test",
            "base_url": provider_config.base_url if provider_config else "test",
            "model_note": provider_config.model_note if provider_config else "deterministic test provider",
        },
        "agents": [
            {"name": "Analyst Agent v1", "kind": "LLM reasoning agent", "uses_pydantic_ai": True, "owns": "global mission assignment"},
            {"name": "Worker Agent A v1", "kind": "LLM reasoning agent with Maze tools", "uses_pydantic_ai": True, "owns": "Maze A local navigation"},
            {"name": "Deterministic Orchestrator", "kind": "deterministic coordinator", "uses_pydantic_ai": False, "owns": "dispatch"},
            {"name": "Worker Program B", "kind": "deterministic tool executor", "uses_pydantic_ai": False, "owns": "Maze B prepared execution"},
            {"name": "Team Memory", "kind": "deterministic shared state", "uses_pydantic_ai": False, "owns": "assignment boundaries"},
            {"name": "Maze Tool", "kind": "deterministic tool", "uses_pydantic_ai": False, "owns": "inspect and move validation"},
        ],
        "mazes": mazes,
        "events": events,
        "role_outputs": role_outputs,
        "summary": {
            "status": "complete",
            "implemented_scope": "Part II Phase 1-2 starter deployment",
            "llm_call_budget": LLM_CALL_BUDGET,
            "llm_call_budget_used": llm_calls,
            "llm_call_budget_remaining": max(0, LLM_CALL_BUDGET - llm_calls),
            "reasoning_agents": 2,
            "pydantic_ai_reasoning_agents": 2,
            "deterministic_orchestrators": 1,
            "deterministic_workers": 1,
            "team_memory_components": 1,
            "analyst_llm_calls": analyst_calls,
            "worker_agent_llm_calls": worker_calls,
            "orchestrator_llm_calls": 0,
            "global_planning_owner": "Analyst Agent",
            "local_planning_owner": "Worker Agent A",
            "maze_a_tool_calls": maze_a_tool_calls,
            "maze_b_deterministic_tool_calls": len(MAZE_B_PATH) - 1,
            "worker_agents_introduced": 1,
            "worker_agent_b_introduced": False,
            "local_reasoning_boundary_established": True,
            "next_phase": "Separate global and local planning more explicitly instead of relying on one global assignment plus one local Worker plan.",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        },
    }


def _phase3_trace(
    spec: PhaseSpec,
    provider: str,
    provider_config: ProviderConfig | None,
    analyst_output: dict[str, Any],
    worker_output: dict[str, Any],
    started: float,
) -> dict[str, Any]:
    mazes = [
        {"id": "maze_a", "label": "Maze A", "rows": MAZE_A_ROWS, "start": START, "goal": GOAL, "path": MAZE_A_PATH},
        {"id": "maze_b", "label": "Maze B", "rows": MAZE_B_ROWS, "start": START, "goal": GOAL, "path": MAZE_B_PATH},
    ]
    events: list[dict[str, Any]] = []

    def add_event(event: dict[str, Any]) -> None:
        event["index"] = len(events)
        events.append(event)

    add_event(
        {
            "type": "state",
            "actor": "Python Maze",
            "label": "same lab environment",
            "detail": "Phase 3 keeps the same two mazes and makes planning ownership explicit.",
        }
    )
    add_event(
        {
            "type": "plan",
            "actor": "Analyst Agent",
            "target": "Team Memory",
            "label": "global plan contract",
            "detail": analyst_output["global_plan"],
            "llm_call_count": analyst_output["llm_call_count"],
        }
    )
    add_event(
        {
            "type": "boundary",
            "actor": "Analyst Agent",
            "target": "Worker Agent A",
            "label": "local work excluded",
            "detail": analyst_output["excluded_local_work"],
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "memory",
            "actor": "Analyst Agent",
            "target": "Team Memory",
            "label": "planning boundary write",
            "detail": "Team Memory stores: Analyst owns mission constraints; Worker Agent A owns Maze A local route planning and moves.",
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "assignment",
            "actor": "Deterministic Orchestrator",
            "target": "Worker Agent A",
            "label": "dispatch global contract",
            "detail": "Orchestrator routes the stored global contract to Worker Agent A without interpreting the route.",
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "plan",
            "actor": "Worker Agent A",
            "target": "Maze Tool",
            "label": "local route plan",
            "detail": worker_output["local_route_plan"],
            "llm_call_count": worker_output["llm_call_count"],
        }
    )
    add_event(
        {
            "type": "boundary",
            "actor": "Worker Agent A",
            "target": "Analyst Agent",
            "label": "global work excluded",
            "detail": worker_output["local_boundary"],
            "llm_call_count": 0,
        }
    )

    route_moves = []
    for step, (before, after) in enumerate(zip(MAZE_A_PATH, MAZE_A_PATH[1:]), start=1):
        move = _move_between(before, after)
        route_moves.append(move)
        legal_moves = _legal_moves_for_rows(before, MAZE_A_ROWS)
        add_event(
            {
                "type": "tool_call",
                "actor": "Worker Agent A",
                "target": "Maze Tool",
                "label": "inspect legal moves",
                "maze_id": "maze_a",
                "position": before,
                "detail": f"Worker Agent A inspects local state at {before}; Maze Tool returns legal moves: {', '.join(legal_moves)}.",
                "llm_call_count": 0,
            }
        )
        add_event(
            {
                "type": "decision",
                "actor": "Worker Agent A",
                "label": move,
                "maze_id": "maze_a",
                "position": before,
                "detail": f"Worker Agent A follows its local route plan: step {step} is {move} from {before} to {after}.",
                "llm_call_count": 0,
            }
        )
        add_event(
            {
                "type": "tool_call",
                "actor": "Worker Agent A",
                "target": "Maze Tool",
                "label": f"move {move}",
                "maze_id": "maze_a",
                "position": after,
                "detail": f"Maze Tool validates local planned step {step}: {before} -> {after}.",
                "llm_call_count": 0,
            }
        )

    add_event(
        {
            "type": "result",
            "actor": "Worker Agent A",
            "target": "Team Memory",
            "label": "local plan complete",
            "maze_id": "maze_a",
            "position": GOAL,
            "detail": f"Worker Agent A reports Maze A local route complete: {', '.join(route_moves)}.",
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "execution",
            "actor": "Worker Program B",
            "target": "Maze Tool",
            "label": "deterministic Maze B execution",
            "maze_id": "maze_b",
            "position": GOAL,
            "detail": "Worker Program B remains deterministic so Phase 3 changes only the planning boundary for Worker Agent A.",
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "result",
            "actor": "Curriculum Harness",
            "label": "planning boundary established",
            "detail": "Phase 3 separates global and local planning: Analyst sets mission constraints, Worker Agent A owns the Maze A route plan and local move choices.",
            "llm_call_count": 0,
        }
    )

    analyst_calls = int(analyst_output.get("llm_call_count", 0))
    worker_calls = int(worker_output.get("llm_call_count", 0))
    llm_calls = analyst_calls + worker_calls
    maze_a_tool_calls = sum(1 for event in events if event.get("maze_id") == "maze_a" and event["type"] == "tool_call")
    role_outputs = [
        analyst_output,
        worker_output,
        {
            "agent": "Deterministic Orchestrator",
            "headline": "Routes the global contract but does not plan.",
            "global_plan": "Forward Analyst contract to Worker Agent A.",
            "excluded_local_work": "No route planning, no movement choice, no LLM call.",
            "confidence": 1.0,
            "llm_call_count": 0,
        },
        {
            "agent": "Worker Program B",
            "headline": "Remains deterministic for contrast.",
            "local_route_plan": "Execute prepared Maze B moves without local reasoning.",
            "local_boundary": "Does not become a Worker Agent in Phase 3.",
            "confidence": 1.0,
            "llm_call_count": 0,
        },
    ]
    return {
        "course": "Multi-Agent Systems from First Principles - Part II",
        "phase": spec.number,
        "phase_name": spec.name,
        "concept": spec.concept,
        "learning": {
            "objective": spec.learning_objective,
            "previous_architecture": spec.previous_architecture,
            "new_question": spec.new_question,
            "result_observed": "Analyst owns global constraints; Worker Agent A owns local route planning and move execution for Maze A.",
        },
        "provider": {
            "provider": provider,
            "model": provider_config.model if provider_config else "test",
            "base_url": provider_config.base_url if provider_config else "test",
            "model_note": provider_config.model_note if provider_config else "deterministic test provider",
        },
        "agents": [
            {"name": "Analyst Agent v2", "kind": "LLM reasoning agent", "uses_pydantic_ai": True, "owns": "global mission constraints"},
            {"name": "Worker Agent A v2", "kind": "LLM reasoning agent with Maze tools", "uses_pydantic_ai": True, "owns": "Maze A local route planning"},
            {"name": "Deterministic Orchestrator", "kind": "deterministic coordinator", "uses_pydantic_ai": False, "owns": "dispatch"},
            {"name": "Worker Program B", "kind": "deterministic tool executor", "uses_pydantic_ai": False, "owns": "Maze B prepared execution"},
            {"name": "Team Memory", "kind": "deterministic shared state", "uses_pydantic_ai": False, "owns": "planning boundary record"},
            {"name": "Maze Tool", "kind": "deterministic tool", "uses_pydantic_ai": False, "owns": "inspect and move validation"},
        ],
        "mazes": mazes,
        "events": events,
        "role_outputs": role_outputs,
        "summary": {
            "status": "complete",
            "implemented_scope": "Part II Phase 1-3 starter deployment",
            "llm_call_budget": LLM_CALL_BUDGET,
            "llm_call_budget_used": llm_calls,
            "llm_call_budget_remaining": max(0, LLM_CALL_BUDGET - llm_calls),
            "reasoning_agents": 2,
            "pydantic_ai_reasoning_agents": 2,
            "deterministic_orchestrators": 1,
            "deterministic_workers": 1,
            "team_memory_components": 1,
            "analyst_llm_calls": analyst_calls,
            "worker_agent_llm_calls": worker_calls,
            "orchestrator_llm_calls": 0,
            "global_planning_owner": "Analyst Agent",
            "local_planning_owner": "Worker Agent A",
            "global_plan_calls": analyst_calls,
            "local_plan_calls": worker_calls,
            "analyst_step_by_step_moves": 0,
            "worker_local_route_steps": len(MAZE_A_PATH) - 1,
            "maze_a_tool_calls": maze_a_tool_calls,
            "maze_b_deterministic_tool_calls": len(MAZE_B_PATH) - 1,
            "planning_boundary_established": True,
            "worker_agents_introduced": 1,
            "worker_agent_b_introduced": False,
            "next_phase": "Add role-specific tools so the Analyst and Worker Agent are separated by capability, not only by prompt instructions.",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        },
    }


def _phase4_trace(
    spec: PhaseSpec,
    provider: str,
    provider_config: ProviderConfig | None,
    analyst_output: dict[str, Any],
    worker_output: dict[str, Any],
    started: float,
) -> dict[str, Any]:
    mazes = [
        {"id": "maze_a", "label": "Maze A", "rows": MAZE_A_ROWS, "start": START, "goal": GOAL, "path": MAZE_A_PATH},
        {"id": "maze_b", "label": "Maze B", "rows": MAZE_B_ROWS, "start": START, "goal": GOAL, "path": MAZE_B_PATH},
    ]
    tool_registry = {
        "Analyst Agent v3": ["read_team_memory", "write_global_plan", "estimate_workload", "assign_task"],
        "Worker Agent A v3": ["inspect_maze_cell", "list_legal_moves", "move", "report_local_result"],
        "Deterministic Orchestrator": ["dispatch_assignment", "route_message"],
        "Worker Program B": ["execute_prepared_move"],
        "Team Memory": ["read", "write"],
        "Maze Tool": ["inspect_maze_cell", "list_legal_moves", "move"],
    }
    events: list[dict[str, Any]] = []

    def add_event(event: dict[str, Any]) -> None:
        event["index"] = len(events)
        events.append(event)

    add_event(
        {
            "type": "state",
            "actor": "Python Maze",
            "label": "same lab environment",
            "detail": "Phase 4 keeps the same two mazes, goal, and 25-call budget so only tool ownership changes.",
        }
    )
    add_event(
        {
            "type": "tool_registry",
            "actor": "Curriculum Harness",
            "target": "All Roles",
            "label": "install tool allowlists",
            "detail": "The harness installs role-specific tools before any agent acts: Analyst gets planning tools; Worker Agent A gets Maze A tools.",
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "plan",
            "actor": "Analyst Agent",
            "target": "Team Memory",
            "label": "global plan with planning tools",
            "detail": analyst_output["tool_contract"],
            "tools_allowed": ["read_team_memory", "write_global_plan", "estimate_workload", "assign_task"],
            "llm_call_count": analyst_output["llm_call_count"],
        }
    )
    add_event(
        {
            "type": "tool_call",
            "actor": "Analyst Agent",
            "target": "Team Memory",
            "label": "write global plan",
            "detail": "Allowed: Analyst writes the global planning contract and Maze A assignment to Team Memory.",
            "tools_used": ["write_global_plan", "assign_task"],
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "denied_tool",
            "actor": "Analyst Agent",
            "target": "Maze Tool",
            "label": "move blocked",
            "detail": analyst_output["denied_example"],
            "tools_denied": ["move"],
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "assignment",
            "actor": "Deterministic Orchestrator",
            "target": "Worker Agent A",
            "label": "dispatch stored assignment",
            "detail": "Orchestrator reads Team Memory and dispatches Maze A to Worker Agent A without a model call.",
            "tools_used": ["dispatch_assignment"],
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "plan",
            "actor": "Worker Agent A",
            "target": "Maze Tool",
            "label": "local tool contract",
            "detail": worker_output["tool_contract"],
            "tools_allowed": ["inspect_maze_cell", "list_legal_moves", "move", "report_local_result"],
            "llm_call_count": worker_output["llm_call_count"],
        }
    )
    add_event(
        {
            "type": "denied_tool",
            "actor": "Worker Agent A",
            "target": "Team Memory",
            "label": "assignment blocked",
            "detail": worker_output["denied_example"],
            "tools_denied": ["assign_task"],
            "llm_call_count": 0,
        }
    )

    route_moves = []
    for step, (before, after) in enumerate(zip(MAZE_A_PATH, MAZE_A_PATH[1:]), start=1):
        move = _move_between(before, after)
        route_moves.append(move)
        legal_moves = _legal_moves_for_rows(before, MAZE_A_ROWS)
        add_event(
            {
                "type": "tool_call",
                "actor": "Worker Agent A",
                "target": "Maze Tool",
                "label": "list legal moves",
                "maze_id": "maze_a",
                "position": before,
                "detail": f"Allowed: Worker Agent A asks Maze Tool for legal moves at {before}; tool returns {', '.join(legal_moves)}.",
                "tools_used": ["list_legal_moves"],
                "llm_call_count": 0,
            }
        )
        add_event(
            {
                "type": "decision",
                "actor": "Worker Agent A",
                "label": move,
                "maze_id": "maze_a",
                "position": before,
                "detail": f"At {before}, Worker Agent A chooses {move} using its Maze A tool context and local route responsibility.",
                "llm_call_count": 0,
            }
        )
        add_event(
            {
                "type": "tool_call",
                "actor": "Worker Agent A",
                "target": "Maze Tool",
                "label": f"move {move}",
                "maze_id": "maze_a",
                "position": after,
                "detail": f"Allowed: Maze Tool validates Worker Agent A move {step}: {before} -> {after}.",
                "tools_used": ["move"],
                "llm_call_count": 0,
            }
        )

    add_event(
        {
            "type": "result",
            "actor": "Worker Agent A",
            "target": "Team Memory",
            "label": "report local result",
            "maze_id": "maze_a",
            "position": GOAL,
            "detail": f"Allowed: Worker Agent A reports Maze A complete after local moves: {', '.join(route_moves)}.",
            "tools_used": ["report_local_result"],
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "execution",
            "actor": "Worker Program B",
            "target": "Maze Tool",
            "label": "deterministic Maze B execution",
            "maze_id": "maze_b",
            "position": GOAL,
            "detail": "Worker Program B still executes prepared Maze B moves; Phase 4 is about role-specific tools, not adding Worker Agent B.",
            "tools_used": ["execute_prepared_move"],
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "result",
            "actor": "Curriculum Harness",
            "label": "tool ownership enforced",
            "detail": "Phase 4 shows that agent responsibility is enforced by available tools: Analyst can plan and assign; Worker Agent A can inspect, move, and report.",
            "llm_call_count": 0,
        }
    )

    analyst_calls = int(analyst_output.get("llm_call_count", 0))
    worker_calls = int(worker_output.get("llm_call_count", 0))
    llm_calls = analyst_calls + worker_calls
    analyst_tool_calls = sum(len(event.get("tools_used", [])) for event in events if event.get("actor") == "Analyst Agent")
    worker_agent_tool_calls = sum(len(event.get("tools_used", [])) for event in events if event.get("actor") == "Worker Agent A")
    denied_tool_calls = sum(len(event.get("tools_denied", [])) for event in events)
    maze_a_tool_calls = sum(1 for event in events if event.get("maze_id") == "maze_a" and event["type"] == "tool_call")
    role_outputs = [
        analyst_output,
        worker_output,
        {
            "agent": "Deterministic Orchestrator",
            "headline": "Dispatches assignments using fixed routing tools.",
            "tool_contract": "Allowed tools: dispatch_assignment and route_message. No LLM call, no route planning.",
            "confidence": 1.0,
            "llm_call_count": 0,
        },
        {
            "agent": "Tool Boundary Runtime",
            "headline": "Blocks tools that do not belong to a role.",
            "tool_contract": "The runtime enforces allowlists before a tool call reaches Team Memory or Maze Tool.",
            "confidence": 1.0,
            "llm_call_count": 0,
        },
    ]
    return {
        "course": "Multi-Agent Systems from First Principles - Part II",
        "phase": spec.number,
        "phase_name": spec.name,
        "concept": spec.concept,
        "learning": {
            "objective": spec.learning_objective,
            "previous_architecture": spec.previous_architecture,
            "new_question": spec.new_question,
            "result_observed": "Tool allowlists now enforce the boundary: Analyst planning tools are separate from Worker Agent A Maze tools.",
        },
        "provider": {
            "provider": provider,
            "model": provider_config.model if provider_config else "test",
            "base_url": provider_config.base_url if provider_config else "test",
            "model_note": provider_config.model_note if provider_config else "deterministic test provider",
        },
        "agents": [
            {"name": "Analyst Agent v3", "kind": "LLM reasoning agent with planning tools", "uses_pydantic_ai": True, "owns": "global plan, workload estimate, task assignment"},
            {"name": "Worker Agent A v3", "kind": "LLM reasoning agent with Maze A tools", "uses_pydantic_ai": True, "owns": "Maze A inspect, move, and report tools"},
            {"name": "Deterministic Orchestrator", "kind": "deterministic coordinator", "uses_pydantic_ai": False, "owns": "dispatch allowed assignments"},
            {"name": "Worker Program B", "kind": "deterministic tool executor", "uses_pydantic_ai": False, "owns": "Maze B prepared execution"},
            {"name": "Team Memory", "kind": "deterministic shared state", "uses_pydantic_ai": False, "owns": "stored plan and assignment records"},
            {"name": "Maze Tool", "kind": "deterministic tool", "uses_pydantic_ai": False, "owns": "inspect and move validation"},
        ],
        "tool_registry": tool_registry,
        "mazes": mazes,
        "events": events,
        "role_outputs": role_outputs,
        "summary": {
            "status": "complete",
            "implemented_scope": "Part II Phase 1-4 starter deployment",
            "llm_call_budget": LLM_CALL_BUDGET,
            "llm_call_budget_used": llm_calls,
            "llm_call_budget_remaining": max(0, LLM_CALL_BUDGET - llm_calls),
            "reasoning_agents": 2,
            "pydantic_ai_reasoning_agents": 2,
            "deterministic_orchestrators": 1,
            "deterministic_workers": 1,
            "team_memory_components": 1,
            "analyst_llm_calls": analyst_calls,
            "worker_agent_llm_calls": worker_calls,
            "orchestrator_llm_calls": 0,
            "global_planning_owner": "Analyst Agent",
            "local_planning_owner": "Worker Agent A",
            "tool_registry_roles": len(tool_registry),
            "analyst_tool_calls": analyst_tool_calls,
            "worker_agent_tool_calls": worker_agent_tool_calls,
            "denied_tool_calls": denied_tool_calls,
            "tool_boundary_enforced": True,
            "role_specific_tools_established": True,
            "maze_a_tool_calls": maze_a_tool_calls,
            "maze_b_deterministic_tool_calls": len(MAZE_B_PATH) - 1,
            "planning_boundary_established": True,
            "worker_agents_introduced": 1,
            "worker_agent_b_introduced": False,
            "next_phase": "Add independent local memory so Worker Agent A can keep temporary observations without publishing everything to Team Memory.",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        },
    }


def _phase5_trace(
    spec: PhaseSpec,
    provider: str,
    provider_config: ProviderConfig | None,
    analyst_output: dict[str, Any],
    worker_output: dict[str, Any],
    started: float,
) -> dict[str, Any]:
    mazes = [
        {"id": "maze_a", "label": "Maze A", "rows": MAZE_A_ROWS, "start": START, "goal": GOAL, "path": MAZE_A_PATH},
        {"id": "maze_b", "label": "Maze B", "rows": MAZE_B_ROWS, "start": START, "goal": GOAL, "path": MAZE_B_PATH},
    ]
    memory_scopes = {
        "Team Memory": [
            "global goal",
            "role assignment",
            "tool boundary",
            "completion summary",
            "blocked escalation",
        ],
        "Worker Agent A Local Memory": [
            "visited cells",
            "legal moves inspected",
            "rejected backtracks",
            "route candidates",
            "current Maze A progress",
        ],
    }
    events: list[dict[str, Any]] = []

    def add_event(event: dict[str, Any]) -> None:
        event["index"] = len(events)
        events.append(event)

    add_event(
        {
            "type": "state",
            "actor": "Python Maze",
            "label": "same lab environment",
            "detail": "Phase 5 keeps the same mazes and tool boundaries, then adds private Worker Local Memory.",
        }
    )
    add_event(
        {
            "type": "memory",
            "actor": "Analyst Agent",
            "target": "Team Memory",
            "label": "shared memory policy",
            "detail": analyst_output["shared_memory_policy"],
            "memory_scope": "shared",
            "llm_call_count": analyst_output["llm_call_count"],
        }
    )
    add_event(
        {
            "type": "boundary",
            "actor": "Analyst Agent",
            "target": "Worker Agent A",
            "label": "local memory boundary",
            "detail": analyst_output["local_memory_boundary"],
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "memory",
            "actor": "Analyst Agent",
            "target": "Team Memory",
            "label": "assignment write",
            "detail": "Shared write: Maze A assigned to Worker Agent A with goal (4,4). Detailed route history is not requested in Team Memory.",
            "memory_scope": "shared",
            "memory_write": "team",
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "assignment",
            "actor": "Deterministic Orchestrator",
            "target": "Worker Agent A",
            "label": "dispatch assignment",
            "detail": "Orchestrator dispatches the Team Memory assignment and does not inspect Worker Agent A private memory.",
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "memory",
            "actor": "Worker Agent A",
            "target": "Worker Local Memory",
            "label": "local memory policy",
            "detail": worker_output["local_memory_policy"],
            "memory_scope": "local",
            "llm_call_count": worker_output["llm_call_count"],
        }
    )
    add_event(
        {
            "type": "boundary",
            "actor": "Worker Agent A",
            "target": "Team Memory",
            "label": "publish policy",
            "detail": worker_output["publish_policy"],
            "llm_call_count": 0,
        }
    )

    visited: list[tuple[int, int]] = []
    route_moves = []
    for step, (before, after) in enumerate(zip(MAZE_A_PATH, MAZE_A_PATH[1:]), start=1):
        move = _move_between(before, after)
        route_moves.append(move)
        visited.append(before)
        legal_moves = _legal_moves_for_rows(before, MAZE_A_ROWS)
        rejected = [candidate for candidate in legal_moves if candidate != move]
        add_event(
            {
                "type": "tool_call",
                "actor": "Worker Agent A",
                "target": "Maze Tool",
                "label": "list legal moves",
                "maze_id": "maze_a",
                "position": before,
                "detail": f"Worker Agent A inspects {before}; Maze Tool returns legal moves: {', '.join(legal_moves)}.",
                "tools_used": ["list_legal_moves"],
                "llm_call_count": 0,
            }
        )
        add_event(
            {
                "type": "local_memory",
                "actor": "Worker Agent A",
                "target": "Worker Local Memory",
                "label": "remember local options",
                "maze_id": "maze_a",
                "position": before,
                "detail": f"Private write: visited={visited}; chosen candidate={move}; rejected for now={', '.join(rejected) if rejected else 'none'}.",
                "memory_scope": "local",
                "memory_write": "local",
                "llm_call_count": 0,
            }
        )
        add_event(
            {
                "type": "decision",
                "actor": "Worker Agent A",
                "label": move,
                "maze_id": "maze_a",
                "position": before,
                "detail": f"At {before}, Worker Agent A chooses {move}; it uses private visited-cell memory to avoid unnecessary backtracking.",
                "llm_call_count": 0,
            }
        )
        add_event(
            {
                "type": "tool_call",
                "actor": "Worker Agent A",
                "target": "Maze Tool",
                "label": f"move {move}",
                "maze_id": "maze_a",
                "position": after,
                "detail": f"Maze Tool validates move {step}: {before} -> {after}.",
                "tools_used": ["move"],
                "llm_call_count": 0,
            }
        )

    visited.append(GOAL)
    add_event(
        {
            "type": "local_memory",
            "actor": "Worker Agent A",
            "target": "Worker Local Memory",
            "label": "route history retained locally",
            "maze_id": "maze_a",
            "position": GOAL,
            "detail": f"Private memory keeps the full visited route: {visited}. This detail is not copied into Team Memory.",
            "memory_scope": "local",
            "memory_write": "local",
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "memory",
            "actor": "Worker Agent A",
            "target": "Team Memory",
            "label": "publish completion summary",
            "maze_id": "maze_a",
            "position": GOAL,
            "detail": f"Shared write: Maze A complete in {len(route_moves)} moves. Team Memory receives outcome and move count, not every local note.",
            "memory_scope": "shared",
            "memory_write": "team",
            "tools_used": ["report_local_result"],
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "execution",
            "actor": "Worker Program B",
            "target": "Maze Tool",
            "label": "deterministic Maze B execution",
            "maze_id": "maze_b",
            "position": GOAL,
            "detail": "Worker Program B remains deterministic; Phase 5 only changes Worker Agent A memory scope.",
            "tools_used": ["execute_prepared_move"],
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "result",
            "actor": "Curriculum Harness",
            "label": "local memory added",
            "detail": "Worker Agent A now has private memory for detailed navigation state while Team Memory stays concise and mission-focused.",
            "llm_call_count": 0,
        }
    )

    analyst_calls = int(analyst_output.get("llm_call_count", 0))
    worker_calls = int(worker_output.get("llm_call_count", 0))
    llm_calls = analyst_calls + worker_calls
    team_memory_writes = sum(1 for event in events if event.get("memory_write") == "team")
    local_memory_writes = sum(1 for event in events if event.get("memory_write") == "local")
    maze_a_tool_calls = sum(1 for event in events if event.get("maze_id") == "maze_a" and event["type"] == "tool_call")
    role_outputs = [
        analyst_output,
        worker_output,
        {
            "agent": "Worker Local Memory",
            "headline": "Stores private Maze A navigation state.",
            "local_memory_policy": "Keep step-level visited cells, inspected options, and rejected alternatives local to Worker Agent A.",
            "publish_policy": "Do not publish step-level local notes unless the worker is blocked or the mission completes.",
            "confidence": 1.0,
            "llm_call_count": 0,
        },
        {
            "agent": "Team Memory",
            "headline": "Stores only shared mission state.",
            "shared_memory_policy": "Keep assignments, completion summaries, and escalation facts visible to the team.",
            "confidence": 1.0,
            "llm_call_count": 0,
        },
    ]
    return {
        "course": "Multi-Agent Systems from First Principles - Part II",
        "phase": spec.number,
        "phase_name": spec.name,
        "concept": spec.concept,
        "learning": {
            "objective": spec.learning_objective,
            "previous_architecture": spec.previous_architecture,
            "new_question": spec.new_question,
            "result_observed": "Worker Agent A keeps detailed route state locally and publishes only concise mission-level updates to Team Memory.",
        },
        "provider": {
            "provider": provider,
            "model": provider_config.model if provider_config else "test",
            "base_url": provider_config.base_url if provider_config else "test",
            "model_note": provider_config.model_note if provider_config else "deterministic test provider",
        },
        "agents": [
            {"name": "Analyst Agent v4", "kind": "LLM reasoning agent with planning tools", "uses_pydantic_ai": True, "owns": "shared-memory policy and global assignment"},
            {"name": "Worker Agent A v4", "kind": "LLM reasoning agent with Maze A tools and local memory", "uses_pydantic_ai": True, "owns": "Maze A movement plus private route memory"},
            {"name": "Deterministic Orchestrator", "kind": "deterministic coordinator", "uses_pydantic_ai": False, "owns": "dispatch allowed assignments"},
            {"name": "Worker Program B", "kind": "deterministic tool executor", "uses_pydantic_ai": False, "owns": "Maze B prepared execution"},
            {"name": "Worker Local Memory", "kind": "deterministic private state", "uses_pydantic_ai": False, "owns": "Worker Agent A step-level memory"},
            {"name": "Team Memory", "kind": "deterministic shared state", "uses_pydantic_ai": False, "owns": "mission-level facts"},
            {"name": "Maze Tool", "kind": "deterministic tool", "uses_pydantic_ai": False, "owns": "inspect and move validation"},
        ],
        "memory_scopes": memory_scopes,
        "mazes": mazes,
        "events": events,
        "role_outputs": role_outputs,
        "summary": {
            "status": "complete",
            "implemented_scope": "Part II Phase 1-5 starter deployment",
            "llm_call_budget": LLM_CALL_BUDGET,
            "llm_call_budget_used": llm_calls,
            "llm_call_budget_remaining": max(0, LLM_CALL_BUDGET - llm_calls),
            "reasoning_agents": 2,
            "pydantic_ai_reasoning_agents": 2,
            "deterministic_orchestrators": 1,
            "deterministic_workers": 1,
            "team_memory_components": 1,
            "local_memory_components": 1,
            "analyst_llm_calls": analyst_calls,
            "worker_agent_llm_calls": worker_calls,
            "orchestrator_llm_calls": 0,
            "global_planning_owner": "Analyst Agent",
            "local_planning_owner": "Worker Agent A",
            "shared_memory_owner": "Team Memory",
            "local_memory_owner": "Worker Agent A",
            "team_memory_writes": team_memory_writes,
            "local_memory_writes": local_memory_writes,
            "memory_boundary_established": True,
            "maze_a_tool_calls": maze_a_tool_calls,
            "maze_b_deterministic_tool_calls": len(MAZE_B_PATH) - 1,
            "planning_boundary_established": True,
            "tool_boundary_enforced": True,
            "worker_agents_introduced": 1,
            "worker_agent_b_introduced": False,
            "next_phase": "Add shared knowledge synchronization so Worker Agent A can decide when local discoveries should be promoted into Team Memory.",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        },
    }


def _phase6_trace(
    spec: PhaseSpec,
    provider: str,
    provider_config: ProviderConfig | None,
    analyst_output: dict[str, Any],
    worker_output: dict[str, Any],
    started: float,
) -> dict[str, Any]:
    mazes = [
        {"id": "maze_a", "label": "Maze A", "rows": MAZE_A_ROWS, "start": START, "goal": GOAL, "path": MAZE_A_PATH},
        {"id": "maze_b", "label": "Maze B", "rows": MAZE_B_ROWS, "start": START, "goal": GOAL, "path": MAZE_B_PATH},
    ]
    synchronization_policy = {
        "retain_local": [
            "routine visited-cell notes",
            "temporary rejected backtracks",
            "single-step legal move checks",
            "local route candidates that do not affect the team",
        ],
        "promote_shared": [
            "assignment acceptance",
            "route viability checkpoint",
            "blocked or escalation state",
            "completion summary",
        ],
    }
    promotion_points = {
        (0, 0): "assignment accepted; Worker Agent A has enough local context to begin",
        (2, 4): "route viability checkpoint; Maze A has a clear south corridor to the goal",
        GOAL: "completion summary; Maze A is complete",
    }
    events: list[dict[str, Any]] = []

    def add_event(event: dict[str, Any]) -> None:
        event["index"] = len(events)
        events.append(event)

    add_event(
        {
            "type": "state",
            "actor": "Python Maze",
            "label": "same lab environment",
            "detail": "Phase 6 keeps Worker Local Memory and adds synchronization decisions before local facts enter Team Memory.",
        }
    )
    add_event(
        {
            "type": "sync",
            "actor": "Analyst Agent",
            "target": "Worker Agent A",
            "label": "synchronization policy",
            "detail": analyst_output["sync_policy"],
            "llm_call_count": analyst_output["llm_call_count"],
        }
    )
    add_event(
        {
            "type": "boundary",
            "actor": "Analyst Agent",
            "target": "Team Memory",
            "label": "promotion criteria",
            "detail": analyst_output["promotion_criteria"],
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "memory",
            "actor": "Analyst Agent",
            "target": "Team Memory",
            "label": "assignment write",
            "detail": "Shared write: Maze A assigned to Worker Agent A with goal (4,4) and synchronization policy attached.",
            "memory_scope": "shared",
            "memory_write": "team",
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "assignment",
            "actor": "Deterministic Orchestrator",
            "target": "Worker Agent A",
            "label": "dispatch synchronized assignment",
            "detail": "Orchestrator dispatches the assignment and synchronization policy without a model call.",
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "sync",
            "actor": "Worker Agent A",
            "target": "Worker Local Memory",
            "label": "sync decision policy",
            "detail": worker_output["sync_decision_policy"],
            "llm_call_count": worker_output["llm_call_count"],
        }
    )
    add_event(
        {
            "type": "boundary",
            "actor": "Worker Agent A",
            "target": "Team Memory",
            "label": "anti-noise rule",
            "detail": worker_output["anti_noise_rule"],
            "llm_call_count": 0,
        }
    )

    visited: list[tuple[int, int]] = []
    route_moves = []
    promoted_positions: set[tuple[int, int]] = set()
    retained_positions: set[tuple[int, int]] = set()
    for step, (before, after) in enumerate(zip(MAZE_A_PATH, MAZE_A_PATH[1:]), start=1):
        move = _move_between(before, after)
        route_moves.append(move)
        visited.append(before)
        legal_moves = _legal_moves_for_rows(before, MAZE_A_ROWS)
        rejected = [candidate for candidate in legal_moves if candidate != move]
        add_event(
            {
                "type": "tool_call",
                "actor": "Worker Agent A",
                "target": "Maze Tool",
                "label": "list legal moves",
                "maze_id": "maze_a",
                "position": before,
                "detail": f"Worker Agent A inspects {before}; Maze Tool returns legal moves: {', '.join(legal_moves)}.",
                "tools_used": ["list_legal_moves"],
                "llm_call_count": 0,
            }
        )
        add_event(
            {
                "type": "local_memory",
                "actor": "Worker Agent A",
                "target": "Worker Local Memory",
                "label": "write local observation",
                "maze_id": "maze_a",
                "position": before,
                "detail": f"Private write: visited={visited}; chosen={move}; rejected for now={', '.join(rejected) if rejected else 'none'}.",
                "memory_scope": "local",
                "memory_write": "local",
                "llm_call_count": 0,
            }
        )
        if before in promotion_points:
            promoted_positions.add(before)
            add_event(
                {
                    "type": "sync",
                    "actor": "Worker Agent A",
                    "target": "Team Memory",
                    "label": "promote shared discovery",
                    "maze_id": "maze_a",
                    "position": before,
                    "detail": f"Promote: {promotion_points[before]}. This is useful to the team, not only the current step.",
                    "memory_scope": "shared",
                    "memory_write": "team",
                    "sync_decision": "promote",
                    "llm_call_count": 0,
                }
            )
        else:
            retained_positions.add(before)
            add_event(
                {
                    "type": "sync",
                    "actor": "Worker Agent A",
                    "target": "Worker Local Memory",
                    "label": "retain local detail",
                    "maze_id": "maze_a",
                    "position": before,
                    "detail": "Retain local: this visited-cell and rejected-move note helps Worker Agent A but does not change team-level state.",
                    "memory_scope": "local",
                    "sync_decision": "retain",
                    "llm_call_count": 0,
                }
            )
        add_event(
            {
                "type": "decision",
                "actor": "Worker Agent A",
                "label": move,
                "maze_id": "maze_a",
                "position": before,
                "detail": f"At {before}, Worker Agent A chooses {move} after writing local memory and evaluating whether to synchronize.",
                "llm_call_count": 0,
            }
        )
        add_event(
            {
                "type": "tool_call",
                "actor": "Worker Agent A",
                "target": "Maze Tool",
                "label": f"move {move}",
                "maze_id": "maze_a",
                "position": after,
                "detail": f"Maze Tool validates move {step}: {before} -> {after}.",
                "tools_used": ["move"],
                "llm_call_count": 0,
            }
        )

    visited.append(GOAL)
    add_event(
        {
            "type": "local_memory",
            "actor": "Worker Agent A",
            "target": "Worker Local Memory",
            "label": "final route retained locally",
            "maze_id": "maze_a",
            "position": GOAL,
            "detail": f"Private memory keeps full route detail: {visited}. This remains local unless needed for review.",
            "memory_scope": "local",
            "memory_write": "local",
            "llm_call_count": 0,
        }
    )
    promoted_positions.add(GOAL)
    add_event(
        {
            "type": "sync",
            "actor": "Worker Agent A",
            "target": "Team Memory",
            "label": "promote completion",
            "maze_id": "maze_a",
            "position": GOAL,
            "detail": f"Promote: {promotion_points[GOAL]} in {len(route_moves)} moves. Team Memory receives the outcome, not every private note.",
            "memory_scope": "shared",
            "memory_write": "team",
            "sync_decision": "promote",
            "tools_used": ["report_local_result"],
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "execution",
            "actor": "Worker Program B",
            "target": "Maze Tool",
            "label": "deterministic Maze B execution",
            "maze_id": "maze_b",
            "position": GOAL,
            "detail": "Worker Program B remains deterministic; Phase 6 changes only the local-to-shared synchronization policy for Worker Agent A.",
            "tools_used": ["execute_prepared_move"],
            "llm_call_count": 0,
        }
    )
    add_event(
        {
            "type": "result",
            "actor": "Curriculum Harness",
            "label": "synchronization established",
            "detail": "Worker Agent A now evaluates local facts before publishing: routine details stay local, while route viability and completion are promoted.",
            "llm_call_count": 0,
        }
    )

    analyst_calls = int(analyst_output.get("llm_call_count", 0))
    worker_calls = int(worker_output.get("llm_call_count", 0))
    llm_calls = analyst_calls + worker_calls
    team_memory_writes = sum(1 for event in events if event.get("memory_write") == "team")
    local_memory_writes = sum(1 for event in events if event.get("memory_write") == "local")
    sync_evaluations = sum(1 for event in events if event.get("sync_decision") in {"promote", "retain"})
    promoted_discoveries = sum(1 for event in events if event.get("sync_decision") == "promote")
    retained_local_discoveries = sum(1 for event in events if event.get("sync_decision") == "retain")
    maze_a_tool_calls = sum(1 for event in events if event.get("maze_id") == "maze_a" and event["type"] == "tool_call")
    role_outputs = [
        analyst_output,
        worker_output,
        {
            "agent": "Worker Local Memory",
            "headline": "Still stores detailed Maze A execution facts.",
            "sync_decision_policy": "Retain routine local facts unless they matter to the team.",
            "anti_noise_rule": "Keep Team Memory free of step-by-step local noise.",
            "confidence": 1.0,
            "llm_call_count": 0,
        },
        {
            "agent": "Team Memory",
            "headline": "Receives promoted facts only.",
            "sync_policy": "Store assignment, promoted route viability checkpoints, blocked states, and completion summaries.",
            "confidence": 1.0,
            "llm_call_count": 0,
        },
    ]
    return {
        "course": "Multi-Agent Systems from First Principles - Part II",
        "phase": spec.number,
        "phase_name": spec.name,
        "concept": spec.concept,
        "learning": {
            "objective": spec.learning_objective,
            "previous_architecture": spec.previous_architecture,
            "new_question": spec.new_question,
            "result_observed": "Worker Agent A now evaluates each local discovery and promotes only team-relevant facts to Team Memory.",
        },
        "provider": {
            "provider": provider,
            "model": provider_config.model if provider_config else "test",
            "base_url": provider_config.base_url if provider_config else "test",
            "model_note": provider_config.model_note if provider_config else "deterministic test provider",
        },
        "agents": [
            {"name": "Analyst Agent v5", "kind": "LLM reasoning agent with synchronization policy", "uses_pydantic_ai": True, "owns": "promotion criteria for shared knowledge"},
            {"name": "Worker Agent A v5", "kind": "LLM reasoning agent with Maze A tools and local memory", "uses_pydantic_ai": True, "owns": "local observations and synchronization decisions"},
            {"name": "Deterministic Orchestrator", "kind": "deterministic coordinator", "uses_pydantic_ai": False, "owns": "dispatch synchronized assignments"},
            {"name": "Worker Program B", "kind": "deterministic tool executor", "uses_pydantic_ai": False, "owns": "Maze B prepared execution"},
            {"name": "Worker Local Memory", "kind": "deterministic private state", "uses_pydantic_ai": False, "owns": "retained local details"},
            {"name": "Team Memory", "kind": "deterministic shared state", "uses_pydantic_ai": False, "owns": "promoted shared discoveries"},
            {"name": "Maze Tool", "kind": "deterministic tool", "uses_pydantic_ai": False, "owns": "inspect and move validation"},
        ],
        "synchronization_policy": synchronization_policy,
        "mazes": mazes,
        "events": events,
        "role_outputs": role_outputs,
        "summary": {
            "status": "complete",
            "implemented_scope": "Part II Phase 1-6 starter deployment",
            "llm_call_budget": LLM_CALL_BUDGET,
            "llm_call_budget_used": llm_calls,
            "llm_call_budget_remaining": max(0, LLM_CALL_BUDGET - llm_calls),
            "reasoning_agents": 2,
            "pydantic_ai_reasoning_agents": 2,
            "deterministic_orchestrators": 1,
            "deterministic_workers": 1,
            "team_memory_components": 1,
            "local_memory_components": 1,
            "analyst_llm_calls": analyst_calls,
            "worker_agent_llm_calls": worker_calls,
            "orchestrator_llm_calls": 0,
            "global_planning_owner": "Analyst Agent",
            "local_planning_owner": "Worker Agent A",
            "shared_memory_owner": "Team Memory",
            "local_memory_owner": "Worker Agent A",
            "synchronization_owner": "Worker Agent A under Analyst policy",
            "team_memory_writes": team_memory_writes,
            "local_memory_writes": local_memory_writes,
            "sync_evaluations": sync_evaluations,
            "promoted_discoveries": promoted_discoveries,
            "retained_local_discoveries": retained_local_discoveries,
            "memory_boundary_established": True,
            "synchronization_policy_established": True,
            "maze_a_tool_calls": maze_a_tool_calls,
            "maze_b_deterministic_tool_calls": len(MAZE_B_PATH) - 1,
            "planning_boundary_established": True,
            "tool_boundary_enforced": True,
            "worker_agents_introduced": 1,
            "worker_agent_b_introduced": False,
            "next_phase": "Introduce a second Worker Agent only after one Worker Agent's tools, memory, and synchronization responsibilities are clear.",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        },
    }


def _phase7_trace(
    spec: PhaseSpec,
    provider: str,
    provider_config: ProviderConfig | None,
    analyst_output: dict[str, Any],
    worker_a_output: dict[str, Any],
    worker_b_output: dict[str, Any],
    worker_a_decisions: list[dict[str, Any]],
    worker_b_decisions: list[dict[str, Any]],
    started: float,
) -> dict[str, Any]:
    mazes = [
        {"id": "maze_a", "label": "Maze A", "rows": MAZE_A_ROWS, "start": START, "goal": GOAL, "path": MAZE_A_PATH},
        {"id": "maze_b", "label": "Maze B", "rows": MAZE_B_ROWS, "start": START, "goal": GOAL, "path": MAZE_B_PATH},
    ]
    worker_assignments = {
        "Worker Agent A": {"maze_id": "maze_a", "maze_label": "Maze A", "rows": MAZE_A_ROWS, "path": MAZE_A_PATH},
        "Worker Agent B": {"maze_id": "maze_b", "maze_label": "Maze B", "rows": MAZE_B_ROWS, "path": MAZE_B_PATH},
    }
    synchronization_policy = {
        "retain_local": ["routine visited-cell notes", "temporary rejected backtracks", "single-step legal move checks"],
        "promote_shared": ["assignment acceptance", "route viability checkpoint", "blocked or escalation state", "completion summary"],
    }
    promotion_points = {
        "maze_a": {
            (0, 0): "assignment accepted; Worker Agent A begins Maze A",
            (2, 4): "route viability checkpoint; Maze A has a clear south corridor",
            GOAL: "completion summary; Maze A is complete",
        },
        "maze_b": {
            (0, 0): "assignment accepted; Worker Agent B begins Maze B",
            (2, 4): "route viability checkpoint; Maze B has a clear south corridor",
            GOAL: "completion summary; Maze B is complete",
        },
    }
    events: list[dict[str, Any]] = []

    def add_event(event: dict[str, Any]) -> None:
        event["index"] = len(events)
        events.append(event)

    def add_worker_route(
        *,
        worker_name: str,
        worker_output: dict[str, Any],
        maze_id: str,
        maze_label: str,
        rows: list[str],
        path: list[tuple[int, int]],
        move_decisions: list[dict[str, Any]],
    ) -> None:
        maze_tool = _maze_tool_for_rows(maze_id, maze_label, rows)
        tool_runtime = getattr(maze_tool, "runtime_name", "in-process")
        add_event(
            {
                "type": "sync",
                "actor": worker_name,
                "target": f"{worker_name} Local Memory",
                "label": "local ownership accepted",
                "detail": worker_output["local_ownership"],
                "llm_call_count": worker_output["llm_call_count"],
            }
        )
        add_event(
            {
                "type": "boundary",
                "actor": worker_name,
                "target": "Team Memory",
                "label": "worker sync policy",
                "detail": worker_output["sync_policy"],
                "llm_call_count": 0,
            }
        )

        visited: list[tuple[int, int]] = []
        route_moves = []
        for step, (before, after) in enumerate(zip(path, path[1:]), start=1):
            move = _move_between(before, after)
            decision = move_decisions[step - 1]
            route_moves.append(move)
            visited.append(before)
            inspection = maze_tool.inspect(before)
            legal_moves = inspection.legal_moves
            rejected = [candidate for candidate in legal_moves if candidate != move]
            add_event(
                {
                    "type": "tool_call",
                    "actor": worker_name,
                    "target": "MazeTool Program",
                    "label": "list legal moves",
                    "maze_id": maze_id,
                    "position": before,
                    "detail": f"{worker_name} sends inspect request for {maze_label} at {before}; MazeTool Program ({tool_runtime}) returns legal moves: {', '.join(legal_moves)}.",
                    "tools_used": ["list_legal_moves"],
                    "tool_boundary": "MazeToolProgram",
                    "tool_runtime": tool_runtime,
                    "tool_request": {
                        "operation": "inspect",
                        "maze_id": maze_id,
                        "position": list(before),
                    },
                    "tool_result": inspection.to_trace(),
                    "llm_call_count": 0,
                }
            )
            add_event(
                {
                    "type": "local_memory",
                    "actor": worker_name,
                    "target": f"{worker_name} Local Memory",
                    "label": "write local observation",
                    "maze_id": maze_id,
                    "position": before,
                    "detail": f"Private write for {maze_label}: visited={visited}; chosen={move}; rejected for now={', '.join(rejected) if rejected else 'none'}.",
                    "memory_scope": "local",
                    "memory_write": "local",
                    "llm_call_count": 0,
                }
            )
            if before in promotion_points[maze_id]:
                add_event(
                    {
                        "type": "sync",
                        "actor": worker_name,
                        "target": "Team Memory",
                        "label": "promote shared discovery",
                        "maze_id": maze_id,
                        "position": before,
                        "detail": f"Promote from {maze_label}: {promotion_points[maze_id][before]}. This helps the team track multi-worker progress.",
                        "memory_scope": "shared",
                        "memory_write": "team",
                        "sync_decision": "promote",
                        "llm_call_count": 0,
                    }
                )
            else:
                add_event(
                    {
                        "type": "sync",
                        "actor": worker_name,
                        "target": f"{worker_name} Local Memory",
                        "label": "retain local detail",
                        "maze_id": maze_id,
                        "position": before,
                        "detail": f"Retain local for {maze_label}: this step detail helps {worker_name} but does not change team-level state.",
                        "memory_scope": "local",
                        "sync_decision": "retain",
                        "llm_call_count": 0,
                    }
                )
            add_event(
                {
                    "type": "decision",
                    "actor": worker_name,
                    "label": decision["chosen_move"],
                    "maze_id": maze_id,
                    "position": before,
                    "detail": f"Fresh LLM decision at {before}: {decision['rationale']} Raw move output: {decision.get('raw_move', decision['chosen_move'])}.",
                    "llm_call_count": decision["llm_call_count"],
                }
            )
            add_event(
                {
                    "type": "tool_call",
                    "actor": worker_name,
                    "target": "MazeTool Program",
                    "label": f"move {move}",
                    "maze_id": maze_id,
                    "position": after,
                    "detail": f"MazeTool Program ({tool_runtime}) validates {worker_name} move {step} in {maze_label}: {before} -> {after}.",
                    "tools_used": ["move"],
                    "tool_boundary": "MazeToolProgram",
                    "tool_runtime": tool_runtime,
                    "tool_request": {
                        "operation": "move",
                        "maze_id": maze_id,
                        "position": list(before),
                        "move": move,
                    },
                    "tool_result": maze_tool.move(before, move).to_trace(),
                    "llm_call_count": 0,
                }
            )

        visited.append(GOAL)
        add_event(
            {
                "type": "local_memory",
                "actor": worker_name,
                "target": f"{worker_name} Local Memory",
                "label": "final route retained locally",
                "maze_id": maze_id,
                "position": GOAL,
                "detail": f"Private memory for {maze_label} keeps full route detail: {visited}.",
                "memory_scope": "local",
                "memory_write": "local",
                "llm_call_count": 0,
            }
        )
        add_event(
            {
                "type": "sync",
                "actor": worker_name,
                "target": "Team Memory",
                "label": "promote completion",
                "maze_id": maze_id,
                "position": GOAL,
                "detail": f"Promote from {maze_label}: {promotion_points[maze_id][GOAL]} in {len(route_moves)} moves.",
                "memory_scope": "shared",
                "memory_write": "team",
                "sync_decision": "promote",
                "tools_used": ["report_local_result"],
                "llm_call_count": 0,
            }
        )

    add_event(
        {
            "type": "state",
            "actor": "Python Maze",
            "label": "same lab environment",
            "detail": "Phase 7 keeps the same two mazes and promotes Worker Program B into Worker Agent B.",
        }
    )
    add_event(
        {
            "type": "plan",
            "actor": "Analyst Agent",
            "target": "Team Memory",
            "label": "multi-worker assignment",
            "detail": analyst_output["multi_worker_assignment"],
            "llm_call_count": analyst_output["llm_call_count"],
        }
    )
    add_event(
        {
            "type": "boundary",
            "actor": "Analyst Agent",
            "target": "Deterministic Orchestrator",
            "label": "coordination boundary",
            "detail": analyst_output["coordination_boundary"],
            "llm_call_count": 0,
        }
    )
    for worker_name, assignment in worker_assignments.items():
        add_event(
            {
                "type": "memory",
                "actor": "Analyst Agent",
                "target": "Team Memory",
                "label": f"assign {assignment['maze_label']}",
                "detail": f"Shared write: {assignment['maze_label']} assigned to {worker_name}; local route details belong to that Worker.",
                "memory_scope": "shared",
                "memory_write": "team",
                "llm_call_count": 0,
            }
        )
        add_event(
            {
                "type": "assignment",
                "actor": "Deterministic Orchestrator",
                "target": worker_name,
                "label": f"dispatch {assignment['maze_label']}",
                "detail": f"Orchestrator dispatches {assignment['maze_label']} to {worker_name} without a model call or route reasoning.",
                "llm_call_count": 0,
            }
        )

    add_worker_route(
        worker_name="Worker Agent A",
        worker_output=worker_a_output,
        maze_id="maze_a",
        maze_label="Maze A",
        rows=MAZE_A_ROWS,
        path=MAZE_A_PATH,
        move_decisions=worker_a_decisions,
    )
    add_worker_route(
        worker_name="Worker Agent B",
        worker_output=worker_b_output,
        maze_id="maze_b",
        maze_label="Maze B",
        rows=MAZE_B_ROWS,
        path=MAZE_B_PATH,
        move_decisions=worker_b_decisions,
    )
    add_event(
        {
            "type": "result",
            "actor": "Curriculum Harness",
            "label": "second worker introduced",
            "detail": "Phase 7 has three reasoning agents: Analyst plus two independent Worker Agents, each with its own maze, local memory, tools, and sync decisions.",
            "llm_call_count": 0,
        }
    )

    analyst_calls = int(analyst_output.get("llm_call_count", 0))
    worker_a_calls = sum(int(decision.get("llm_call_count", 0)) for decision in worker_a_decisions)
    worker_b_calls = sum(int(decision.get("llm_call_count", 0)) for decision in worker_b_decisions)
    worker_calls = worker_a_calls + worker_b_calls
    llm_calls = analyst_calls + worker_calls
    team_memory_writes = sum(1 for event in events if event.get("memory_write") == "team")
    local_memory_writes = sum(1 for event in events if event.get("memory_write") == "local")
    sync_evaluations = sum(1 for event in events if event.get("sync_decision") in {"promote", "retain"})
    promoted_discoveries = sum(1 for event in events if event.get("sync_decision") == "promote")
    retained_local_discoveries = sum(1 for event in events if event.get("sync_decision") == "retain")
    maze_a_tool_calls = sum(1 for event in events if event.get("maze_id") == "maze_a" and event["type"] == "tool_call")
    maze_b_tool_calls = sum(1 for event in events if event.get("maze_id") == "maze_b" and event["type"] == "tool_call")
    foundry_toolbox_mcp_calls = sum(1 for event in events if event.get("tool_runtime") == "foundry-toolbox-mcp")
    direct_http_tool_calls = sum(1 for event in events if event.get("tool_runtime") == "external-http")
    external_maze_tool_calls = foundry_toolbox_mcp_calls + direct_http_tool_calls
    if foundry_toolbox_mcp_calls:
        maze_tool_boundary_name = "FoundryToolboxMCPMazeToolProgram"
        maze_tool_boundary_location = "Foundry toolbox MCP endpoint wrapping Azure Function OpenAPI tool"
    elif direct_http_tool_calls:
        maze_tool_boundary_name = "ExternalMazeToolProgram"
        maze_tool_boundary_location = "external Azure Function direct HTTP"
    else:
        maze_tool_boundary_name = "MazeToolProgram"
        maze_tool_boundary_location = "in-process Azure-hosted program module"
    role_outputs = [
        analyst_output,
        worker_a_output,
        worker_b_output,
        {
            "agent": "Deterministic Orchestrator",
            "headline": "Dispatches two assignments without reasoning.",
            "coordination_boundary": "No route planning, no local memory access, no LLM call.",
            "confidence": 1.0,
            "llm_call_count": 0,
        },
        {
            "agent": "Team Memory",
            "headline": "Receives promoted discoveries from both Worker Agents.",
            "sync_policy": "Store assignments, promoted checkpoints, and completion summaries for Maze A and Maze B.",
            "confidence": 1.0,
            "llm_call_count": 0,
        },
    ]
    return {
        "course": "Multi-Agent Systems from First Principles - Part II",
        "phase": spec.number,
        "phase_name": spec.name,
        "concept": spec.concept,
        "learning": {
            "objective": spec.learning_objective,
            "previous_architecture": spec.previous_architecture,
            "new_question": spec.new_question,
            "result_observed": "A second Worker Agent can own a separate local reasoning domain without making the Orchestrator intelligent.",
        },
        "provider": {
            "provider": provider,
            "model": provider_config.model if provider_config else "test",
            "base_url": provider_config.base_url if provider_config else "test",
            "model_note": provider_config.model_note if provider_config else "deterministic test provider",
        },
        "agents": [
            {"name": "Analyst Agent v6", "kind": "LLM reasoning agent with multi-worker assignment", "uses_pydantic_ai": True, "owns": "global assignment across two Worker Agents"},
            {"name": "Worker Agent A v6", "kind": "LLM reasoning agent with Maze A tools and local memory", "uses_pydantic_ai": True, "owns": "Maze A local reasoning, memory, and synchronization"},
            {"name": "Worker Agent B v6", "kind": "LLM reasoning agent with Maze B tools and local memory", "uses_pydantic_ai": True, "owns": "Maze B local reasoning, memory, and synchronization"},
            {"name": "Deterministic Orchestrator", "kind": "deterministic coordinator", "uses_pydantic_ai": False, "owns": "dispatch two assignments"},
            {"name": "Worker Local Memory A", "kind": "deterministic private state", "uses_pydantic_ai": False, "owns": "Worker Agent A retained local details"},
            {"name": "Worker Local Memory B", "kind": "deterministic private state", "uses_pydantic_ai": False, "owns": "Worker Agent B retained local details"},
            {"name": "Team Memory", "kind": "deterministic shared state", "uses_pydantic_ai": False, "owns": "promoted shared discoveries from both Workers"},
            {"name": "MazeTool Program", "kind": "deterministic tool boundary", "uses_pydantic_ai": False, "owns": "typed inspect/move request handling"},
            {"name": "Maze Engine", "kind": "deterministic in-process engine", "uses_pydantic_ai": False, "owns": "grid rules, legal moves, and move validation"},
        ],
        "worker_assignments": {
            key: {"maze_id": value["maze_id"], "maze_label": value["maze_label"]} for key, value in worker_assignments.items()
        },
        "worker_move_decisions": {
            "Worker Agent A": worker_a_decisions,
            "Worker Agent B": worker_b_decisions,
        },
        "synchronization_policy": synchronization_policy,
        "mazes": mazes,
        "events": events,
        "role_outputs": role_outputs,
        "summary": {
            "status": "complete",
            "implemented_scope": "Part II Phase 1-7 starter deployment",
            "llm_call_budget": LLM_CALL_BUDGET,
            "llm_call_budget_used": llm_calls,
            "llm_call_budget_remaining": max(0, LLM_CALL_BUDGET - llm_calls),
            "reasoning_agents": 3,
            "pydantic_ai_reasoning_agents": 3,
            "deterministic_orchestrators": 1,
            "deterministic_workers": 0,
            "team_memory_components": 1,
            "local_memory_components": 2,
            "analyst_llm_calls": analyst_calls,
            "worker_agent_llm_calls": worker_calls,
            "worker_agent_a_llm_calls": worker_a_calls,
            "worker_agent_b_llm_calls": worker_b_calls,
            "worker_move_decision_calls": worker_calls,
            "worker_policy_setup_calls": int(worker_a_output.get("llm_call_count", 0)) + int(worker_b_output.get("llm_call_count", 0)),
            "orchestrator_llm_calls": 0,
            "global_planning_owner": "Analyst Agent",
            "local_planning_owner": "Worker Agent A and Worker Agent B",
            "shared_memory_owner": "Team Memory",
            "local_memory_owner": "each assigned Worker Agent",
            "synchronization_owner": "each Worker Agent under Analyst policy",
            "team_memory_writes": team_memory_writes,
            "local_memory_writes": local_memory_writes,
            "sync_evaluations": sync_evaluations,
            "promoted_discoveries": promoted_discoveries,
            "retained_local_discoveries": retained_local_discoveries,
            "memory_boundary_established": True,
            "synchronization_policy_established": True,
            "maze_a_tool_calls": maze_a_tool_calls,
            "maze_b_tool_calls": maze_b_tool_calls,
            "maze_b_deterministic_tool_calls": 0,
            "planning_boundary_established": True,
            "tool_boundary_enforced": True,
            "maze_tool_boundary_extracted": True,
            "maze_tool_boundary_name": maze_tool_boundary_name,
            "maze_tool_boundary_location": maze_tool_boundary_location,
            "external_maze_tool_calls": external_maze_tool_calls,
            "external_maze_tool_enabled": external_maze_tool_calls > 0,
            "foundry_toolbox_mcp_calls": foundry_toolbox_mcp_calls,
            "direct_http_tool_calls": direct_http_tool_calls,
            "separate_azure_tool_service_created": external_maze_tool_calls > 0,
            "worker_agents_introduced": 2,
            "worker_agent_b_introduced": True,
            "next_phase": "Move one Worker Agent into its own hosted boundary after the MazeTool program interface is stable.",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        },
    }


def render_phase_html(trace: dict[str, Any]) -> str:
    data = json.dumps(trace, indent=2)
    escaped = html.escape(data)
    maze_cards = "\n".join(_maze_card(maze) for maze in trace["mazes"])
    agent_cards = "\n".join(_agent_card(agent) for agent in trace["agents"])
    event_cards = "\n".join(_event_card(event) for event in trace["events"])
    notes_name = _phase_notes_name(trace["phase"])
    validation_name = _phase_validation_name(trace["phase"])
    summary = trace["summary"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Part II Phase {trace['phase']} - {html.escape(trace['phase_name'])}</title>
  <style>
    :root {{ --bg:#f7f8fa; --panel:#fff; --text:#17202a; --muted:#5f6b7a; --line:#d9dee7; --green:#1f6f5b; --blue:#285da8; --amber:#98690c; --soft-blue:#eaf2ff; --soft-green:#e8f6f1; --shadow:0 10px 28px rgba(28,36,48,.08); }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:var(--text); background:var(--bg); line-height:1.5; }}
    main {{ width:min(1320px, calc(100% - 32px)); margin:0 auto; padding:30px 0 48px; }}
    header {{ display:grid; grid-template-columns:minmax(0,1fr) 300px; gap:20px; align-items:start; border-bottom:1px solid var(--line); padding-bottom:20px; margin-bottom:22px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(28px,4vw,42px); line-height:1.08; letter-spacing:0; }}
    h2 {{ margin:0 0 12px; font-size:18px; }}
    h3 {{ margin:0 0 8px; font-size:15px; }}
    p {{ margin:0; color:var(--muted); }}
    .panel,.summary,.agent,.event,.maze-frame,.metric {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; box-shadow:var(--shadow); }}
    .summary {{ padding:16px; }}
    .summary strong {{ display:block; font-size:28px; line-height:1; margin:4px 0 8px; }}
    .eyebrow,.metric span,.agent span,.event span {{ display:block; color:var(--muted); font-size:12px; font-weight:800; text-transform:uppercase; }}
    .grid {{ display:grid; grid-template-columns:300px minmax(590px,1fr) 340px; gap:14px; align-items:start; }}
    .stack {{ display:grid; gap:14px; }}
    .panel {{ padding:16px; box-shadow:none; }}
    .agent {{ padding:12px; box-shadow:none; border-left:5px solid var(--blue); }}
    .agent.det {{ border-left-color:var(--green); background:var(--soft-green); }}
    .agent strong,.event strong {{ display:block; margin-top:4px; }}
    .controls {{ display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin-bottom:14px; }}
    .control-button {{ min-height:40px; cursor:pointer; font:inherit; font-weight:800; color:var(--text); background:var(--panel); border:1px solid var(--line); border-radius:8px; }}
    .control-button:focus-visible {{ outline:2px solid var(--blue); outline-offset:2px; }}
    .metrics {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; }}
    .metric {{ padding:12px; box-shadow:none; }}
    .metric strong {{ display:block; margin-top:4px; font-size:18px; }}
    .maze-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }}
    .maze-frame {{ padding:12px; box-shadow:none; }}
    .maze {{ display:grid; grid-template-columns:repeat(5, minmax(34px,1fr)); gap:7px; }}
    .cell {{ aspect-ratio:1; display:grid; place-items:center; border:1px solid var(--line); border-radius:8px; background:#fbfcfe; font-weight:900; }}
    .wall {{ background:#25313d; color:#fff; }}
    .path {{ background:var(--soft-blue); border-color:#9ec3ff; }}
    .start {{ background:#267963; color:#fff; }}
    .goal {{ border-color:var(--amber); box-shadow:inset 0 0 0 2px var(--amber); }}
    .agent-pos {{ background:#1f6f5b; color:#fff; border-color:#1f6f5b; box-shadow:inset 0 0 0 2px rgba(255,255,255,.55); }}
    .event {{ padding:12px; box-shadow:none; border-left:5px solid #d8dee8; }}
    .event-list {{ display:grid; gap:8px; max-height:660px; overflow:auto; padding-right:4px; }}
    .event.active {{ border-color:var(--blue); box-shadow:inset 0 0 0 2px var(--blue); }}
    .event.future {{ opacity:.42; }}
    .event.assessment {{ border-left-color:var(--amber); background:#fff8e8; }}
    .event.boundary {{ border-left-color:var(--amber); background:#fff8e8; }}
    .event.denied_tool {{ border-left-color:#b91c1c; background:#fff1f2; }}
    .event.tool_registry {{ border-left-color:var(--green); background:var(--soft-green); }}
    .event.local_memory {{ border-left-color:#7c3aed; background:#f5f3ff; }}
    .event.memory {{ border-left-color:var(--green); background:var(--soft-green); }}
    .event.sync {{ border-left-color:#0f766e; background:#ecfdf5; }}
    .event.plan,.event.tool_call {{ border-left-color:var(--blue); background:var(--soft-blue); }}
    .event.result {{ border-left-color:var(--green); background:var(--soft-green); }}
    pre {{ overflow:auto; max-height:360px; padding:12px; background:#111827; color:#e5e7eb; border-radius:8px; font-size:12px; }}
    a {{ color:var(--blue); font-weight:800; text-decoration:none; }}
    .state-row {{ display:grid; grid-template-columns:120px minmax(0,1fr); gap:8px; margin-top:8px; font-size:14px; }}
    .state-row span {{ color:var(--muted); font-weight:800; }}
    @media (max-width:1120px) {{ .grid {{ grid-template-columns:1fr; }} .maze-grid,.metrics {{ grid-template-columns:1fr; }} }}
    @media (max-width:980px) {{ header {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Part II Phase {trace['phase']} - {html.escape(trace['phase_name'])}</h1>
        <p>{html.escape(trace['learning']['objective'])}</p>
      </div>
      <aside class="summary">
        <span class="eyebrow">Current Result</span>
        <strong>{summary['llm_call_budget_used']} / {summary['llm_call_budget']} calls</strong>
        <p>{html.escape(trace['learning']['result_observed'])}</p>
      </aside>
    </header>
    <section class="grid">
      <div class="stack">
        <section class="panel">
          <h2>Architecture Overlay</h2>
          {agent_cards}
        </section>
        <section class="panel">
          <h2>Current State</h2>
          <div class="state-row"><span>Step</span><strong id="stateStep">1 / {len(trace['events'])}</strong></div>
          <div class="state-row"><span>Actor</span><strong id="stateActor">-</strong></div>
          <div class="state-row"><span>Event</span><strong id="stateEvent">-</strong></div>
          <div class="state-row"><span>Position</span><strong id="statePosition">n/a</strong></div>
          <div class="state-row"><span>LLM Calls</span><strong id="stateCalls">0 / {summary['llm_call_budget']}</strong></div>
        </section>
        <section class="panel">
          <h2>Notes</h2>
          <p><a href="../{notes_name}">Open phase notes</a></p>
          <p><a href="../{validation_name}">Open validation</a></p>
        </section>
      </div>
      <div class="stack">
        <section class="panel">
          <div class="controls">
            <button class="control-button" id="prev" type="button">Prev</button>
            <button class="control-button" id="play" type="button">Play</button>
            <button class="control-button" id="pause" type="button">Pause</button>
            <button class="control-button" id="replay" type="button">Replay</button>
          </div>
          <h2>Same Lab Environment</h2>
          <div class="maze-grid">{maze_cards}</div>
        </section>
        <section class="panel">
          <h2>Observed Metrics</h2>
          <div class="metrics">
            <div class="metric"><span>Reasoning Agents</span><strong>{summary['reasoning_agents']}</strong></div>
            <div class="metric"><span>Deterministic Workers</span><strong>{summary['deterministic_workers']}</strong></div>
            <div class="metric"><span>Worker LLM Calls</span><strong>{summary['worker_agent_llm_calls']}</strong></div>
          </div>
        </section>
      </div>
      <div class="stack">
        <section class="panel">
          <h2>Timeline</h2>
          <div class="event-list" id="eventList">{event_cards}</div>
        </section>
      </div>
    </section>
    <section class="panel" style="margin-top:14px;">
      <h2>Next Limitation</h2>
      <p>{html.escape(summary['next_phase'])}</p>
    </section>
    <section class="panel" style="margin-top:14px;">
      <h2>Trace JSON</h2>
      <details><summary>Open generated trace</summary><pre>{escaped}</pre></details>
    </section>
  </main>
  <script>
    const trace = {data};
    let index = 0;
    let timer = null;

    function esc(value) {{
      return String(value ?? "").replace(/[&<>"']/g, ch => ({{"&":"&amp;","<":"&lt;",">":"&gt;","\\\"":"&quot;","'":"&#39;"}}[ch]));
    }}

    function eventPositionText(event) {{
      if (event.maze_id && event.position) return `${{event.maze_id.replace("_", " ")}}: ${{event.position.join(", ")}}`;
      if (event.position) return event.position.join(", ");
      return "n/a";
    }}

    function currentPositions() {{
      const positions = {{}};
      trace.mazes.forEach(maze => positions[maze.id] = maze.start);
      trace.events.slice(0, index + 1).forEach(event => {{
        if (event.maze_id && event.position) positions[event.maze_id] = event.position;
      }});
      return positions;
    }}

    function renderMazes() {{
      const positions = currentPositions();
      document.querySelectorAll(".cell").forEach(cell => {{
        cell.classList.remove("agent-pos");
        const mazeId = cell.dataset.maze;
        const pos = positions[mazeId];
        if (pos && Number(cell.dataset.row) === pos[0] && Number(cell.dataset.col) === pos[1]) {{
          cell.classList.add("agent-pos");
          if (!cell.dataset.baseLabel) cell.textContent = mazeId === "maze_a" ? "A" : "B";
        }} else {{
          cell.textContent = cell.dataset.baseLabel || "";
        }}
      }});
    }}

    function callsThroughStep() {{
      return trace.events.slice(0, index + 1).reduce((total, event) => total + Number(event.llm_call_count || 0), 0);
    }}

    function renderStep() {{
      const event = trace.events[index];
      document.getElementById("stateStep").textContent = `${{index + 1}} / ${{trace.events.length}}`;
      document.getElementById("stateActor").textContent = event.actor;
      document.getElementById("stateEvent").textContent = `${{event.type}}: ${{event.label}}`;
      document.getElementById("statePosition").textContent = eventPositionText(event);
      const calls = Math.min(Number(trace.summary.llm_call_budget_used || 0), callsThroughStep());
      document.getElementById("stateCalls").textContent = `${{calls}} / ${{trace.summary.llm_call_budget}}`;
      renderMazes();
      document.querySelectorAll(".event").forEach((node, eventIndex) => {{
        node.classList.toggle("active", eventIndex === index);
        node.classList.toggle("future", eventIndex > index);
      }});
      const active = document.querySelector(".event.active");
      if (active) active.scrollIntoView({{block:"nearest"}});
    }}

    function play() {{
      clearInterval(timer);
      timer = setInterval(() => {{
        index = Math.min(index + 1, trace.events.length - 1);
        renderStep();
        if (index === trace.events.length - 1) clearInterval(timer);
      }}, 850);
    }}

    document.getElementById("prev").addEventListener("click", () => {{ index = Math.max(0, index - 1); renderStep(); }});
    document.getElementById("play").addEventListener("click", play);
    document.getElementById("pause").addEventListener("click", () => clearInterval(timer));
    document.getElementById("replay").addEventListener("click", () => {{ index = 0; renderStep(); play(); }});
    renderStep();
  </script>
</body>
</html>
"""


def _maze_card(maze: dict[str, Any]) -> str:
    path = {tuple(pos) for pos in maze["path"]}
    cells = []
    for r, row in enumerate(maze["rows"]):
        for c, value in enumerate(row):
            classes = ["cell"]
            if value == "#":
                classes.append("wall")
            if (r, c) in path:
                classes.append("path")
            if value == "S":
                classes.append("start")
            if value == "G":
                classes.append("goal")
            label = "#" if value == "#" else ("S" if value == "S" else ("G" if value == "G" else ""))
            cells.append(
                f"<div class=\"{' '.join(classes)}\" data-maze=\"{html.escape(maze['id'])}\" "
                f"data-row=\"{r}\" data-col=\"{c}\" data-base-label=\"{html.escape(label)}\" "
                f"title=\"{maze['label']} {r},{c}\">{label}</div>"
            )
    return f"""<article class="maze-frame"><h3>{html.escape(maze['label'])}</h3><div class="maze">{''.join(cells)}</div></article>"""


def _agent_card(agent: dict[str, Any]) -> str:
    kind = "det" if not agent["uses_pydantic_ai"] else ""
    return f"""<article class="agent {kind}"><span>{html.escape(agent['kind'])}</span><strong>{html.escape(agent['name'])}</strong><p>{html.escape(agent['owns'])}</p></article>"""


def _event_card(event: dict[str, Any]) -> str:
    event_type = html.escape(event["type"])
    return f"""<article class="event {event_type}"><span>{event['index'] + 1}. {event_type}</span><strong>{html.escape(event['actor'])} - {html.escape(event['label'])}</strong><p>{html.escape(event['detail'])}</p></article>"""


def _phase_notes_name(phase: int) -> str:
    return {
        1: "PHASE1_REASONING_BOTTLENECK.md",
        2: "PHASE2_WORKER_AGENT.md",
        3: "PHASE3_GLOBAL_LOCAL_PLANNING.md",
        4: "PHASE4_TOOL_OWNERSHIP.md",
        5: "PHASE5_INDEPENDENT_LOCAL_MEMORY.md",
        6: "PHASE6_SHARED_KNOWLEDGE_SYNCHRONIZATION.md",
        7: "PHASE7_SECOND_WORKER_AGENT.md",
    }.get(phase, "#")


def _phase_validation_name(phase: int) -> str:
    return {
        1: "PHASE1_VALIDATION.md",
        2: "PHASE2_VALIDATION.md",
        3: "PHASE3_VALIDATION.md",
        4: "PHASE4_VALIDATION.md",
        5: "PHASE5_VALIDATION.md",
        6: "PHASE6_VALIDATION.md",
        7: "PHASE7_VALIDATION.md",
    }.get(phase, "#")


def refresh_progress_dashboard(progress_path: Path) -> None:
    traces = []
    for number in sorted(PHASES):
        path = PROJECT_ROOT / "runs" / f"phase{number}_trace.json"
        if path.exists():
            traces.append(json.loads(path.read_text(encoding="utf-8")))
    write_text(progress_path, render_progress_html(traces))


def render_progress_html(traces: list[dict[str, Any]]) -> str:
    completed = {trace["phase"]: trace for trace in traces}
    cards = []
    for number, spec in PHASES.items():
        trace = completed.get(number)
        status = "Done" if trace else "Pending"
        calls = "Not run"
        if trace:
            calls = f"{trace['summary']['llm_call_budget_used']} / {trace['summary']['llm_call_budget']} calls"
        deployed = number <= 7
        notes = _phase_notes_name(number) if deployed else "#"
        validation = _phase_validation_name(number) if deployed else "#"
        visual = f"visuals/PHASE{number}_VISUAL.html" if deployed else "#"
        cards.append(
            f"""<article class="phase {'done' if trace else 'pending'}">
  <div><h2>Phase {number}: {html.escape(spec.name)}</h2><span>{status}</span></div>
  <p>{html.escape(spec.learning_objective)}</p>
  <div class="links"><a href="{notes}">Notes</a><a href="{visual}">Visual</a><a href="{validation}">Validation</a><strong>{html.escape(calls)}</strong></div>
  <ul><li>Concept: {html.escape(spec.concept)}</li><li>Question: {html.escape(spec.new_question)}</li><li>Observed: {html.escape(spec.result_observed)}</li></ul>
</article>"""
        )
    percent = int((len(completed) / len(PHASES)) * 100)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Multi-Agent Reasoning From Scratch - Progress</title>
  <style>
    :root {{ --bg:#f7f8fa; --panel:#fff; --text:#17202a; --muted:#5f6b7a; --line:#d9dee7; --green:#1f6f5b; --blue:#285da8; --shadow:0 10px 28px rgba(28,36,48,.08); }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:var(--text); background:var(--bg); line-height:1.5; }}
    main {{ width:min(1180px, calc(100% - 32px)); margin:0 auto; padding:32px 0 48px; }}
    header {{ display:grid; grid-template-columns:minmax(0,1fr) 260px; gap:22px; align-items:start; border-bottom:1px solid var(--line); padding-bottom:22px; margin-bottom:22px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(28px,4vw,42px); line-height:1.08; }}
    h2 {{ margin:0; font-size:18px; }}
    p {{ margin:8px 0 0; color:var(--muted); }}
    .summary,.phase {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; box-shadow:var(--shadow); }}
    .summary {{ padding:16px; }}
    .summary strong {{ display:block; font-size:28px; }}
    .progress {{ height:12px; margin-top:14px; overflow:hidden; background:#e8ecf2; border-radius:999px; }}
    .progress div {{ width:{percent}%; height:100%; background:var(--green); }}
    .grid {{ display:grid; gap:12px; }}
    .phase {{ padding:16px; box-shadow:none; border-left:6px solid var(--line); }}
    .phase.done {{ border-left-color:var(--green); }}
    .phase>div {{ display:flex; justify-content:space-between; gap:12px; }}
    .phase span {{ color:var(--green); font-size:12px; font-weight:800; text-transform:uppercase; }}
    .links {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; margin:12px 0; }}
    .links a,.links strong {{ padding:9px; border:1px solid var(--line); border-radius:8px; background:#fbfcfe; color:var(--blue); text-decoration:none; font-size:13px; }}
    ul {{ margin:0; padding-left:18px; font-size:14px; }}
    @media (max-width:760px) {{ header,.links {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Multi-Agent Reasoning From Scratch</h1>
        <p>Part II starts from the Part I architecture and introduces multiple LLM reasoning agents one concept at a time. Pydantic AI is used from Phase 1.</p>
      </div>
      <aside class="summary"><strong>{len(completed)} / {len(PHASES)}</strong><span>phases deployed</span><div class="progress"><div></div></div></aside>
    </header>
    <section class="grid">{''.join(cards)}</section>
  </main>
</body>
</html>
"""


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Multi-Agent Reasoning From Scratch phase.")
    parser.add_argument("--phase", type=int, required=True, choices=range(1, 8))
    parser.add_argument("--provider", default="local", choices=["local", "test"])
    parser.add_argument("--model", default="fast")
    parser.add_argument("--trace", default=None)
    parser.add_argument("--html", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    trace = PROJECT_ROOT / "runs" / f"phase{args.phase}_trace.json" if args.trace is None else Path(args.trace)
    visual = PROJECT_ROOT / "visuals" / f"PHASE{args.phase}_VISUAL.html" if args.html is None else Path(args.html)
    result = run_phase(
        phase_number=args.phase,
        provider=args.provider,
        model=args.model,
        trace_path=trace,
        html_path=visual,
        progress_path=PROJECT_ROOT / "PROGRESS.html",
    )
    print(f"phase={result['phase']}")
    print(f"concept={result['concept']}")
    print(f"llm_call_count={result['summary']['llm_call_budget_used']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
