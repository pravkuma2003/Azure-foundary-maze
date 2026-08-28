# Customer Non-Prod Azure Deployment Runbook

## Purpose

This runbook explains how to duplicate the current Maze Foundry learning app
from the personal Azure subscription into a customer non-prod Azure tenant.

The target state is a separate customer-owned Azure environment with its own:

```text
customer Azure tenant
customer non-prod subscription
customer resource group
customer Azure AI Foundry account and project
customer model deployment
customer Foundry-hosted Analyst and Worker agents
customer Maze Tool Function App
customer WebUI Function App
customer storage accounts
customer App Insights and Log Analytics workspace
customer RBAC assignments
```

The goal is not to connect the customer tenant back to the personal lab. The
goal is to reuse the working source code and recreate the architecture in the
customer tenant with no changes or very small configuration-only changes.

## Current Personal Lab Baseline

The working personal-lab deployment is:

```text
Resource group: rg-maze-foundry-lab
Foundry account: maze-foundry-prav-ada483
Foundry project: maze-migration-lab
Model deployment: gpt41mini-maze
WebUI Function App: maze-webui-func-prav-ada483
Maze Tool Function App: maze-tool-func-prav-ada483
Hosted agents:
  maze-analyst-agent
  maze-worker-agent-a
  maze-worker-agent-b
Team Memory: Azure Blob Storage container named team-memory
Telemetry: Application Insights connected to Log Analytics
```

The currently relevant source folders are:

```text
hosted/phase13-split-role-agents/
webui/phase8-azure-webui/
tools/phase10-maze-tool-function/
tools/phase11-foundry-toolbox/
scripts/
```

The important point: the role-agent code, Maze Tool code, and WebUI code should
stay mostly the same. Tenant-specific values should move into deployment
parameters and Azure app settings.

## High-Level Architecture

```text
Browser
  -> Azure WebUI Function App
       -> durable Team Memory in Azure Blob Storage
       -> Foundry-hosted Analyst Agent
       -> Foundry-hosted Worker Agent A
       -> Foundry-hosted Worker Agent B
            -> Foundry toolbox MCP endpoint
                 -> OpenAPI wrapper
                      -> Maze Tool Azure Function App
       -> Application Insights / Log Analytics
```

The WebUI is the coordinator. It does not reason with an LLM. It calls hosted
role agents, persists Team Memory, and renders the timeline.

The Analyst and Worker agents are independent Foundry-hosted agents. They use
Pydantic AI in their runtime code and call the Foundry model deployment.

The Maze Tool is a real external Azure Function. It validates maze moves and
inspection requests. It does not solve the maze for the workers.

## Customer Tenant Assumptions

This runbook assumes:

```text
Target environment: customer non-prod Azure tenant
Network access: only reachable while connected to company VPN
Subscription scope: a customer non-prod subscription
Deployment machine: Mac/Linux workstation or company build runner
Source: copy of the current functioning GitHub code
Authentication: Azure device-code login or customer-approved equivalent
Cost posture: minimum viable non-prod resources
```

If the customer tenant enforces private endpoints, public network restrictions,
or policy-driven resource naming, handle those as deployment parameters. Do not
hardcode customer-specific values into source files that will be pushed back to
GitHub.

## Required Access

You need these permissions in the customer tenant:

```text
Azure subscription or resource group:
  Contributor, or an equivalent custom role that can create the required resources

RBAC assignment scope:
  Owner or User Access Administrator, or a customer admin who can run role assignments

Azure AI Foundry:
  Permission to create or use a Foundry account/project
  Permission to deploy or use the selected model
  Permission to create hosted agents and toolboxes

Function Apps:
  Permission to create Function Apps, storage accounts, App Service plans,
  managed identities, and app settings

Monitoring:
  Permission to create or attach Application Insights and Log Analytics workspace
```

If your account can create resources but cannot assign RBAC, split the process:
you deploy the resources, then give the customer admin a short list of exact role
assignments to apply.

## Local Prerequisites

Install or verify:

```bash
git --version
az version
azd version
python3 --version
zip -v
```

Recommended:

```bash
az extension add --name application-insights
az extension add --name log-analytics
azd ext install microsoft.foundry
```

Notes:

```text
az  = Azure CLI, used for Azure resource operations and RBAC.
azd = Azure Developer CLI, used here for Foundry hosted-agent and toolbox deploys.
```

