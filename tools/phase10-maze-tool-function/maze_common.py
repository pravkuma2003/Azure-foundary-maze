from __future__ import annotations

import json
from typing import Any

import azure.functions as func


DIRECTIONS: dict[str, tuple[int, int]] = {
    "north": (-1, 0),
    "south": (1, 0),
    "west": (0, -1),
    "east": (0, 1),
}

MAZES: dict[str, dict[str, Any]] = {
    "maze_a": {
        "label": "Maze A",
        "rows": [
            "S..#.",
            "##.#.",
            ".....",
            ".###.",
            "....G",
        ],
    },
    "maze_b": {
        "label": "Maze B",
        "rows": [
            "S.#..",
            "..#..",
            "#....",
            ".###.",
            "....G",
        ],
    },
}


def json_response(payload: dict[str, Any], status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload),
        status_code=status_code,
        mimetype="application/json",
    )


def parse_body(req: func.HttpRequest) -> dict[str, Any]:
    try:
        payload = req.get_json()
    except ValueError as exc:
        raise ValueError("request body must be JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")
    return payload


def parse_position(payload: dict[str, Any]) -> tuple[int, int]:
    raw = payload.get("position")
    if not isinstance(raw, list) or len(raw) != 2:
        raise ValueError("position must be [row, col]")
    return int(raw[0]), int(raw[1])


def maze_rows(maze_id: str) -> list[str]:
    maze = MAZES.get(maze_id)
    if not maze:
        raise ValueError(f"unknown maze_id: {maze_id}")
    return list(maze["rows"])


def rows_from_payload(payload: dict[str, Any]) -> list[str]:
    raw_rows = payload.get("rows")
    if raw_rows is None:
        return maze_rows(str(payload.get("maze_id") or ""))
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError("rows must be a non-empty list of strings")
    rows = [str(row) for row in raw_rows]
    width = len(rows[0])
    if not width or any(len(row) != width for row in rows):
        raise ValueError("rows must form a rectangular maze")
    chars = "".join(rows)
    if any(ch not in ".#SG" for ch in chars):
        raise ValueError("rows may contain only '.', '#', 'S', and 'G'")
    if chars.count("S") != 1 or chars.count("G") != 1:
        raise ValueError("rows must contain exactly one S and exactly one G")
    return rows


def is_open(position: tuple[int, int], rows: list[str]) -> bool:
    row, col = position
    return 0 <= row < len(rows) and 0 <= col < len(rows[0]) and rows[row][col] != "#"


def legal_moves(position: tuple[int, int], rows: list[str]) -> list[str]:
    legal = []
    for move, (dr, dc) in DIRECTIONS.items():
        candidate = (position[0] + dr, position[1] + dc)
        if is_open(candidate, rows):
            legal.append(move)
    return legal


def inspect_payload(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    maze_id = str(payload.get("maze_id") or "")
    position = parse_position(payload)
    rows = rows_from_payload(payload)
    if not is_open(position, rows):
        return 400, {
            "ok": False,
            "maze_id": maze_id,
            "position": list(position),
            "legal_moves": [],
            "error": f"blocked or out-of-bounds position: {position}",
        }
    return 200, {
        "ok": True,
        "maze_id": maze_id,
        "position": list(position),
        "legal_moves": legal_moves(position, rows),
    }


def move_payload(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    maze_id = str(payload.get("maze_id") or "")
    position = parse_position(payload)
    requested_move = str(payload.get("move") or "")
    rows = rows_from_payload(payload)
    current_legal_moves = legal_moves(position, rows) if is_open(position, rows) else []
    if requested_move not in DIRECTIONS:
        return 400, {
            "ok": False,
            "maze_id": maze_id,
            "position": list(position),
            "legal_moves": current_legal_moves,
            "error": f"unknown move: {requested_move}",
        }
    if requested_move not in current_legal_moves:
        return 400, {
            "ok": False,
            "maze_id": maze_id,
            "position": list(position),
            "legal_moves": current_legal_moves,
            "error": f"illegal move from {position}: {requested_move}",
        }
    dr, dc = DIRECTIONS[requested_move]
    new_position = (position[0] + dr, position[1] + dc)
    return 200, {
        "ok": True,
        "maze_id": maze_id,
        "position": list(position),
        "legal_moves": current_legal_moves,
        "new_position": list(new_position),
    }


def openapi_spec(base_url: str) -> dict[str, Any]:
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Maze Tool API",
            "version": "1.0.0",
            "description": "External Maze Tool for inspect and move validation.",
        },
        "servers": [{"url": base_url}],
        "paths": {
            "/api/maze/inspect": {
                "post": {
                    "operationId": "inspectMaze",
                    "summary": "Return legal moves from the current maze position.",
                    "security": [{"functionKey": []}],
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/InspectRequest"}}}},
                    "responses": {"200": {"description": "Legal moves", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/MazeToolResult"}}}}},
                }
            },
            "/api/maze/move": {
                "post": {
                    "operationId": "moveInMaze",
                    "summary": "Validate and apply a requested maze move.",
                    "security": [{"functionKey": []}],
                    "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/MoveRequest"}}}},
                    "responses": {"200": {"description": "Validated move result", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/MazeToolResult"}}}}},
                }
            },
        },
        "components": {
            "securitySchemes": {
                "functionKey": {"type": "apiKey", "in": "header", "name": "x-functions-key"}
            },
            "schemas": {
                "InspectRequest": {
                    "type": "object",
                    "required": ["maze_id", "position"],
                    "properties": {
                        "maze_id": {"type": "string", "enum": ["maze_a", "maze_b"]},
                        "position": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "integer"}},
                        "rows": {"type": "array", "items": {"type": "string"}, "description": "Optional per-run maze layout. If omitted, the default maze_id layout is used."},
                    },
                },
                "MoveRequest": {
                    "type": "object",
                    "required": ["maze_id", "position", "move"],
                    "properties": {
                        "maze_id": {"type": "string", "enum": ["maze_a", "maze_b"]},
                        "position": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "integer"}},
                        "move": {"type": "string", "enum": ["north", "south", "west", "east"]},
                        "rows": {"type": "array", "items": {"type": "string"}, "description": "Optional per-run maze layout. If omitted, the default maze_id layout is used."},
                    },
                },
                "MazeToolResult": {
                    "type": "object",
                    "required": ["ok", "maze_id", "position", "legal_moves"],
                    "properties": {
                        "ok": {"type": "boolean"},
                        "maze_id": {"type": "string"},
                        "position": {"type": "array", "items": {"type": "integer"}},
                        "legal_moves": {"type": "array", "items": {"type": "string"}},
                        "new_position": {"type": "array", "items": {"type": "integer"}},
                        "error": {"type": "string"},
                    },
                },
            },
        },
    }
