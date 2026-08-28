# Phase 15 Validation

## Expected Result

```text
Maze Tool Function App points to shared WebUI Application Insights.
Duplicate Maze Tool Application Insights is removed.
Duplicate Maze Tool managed Log Analytics workspace resource group is removed.
Storage accounts remain unchanged.
App Service plan remains unchanged.
```

## Live Result

```text
status: complete
shared_app_insights: maze-webui-func-prav-ada483
removed_app_insights: maze-tool-func-prav-ada483
removed_managed_law_resource_group: ai_maze-tool-func-prav-ada483_a4fb8274-f365-4b8c-b42a-badc02c7562a_managed
storage_accounts_changed: 0
app_service_plans_changed: 0
webui_health: 200
tool_health: 200
```