The exact Foundry `azd` commands can shift because hosted agents and toolbox
support are still evolving. Check the installed command help in the customer
environment before running:

```bash
azd ai --help
azd ai agent --help
azd ai toolbox --help
```

## Source Code Preparation

Customer deployment should use a standalone Maze deployment repository or a
minimal deployment archive. The customer machine should not clone the larger
development repository.

Customer-facing source shape:

```text
repo root
  README.md
  CUSTOMER_NONPROD_AZURE_DEPLOYMENT_RUNBOOK.md
  hosted/phase13-split-role-agents/
  webui/phase8-azure-webui/
  tools/phase10-maze-tool-function/
  tools/phase11-foundry-toolbox/
  scripts/
  requirements-phase6.txt
```

Customer clone command:

```bash
git clone <standalone-maze-migration-repo-url> maze-foundry-customer-nonprod
cd maze-foundry-customer-nonprod
```

If GitHub is not allowed from the customer network, provide a customer-approved
source archive containing only the standalone repo contents.

Source-package rule:

```text
Include only the Maze Foundry migration app.
Exclude unrelated parent-repo folders, trading files, reports, caches,
local run artifacts, local Azure state, virtual environments, and secrets.
```

Recommended customer handoff shape is:

```text
standalone repo containing only this Maze Foundry migration app
```

This keeps the customer environment focused on the Azure Foundry migration app
and avoids unrelated source code, unrelated history, and accidental exposure of
non-customer artifacts.

## Secret Hygiene

Do not commit:

```text
.env
.azure/
local.settings.json
function keys
connection strings
SAS URLs
App Insights connection strings
Azure access tokens
customer tenant IDs if customer policy treats them as sensitive
customer subscription IDs if customer policy treats them as sensitive
```

Before publishing or handing off code, run:

```bash
git status --short
rg -n "AccountKey=|DefaultEndpointsProtocol=|BEGIN .*PRIVATE KEY|AZURE_CLIENT_SECRET|FOUNDRY_API_KEY|x-functions-key|sig=" .
```

Expected result: no real secrets. Placeholder examples such as
`<customer-tenant-id>` are fine.

## Customer Deployment Parameters

Create an untracked local parameter file for the customer tenant:

```bash
cp .env.customer-nonprod.example .env.customer-nonprod
```

If the example file does not exist yet, create a local-only file with this shape:

```bash
export CUSTOMER_TENANT_ID="<customer-tenant-id>"
export CUSTOMER_SUBSCRIPTION_ID="<customer-nonprod-subscription-id>"
export AZURE_LOCATION="eastus2"
export AZURE_RESOURCE_GROUP="rg-maze-foundry-nonprod"

export FOUNDRY_ACCOUNT_NAME="<globally-unique-foundry-account-name>"
export FOUNDRY_PROJECT_NAME="maze-migration-nonprod"
export FOUNDRY_PROJECT_ENDPOINT="https://<foundry-account>.services.ai.azure.com/api/projects/maze-migration-nonprod"

export FOUNDRY_MODEL_DEPLOYMENT="gpt41mini-maze"
export FOUNDRY_MODEL_NAME="gpt-4.1-mini"
export FOUNDRY_MODEL_VERSION="2025-04-14"
export FOUNDRY_MODEL_SKU="GlobalStandard"
export FOUNDRY_MODEL_CAPACITY="10"

export WEBUI_FUNCTION_APP_NAME="<globally-unique-webui-function-name>"
export WEBUI_STORAGE_ACCOUNT="<globally-unique-webui-storage-name>"
export TOOL_FUNCTION_APP_NAME="<globally-unique-maze-tool-function-name>"
export TOOL_STORAGE_ACCOUNT="<globally-unique-tool-storage-name>"

export APP_INSIGHTS_NAME="maze-foundry-nonprod-ai"
export LOG_ANALYTICS_WORKSPACE="maze-foundry-nonprod-law"

export ANALYST_AGENT_NAME="maze-analyst-agent"
export WORKER_A_AGENT_NAME="maze-worker-agent-a"
export WORKER_B_AGENT_NAME="maze-worker-agent-b"
export TOOLBOX_NAME="maze-toolbox-dynamic"
export TEAM_MEMORY_CONTAINER="team-memory"
```

