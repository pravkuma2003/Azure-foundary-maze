from __future__ import annotations

import azure.functions as func

from maze_common import json_response


def main(req: func.HttpRequest) -> func.HttpResponse:
    return json_response({"status": "ok", "service": "maze-tool-function"})
