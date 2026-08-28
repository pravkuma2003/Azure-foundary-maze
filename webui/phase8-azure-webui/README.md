# Phase 8 Azure WebUI Adapter

Azure Functions-hosted WebUI for the Foundry monolithic maze agent.

The browser talks only to this web app:

```text
Browser
  -> native /api/run route inside Azure Functions
  -> managed identity token
  -> Foundry hosted agent endpoint
  -> trace JSON
  -> play/pause/replay maze timeline
```

The app includes a packaged sample trace so the UI still loads even before
managed-identity RBAC is complete.