Keep this file out of Git.

For a low-cost customer non-prod lab, start with model capacity `10` unless the
customer has approved a higher request-per-minute and token-per-minute limit.
The personal lab used capacity `50` after rate-limit testing, but that does not
need to be the customer default.

## Login and Subscription Selection

Connect to the company VPN first.

Login with device code:

```bash
az login --tenant "$CUSTOMER_TENANT_ID" --use-device-code
az account set --subscription "$CUSTOMER_SUBSCRIPTION_ID"
az account show --query "{tenantId:tenantId, subscriptionId:id, name:name}" --output table
```

Login for Azure Developer CLI:

```bash
azd auth login --tenant-id "$CUSTOMER_TENANT_ID" --use-device-code
```

If `azd auth login` does not support the exact flags in the installed version,
use:

```bash
azd auth login --help
```

Then follow the customer-approved device-code flow.

## Deployment Order

Use this order. It matches the working lab and keeps each boundary testable.

```text
1. Create resource group.
2. Create Foundry account and Foundry project.
3. Deploy the model.
4. Deploy Maze Tool Function App.
5. Register Foundry toolbox/OpenAPI/MCP wrapper for the Maze Tool.
6. Deploy Analyst, Worker A, and Worker B as independent Foundry-hosted agents.
7. Deploy WebUI Function App.
8. Configure WebUI app settings with hosted-agent endpoints and storage.
9. Assign RBAC to managed identities.
10. Validate health, mission generation, worker execution, telemetry, and feedback.
```

## Step 1 - Create Resource Group

```bash
az group create \
  --name "$AZURE_RESOURCE_GROUP" \
  --location "$AZURE_LOCATION" \
  --tags app=maze-foundry-lab environment=nonprod costProfile=learning
```

Use one resource group so cleanup is clear and customer cost reporting is easy.

## Step 2 - Create Foundry Account and Project

The current personal-lab script is:

```bash
python3 scripts/phase4_foundry_project_model.py --apply
```

Before using it in the customer tenant, parameterize the hardcoded values near
the top of the script:

```text
LOCATION
RESOURCE_GROUP
FOUNDRY_RESOURCE_PREFIX or FOUNDRY_ACCOUNT_NAME
FOUNDRY_PROJECT
MODEL_DEPLOYMENT
MODEL_NAME
MODEL_VERSION
MODEL_SKU
MODEL_CAPACITY
```

For the customer tenant, prefer reading those values from environment variables
instead of editing them directly:

```python
LOCATION = os.environ.get("AZURE_LOCATION", "eastus2")
RESOURCE_GROUP = os.environ["AZURE_RESOURCE_GROUP"]
FOUNDRY_PROJECT = os.environ.get("FOUNDRY_PROJECT_NAME", "maze-migration-nonprod")
MODEL_DEPLOYMENT = os.environ.get("FOUNDRY_MODEL_DEPLOYMENT", "gpt41mini-maze")
```

If you use direct Azure CLI commands instead of the script, the resource pattern
is:

```bash
az cognitiveservices account create \
  --name "$FOUNDRY_ACCOUNT_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --location "$AZURE_LOCATION" \
  --kind AIServices \
  --sku S0 \
  --custom-domain "$FOUNDRY_ACCOUNT_NAME"
```

Then create the Foundry project under that account using the Foundry portal,
`azd`, or the same ARM/REST shape used by `scripts/phase4_foundry_project_model.py`.

Validation:

```bash
az cognitiveservices account show \
  --name "$FOUNDRY_ACCOUNT_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --query "{name:name, location:location, endpoint:properties.endpoint}" \
  --output table
```

## Step 3 - Deploy the Model

Use the smallest model and capacity that teaches the lesson. For this lab, use
`gpt-4.1-mini` or a customer-approved equivalent. If the customer wants to use a
different Foundry-hosted model that is closer to the local model, keep the
deployment name stable and update only the model deployment configuration.

Example:

```bash
az cognitiveservices account deployment create \
  --name "$FOUNDRY_ACCOUNT_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --deployment-name "$FOUNDRY_MODEL_DEPLOYMENT" \
  --model-name "$FOUNDRY_MODEL_NAME" \
  --model-version "$FOUNDRY_MODEL_VERSION" \
  --model-format OpenAI \
  --sku-name "$FOUNDRY_MODEL_SKU" \
  --sku-capacity "$FOUNDRY_MODEL_CAPACITY"
```

