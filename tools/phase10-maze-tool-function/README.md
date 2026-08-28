# Phase 10 Maze Tool Function

This Azure Function App hosts the Maze Tool outside the hosted agent package.

It exposes:

```text
GET  /api/maze/health
GET  /api/maze/openapi.json
POST /api/maze/inspect
POST /api/maze/move
```

The inspect and move routes use Azure Functions function-level auth. The
function key is not committed to source. The hosted agent receives it through an
environment variable during deployment.

This does not make the maze smarter. It teaches the Azure-native external tool
pattern:

```text
Foundry hosted agent
  -> HTTP/OpenAPI Maze Tool contract
  -> Azure Function App
  -> typed tool result
```
