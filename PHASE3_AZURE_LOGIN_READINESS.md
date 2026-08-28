# Phase 3: Azure Login and Subscription Readiness

## Learning Objective

Authenticate to Azure and verify subscription readiness before creating any
Foundry resources.

## New Concept

Cloud control-plane readiness.

```text
Local repo readiness:
  source is public-safe

Azure readiness:
  CLI exists
  identity is authenticated
  intended personal subscription is visible
  cost guardrails are understood
  deployment CLI is available
```

## What Phase 3 Does

```text
Checks Azure CLI availability.
Checks Azure CLI login status.
Checks visible subscriptions without storing full subscription IDs.
Checks Azure Developer CLI availability.
Documents device-code login commands.
Confirms this phase creates zero Azure resources.
```

## What Phase 3 Does Not Do

```text
No resource group is created.
No Foundry project is created.
No model is deployed.
No Foundry-hosted agent is deployed.
No Azure Functions, Cosmos DB, Storage, or monitoring resource is created.
```

## Commands

```bash
az login --tenant cciepraveenyahoo.onmicrosoft.com --use-device-code
az account list --output table
az account set --subscription "Visual Studio Enterprise Subscription"
azd auth login --use-device-code
azd auth status
```

## Cost Impact

```text
Azure cost: $0
Reason: login and subscription discovery do not provision resources.
```

## Cost Readiness

Before Phase 4, decide whether to create a budget alert in the Azure portal or
with the Azure CLI budget command. This is optional for the lab, but recommended
for a personal subscription before any model or hosted-agent deployment.

## Deliverable

```text
runs/phase3_azure_login_readiness.json
visuals/PHASE3_VISUAL.html
PHASE3_VALIDATION.md
```

## Knowledge Check

1. Why do we verify subscription readiness before provisioning?
2. Why is device-code login useful from Mac/Linux terminals?
3. Why is Azure Developer CLI separate from Azure CLI?
4. Why is this phase still zero-cost?
5. Which readiness gates must pass before Phase 4?