If `Standard` quota is zero in the customer region, use a customer-approved
alternative such as `GlobalStandard`, a different region, or a different model.

Validation:

```bash
az cognitiveservices account deployment show \
  --name "$FOUNDRY_ACCOUNT_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --deployment-name "$FOUNDRY_MODEL_DEPLOYMENT" \
  --query "{deployment:name, sku:sku.name, capacity:sku.capacity, state:properties.provisioningState}" \
  --output table
```

## Step 4 - Deploy Maze Tool Function App

Source folder:

```text
tools/phase10-maze-tool-function/
```

Current endpoints:

```text
GET  /api/maze/health
GET  /api/maze/openapi.json
POST /api/maze/inspect
POST /api/maze/move
```

The Maze Tool is deterministic. It validates and applies moves. It does not plan
or solve the maze for the workers.

Create storage and the Function App:

```bash
az storage account create \
  --name "$TOOL_STORAGE_ACCOUNT" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --location "$AZURE_LOCATION" \
  --sku Standard_LRS

az functionapp create \
  --name "$TOOL_FUNCTION_APP_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --storage-account "$TOOL_STORAGE_ACCOUNT" \
  --consumption-plan-location "$AZURE_LOCATION" \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --os-type Linux
```

Package and deploy:

```bash
cd tools/phase10-maze-tool-function
zip -r ../../runs/customer_maze_tool.zip . -x ".venv/*" "__pycache__/*" "*.pyc"
cd ../..

az functionapp deployment source config-zip \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$TOOL_FUNCTION_APP_NAME" \
  --src runs/customer_maze_tool.zip
```

Validation:

```bash
curl "https://$TOOL_FUNCTION_APP_NAME.azurewebsites.net/api/maze/health"
curl "https://$TOOL_FUNCTION_APP_NAME.azurewebsites.net/api/maze/openapi.json"
```

For function-level auth operations, retrieve the function key securely:

```bash
az functionapp keys list \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$TOOL_FUNCTION_APP_NAME" \
  --query "functionKeys.default" \
  --output tsv
```

Do not paste or commit that key.

## Step 5 - Register Foundry Toolbox

The working lab uses a Foundry toolbox that exposes the Maze Tool through an
MCP-compatible endpoint. The underlying tool is an OpenAPI wrapper around the
Maze Tool Function App.

Source folder:

```text
tools/phase11-foundry-toolbox/
```

Customer-specific values to update in the toolbox JSON:

```text
OpenAPI URL:
  https://<tool-function-app>.azurewebsites.net/api/maze/openapi.json

Auth:
  function key or customer-approved auth mechanism
```

Create or update the toolbox:

```bash
azd ai toolbox create "$TOOLBOX_NAME" \
  --from-file tools/phase11-foundry-toolbox/maze_toolbox_dynamic.json \
  --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT" \
  --output json
```

Get the MCP endpoint:

```bash
azd ai toolbox show "$TOOLBOX_NAME" \
  --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT" \
  --output json
```

Record the returned endpoint as:

```bash
export MAZE_TOOL_MCP_ENDPOINT="<toolbox-mcp-endpoint>"
```

Validation:

```bash
azd ai toolbox show "$TOOLBOX_NAME" \
  --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT" \
  --output table
```

## Step 6 - Deploy Split Foundry-Hosted Agents

Source folder:

```text
hosted/phase13-split-role-agents/
```

The deployed role agents should be:

```text
maze-analyst-agent
maze-worker-agent-a
maze-worker-agent-b
```

Before deploying in the customer tenant, update `hosted/phase13-split-role-agents/azure.yaml`
so it no longer points to the personal lab endpoint:

```yaml
services:
  maze-migration-lab:
    host: azure.ai.project
    endpoint: ${FOUNDRY_PROJECT_ENDPOINT}
```

Keep these environment variables in each agent service:

```yaml
env:
  AZURE_AI_MODEL_DEPLOYMENT_NAME: ${FOUNDRY_MODEL_DEPLOYMENT}
  FOUNDRY_MODEL_DEPLOYMENT: ${FOUNDRY_MODEL_DEPLOYMENT}
  FOUNDRY_PROJECT_ENDPOINT: ${FOUNDRY_PROJECT_ENDPOINT}
  MAZE_PROVIDER: foundry
  MAZE_HOSTED_ROLE: analyst | worker_a | worker_b
  MAZE_TOOL_MCP_ENDPOINT: ${MAZE_TOOL_MCP_ENDPOINT}
```

