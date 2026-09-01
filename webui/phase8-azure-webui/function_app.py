from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
import base64
import hashlib
import hmac
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import formatdate
from pathlib import Path
from typing import Any
from urllib import parse, request
from urllib.error import HTTPError

import azure.functions as func


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
TRACE_PATH = STATIC / "sample_trace.json"
TOKEN_RESOURCE = "https://ai.azure.com"
TEAM_MEMORY_CONTAINER = os.environ.get("TEAM_MEMORY_CONTAINER") or "team-memory"
WORKER_LLM_CALL_BUDGET = 50
WORKER_STEP_REQUEST_LIMIT = 3
TERMINAL_WORKER_OUTCOMES = {
    "goal_reached",
    "reported_impossible",
    "reported_stuck",
    "budget_exhausted",
    "invalid_move",
    "tool_rejected_move",
    "agent_error",
}
TOKEN_CACHE: dict[str, Any] = {}
TOKEN_CACHE_LOCK = threading.Lock()


app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
logging.getLogger().setLevel(logging.INFO)


def load_sample_trace() -> dict[str, Any]:
    return json.loads(TRACE_PATH.read_text(encoding="utf-8"))


def extract_output_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    parts: list[str] = []
    for item in payload.get("output") or []:
        for content in item.get("content") or []:
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def parse_trace_from_agent_text(text: str) -> dict[str, Any]:
    if not text.strip():
        raise ValueError("hosted agent returned empty text")
    payload = json.loads(text)
    if "trace" in payload and isinstance(payload["trace"], dict):
        return payload["trace"]
    if "events" in payload and "mazes" in payload:
        return payload
    return {
        "phase": payload.get("phase"),
        "concept": payload.get("concept"),
        "summary": payload.get("summary") or payload,
        "mazes": [],
        "events": [],
        "worker_move_decisions": {},
        "webui_note": "Hosted agent returned summary JSON but no full trace payload.",
    }


