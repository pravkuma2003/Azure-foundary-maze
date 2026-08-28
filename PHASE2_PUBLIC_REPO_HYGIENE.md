# Phase 2: Public Repo and Secret Hygiene

## Learning Objective

Create a public-safe candidate copy of the local maze app before publishing to
GitHub or provisioning Azure resources.

## New Concept

Secret hygiene boundary.

```text
Source app:
  can contain local host assumptions, generated traces, and local review URLs

Public candidate:
  must contain portable source, docs, examples, and ignore rules only
```

## What Phase 2 Does

```text
Copies source code, scripts, and curriculum docs.
Excludes generated runs and visual HTML.
Redacts private IP addresses and local filesystem paths.
Adds .env.example for local model configuration.
Adds .gitignore rules so real .env files and generated outputs stay out of Git.
Scans the exported candidate for remaining blocking machine-specific values.
```

## What Phase 2 Does Not Do

```text
No GitHub repository is created yet.
No Azure login is performed.
No Azure resources are provisioned.
No Foundry project, model, agent, storage, or function is created.
```

## Cost Impact

```text
Azure cost: $0
Reason: this phase is local-only.
```

## Deliverable

```text
exports/multi-agent-reasoning-from-scratch-public/
runs/phase2_public_repo_hygiene.json
visuals/PHASE2_VISUAL.html
PHASE2_VALIDATION.md
```

## Knowledge Check

1. Why are generated traces excluded from the public candidate?
2. Why is `.env.example` safe while `.env` is not?
3. Why should GitHub publishing happen before Azure provisioning?
4. Which values block public publishing?
5. Why is Phase 2 still a zero-cost phase?