The role value changes by agent:

```text
maze-analyst-agent   -> MAZE_HOSTED_ROLE=analyst
maze-worker-agent-a  -> MAZE_HOSTED_ROLE=worker_a
maze-worker-agent-b  -> MAZE_HOSTED_ROLE=worker_b
```

Deploy:

```bash
cd hosted/phase13-split-role-agents

azd env new customer-nonprod
azd env set FOUNDRY_PROJECT_ENDPOINT "$FOUNDRY_PROJECT_ENDPOINT"
azd env set FOUNDRY_MODEL_DEPLOYMENT "$FOUNDRY_MODEL_DEPLOYMENT"
azd env set MAZE_TOOL_MCP_ENDPOINT "$MAZE_TOOL_MCP_ENDPOINT"

azd deploy maze-analyst-agent --no-prompt --timeout 1200
azd deploy maze-worker-agent-a --no-prompt --timeout 1200
azd deploy maze-worker-agent-b --no-prompt --timeout 1200
```

Validation:

```bash
azd ai agent show maze-analyst-agent --output table
azd ai agent show maze-worker-agent-a --output table
azd ai agent show maze-worker-agent-b --output table
```

Capture the three hosted-agent endpoints. You will use them in the WebUI
Function App settings:

```bash
export FOUNDRY_ANALYST_AGENT_ENDPOINT="<analyst-agent-endpoint>"
export FOUNDRY_WORKER_AGENT_A_ENDPOINT="<worker-a-agent-endpoint>"
export FOUNDRY_WORKER_AGENT_B_ENDPOINT="<worker-b-agent-endpoint>"
```

## Step 7 - Deploy WebUI Function App

Source folder:

```text
webui/phase8-azure-webui/
```

The WebUI hosts:

```text
GET  /
GET  /api/health
GET  /api/memory
POST /api/mission
POST /api/worker-step
POST /api/worker-steps
POST /api/feedback
```

Create storage and the Function App:

```bash
az storage account create \
  --name "$WEBUI_STORAGE_ACCOUNT" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --location "$AZURE_LOCATION" \
  --sku Standard_LRS

az functionapp create \
  --name "$WEBUI_FUNCTION_APP_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --storage-account "$WEBUI_STORAGE_ACCOUNT" \
  --consumption-plan-location "$AZURE_LOCATION" \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --os-type Linux \
  --assign-identity
```

Package and deploy:

```bash
cd webui/phase8-azure-webui
zip -r ../../runs/customer_webui.zip . -x ".venv/*" "__pycache__/*" "*.pyc"
cd ../..

az functionapp deployment source config-zip \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$WEBUI_FUNCTION_APP_NAME" \
  --src runs/customer_webui.zip
```

## Step 8 - Configure WebUI App Settings

Set the WebUI settings:

```bash
az functionapp config appsettings set \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$WEBUI_FUNCTION_APP_NAME" \
  --settings \
    FUNCTIONS_WORKER_RUNTIME=python \
    TEAM_MEMORY_BACKEND=azure-blob \
    TEAM_MEMORY_CONTAINER="$TEAM_MEMORY_CONTAINER" \
    FOUNDRY_ANALYST_AGENT_ENDPOINT="$FOUNDRY_ANALYST_AGENT_ENDPOINT" \
    FOUNDRY_WORKER_AGENT_A_ENDPOINT="$FOUNDRY_WORKER_AGENT_A_ENDPOINT" \
    FOUNDRY_WORKER_AGENT_B_ENDPOINT="$FOUNDRY_WORKER_AGENT_B_ENDPOINT" \
    FOUNDRY_DELETE_SESSIONS_AFTER_CALL=false
```

The WebUI uses `AzureWebJobsStorage` for the Function runtime and Team Memory.
The `team-memory` blob container is created lazily when the first run writes
memory.

Keep `FOUNDRY_DELETE_SESSIONS_AFTER_CALL=false` unless the customer explicitly
approves automatic deletion of Foundry hosted-agent sessions. Hosted-agent
session cleanup can delete persistent session filesystem volumes, so treat it as
an intentional lifecycle decision.

