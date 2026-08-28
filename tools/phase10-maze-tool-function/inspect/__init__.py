from __future__ import annotations

import azure.functions as func

from maze_common import inspect_payload, json_response, parse_body


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        status, payload = inspect_payload(parse_body(req))
        return json_response(payload, status)
    except Exception as exc:
        return json_response({"ok": False, "error": str(exc), "legal_moves": []}, 400)
