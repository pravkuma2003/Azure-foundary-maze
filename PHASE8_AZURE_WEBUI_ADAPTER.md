# Phase 8 - Azure-Hosted WebUI Adapter

## Objective

Host the maze playback UI in Azure Functions while keeping Foundry authentication
server-side.

## Architecture

```text
Browser
  -> Azure Functions WebUI
  -> native Azure Functions HTTP route
  -> Function App managed identity
  -> Foundry hosted agent endpoint
  -> trace JSON
  -> play/pause/replay timeline
```

The browser never receives an Azure token or API key.

## Cost Choice

The deployment uses Azure Functions Consumption because this is a small learning
UI and proxy and the App Service Free plan path hit a zero-VM quota limit in the
personal subscription. A storage account is required by Azure Functions.

## Current Azure URL

```text
https://maze-webui-func-prav-ada483.azurewebsites.net
```

## Current Boundary

Packaged sample playback works now. Live hosted-agent playback reaches Foundry
but requires explicit managed-identity RBAC approval for the WebUI identity.