## Step 9 - Configure Monitoring

For a low-cost non-prod lab, prefer one shared Application Insights component
and one Log Analytics workspace.

Create or attach:

```bash
az monitor log-analytics workspace create \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --workspace-name "$LOG_ANALYTICS_WORKSPACE" \
  --location "$AZURE_LOCATION"

az monitor app-insights component create \
  --app "$APP_INSIGHTS_NAME" \
  --location "$AZURE_LOCATION" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --workspace "$LOG_ANALYTICS_WORKSPACE" \
  --application-type web
```

Get the connection string:

```bash
az monitor app-insights component show \
  --app "$APP_INSIGHTS_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --query connectionString \
  --output tsv
```

Set it on both Function Apps:

```bash
az functionapp config appsettings set \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$WEBUI_FUNCTION_APP_NAME" \
  --settings APPLICATIONINSIGHTS_CONNECTION_STRING="<app-insights-connection-string>"

az functionapp config appsettings set \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$TOOL_FUNCTION_APP_NAME" \
  --settings APPLICATIONINSIGHTS_CONNECTION_STRING="<app-insights-connection-string>"
```

Do not commit the connection string. In customer environments, Key Vault or
customer-managed deployment variables may be required.

## Step 10 - RBAC

Get the WebUI managed identity principal:

```bash
WEBUI_PRINCIPAL_ID=$(
  az functionapp identity show \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --name "$WEBUI_FUNCTION_APP_NAME" \
    --query principalId \
    --output tsv
)
```

Assign project-scoped Foundry access:

```bash
az role assignment create \
  --assignee "$WEBUI_PRINCIPAL_ID" \
  --role "Foundry User" \
  --scope "/subscriptions/$CUSTOMER_SUBSCRIPTION_ID/resourceGroups/$AZURE_RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/$FOUNDRY_ACCOUNT_NAME/projects/$FOUNDRY_PROJECT_NAME"
```

If model calls fail with authorization errors, the customer admin may also need
to assign a model/account role such as:

```bash
az role assignment create \
  --assignee "$WEBUI_PRINCIPAL_ID" \
  --role "Cognitive Services OpenAI User" \
  --scope "/subscriptions/$CUSTOMER_SUBSCRIPTION_ID/resourceGroups/$AZURE_RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/$FOUNDRY_ACCOUNT_NAME"
```

Storage access depends on how `AzureWebJobsStorage` is configured:

```text
Connection-string mode:
  The Function App uses storage account keys in app settings.

Identity mode:
  Assign the Function App managed identity Blob/Data roles on the storage account.
```

The current lab uses the normal Function App storage setting. For stricter
customer tenants, prefer identity-based storage access if their platform team
requires it.

## Step 11 - Network and VPN Considerations

Because the customer tenant is reachable only from company VPN, confirm the
network posture before deployment.

Minimal non-prod option:

```text
Function Apps have public endpoints.
Access is controlled by function keys, Entra/RBAC for backend calls, and customer policy.
Deployment runs from a VPN-connected machine.
```

Private-only option:

```text
Function Apps use access restrictions or private endpoints.
Storage uses private endpoints.
Foundry account/project uses private networking where supported.
Private DNS zones are configured for privatelink names.
The deployment machine or build runner must resolve and reach private endpoints.
```

Private-only is more enterprise-realistic but more expensive and operationally
heavier. For the first customer non-prod learning deployment, use the minimal
option unless customer policy requires private endpoints.

## Step 12 - Validate the Deployment

Health checks:

```bash
curl "https://$TOOL_FUNCTION_APP_NAME.azurewebsites.net/api/maze/health"
curl "https://$WEBUI_FUNCTION_APP_NAME.azurewebsites.net/api/health"
```

Open the WebUI:

```text
https://<webui-function-app-name>.azurewebsites.net/
```

Functional validation:

```text
1. Click Run Fresh Maze.
2. Confirm Analyst-generated Maze A and Maze B appear before Worker execution.
3. Click Play.
4. Confirm Worker Agent A and Worker Agent B move in parallel ticks.
5. Confirm each worker has its own 50-call budget.
6. Confirm one worker reaching a limit does not stop the other worker.
7. Add thumbs-up or thumbs-down feedback per maze.
8. Confirm feedback saved in the UI.
```

