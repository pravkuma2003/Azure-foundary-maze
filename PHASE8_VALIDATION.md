# Phase 8 Validation

## Expected Result

```text
Azure WebUI package is created.
Web app deploys to Azure Functions Consumption.
UI loads sample trace without secrets.
Live Run Hosted Agent button returns a Foundry-hosted trace after managed-identity RBAC propagation.
```

## Command

```bash
python3 scripts/phase8_azure_webui_adapter.py --deploy
```

## Observed Validation

```text
Root page: HTTP 200
/api/health: HTTP 200
/api/sample-trace: HTTP 200 and returns packaged maze trace JSON
/api/run before WebUI RBAC: reached Foundry but returned HTTP 403 for WebUI managed identity
/api/run after WebUI RBAC: reached hosted agent boundary and temporarily returned HTTP 500 during RBAC propagation
/api/run after hosted-agent RBAC propagation: HTTP 200, source=foundry-hosted-agent, provider=foundry, model=gpt41mini-maze, llm_call_budget_used=17
```

## Completed WebUI Permission

The WebUI managed identity is:

```text
3dd0a192-5ac9-4a76-9ba8-52ee5cfab0b0
```

The project-scoped role assignment completed for live `/api/run` is:

```bash
az role assignment create --assignee 3dd0a192-5ac9-4a76-9ba8-52ee5cfab0b0 --role "Foundry User" --scope /subscriptions/0ecda5cf-8c20-4818-856e-0acac9ce9aa9/resourceGroups/rg-maze-foundry-lab/providers/Microsoft.CognitiveServices/accounts/maze-foundry-prav-ada483/projects/maze-migration-lab
```

## Completed Hosted-Agent Permission

The hosted maze agent managed identity is:

```text
ef0c0ce9-ae88-416e-8619-637a4d6f4c96
```

The account-scoped role assignment completed for hosted-agent LLM calls is:

```bash
az role assignment create --assignee ef0c0ce9-ae88-416e-8619-637a4d6f4c96 --role "Cognitive Services OpenAI User" --scope /subscriptions/0ecda5cf-8c20-4818-856e-0acac9ce9aa9/resourceGroups/rg-maze-foundry-lab/providers/Microsoft.CognitiveServices/accounts/maze-foundry-prav-ada483
```
