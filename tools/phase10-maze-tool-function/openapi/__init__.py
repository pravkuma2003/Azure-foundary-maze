from __future__ import annotations

import azure.functions as func

from maze_common import json_response, openapi_spec


def main(req: func.HttpRequest) -> func.HttpResponse:
    base_url = req.url.split("/api/maze/openapi.json")[0]
    return json_response(openapi_spec(base_url))