API validation examples:

```bash
curl -X POST "https://$WEBUI_FUNCTION_APP_NAME.azurewebsites.net/api/mission" \
  -H "Content-Type: application/json" \
  -d '{"phase":18}'

curl -X POST "https://$WEBUI_FUNCTION_APP_NAME.azurewebsites.net/api/worker-steps" \
  -H "Content-Type: application/json" \
  -d '{"run_id":"<run-id-from-mission>"}'

curl -X POST "https://$WEBUI_FUNCTION_APP_NAME.azurewebsites.net/api/feedback" \
  -H "Content-Type: application/json" \
  -d '{
        "run_id":"<run-id>",
        "maze_id":"maze_a",
        "maze_label":"Maze A",
        "worker":"Worker Agent A",
        "rating":"up",
        "note":"Worker reached the goal cleanly."
      }'
```

## Step 13 - Verify Feedback in Log Analytics

In the Log Analytics workspace, use:

```kusto
AppTraces
| where Message startswith "MazeFeedback "
| extend payload = parse_json(substring(Message, strlen("MazeFeedback ")))
| project TimeGenerated,
          run_id=tostring(payload.run_id),
          phase=toint(payload.phase),
          maze_id=tostring(payload.maze_id),
          maze_label=tostring(payload.maze_label),
          worker=tostring(payload.worker),
          rating=tostring(payload.rating),
          note=tostring(payload.note),
          worker_a_calls=toint(payload.worker_a_calls),
          worker_b_calls=toint(payload.worker_b_calls),
          workflow_stage=tostring(payload.workflow_stage)
| order by TimeGenerated desc
```

In Application Insights Logs, use:

```kusto
traces
| where message startswith "MazeFeedback "
| extend payload = parse_json(substring(message, strlen("MazeFeedback ")))
| project timestamp,
          run_id=tostring(payload.run_id),
          maze_id=tostring(payload.maze_id),
          worker=tostring(payload.worker),
          rating=tostring(payload.rating),
          note=tostring(payload.note),
          worker_a_calls=toint(payload.worker_a_calls),
          worker_b_calls=toint(payload.worker_b_calls)
| order by timestamp desc
```

## Step 14 - Validate Team Memory

The current WebUI writes durable Team Memory to Blob Storage using the WebUI
Function App storage account.

Expected container:

```text
team-memory
```

Expected memory categories include:

```text
maze layouts
assignment plan
worker state
worker call counts
agent session IDs
feedback.events
```

Inspect with Azure Portal:

```text
Storage Account
  -> Containers
  -> team-memory
```

Or with CLI:

```bash
az storage blob list \
  --account-name "$WEBUI_STORAGE_ACCOUNT" \
  --container-name "$TEAM_MEMORY_CONTAINER" \
  --auth-mode login \
  --output table
```

If `--auth-mode login` fails, either assign data-plane storage roles to your
user or inspect through the portal with customer-approved access.

## Step 15 - Customer Acceptance Checklist

Use this checklist before calling the customer non-prod deployment complete:

```text
[ ] Azure CLI is logged into the customer tenant, not the personal tenant.
[ ] All resources are in the customer non-prod subscription.
[ ] Resource group is customer-owned and tagged.
[ ] Foundry account and project exist in the customer tenant.
[ ] Model deployment exists and has approved capacity.
[ ] Maze Tool Function App health endpoint works.
[ ] Foundry toolbox exists and points to the customer Maze Tool Function App.
[ ] Analyst, Worker A, and Worker B hosted agents are running.
[ ] WebUI Function App loads from the customer URL.
[ ] Run Fresh Maze creates a new Analyst-generated maze before Worker execution.
[ ] Play invokes workers and renders parallel ticks.
[ ] Worker A and Worker B budgets are independent.
[ ] Feedback buttons save thumbs-up/thumbs-down events.
[ ] Feedback appears in App Insights or Log Analytics.
[ ] No personal-lab endpoints remain in app settings or azure.yaml.
[ ] No secrets were committed.
```

## Cost Controls

Recommended customer non-prod defaults:

