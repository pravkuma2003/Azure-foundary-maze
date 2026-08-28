from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Any
from urllib import request


DIRECTIONS: dict[str, tuple[int, int]] = {
    "north": (-1, 0),
    "south": (1, 0),
    "west": (0, -1),
    "east": (0, 1),
}


@dataclass(frozen=True)
class MazeToolRequest:
    operation: str
    maze_id: str
    position: tuple[int, int]
    move: str | None = None

    def to_trace(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["position"] = list(self.position)
        return payload


@dataclass(frozen=True)
class MazeToolResult:
    ok: bool
    maze_id: str
    position: tuple[int, int]
    legal_moves: list[str]
    new_position: tuple[int, int] | None = None
    error: str | None = None

    def to_trace(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["position"] = list(self.position)
        if self.new_position is not None:
            payload["new_position"] = list(self.new_position)
        return payload


class MazeToolProgram:
    """Stable program boundary around maze inspection and movement."""

    runtime_name = "in-process"

    def __init__(self, *, maze_id: str, label: str, rows: list[str]) -> None:
        self.maze_id = maze_id
        self.label = label
        self.rows = rows

    def is_open(self, position: tuple[int, int]) -> bool:
        row, col = position
        return 0 <= row < len(self.rows) and 0 <= col < len(self.rows[0]) and self.rows[row][col] != "#"

    def inspect(self, position: tuple[int, int]) -> MazeToolResult:
        legal = []
        for move, (dr, dc) in DIRECTIONS.items():
            candidate = (position[0] + dr, position[1] + dc)
            if self.is_open(candidate):
                legal.append(move)
        return MazeToolResult(
            ok=True,
            maze_id=self.maze_id,
            position=position,
            legal_moves=legal,
        )

    def move(self, position: tuple[int, int], move: str) -> MazeToolResult:
        inspection = self.inspect(position)
        if move not in DIRECTIONS:
            return MazeToolResult(
                ok=False,
                maze_id=self.maze_id,
                position=position,
                legal_moves=inspection.legal_moves,
                error=f"unknown move: {move}",
            )
        if move not in inspection.legal_moves:
            return MazeToolResult(
                ok=False,
                maze_id=self.maze_id,
                position=position,
                legal_moves=inspection.legal_moves,
                error=f"illegal move from {position}: {move}",
            )
        dr, dc = DIRECTIONS[move]
        new_position = (position[0] + dr, position[1] + dc)
        return MazeToolResult(
            ok=True,
            maze_id=self.maze_id,
            position=position,
            legal_moves=inspection.legal_moves,
            new_position=new_position,
        )


class ExternalMazeToolProgram:
    """HTTP-backed Maze Tool implementation with the same caller contract."""

    runtime_name = "external-http"

    def __init__(self, *, maze_id: str, label: str, rows: list[str], base_url: str, function_key: str | None = None) -> None:
        self.maze_id = maze_id
        self.label = label
        self.rows = rows
        self.base_url = base_url.rstrip("/")
        self.function_key = function_key or ""

    def is_open(self, position: tuple[int, int]) -> bool:
        return bool(self.inspect(position).legal_moves or position == (4, 4))

    def inspect(self, position: tuple[int, int]) -> MazeToolResult:
        return self._post(
            "/api/maze/inspect",
            {
                "maze_id": self.maze_id,
                "position": list(position),
                "rows": self.rows,
            },
        )

    def move(self, position: tuple[int, int], move: str) -> MazeToolResult:
        return self._post(
            "/api/maze/move",
            {
                "maze_id": self.maze_id,
                "position": list(position),
                "move": move,
                "rows": self.rows,
            },
        )

    def _post(self, path: str, payload: dict[str, Any]) -> MazeToolResult:
        headers = {"Content-Type": "application/json"}
        if self.function_key:
            headers["x-functions-key"] = self.function_key
        req = request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with request.urlopen(req, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
        return _result_from_payload(body)


class FoundryToolboxMCPMazeToolProgram:
    """Foundry toolbox MCP-backed Maze Tool implementation."""

    runtime_name = "foundry-toolbox-mcp"
    _cached_token: str = ""
    _cached_token_expires_at: float = 0.0
    _cached_tool_names: dict[str, dict[str, str]] = {}

    def __init__(self, *, maze_id: str, label: str, rows: list[str], endpoint: str) -> None:
        self.maze_id = maze_id
        self.label = label
        self.rows = rows
        self.endpoint = endpoint

    def is_open(self, position: tuple[int, int]) -> bool:
        return bool(self.inspect(position).legal_moves or position == (4, 4))

    def inspect(self, position: tuple[int, int]) -> MazeToolResult:
        return self._call(
            "inspectMaze",
            {
                "maze_id": self.maze_id,
                "position": list(position),
                "rows": self.rows,
            },
        )

    def move(self, position: tuple[int, int], move: str) -> MazeToolResult:
        return self._call(
            "moveInMaze",
            {
                "maze_id": self.maze_id,
                "position": list(position),
                "move": move,
                "rows": self.rows,
            },
        )

    def _call(self, operation_id: str, arguments: dict[str, Any]) -> MazeToolResult:
        return asyncio.run(self._call_async(operation_id, arguments))

    async def _call_async(self, operation_id: str, arguments: dict[str, Any]) -> MazeToolResult:
        from pydantic_ai.mcp import MCPToolset

        token = self._azure_ai_token()
        toolset = MCPToolset(
            self.endpoint,
            auth=token,
            tool_error_behavior="error",
            init_timeout=60,
            read_timeout=120,
        )
        async with toolset:
            tool_name = await self._tool_name(toolset, operation_id)
            payload = await toolset.direct_call_tool(tool_name, arguments)
        return _result_from_any_payload(payload)

    async def _tool_name(self, toolset: Any, operation_id: str) -> str:
        cached = self._cached_tool_names.get(self.endpoint, {})
        if operation_id in cached:
            return cached[operation_id]

        tools = await toolset.client.list_tools()
        names = [str(getattr(tool, "name", "")) for tool in tools]
        aliases = [
            operation_id,
            f"maze_tool_api.{operation_id}",
            f"maze_tool_api_{operation_id}",
            f"maze_tool_api__{operation_id}",
        ]
        for alias in aliases:
            if alias in names:
                self._cached_tool_names.setdefault(self.endpoint, {})[operation_id] = alias
                return alias
        for name in names:
            if operation_id.lower() in name.lower():
                self._cached_tool_names.setdefault(self.endpoint, {})[operation_id] = name
                return name
        raise RuntimeError(f"Foundry toolbox MCP endpoint did not expose {operation_id}; tools={names}")

    @classmethod
    def _azure_ai_token(cls) -> str:
        now = time.time()
        if cls._cached_token and now < cls._cached_token_expires_at - 120:
            return cls._cached_token
        from azure.identity import AzureCliCredential, DefaultAzureCredential

        credential_error: Exception | None = None
        for credential in (DefaultAzureCredential(exclude_interactive_browser_credential=True), AzureCliCredential()):
            try:
                token = credential.get_token("https://ai.azure.com/.default")
                cls._cached_token = token.token
                cls._cached_token_expires_at = float(token.expires_on)
                return token.token
            except Exception as exc:
                credential_error = exc
        raise RuntimeError(f"Unable to obtain Azure AI token for Foundry toolbox MCP endpoint: {credential_error}")


def build_maze_tool(
    *,
    maze_id: str,
    label: str,
    rows: list[str],
) -> MazeToolProgram | ExternalMazeToolProgram | FoundryToolboxMCPMazeToolProgram:
    mcp_endpoint = os.environ.get("MAZE_TOOL_MCP_ENDPOINT", "").strip()
    if mcp_endpoint:
        return FoundryToolboxMCPMazeToolProgram(maze_id=maze_id, label=label, rows=rows, endpoint=mcp_endpoint)
    base_url = os.environ.get("MAZE_TOOL_BASE_URL", "").strip()
    if base_url:
        return ExternalMazeToolProgram(
            maze_id=maze_id,
            label=label,
            rows=rows,
            base_url=base_url,
            function_key=os.environ.get("MAZE_TOOL_KEY"),
        )
    return MazeToolProgram(maze_id=maze_id, label=label, rows=rows)


def _result_from_any_payload(payload: Any) -> MazeToolResult:
    if isinstance(payload, dict):
        if "structured_content" in payload and isinstance(payload["structured_content"], dict):
            return _result_from_payload(payload["structured_content"])
        return _result_from_payload(payload)
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                if "text" in item and isinstance(item["text"], str):
                    try:
                        return _result_from_payload(json.loads(item["text"]))
                    except json.JSONDecodeError:
                        continue
                if "structured_content" in item and isinstance(item["structured_content"], dict):
                    return _result_from_payload(item["structured_content"])
        raise RuntimeError(f"Unable to parse MCP tool result list: {payload}")
    if isinstance(payload, str):
        return _result_from_payload(json.loads(payload))
    text = getattr(payload, "text", None)
    if isinstance(text, str):
        return _result_from_payload(json.loads(text))
    structured = getattr(payload, "structured_content", None) or getattr(payload, "structuredContent", None)
    if isinstance(structured, dict):
        return _result_from_payload(structured)
    raise RuntimeError(f"Unable to parse MCP tool result: {payload!r}")


def _result_from_payload(payload: dict[str, Any]) -> MazeToolResult:
    position = tuple(payload.get("position") or (0, 0))
    new_position_payload = payload.get("new_position")
    new_position = tuple(new_position_payload) if new_position_payload is not None else None
    return MazeToolResult(
        ok=bool(payload.get("ok")),
        maze_id=str(payload.get("maze_id") or ""),
        position=(int(position[0]), int(position[1])),
        legal_moves=[str(move) for move in payload.get("legal_moves") or []],
        new_position=(int(new_position[0]), int(new_position[1])) if new_position is not None else None,
        error=payload.get("error"),
    )
