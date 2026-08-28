from __future__ import annotations

import azure.functions as func

from maze_common import json_response, move_payload, parse_body


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        status, payload = move_payload(parse_body(req))
        return json_response(payload, status)
    except Exception as exc:
        return json_response({"ok": False, "error": str(exc), "legal_moves": []}, 400)