```text
One resource group.
One Foundry project.
One small model deployment.
Consumption-plan Azure Functions unless customer policy requires another plan.
One WebUI Function App.
One Maze Tool Function App.
One shared Application Insights component.
One shared Log Analytics workspace.
Keep existing separate Function App storage accounts unless consolidation is
explicitly reviewed.
No Cosmos DB, Container Apps, API Management, VNet integration, or private
endpoints unless customer policy requires them.
```

Function Apps require storage. Multiple Function Apps can technically share a
storage account, but separate storage accounts are simpler for isolation and
avoid Function host ID and operational coupling problems. For this learning app,
the cost difference is usually small. Consolidate only after customer policy and
runtime behavior are understood.

## What Must Change Between Personal and Customer Tenants

These values must be replaced:

```text
tenant ID
subscription ID
resource group name
location if customer requires a different region
Foundry account name
Foundry project name
Foundry project endpoint
model deployment capacity/SKU if quota differs
Function App names
storage account names
Application Insights name
Log Analytics workspace name
hosted-agent endpoints
toolbox endpoint
function keys
RBAC principal IDs
```

These should not need material logic changes:

```text
Pydantic AI role-agent code
Analyst prompt and output schema
Worker prompt and output schema
Maze Tool inspect/move behavior
WebUI timeline rendering
parallel worker tick behavior
feedback payload schema
Log Analytics query shape
```

## Known Lab-Specific Hardcoding

Some current scripts were built phase-by-phase for the personal lab and contain
personal resource names. Before using them in a customer tenant, convert the
constants to environment variables or use a customer deployment branch.

Known examples:

```text
scripts/phase4_foundry_project_model.py
scripts/phase8_azure_webui_adapter.py
scripts/phase10_external_maze_tool.py
scripts/phase11_foundry_toolbox_registration.py
scripts/phase12_foundry_toolbox_mcp_runtime.py
scripts/phase13_split_independent_role_agents.py
scripts/phase14_azure_durable_team_memory.py
scripts/phase15_monitoring_consolidation.py
scripts/phase16_dynamic_mission_design.py
hosted/phase13-split-role-agents/azure.yaml
```

For customer deployment, do not globally search-and-replace personal values in a
rushed way. Replace them with parameter reads, then deploy using customer
environment variables.

## Rollback and Cleanup

For non-prod, the cleanest rollback is deleting the customer resource group:

```bash
az group delete \
  --name "$AZURE_RESOURCE_GROUP" \
  --yes \
  --no-wait
```

Only run this when the customer approves deletion. It removes Function Apps,
storage, Foundry resources, monitoring, Team Memory, and telemetry in that
resource group.

If customer policy requires partial cleanup:

```text
Disable WebUI Function App first.
Disable Maze Tool Function App.
Delete hosted-agent versions or agents only after session lifecycle is reviewed.
Delete toolbox after agents no longer reference it.
Delete model deployment if no other lab depends on it.
Delete storage last, because it contains Function runtime state and Team Memory.
Delete monitoring last if logs need to be retained.
```

## Recommended First Customer Dry Run

Use this as the first deployment objective:

```text
Deploy into one customer non-prod resource group.
Keep public Function App endpoints unless customer policy blocks that.
Use model capacity 10.
Use one shared App Insights and LAW.
Use separate storage accounts for WebUI and Maze Tool.
Deploy only Analyst, Worker A, Worker B.
Do not deploy the deleted monolithic agent.
Run one fresh maze.
Submit one thumbs-up and one thumbs-down feedback item.
Validate both feedback rows in LAW.
```

After that works, decide whether the next customer phase should be:

```text
private networking
identity-based storage instead of connection strings
Key Vault-backed tool keys
custom dashboard/workbook for agent quality feedback
CI/CD deployment from customer-controlled GitHub or Azure DevOps
```

## Reference Links

Microsoft references used while preparing this runbook:

```text
Hosted agents:
https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent

azure.yaml for hosted agents:
https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/azure-yaml-reference

Foundry toolboxes:
https://learn.microsoft.com/azure/foundry/agents/how-to/tools/toolbox

Foundry tool catalog:
https://learn.microsoft.com/en-au/azure/ai-foundry/agents/concepts/tool-catalog

Azure Functions storage:
https://learn.microsoft.com/en-us/azure/azure-functions/storage-considerations

Azure Functions monitoring:
https://learn.microsoft.com/en-us/azure/azure-functions/functions-monitoring

Application Insights overview:
https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview
```