def parse_agent_json(text: str) -> dict[str, Any]:
    if not text.strip():
        raise ValueError("hosted agent returned empty text")
    payload = json.loads(text)
    return payload if isinstance(payload, dict) else {"value": payload}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TeamMemoryStore:
    backend_name = "request-scoped WebUI coordinator JSON"

    def __init__(self, run_id: str, fallback_error: str | None = None) -> None:
        self.run_id = run_id
        self.memory: dict[str, Any] = {}
        self.write_count = 0
        self.read_count = 0
        self.fallback_error = fallback_error

    def snapshot(self) -> dict[str, Any]:
        self.read_count += 1
        return dict(self.memory)

    def write_many(self, source: str, writes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        persisted: list[dict[str, Any]] = []
        for item in writes:
            key = item.get("key")
            if not isinstance(key, str):
                continue
            value = item.get("value")
            self.memory[key] = value
            self.write_count += 1
            persisted.append({"key": key, "value": value, "source": source})
        return persisted

    def write_grouped(self, groups: list[tuple[str, list[dict[str, Any]]]]) -> list[list[dict[str, Any]]]:
        return [self.write_many(source, writes) for source, writes in groups]


def parse_connection_string(connection_string: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for part in connection_string.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        values[key] = value
    return values


class AzureBlobTeamMemoryStore(TeamMemoryStore):
    backend_name = "Azure Blob Storage"

    def __init__(self, run_id: str) -> None:
        super().__init__(run_id)
        connection_string = os.environ.get("AzureWebJobsStorage")
        if not connection_string:
            raise RuntimeError("AzureWebJobsStorage is not configured")
        values = parse_connection_string(connection_string)
        self.account_name = values.get("AccountName", "")
        self.account_key = values.get("AccountKey", "")
        if not self.account_name or not self.account_key:
            raise RuntimeError("AzureWebJobsStorage must include AccountName and AccountKey")
        endpoint_suffix = values.get("EndpointSuffix") or "core.windows.net"
        self.blob_endpoint = values.get("BlobEndpoint") or f"https://{self.account_name}.blob.{endpoint_suffix}"
        self.container = TEAM_MEMORY_CONTAINER
        self.blob_name = f"{safe_blob_name(run_id)}.json"
        self.history: list[dict[str, Any]] = []
        self.ensure_container()

    def ensure_container(self) -> None:
        status, _ = self.azure_blob_request("PUT", f"/{self.container}", {"restype": "container"})
        if status not in {201, 202, 409}:
            raise RuntimeError(f"could not initialize durable memory container: HTTP {status}")

    def snapshot(self) -> dict[str, Any]:
        self.read_count += 1
        status, body = self.azure_blob_request("GET", f"/{self.container}/{self.blob_name}")
        if status == 404:
            return dict(self.memory)
        if status != 200:
            raise RuntimeError(f"could not read durable Team Memory: HTTP {status}")
        payload = json.loads(body.decode("utf-8"))
        memory = payload.get("memory")
        history = payload.get("history")
        self.memory = memory if isinstance(memory, dict) else {}
        self.history = history if isinstance(history, list) else []
        return dict(self.memory)

    def write_many(self, source: str, writes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.snapshot()
        persisted: list[dict[str, Any]] = []
        for item in writes:
            key = item.get("key")
            if not isinstance(key, str):
                continue
            value = item.get("value")
            self.memory[key] = value
            self.write_count += 1
            self.history.append({"source": source, "key": key, "value": value, "updated_at": utc_now()})
            persisted.append({"key": key, "value": value, "source": source})
        self.persist()
        return persisted

    def write_grouped(self, groups: list[tuple[str, list[dict[str, Any]]]]) -> list[list[dict[str, Any]]]:
        self.snapshot()
        grouped_persisted: list[list[dict[str, Any]]] = []
        changed = False
        for source, writes in groups:
            persisted: list[dict[str, Any]] = []
            for item in writes:
                key = item.get("key")
                if not isinstance(key, str):
                    continue
                value = item.get("value")
                self.memory[key] = value
                self.write_count += 1
                self.history.append({"source": source, "key": key, "value": value, "updated_at": utc_now()})
                persisted.append({"key": key, "value": value, "source": source})
                changed = True
            grouped_persisted.append(persisted)
        if changed:
            self.persist()
        return grouped_persisted

    def persist(self) -> None:
        body = json.dumps(
            {
                "run_id": self.run_id,
                "backend": self.backend_name,
                "updated_at": utc_now(),
                "memory": self.memory,
                "history": self.history,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        status, _ = self.azure_blob_request(
            "PUT",
            f"/{self.container}/{self.blob_name}",
            body=body,
            headers={"Content-Type": "application/json", "x-ms-blob-type": "BlockBlob"},
        )
        if status not in {201, 202}:
            raise RuntimeError(f"could not persist durable Team Memory: HTTP {status}")

    def azure_blob_request(
        self,
        method: str,
        path: str,
        query_params: dict[str, str] | None = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, bytes]:
        query_params = query_params or {}
        request_headers = {
            "x-ms-date": formatdate(usegmt=True),
            "x-ms-version": "2023-11-03",
        }
        if headers:
            request_headers.update(headers)
        if body is not None:
            request_headers["Content-Length"] = str(len(body))
        encoded_path = "/".join(parse.quote(part, safe="") for part in path.split("/"))
        url = self.blob_endpoint.rstrip("/") + encoded_path
        if query_params:
            url += "?" + parse.urlencode(query_params)
        request_headers["Authorization"] = self.authorization_header(method, encoded_path, query_params, request_headers)
        blob_request = request.Request(url, data=body, headers=request_headers, method=method)
        try:
            with request.urlopen(blob_request, timeout=60) as response:
                return int(response.status), response.read()
        except HTTPError as exc:
            return int(exc.code), exc.read()

    def authorization_header(
        self,
        method: str,
        encoded_path: str,
        query_params: dict[str, str],
        headers: dict[str, str],
    ) -> str:
        canonical_headers = ""
        for key in sorted(k.lower() for k in headers if k.lower().startswith("x-ms-")):
            canonical_headers += f"{key}:{str(headers[key]).strip()}\n"
        canonical_resource = f"/{self.account_name}{encoded_path}"
        for key in sorted(query_params):
            canonical_resource += f"\n{key.lower()}:{query_params[key]}"
        content_length = headers.get("Content-Length", "")
        if content_length == "0":
            content_length = ""
        string_to_sign = "\n".join(
            [
                method,
                "",
                "",
                content_length,
                "",
                headers.get("Content-Type", ""),
                "",
                "",
                "",
                "",
                "",
                "",
                canonical_headers + canonical_resource,
            ]
        )
        digest = hmac.new(base64.b64decode(self.account_key), string_to_sign.encode("utf-8"), hashlib.sha256).digest()
        signature = base64.b64encode(digest).decode("utf-8")
        return f"SharedKey {self.account_name}:{signature}"


def safe_blob_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]+", "_", value.strip())
    return cleaned[:256] or "memory"


def build_team_memory_store(run_id: str | None = None) -> TeamMemoryStore:
    run_id = run_id or f"phase18-{uuid.uuid4().hex[:16]}"
    if os.environ.get("TEAM_MEMORY_BACKEND", "azure-blob").strip().lower() == "request":
        return TeamMemoryStore(run_id)
    return AzureBlobTeamMemoryStore(run_id)


def get_managed_identity_token() -> str:
    cached = TOKEN_CACHE.get(TOKEN_RESOURCE)
    now = time.time()
    if isinstance(cached, dict) and cached.get("token") and float(cached.get("expires_at") or 0) > now + 60:
        return str(cached["token"])
    with TOKEN_CACHE_LOCK:
        cached = TOKEN_CACHE.get(TOKEN_RESOURCE)
        now = time.time()
        if isinstance(cached, dict) and cached.get("token") and float(cached.get("expires_at") or 0) > now + 60:
            return str(cached["token"])
        endpoint = os.environ.get("IDENTITY_ENDPOINT")
        header = os.environ.get("IDENTITY_HEADER")
        if not endpoint or not header:
            raise RuntimeError("Function managed identity endpoint is not available")
        url = endpoint + "?" + parse.urlencode({"api-version": "2019-08-01", "resource": TOKEN_RESOURCE})
        token_request = request.Request(url, headers={"X-IDENTITY-HEADER": header, "Metadata": "true"})
        with request.urlopen(token_request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        token = payload.get("access_token")
        if not token:
            raise RuntimeError("managed identity token response did not include access_token")
        expires_on = payload.get("expires_on")
        expires_at = now + 300
        if isinstance(expires_on, (int, float)):
            expires_at = float(expires_on)
        elif isinstance(expires_on, str) and expires_on.isdigit():
            expires_at = float(expires_on)
        TOKEN_CACHE[TOKEN_RESOURCE] = {"token": token, "expires_at": expires_at}
        return token


def extract_agent_session_id(payload: dict[str, Any]) -> str:
    for key in ("agent_session_id", "session_id"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    model_extra = payload.get("model_extra")
    if isinstance(model_extra, dict):
        value = model_extra.get("agent_session_id")
        if isinstance(value, str) and value:
            return value
    return ""


def foundry_session_delete_url(endpoint: str, session_id: str) -> str:
    parsed = parse.urlsplit(endpoint)
    if "/endpoint/protocols/" not in parsed.path:
        raise ValueError("endpoint does not look like a Foundry hosted-agent protocol endpoint")
    agent_path = parsed.path.split("/endpoint/protocols/", 1)[0]
    query = parse.parse_qs(parsed.query)
    api_version = (query.get("api-version") or ["v1"])[0]
    session_path = f"{agent_path}/endpoint/sessions/{parse.quote(session_id, safe='')}"
    return parse.urlunsplit((parsed.scheme, parsed.netloc, session_path, parse.urlencode({"api-version": api_version}), ""))


def delete_foundry_agent_session(endpoint: str, session_id: str, token: str) -> dict[str, Any]:
    if not session_id:
        return {"attempted": False, "deleted": False}
    if os.environ.get("FOUNDRY_DELETE_SESSIONS_AFTER_CALL", "false").strip().lower() not in {"1", "true", "yes"}:
        return {"attempted": False, "deleted": False, "reason": "disabled"}
    delete_request = request.Request(
        foundry_session_delete_url(endpoint, session_id),
        headers={"Authorization": f"Bearer {token}"},
        method="DELETE",
    )
    try:
        with request.urlopen(delete_request, timeout=60) as response:
            return {"attempted": True, "deleted": int(response.status) in {200, 202, 204}, "status": int(response.status)}
    except HTTPError as exc:
        if int(exc.code) == 404:
            return {"attempted": True, "deleted": False, "status": 404, "reason": "not_found"}
        body = exc.read().decode("utf-8", errors="replace")
        return {"attempted": True, "deleted": False, "status": int(exc.code), "error": body[:500]}
    except Exception as exc:
        return {"attempted": True, "deleted": False, "error": str(exc)[:500]}


def call_foundry_endpoint(endpoint: str, input_payload: str, timeout: int = 600, agent_session_id: str = "") -> dict[str, Any]:
    if not endpoint:
        raise RuntimeError("FOUNDRY_AGENT_ENDPOINT is not configured")
    token = get_managed_identity_token()
    request_body = {
        "input": input_payload,
        "stream": False,
        "store": False,
    }
    if agent_session_id:
        request_body["agent_session_id"] = agent_session_id
    agent_request = request.Request(
        endpoint,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        data=json.dumps(request_body).encode("utf-8"),
        method="POST",
    )
    try:
        with request.urlopen(agent_request, timeout=timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Foundry agent call failed: HTTP {exc.code}: {body[:1200]}") from exc
    if isinstance(response_payload, dict):
        session_id = extract_agent_session_id(response_payload)
        response_payload["_agent_session_cleanup"] = delete_foundry_agent_session(endpoint, session_id, token)
    return response_payload


def call_foundry_agent() -> dict[str, Any]:
    endpoint = os.environ.get("FOUNDRY_AGENT_ENDPOINT", "").strip()
    response_payload = call_foundry_endpoint(endpoint, "Run the hosted maze validation and return the full trace JSON.")
    return parse_trace_from_agent_text(extract_output_text(response_payload))


def stored_foundry_session_id(team_memory: dict[str, Any], role: str) -> str:
    stored_role = team_memory.get(f"_role.{role}")
    if isinstance(stored_role, dict):
        value = stored_role.get("_foundry_agent_session_id")
        if isinstance(value, str) and value:
            return value
    return ""


def call_role_agent(endpoint: str, role: str, team_memory: dict[str, Any]) -> dict[str, Any]:
    response_payload = call_foundry_endpoint(
        endpoint,
        json.dumps({"role": role, "team_memory": team_memory}),
        timeout=900,
        agent_session_id=stored_foundry_session_id(team_memory, role),
    )
    parsed = parse_agent_json(extract_output_text(response_payload))
    session_id = extract_agent_session_id(response_payload)
    if session_id:
        parsed["_foundry_agent_session_id"] = session_id
    cleanup = response_payload.get("_agent_session_cleanup") if isinstance(response_payload, dict) else None
    if isinstance(cleanup, dict):
        parsed["_foundry_agent_session_cleanup"] = cleanup
    return parsed


def apply_shared_writes(team_memory: dict[str, Any], writes: list[dict[str, Any]]) -> None:
    for item in writes:
        key = item.get("key")
        if isinstance(key, str):
            team_memory[key] = item.get("value")


def move_delta(move: str) -> tuple[int, int]:
    return {
        "north": (-1, 0),
        "south": (1, 0),
        "west": (0, -1),
        "east": (0, 1),
    }[move]


def normalize_position(value: Any) -> list[int]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return [int(value[0]), int(value[1])]
    return [0, 0]


def role_result_events(role_payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = role_payload.get("result") or {}
    events = result.get("events")
    return events if isinstance(events, list) else []


def role_move_decisions(role_payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = role_payload.get("result") or {}
    decisions = result.get("move_decisions")
    return decisions if isinstance(decisions, list) else []


def position_list(value: Any) -> list[int] | None:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return [int(value[0]), int(value[1])]
    return None


def parallel_tick_events(worker_a: dict[str, Any], worker_b: dict[str, Any]) -> list[dict[str, Any]]:
    workers = [
        ("Worker Agent A", "maze_a", "Maze A", role_move_decisions(worker_a)),
        ("Worker Agent B", "maze_b", "Maze B", role_move_decisions(worker_b)),
    ]
    max_steps = max((len(decisions) for _, _, _, decisions in workers), default=0)
    ticks: list[dict[str, Any]] = []
    for tick_index in range(max_steps):
        moves: list[dict[str, Any]] = []
        descriptions: list[str] = []
        llm_calls = 0
        for worker_name, maze_id, maze_label, decisions in workers:
            if tick_index >= len(decisions):
                continue
            decision = decisions[tick_index]
            llm_calls += int(decision.get("llm_call_count") or 0)
            before = position_list(decision.get("position"))
            after = position_list(decision.get("new_position") or decision.get("position"))
            action = str(decision.get("action") or "")
            chosen_move = str(decision.get("chosen_move") or "")
            move_applied = bool(decision.get("move_applied"))
            if move_applied and before and after:
                descriptions.append(f"{worker_name} moved {chosen_move} on {maze_label}: ({before[0]}, {before[1]}) -> ({after[0]}, {after[1]}).")
            else:
                descriptions.append(f"{worker_name} reported {action or 'stop'} on {maze_label}.")
            moves.append(
                {
                    "worker": worker_name,
                    "maze_id": maze_id,
                    "maze_label": maze_label,
                    "action": action,
                    "chosen_move": chosen_move,
                    "from": before,
                    "position": after,
                    "move_applied": move_applied,
                    "rationale": decision.get("rationale"),
                }
            )
        if moves:
            worker_names = [str(item.get("worker") or "Worker Agent") for item in moves]
            maze_labels = [str(item.get("maze_label") or "Maze") for item in moves]
            ticks.append(
                {
                    "type": "parallel_tick",
                    "actor": " + ".join(worker_names),
                    "target": " + ".join(maze_labels),
                    "label": f"parallel tick {tick_index + 1}",
                    "detail": " ".join(descriptions),
                    "parallel_tick": tick_index + 1,
                    "parallel_moves": moves,
                    "llm_call_count": llm_calls,
                }
            )
    return ticks


def role_summary(role_payload: dict[str, Any]) -> dict[str, Any]:
    direct = role_payload.get("summary")
    if isinstance(direct, dict):
        summary = dict(direct)
        summary["llm_calls"] = summary.get("llm_calls") or role_payload.get("llm_calls") or 0
        summary["maze_tool_calls"] = summary.get("maze_tool_calls") or role_payload.get("maze_tool_calls") or 0
        return summary
    nested = (role_payload.get("result") or {}).get("summary")
    if isinstance(nested, dict):
        summary = dict(nested)
        summary["llm_calls"] = summary.get("llm_calls") or role_payload.get("llm_calls") or 0
        summary["maze_tool_calls"] = summary.get("maze_tool_calls") or role_payload.get("maze_tool_calls") or 0
        return summary
    return {
        "llm_calls": role_payload.get("llm_calls") or 0,
        "maze_tool_calls": role_payload.get("maze_tool_calls") or 0,
    }


def empty_role_payload(role: str) -> dict[str, Any]:
    return {
        "status": "pending",
        "phase": 16,
        "concept": "Analyst-Generated Work",
        "role": role,
        "result": {
            "status": "pending",
            "role": role,
            "events": [],
            "move_decisions": [],
            "summary": {
                "llm_calls": 0,
                "maze_tool_calls": 0,
                "goal_reached": None,
                "outcome": "pending",
                "invalid_moves": 0,
                "worker_side_path_rescue": False,
                "guardrail_corrections": 0,
            },
        },
        "summary": {
            "llm_calls": 0,
            "maze_tool_calls": 0,
            "goal_reached": None,
            "outcome": "pending",
            "invalid_moves": 0,
            "worker_side_path_rescue": False,
            "guardrail_corrections": 0,
        },
    }


def find_marker(rows: list[str], marker: str, fallback: list[int]) -> list[int]:
    for row_index, row in enumerate(rows):
        col_index = row.find(marker)
        if col_index >= 0:
            return [row_index, col_index]
    return fallback


def valid_maze_rows(rows: Any) -> bool:
    if not isinstance(rows, list) or len(rows) != 5:
        return False
    if not all(isinstance(row, str) and len(row) == 5 and re.fullmatch(r"[SG.#]+", row) for row in rows):
        return False
    joined = "".join(rows)
    return joined.count("S") == 1 and joined.count("G") == 1


def trace_mazes_from_memory(team_memory: dict[str, Any]) -> list[dict[str, Any]]:
    sample = load_sample_trace()
    sample_mazes = {maze.get("id"): maze for maze in sample.get("mazes") or [] if isinstance(maze, dict)}
    mazes: list[dict[str, Any]] = []
    for maze_id, label in (("maze_a", "Maze A"), ("maze_b", "Maze B")):
        rows = team_memory.get(f"maze.{maze_id}.rows")
        if valid_maze_rows(rows):
            profile = team_memory.get(f"maze.{maze_id}.profile") if isinstance(team_memory.get(f"maze.{maze_id}.profile"), dict) else {}
            mazes.append(
                {
                    "id": maze_id,
                    "label": label,
                    "rows": rows,
                    "start": find_marker(rows, "S", [0, 0]),
                    "goal": find_marker(rows, "G", [4, 4]),
                    "profile": profile,
                    "layout_source": "Analyst-generated per-run Team Memory",
                }
            )
        elif maze_id in sample_mazes:
            mazes.append(sample_mazes[maze_id])
    return mazes


def build_split_trace(
    analyst: dict[str, Any],
    worker_a: dict[str, Any],
    worker_b: dict[str, Any],
    team_memory: dict[str, Any],
    memory_store: TeamMemoryStore,
    memory_events: list[dict[str, Any]],
    reviewer: dict[str, Any] | None = None,
    workflow_stage: str = "workers_complete",
    phase_override: int | None = None,
    phase_name_override: str | None = None,
    concept_override: str | None = None,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = [
        {
            "type": "state",
            "actor": "Azure WebUI Coordinator",
            "label": "split role run",
            "detail": f"WebUI coordinated independent Foundry-hosted role agents and used {memory_store.backend_name} for Team Memory.",
            "llm_call_count": 0,
        }
    ]
    events.extend(memory_events)
    base_role_payloads = [analyst, worker_a, worker_b]
    role_payloads = list(base_role_payloads)
    if isinstance(reviewer, dict):
        role_payloads.append(reviewer)
    for payload in base_role_payloads:
        for event in role_result_events(payload):
            copied = dict(event)
            copied.setdefault("llm_call_count", 0)
            events.append(copied)
    if phase_override is not None and phase_override >= 17:
        events.extend(parallel_tick_events(worker_a, worker_b))
    if isinstance(reviewer, dict):
        for event in role_result_events(reviewer):
            copied = dict(event)
            copied.setdefault("llm_call_count", 0)
            events.append(copied)
    for index, event in enumerate(events):
        event["index"] = index

    summaries = [role_summary(payload) for payload in role_payloads]
    worker_a_llm_calls = int(summaries[1].get("llm_calls") or 0)
    worker_b_llm_calls = int(summaries[2].get("llm_calls") or 0)
    reviewer_summary = role_summary(reviewer) if isinstance(reviewer, dict) else {}
    worker_a_outcome = worker_outcome_with_budget(worker_a, team_memory, "maze_a")
    worker_b_outcome = worker_outcome_with_budget(worker_b, team_memory, "maze_b")
    llm_calls = sum(int(summary.get("llm_calls") or 0) for summary in summaries)
    maze_tool_calls = sum(int(summary.get("maze_tool_calls") or 0) for summary in summaries)
    role_phases = [int(payload.get("phase") or 0) for payload in role_payloads if str(payload.get("phase") or "").isdigit()]
    phase = phase_override or (max(role_phases) if role_phases else 14)
    dynamic_layouts = all(isinstance(team_memory.get(f"maze.{maze_id}.rows"), list) for maze_id in ("maze_a", "maze_b"))
    return {
        "course": "Azure Foundry Maze Migration From Scratch",
        "phase": phase,
        "phase_name": phase_name_override or ("Dynamic Mission Design" if dynamic_layouts else "Azure Durable Team Memory"),
        "concept": concept_override or ("Analyst-Generated Work" if dynamic_layouts else "Durable Shared State"),
        "provider": {"provider": "foundry", "model": "gpt41mini-maze", "model_note": "Azure Foundry project model deployment"},
        "agents": [
            {"name": "maze-analyst-agent", "kind": "independent Foundry-hosted PydanticAI Analyst", "uses_pydantic_ai": True, "owns": "global assignment"},
            {"name": "maze-worker-agent-a", "kind": "independent Foundry-hosted PydanticAI Worker", "uses_pydantic_ai": True, "owns": "Maze A local reasoning"},
            {"name": "maze-worker-agent-b", "kind": "independent Foundry-hosted PydanticAI Worker", "uses_pydantic_ai": True, "owns": "Maze B local reasoning"},
            {"name": "maze-reviewer-agent", "kind": "independent Foundry-hosted PydanticAI Reviewer", "uses_pydantic_ai": True, "owns": "post-run evaluation", "active": isinstance(reviewer, dict)},
            {"name": "Azure WebUI Coordinator", "kind": "deterministic request coordinator", "uses_pydantic_ai": False, "owns": "durable Team Memory and trace assembly"},
        ],
        "mazes": trace_mazes_from_memory(team_memory),
        "events": events,
        "worker_move_decisions": {
            "Worker Agent A": ((worker_a.get("result") or {}).get("move_decisions") or []),
            "Worker Agent B": ((worker_b.get("result") or {}).get("move_decisions") or []),
        },
        "team_memory": team_memory,
        "summary": {
            "llm_call_budget": WORKER_LLM_CALL_BUDGET,
            "llm_call_budget_used": llm_calls,
            "llm_call_budget_scope": "per_worker",
            "worker_llm_call_budget": WORKER_LLM_CALL_BUDGET,
            "worker_a_llm_calls": worker_a_llm_calls,
            "worker_b_llm_calls": worker_b_llm_calls,
            "worker_a_llm_call_budget_remaining": max(0, WORKER_LLM_CALL_BUDGET - worker_a_llm_calls),
            "worker_b_llm_call_budget_remaining": max(0, WORKER_LLM_CALL_BUDGET - worker_b_llm_calls),
            "agent_count": 4 if isinstance(reviewer, dict) else 3,
            "reasoning_agents": 4 if isinstance(reviewer, dict) else 3,
            "hosted_role_agents": 4 if isinstance(reviewer, dict) else 3,
            "maze_tool_calls": maze_tool_calls,
            "foundry_toolbox_mcp_calls": maze_tool_calls,
            "direct_http_tool_calls": 0,
            "shared_memory_backend": memory_store.backend_name,
            "team_memory_run_id": memory_store.run_id,
            "team_memory_container": TEAM_MEMORY_CONTAINER if memory_store.backend_name == "Azure Blob Storage" else None,
            "team_memory_fallback_error": memory_store.fallback_error,
            "team_memory_reads": memory_store.read_count,
            "team_memory_writes": memory_store.write_count,
            "workflow_stage": workflow_stage,
            "parallel_worker_step_execution": phase >= 17,
            "worker_step_mode": phase >= 16,
            "dynamic_maze_generation": dynamic_layouts,
            "analyst_generated_maze_rows": dynamic_layouts,
            "worker_a_goal_reached": summaries[1].get("goal_reached"),
            "worker_b_goal_reached": summaries[2].get("goal_reached"),
            "worker_a_outcome": worker_a_outcome,
            "worker_b_outcome": worker_b_outcome,
            "worker_invalid_moves": sum(int(summary.get("invalid_moves") or 0) for summary in summaries),
            "worker_side_path_rescue": any(bool(summary.get("worker_side_path_rescue")) for summary in summaries),
            "guardrail_corrections": sum(int(summary.get("guardrail_corrections") or 0) for summary in summaries),
            "review_score": reviewer_summary.get("review_score"),
            "review_threshold": reviewer_summary.get("review_threshold"),
            "review_status": reviewer_summary.get("review_status"),
            "review_findings": reviewer_summary.get("review_findings"),
            "next_phase": "Use agent quality telemetry to explain outcomes, path quality, memory freshness, and LLM budget.",
        },
    }


def split_endpoints() -> tuple[str, str, str]:
    return (
        os.environ.get("FOUNDRY_ANALYST_AGENT_ENDPOINT", "").strip(),
        os.environ.get("FOUNDRY_WORKER_AGENT_A_ENDPOINT", "").strip(),
        os.environ.get("FOUNDRY_WORKER_AGENT_B_ENDPOINT", "").strip(),
    )


def reviewer_endpoint() -> str:
    return os.environ.get("FOUNDRY_REVIEWER_AGENT_ENDPOINT", "").strip()


def call_split_role_agents() -> dict[str, Any]:
    analyst_endpoint, worker_a_endpoint, worker_b_endpoint = split_endpoints()
    if not all([analyst_endpoint, worker_a_endpoint, worker_b_endpoint]):
        raise RuntimeError("split role agent endpoints are not fully configured")
    memory_store = build_team_memory_store()
    memory_events: list[dict[str, Any]] = [
        {
            "type": "memory",
            "actor": "Azure WebUI Coordinator",
            "target": "Team Memory",
            "label": "initialize durable memory",
            "detail": f"Team Memory run {memory_store.run_id} uses {memory_store.backend_name}.",
            "memory_scope": "shared",
            "llm_call_count": 0,
        }
    ]
    analyst = call_role_agent(analyst_endpoint, "analyst", memory_store.snapshot())
    writes = memory_store.write_many("maze-analyst-agent", ((analyst.get("result") or {}).get("team_memory_writes") or []))
    memory_events.append(
        {
            "type": "memory",
            "actor": "maze-analyst-agent",
            "target": "Team Memory",
            "label": "persist analyst writes",
            "detail": f"Persisted {len(writes)} Team Memory records after Analyst assignment.",
            "memory_scope": "shared",
            "llm_call_count": 0,
        }
    )
    worker_a = call_role_agent(worker_a_endpoint, "worker_a", memory_store.snapshot())
    writes = memory_store.write_many("maze-worker-agent-a", ((worker_a.get("result") or {}).get("team_memory_writes") or []))
    memory_events.append(
        {
            "type": "memory",
            "actor": "maze-worker-agent-a",
            "target": "Team Memory",
            "label": "persist worker a result",
            "detail": f"Persisted {len(writes)} Team Memory records after Worker Agent A completed Maze A.",
            "memory_scope": "shared",
            "llm_call_count": 0,
        }
    )
    worker_b = call_role_agent(worker_b_endpoint, "worker_b", memory_store.snapshot())
    writes = memory_store.write_many("maze-worker-agent-b", ((worker_b.get("result") or {}).get("team_memory_writes") or []))
    memory_events.append(
        {
            "type": "memory",
            "actor": "maze-worker-agent-b",
            "target": "Team Memory",
            "label": "persist worker b result",
            "detail": f"Persisted {len(writes)} Team Memory records after Worker Agent B completed Maze B.",
            "memory_scope": "shared",
            "llm_call_count": 0,
        }
    )
    return build_split_trace(analyst, worker_a, worker_b, memory_store.snapshot(), memory_store, memory_events)


def call_analyst_mission() -> dict[str, Any]:
    analyst_endpoint, worker_a_endpoint, worker_b_endpoint = split_endpoints()
    if not all([analyst_endpoint, worker_a_endpoint, worker_b_endpoint]):
        raise RuntimeError("split role agent endpoints are not fully configured")
    memory_store = build_team_memory_store()
    memory_events: list[dict[str, Any]] = [
        {
            "type": "memory",
            "actor": "Azure WebUI Coordinator",
            "target": "Team Memory",
            "label": "initialize durable memory",
            "detail": f"Team Memory run {memory_store.run_id} uses {memory_store.backend_name}.",
            "memory_scope": "shared",
            "llm_call_count": 0,
        }
    ]
    analyst = call_role_agent(analyst_endpoint, "analyst", memory_store.snapshot())
    grouped_writes = memory_store.write_grouped(
        [
            ("maze-analyst-agent", ((analyst.get("result") or {}).get("team_memory_writes") or [])),
            ("Azure WebUI Coordinator", [{"key": "_role.analyst", "value": analyst}]),
        ]
    )
    writes = grouped_writes[0]
    memory_events.append(
        {
            "type": "memory",
            "actor": "maze-analyst-agent",
            "target": "Team Memory",
            "label": "persist analyst writes",
            "detail": f"Persisted {len(writes)} Analyst records. Maze rows are visible; Workers have not run yet.",
            "memory_scope": "shared",
            "llm_call_count": 0,
        }
    )
    memory_events.append(
        {
            "type": "assignment",
            "actor": "Azure WebUI Coordinator",
            "target": "Learner",
            "label": "await play",
            "detail": "Analyst-generated Maze A and Maze B are ready. Press Play to invoke Worker Agent A and Worker Agent B.",
            "llm_call_count": 0,
        }
    )
    return build_split_trace(
        analyst,
        empty_role_payload("worker_a"),
        empty_role_payload("worker_b"),
        memory_store.snapshot(),
        memory_store,
        memory_events,
        workflow_stage="mission_ready",
        phase_override=18,
        phase_name_override="Human Feedback Telemetry",
        concept_override="Human Feedback Telemetry",
    )


def call_workers_for_mission(run_id: str) -> dict[str, Any]:
    if not run_id:
        raise ValueError("run_id is required")
    analyst_endpoint, worker_a_endpoint, worker_b_endpoint = split_endpoints()
    if not all([analyst_endpoint, worker_a_endpoint, worker_b_endpoint]):
        raise RuntimeError("split role agent endpoints are not fully configured")
    memory_store = build_team_memory_store(run_id)
    team_memory = memory_store.snapshot()
    analyst = team_memory.get("_role.analyst")
    if not isinstance(analyst, dict):
        analyst = empty_role_payload("analyst")
    memory_events: list[dict[str, Any]] = [
        {
            "type": "memory",
            "actor": "Azure WebUI Coordinator",
            "target": "Team Memory",
            "label": "load mission",
            "detail": f"Loaded Analyst-generated maze rows from Team Memory run {memory_store.run_id}.",
            "memory_scope": "shared",
            "llm_call_count": 0,
        }
    ]
    worker_input = memory_store.snapshot()
    memory_events.extend(
        [
            {
                "type": "assignment",
                "actor": "Azure WebUI Coordinator",
                "target": "maze-worker-agent-a",
                "label": "dispatch maze a",
                "detail": "Play requested execution. Worker Agent A is running against Maze A from Team Memory.",
                "llm_call_count": 0,
            },
            {
                "type": "assignment",
                "actor": "Azure WebUI Coordinator",
                "target": "maze-worker-agent-b",
                "label": "dispatch maze b",
                "detail": "Play requested execution. Worker Agent B is running against Maze B from Team Memory.",
                "llm_call_count": 0,
            },
        ]
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        worker_a_future = executor.submit(call_role_agent, worker_a_endpoint, "worker_a", worker_input)
        worker_b_future = executor.submit(call_role_agent, worker_b_endpoint, "worker_b", worker_input)
        worker_a = worker_a_future.result()
        worker_b = worker_b_future.result()
    writes = memory_store.write_many("maze-worker-agent-a", ((worker_a.get("result") or {}).get("team_memory_writes") or []))
    memory_store.write_many("Azure WebUI Coordinator", [{"key": "_role.worker_a", "value": worker_a}])
    memory_events.append(
        {
            "type": "memory",
            "actor": "maze-worker-agent-a",
            "target": "Team Memory",
            "label": "persist worker a result",
            "detail": f"Persisted {len(writes)} Team Memory records after Worker Agent A attempted Maze A.",
            "memory_scope": "shared",
            "llm_call_count": 0,
        }
    )
    writes = memory_store.write_many("maze-worker-agent-b", ((worker_b.get("result") or {}).get("team_memory_writes") or []))
    memory_store.write_many("Azure WebUI Coordinator", [{"key": "_role.worker_b", "value": worker_b}])
    memory_events.append(
        {
            "type": "memory",
            "actor": "maze-worker-agent-b",
            "target": "Team Memory",
            "label": "persist worker b result",
            "detail": f"Persisted {len(writes)} Team Memory records after Worker Agent B attempted Maze B.",
            "memory_scope": "shared",
            "llm_call_count": 0,
        }
    )
    return build_split_trace(analyst, worker_a, worker_b, memory_store.snapshot(), memory_store, memory_events)


def stored_role_payload(team_memory: dict[str, Any], key: str, role: str) -> dict[str, Any]:
    payload = team_memory.get(key)
    return payload if isinstance(payload, dict) else empty_role_payload(role)


def accumulated_role_payload(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    if not previous or previous.get("status") == "pending":
        return current
    merged = dict(current)
    previous_result = previous.get("result") if isinstance(previous.get("result"), dict) else {}
    current_result = current.get("result") if isinstance(current.get("result"), dict) else {}
    merged_result = dict(current_result)
    merged_result["events"] = list(previous_result.get("events") or []) + list(current_result.get("events") or [])
    merged_result["move_decisions"] = list(previous_result.get("move_decisions") or []) + list(current_result.get("move_decisions") or [])
    previous_summary = role_summary(previous)
    current_summary = role_summary(current)
    merged_summary = dict(current_summary)
    for key in ("llm_calls", "maze_tool_calls", "invalid_moves", "guardrail_corrections"):
        merged_summary[key] = int(previous_summary.get(key) or 0) + int(current_summary.get(key) or 0)
    merged_summary["worker_side_path_rescue"] = bool(previous_summary.get("worker_side_path_rescue")) or bool(current_summary.get("worker_side_path_rescue"))
    merged_result["summary"] = merged_summary
    merged["result"] = merged_result
    merged["summary"] = merged_summary
    return merged


def worker_outcome(team_memory: dict[str, Any], maze_id: str) -> str:
    state = team_memory.get(f"worker_state.{maze_id}")
    if isinstance(state, dict) and isinstance(state.get("outcome"), str):
        return state["outcome"]
    return "pending"


def worker_outcome_with_budget(role_payload: dict[str, Any], team_memory: dict[str, Any], maze_id: str) -> str:
    outcome = worker_outcome(team_memory, maze_id)
    summary = role_summary(role_payload)
    summary_outcome = summary.get("outcome")
    if outcome == "pending" and isinstance(summary_outcome, str):
        outcome = summary_outcome
    if outcome not in TERMINAL_WORKER_OUTCOMES and int(summary.get("llm_calls") or 0) >= WORKER_LLM_CALL_BUDGET:
        return "budget_exhausted"
    return outcome


def worker_error_payload(role: str, error: Exception, worker_state: dict[str, Any] | None = None) -> dict[str, Any]:
    worker_label = "Worker Agent A" if role == "worker_a" else "Worker Agent B"
    maze_id = "maze_a" if role == "worker_a" else "maze_b"
    maze_label = "Maze A" if role == "worker_a" else "Maze B"
    agent_name = "maze-worker-agent-a" if role == "worker_a" else "maze-worker-agent-b"
    detail = f"{worker_label} call failed before producing a step: {error}"
    state_value = dict(worker_state or {})
    state_value.update(
        {
            "outcome": "agent_error",
            "goal_reached": False,
            "updated_by": worker_label,
            "error": str(error)[:500],
        }
    )
    return {
        "status": "error",
        "phase": 18,
        "role": role,
        "hosted_agent_name": agent_name,
        "result": {
            "status": "error",
            "role": role,
            "events": [
                {
                    "type": "result",
                    "actor": worker_label,
                    "target": maze_label,
                    "maze_id": maze_id,
                    "label": "agent error",
                    "detail": detail,
                    "llm_call_count": 0,
                }
            ],
            "move_decisions": [],
            "team_memory_writes": [
                {
                    "key": f"worker_state.{maze_id}",
                    "value": state_value,
                }
            ],
            "summary": {
                "llm_calls": 0,
                "maze_tool_calls": 0,
                "goal_reached": False,
                "outcome": "agent_error",
                "invalid_moves": 0,
                "worker_side_path_rescue": False,
                "guardrail_corrections": 0,
            },
        },
        "summary": {
            "llm_calls": 0,
            "maze_tool_calls": 0,
            "goal_reached": False,
            "outcome": "agent_error",
            "invalid_moves": 0,
            "worker_side_path_rescue": False,
            "guardrail_corrections": 0,
        },
    }


def call_worker_step_for_mission(run_id: str, role: str) -> dict[str, Any]:
    if not run_id:
        raise ValueError("run_id is required")
    normalized_role = role.strip().lower().replace("-", "_")
    if normalized_role not in {"worker_a", "worker_b"}:
        raise ValueError("role must be worker_a or worker_b")
    analyst_endpoint, worker_a_endpoint, worker_b_endpoint = split_endpoints()
    role_endpoint = worker_a_endpoint if normalized_role == "worker_a" else worker_b_endpoint
    if not analyst_endpoint or not role_endpoint:
        raise RuntimeError("split role agent endpoints are not fully configured")

    memory_store = build_team_memory_store(run_id)
    base_memory = memory_store.snapshot()
    analyst = stored_role_payload(base_memory, "_role.analyst", "analyst")
    existing_worker = stored_role_payload(base_memory, f"_role.{normalized_role}", normalized_role)
    maze_id = "maze_a" if normalized_role == "worker_a" else "maze_b"
    if worker_outcome_with_budget(existing_worker, base_memory, maze_id) in TERMINAL_WORKER_OUTCOMES:
        worker_a = existing_worker if normalized_role == "worker_a" else stored_role_payload(base_memory, "_role.worker_a", "worker_a")
        worker_b = existing_worker if normalized_role == "worker_b" else stored_role_payload(base_memory, "_role.worker_b", "worker_b")
        outcomes = {
            "maze_a": worker_outcome_with_budget(worker_a, base_memory, "maze_a"),
            "maze_b": worker_outcome_with_budget(worker_b, base_memory, "maze_b"),
        }
        workflow_stage = "workers_complete" if all(outcome in TERMINAL_WORKER_OUTCOMES for outcome in outcomes.values()) else "workers_running"
        return build_split_trace(
            analyst,
            worker_a,
            worker_b,
            base_memory,
            memory_store,
            [
                {
                    "type": "assignment",
                    "actor": "Azure WebUI Coordinator",
                    "target": normalized_role,
                    "label": "skip terminal worker",
                    "detail": f"{normalized_role} was not called because its own outcome or 50-call budget is already terminal.",
                    "llm_call_count": 0,
                }
            ],
            workflow_stage=workflow_stage,
            phase_override=18,
            phase_name_override="Human Feedback Telemetry",
            concept_override="Human Feedback Telemetry",
        )
    worker_input = dict(base_memory)
    worker_input["_control.worker_max_steps"] = 1
    worker_input["_control.worker_step_mode"] = True
    worker_input[f"_control.worker_remaining_llm_calls.{normalized_role}"] = max(
        0,
        WORKER_LLM_CALL_BUDGET - int(role_summary(existing_worker).get("llm_calls") or 0),
    )
    try:
        current_worker = call_role_agent(role_endpoint, normalized_role, worker_input)
    except Exception as exc:
        worker_state = base_memory.get(f"worker_state.{maze_id}")
        current_worker = worker_error_payload(normalized_role, exc, worker_state if isinstance(worker_state, dict) else None)
    worker = accumulated_role_payload(existing_worker, current_worker)

    agent_name = "maze-worker-agent-a" if normalized_role == "worker_a" else "maze-worker-agent-b"
    grouped_writes = memory_store.write_grouped(
        [
            (agent_name, ((worker.get("result") or {}).get("team_memory_writes") or [])),
            ("Azure WebUI Coordinator", [{"key": f"_role.{normalized_role}", "value": worker}]),
        ]
    )
    writes = grouped_writes[0]
    team_memory = memory_store.snapshot()
    worker_a = worker if normalized_role == "worker_a" else stored_role_payload(team_memory, "_role.worker_a", "worker_a")
    worker_b = worker if normalized_role == "worker_b" else stored_role_payload(team_memory, "_role.worker_b", "worker_b")
    outcomes = {
        "maze_a": worker_outcome_with_budget(worker_a, team_memory, "maze_a"),
        "maze_b": worker_outcome_with_budget(worker_b, team_memory, "maze_b"),
    }
    workflow_stage = "workers_complete" if all(outcome in TERMINAL_WORKER_OUTCOMES for outcome in outcomes.values()) else "workers_running"
    memory_events = [
        {
            "type": "assignment",
            "actor": "Azure WebUI Coordinator",
            "target": agent_name,
            "label": f"dispatch {normalized_role} step",
            "detail": f"Play requested one visible step from {agent_name}.",
            "llm_call_count": 0,
        },
        {
            "type": "memory",
            "actor": agent_name,
            "target": "Team Memory",
            "label": f"persist {normalized_role} step",
            "detail": f"Persisted {len(writes)} Team Memory records after one visible Worker step.",
            "memory_scope": "shared",
            "llm_call_count": 0,
        },
    ]
    return build_split_trace(
        analyst,
        worker_a,
        worker_b,
        team_memory,
        memory_store,
        memory_events,
        workflow_stage=workflow_stage,
        phase_override=18,
        phase_name_override="Human Feedback Telemetry",
        concept_override="Human Feedback Telemetry",
    )


def call_parallel_worker_steps_for_mission(run_id: str, roles: list[str]) -> dict[str, Any]:
    if not run_id:
        raise ValueError("run_id is required")
    normalized_roles: list[str] = []
    for role in roles:
        normalized_role = str(role).strip().lower().replace("-", "_")
        if normalized_role in {"worker_a", "worker_b"} and normalized_role not in normalized_roles:
            normalized_roles.append(normalized_role)
    if not normalized_roles:
        raise ValueError("at least one active worker role is required")

    analyst_endpoint, worker_a_endpoint, worker_b_endpoint = split_endpoints()
    endpoints = {"worker_a": worker_a_endpoint, "worker_b": worker_b_endpoint}
    if not analyst_endpoint or any(not endpoints[role] for role in normalized_roles):
        raise RuntimeError("split role agent endpoints are not fully configured")

    memory_store = build_team_memory_store(run_id)
    base_memory = memory_store.snapshot()
    analyst = stored_role_payload(base_memory, "_role.analyst", "analyst")
    role_agent_names = {"worker_a": "maze-worker-agent-a", "worker_b": "maze-worker-agent-b"}
    role_mazes = {"worker_a": "maze_a", "worker_b": "maze_b"}
    normalized_roles = [
        role
        for role in normalized_roles
        if worker_outcome_with_budget(stored_role_payload(base_memory, f"_role.{role}", role), base_memory, role_mazes[role])
        not in TERMINAL_WORKER_OUTCOMES
    ]

    if not normalized_roles:
        worker_a = stored_role_payload(base_memory, "_role.worker_a", "worker_a")
        worker_b = stored_role_payload(base_memory, "_role.worker_b", "worker_b")
        outcomes = {
            "maze_a": worker_outcome_with_budget(worker_a, base_memory, "maze_a"),
            "maze_b": worker_outcome_with_budget(worker_b, base_memory, "maze_b"),
        }
        workflow_stage = "workers_complete" if all(outcome in TERMINAL_WORKER_OUTCOMES for outcome in outcomes.values()) else "workers_running"
        return build_split_trace(
            analyst,
            worker_a,
            worker_b,
            base_memory,
            memory_store,
            [],
            workflow_stage=workflow_stage,
            phase_override=18,
            phase_name_override="Human Feedback Telemetry",
            concept_override="Human Feedback Telemetry",
        )

    worker_input = dict(base_memory)
    worker_input["_control.worker_max_steps"] = 1
    worker_input["_control.worker_step_mode"] = True
    for role in normalized_roles:
        existing_worker = stored_role_payload(base_memory, f"_role.{role}", role)
        worker_input[f"_control.worker_remaining_llm_calls.{role}"] = max(
            0,
            WORKER_LLM_CALL_BUDGET - int(role_summary(existing_worker).get("llm_calls") or 0),
        )

    memory_events: list[dict[str, Any]] = [
        {
            "type": "assignment",
            "actor": "Azure WebUI Coordinator",
            "target": ", ".join(role_agent_names[role] for role in normalized_roles),
            "label": "parallel worker tick",
            "detail": "Play requested one parallel execution tick. Active Workers reason at the same time, then Team Memory is updated after both responses return.",
            "llm_call_count": 0,
        }
    ]
    with ThreadPoolExecutor(max_workers=min(2, len(normalized_roles))) as executor:
        futures = {
            role: executor.submit(call_role_agent, endpoints[role], role, worker_input)
            for role in normalized_roles
        }
        workers: dict[str, dict[str, Any]] = {}
        for role in normalized_roles:
            previous = stored_role_payload(base_memory, f"_role.{role}", role)
            try:
                current = futures[role].result()
            except Exception as exc:
                maze_id = role_mazes[role]
                worker_state = base_memory.get(f"worker_state.{maze_id}")
                current = worker_error_payload(role, exc, worker_state if isinstance(worker_state, dict) else None)
            workers[role] = accumulated_role_payload(previous, current)

    next_tick_count = int(base_memory.get("_control.parallel_worker_tick_count") or 0) + 1
    write_groups: list[tuple[str, list[dict[str, Any]]]] = []
    for role in normalized_roles:
        agent_name = role_agent_names[role]
        worker = workers[role]
        write_groups.extend(
            [
                (agent_name, ((worker.get("result") or {}).get("team_memory_writes") or [])),
                ("Azure WebUI Coordinator", [{"key": f"_role.{role}", "value": worker}]),
            ]
        )
    write_groups.append(("Azure WebUI Coordinator", [{"key": "_control.parallel_worker_tick_count", "value": next_tick_count}]))
    persisted_groups = memory_store.write_grouped(write_groups)

    for role_index, role in enumerate(normalized_roles):
        agent_name = role_agent_names[role]
        writes = persisted_groups[role_index * 2]
        memory_events.append(
            {
                "type": "memory",
                "actor": agent_name,
                "target": "Team Memory",
                "label": f"persist {role} step",
                "detail": f"Persisted {len(writes)} Team Memory records after the parallel Worker tick.",
                "memory_scope": "shared",
                "llm_call_count": 0,
            }
        )

    team_memory = memory_store.snapshot()
    worker_a = workers.get("worker_a") or stored_role_payload(team_memory, "_role.worker_a", "worker_a")
    worker_b = workers.get("worker_b") or stored_role_payload(team_memory, "_role.worker_b", "worker_b")
    outcomes = {
        "maze_a": worker_outcome_with_budget(worker_a, team_memory, "maze_a"),
        "maze_b": worker_outcome_with_budget(worker_b, team_memory, "maze_b"),
    }
    workflow_stage = "workers_complete" if all(outcome in TERMINAL_WORKER_OUTCOMES for outcome in outcomes.values()) else "workers_running"
    trace = build_split_trace(
        analyst,
        worker_a,
        worker_b,
        team_memory,
        memory_store,
        memory_events,
        workflow_stage=workflow_stage,
        phase_override=18,
        phase_name_override="Human Feedback Telemetry",
        concept_override="Human Feedback Telemetry",
    )
    trace["summary"]["parallel_worker_roles_this_tick"] = normalized_roles
    trace["summary"]["parallel_worker_tick_count"] = next_tick_count
    return trace


def call_reviewer_for_mission(run_id: str) -> dict[str, Any]:
    if not run_id:
        raise ValueError("run_id is required")
    analyst_endpoint, worker_a_endpoint, worker_b_endpoint = split_endpoints()
    review_endpoint = reviewer_endpoint()
    if not all([analyst_endpoint, worker_a_endpoint, worker_b_endpoint, review_endpoint]):
        raise RuntimeError("reviewer endpoint or split role agent endpoints are not fully configured")

    memory_store = build_team_memory_store(run_id)
    base_memory = memory_store.snapshot()
    analyst = stored_role_payload(base_memory, "_role.analyst", "analyst")
    worker_a = stored_role_payload(base_memory, "_role.worker_a", "worker_a")
    worker_b = stored_role_payload(base_memory, "_role.worker_b", "worker_b")
    outcomes = {
        "maze_a": worker_outcome_with_budget(worker_a, base_memory, "maze_a"),
        "maze_b": worker_outcome_with_budget(worker_b, base_memory, "maze_b"),
    }
    if not all(outcome in TERMINAL_WORKER_OUTCOMES for outcome in outcomes.values()):
        raise RuntimeError("Reviewer can run only after both Workers have terminal outcomes")

    reviewer = call_role_agent(review_endpoint, "reviewer", base_memory)
    grouped_writes = memory_store.write_grouped(
        [
            ("maze-reviewer-agent", ((reviewer.get("result") or {}).get("team_memory_writes") or [])),
            ("Azure WebUI Coordinator", [{"key": "_role.reviewer", "value": reviewer}]),
        ]
    )
    writes = grouped_writes[0]
    team_memory = memory_store.snapshot()
    memory_events = [
        {
            "type": "assignment",
            "actor": "Azure WebUI Coordinator",
            "target": "maze-reviewer-agent",
            "label": "post-run review",
            "detail": "Worker execution is terminal. Reviewer Agent evaluates the completed run from Team Memory and feedback telemetry.",
            "llm_call_count": 0,
        },
        {
            "type": "memory",
            "actor": "maze-reviewer-agent",
            "target": "Team Memory",
            "label": "persist review",
            "detail": f"Persisted {len(writes)} review records after post-run evaluation.",
            "memory_scope": "shared",
            "llm_call_count": 0,
        },
    ]
    return build_split_trace(
        analyst,
        worker_a,
        worker_b,
        team_memory,
        memory_store,
        memory_events,
        reviewer=reviewer,
        workflow_stage="review_complete",
        phase_override=24,
        phase_name_override="Post-Run Evaluation Agent",
        concept_override="Agentic Evaluation",
    )


def call_configured_agent_path() -> tuple[str, dict[str, Any]]:
    analyst_endpoint, worker_a_endpoint, worker_b_endpoint = split_endpoints()
    if all([analyst_endpoint, worker_a_endpoint, worker_b_endpoint]):
        return "foundry-split-role-agents", call_split_role_agents()
    return "foundry-hosted-agent", call_foundry_agent()


def read_durable_memory(run_id: str) -> dict[str, Any]:
    if not run_id:
        raise ValueError("run_id query parameter is required")
    store = AzureBlobTeamMemoryStore(run_id)
    return {
        "run_id": run_id,
        "backend": store.backend_name,
        "container": TEAM_MEMORY_CONTAINER,
        "memory": store.snapshot(),
    }


def clean_feedback_note(value: Any) -> str:
    text = str(value or "").strip()
    return text[:500]


def build_feedback_event(payload: dict[str, Any]) -> dict[str, Any]:
    rating = str(payload.get("rating") or "").strip().lower()
    maze_id = str(payload.get("maze_id") or "").strip().lower()
    if rating not in {"up", "down"}:
        raise ValueError("rating must be up or down")
    if maze_id not in {"maze_a", "maze_b"}:
        raise ValueError("maze_id must be maze_a or maze_b")
    worker = "Worker Agent A" if maze_id == "maze_a" else "Worker Agent B"
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "event_name": "MazeFeedback",
        "phase": 18,
        "feedback_schema": "thumbs_v1",
        "run_id": str(payload.get("run_id") or "").strip()[:256],
        "maze_id": maze_id,
        "maze_label": "Maze A" if maze_id == "maze_a" else "Maze B",
        "worker": worker,
        "rating": rating,
        "note": clean_feedback_note(payload.get("note")),
        "worker_a_calls": int(summary.get("worker_a_llm_calls") or 0),
        "worker_b_calls": int(summary.get("worker_b_llm_calls") or 0),
        "worker_a_outcome": str(summary.get("worker_a_outcome") or "unknown")[:80],
        "worker_b_outcome": str(summary.get("worker_b_outcome") or "unknown")[:80],
        "workflow_stage": str(summary.get("workflow_stage") or "unknown")[:80],
        "created_at": utc_now(),
    }


def record_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    event = build_feedback_event(payload)
    logging.info("MazeFeedback %s", json.dumps(event, separators=(",", ":")))
    memory_persisted = False
    memory_error = None
    if event["run_id"]:
        try:
            store = build_team_memory_store(event["run_id"])
            memory = store.snapshot()
            existing = memory.get("feedback.events")
            feedback_events = existing if isinstance(existing, list) else []
            feedback_events.append(event)
            store.write_many("Azure WebUI Feedback", [{"key": "feedback.events", "value": feedback_events}])
            memory_persisted = True
        except Exception as exc:
            memory_error = str(exc)
            logging.warning("MazeFeedbackMemoryPersistFailed run_id=%s error=%s", event["run_id"], memory_error)
    return {
        "status": "recorded",
        "event_name": "MazeFeedback",
        "feedback": event,
        "app_insights_logged": True,
        "team_memory_persisted": memory_persisted,
        "team_memory_error": memory_error,
    }


def json_response(payload: dict[str, Any], status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload),
        status_code=status_code,
        mimetype="application/json",
    )


@app.route(route="{*route}", methods=["GET", "POST"])
def main(req: func.HttpRequest) -> func.HttpResponse:
    route = (req.route_params.get("route") or "").strip("/")
    if req.method == "GET" and route in ("", "index.html"):
        return func.HttpResponse((STATIC / "index.html").read_text(encoding="utf-8"), mimetype="text/html")
    if req.method == "GET" and route == "api/health":
        return json_response({"status": "ok"})
    if req.method == "GET" and route == "api/sample-trace":
        return json_response(load_sample_trace())
    if req.method == "GET" and route == "api/memory":
        try:
            return json_response(read_durable_memory(req.params.get("run_id", "")))
        except Exception as exc:
            return json_response({"error": str(exc)}, status_code=400)
    if req.method == "POST" and route == "api/mission":
        try:
            return json_response({"source": "foundry-analyst-mission", "trace": call_analyst_mission()})
        except Exception as exc:
            return json_response({"source": "mission-failed", "error": str(exc)}, status_code=502)
    if req.method == "POST" and route == "api/workers":
        try:
            body = req.get_json()
            run_id = body.get("run_id") if isinstance(body, dict) else ""
            return json_response({"source": "foundry-workers", "trace": call_workers_for_mission(str(run_id or ""))})
        except Exception as exc:
            return json_response({"source": "workers-failed", "error": str(exc)}, status_code=502)
    if req.method == "POST" and route == "api/worker-step":
        try:
            body = req.get_json()
            run_id = body.get("run_id") if isinstance(body, dict) else ""
            role = body.get("role") if isinstance(body, dict) else ""
            return json_response({"source": "foundry-worker-step", "trace": call_worker_step_for_mission(str(run_id or ""), str(role or ""))})
        except Exception as exc:
            return json_response({"source": "worker-step-failed", "error": str(exc)}, status_code=502)
    if req.method == "POST" and route == "api/worker-steps":
        try:
            body = req.get_json()
            run_id = body.get("run_id") if isinstance(body, dict) else ""
            roles = body.get("roles") if isinstance(body, dict) else []
            role_list = roles if isinstance(roles, list) else []
            return json_response({"source": "foundry-parallel-worker-steps", "trace": call_parallel_worker_steps_for_mission(str(run_id or ""), role_list)})
        except Exception as exc:
            return json_response({"source": "parallel-worker-steps-failed", "error": str(exc)}, status_code=502)
    if req.method == "POST" and route == "api/feedback":
        try:
            body = req.get_json()
            payload = body if isinstance(body, dict) else {}
            return json_response({"source": "maze-human-feedback", **record_feedback(payload)})
        except Exception as exc:
            return json_response({"source": "feedback-failed", "error": str(exc)}, status_code=400)
    if req.method == "POST" and route == "api/review":
        try:
            body = req.get_json()
            run_id = body.get("run_id") if isinstance(body, dict) else ""
            return json_response({"source": "foundry-reviewer", "trace": call_reviewer_for_mission(str(run_id or ""))})
        except Exception as exc:
            return json_response({"source": "review-failed", "error": str(exc)}, status_code=502)
    if req.method == "POST" and route == "api/run":
        try:
            source, trace = call_configured_agent_path()
            return json_response({"source": source, "trace": trace})
        except Exception as exc:
            return json_response(
                {
                    "source": "sample-fallback",
                    "error": str(exc),
                    "trace": load_sample_trace(),
                },
                status_code=502,
            )
    return json_response({"error": "not found", "route": route}, status_code=404)
