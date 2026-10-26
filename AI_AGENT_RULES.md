# AI Agent Rules — PortalJustPlay

> **Compatibility document:** `RULE.md` is the canonical bootstrap entry point. Read `RULE.md` first; it routes to this detailed policy, the codebase map, changelog and client-specific rules. This file remains here for clients and existing prompts that reference `AI_AGENT_RULES.md` directly.

Follow the workflow below regardless of the IDE, coding agent, or model being used.

## Mission

Reduce context and token usage without reducing correctness. Use the indexed code knowledge first, then inspect only the smallest source slices needed to make and verify a decision.

## Transparency before action

Every AI model/agent working in this repository must make its next intended actions visible before executing them. Do not silently inspect, edit, run commands, index data, or change configuration.

At the start of a task and before each new group of consequential actions, state briefly:

1. **Goal** — what this step is intended to accomplish.
2. **Reason** — why the step is needed and what evidence or uncertainty it addresses.
3. **Scope** — files, symbols, tools, commands, or data boundaries that will be touched.
4. **Expected result** — what will be checked or produced afterward.

The agent does **not** need to reveal private chain-of-thought or hidden token-by-token reasoning. A concise, observable plan, decision summary, assumptions, risks, and tool/action list is required. The agent may proceed without waiting for user approval unless the task is destructive, outside the requested scope, requires a product decision, or has a material security/data-loss risk. If the plan changes, announce the change before taking the new action.

### Mandatory approval gate

Before writing or modifying code, the agent must stop and ask the user for a decision when **any one** of these conditions is true:

- the planned change creates or updates more than 10 files;
- the request requires deciding what is correct/incorrect, or choosing between materially different implementations;
- the request changes a business or technical workflow;
- the request affects security, permissions, privacy, credentials, data exposure, or compliance;
- the request changes agent policy, repository rules, MCP/indexing policy, or development workflow;
- the request changes an existing feature's behavior, scope, acceptance criteria, or user-facing contract.

In these cases, first provide a concise plan containing scope, affected files/modules, alternatives, risks, assumptions, validation strategy, and estimated file count. Then ask the user one focused question with the decision options. Do not start implementation, broad file edits, migrations, destructive commands, or configuration changes until the user answers. Reading a small amount of context needed to prepare the plan is allowed, but it must be announced first.

If none of these conditions applies, the agent may proceed autonomously within the requested scope while still following the transparency-before-action rule. If the change grows beyond 10 files or enters one of the protected categories during implementation, stop immediately, report the new scope, and ask for approval before continuing.

Use this format when practical:

```text
Plan: <goal>
Why: <reason/evidence>
Scope: <files/tools/commands>
Expected: <validation/result>
```

## Required workflow

1. Read this file and `docs/AI_CODEBASE_MAP.md`.
2. Classify the request:
   - **Known symbol/route/flow/impact** → use CodeGraph first.
   - **Unknown implementation, architecture, docs, Docker, config, or cross-module meaning** → use Codebase Memory first.
   - **Known file and precise requested edit** → inspect only the relevant section, then edit.
3. From the graph result, select at most 3–5 directly relevant symbols/files.
4. Read source by symbol or line range. Do not read a whole large file or app unless a specific gap requires it.
5. Make the smallest safe change.
6. Review the diff and run the narrowest relevant checks/tests.
7. If the index is stale, sync/index it before compensating by reading many files.
8. If the task changes modules, features, routes, workflows, integrations, data models, commands, deployment, or agent instructions, update the living documentation before finishing.
9. Review the documentation diff together with the code diff; documentation drift is an incomplete task.

## Living documentation workflow

Documentation is part of the implementation, not an optional follow-up. The canonical files are:

- `AI_AGENT_RULES.md`: universal agent behavior and context policy.
- `docs/AI_CODEBASE_MAP.md`: current architecture, module registry, entry points, workflows, integrations and index boundaries.
- `docs/AI_CHANGELOG.md`: short history of architecture/workflow/module changes and the reason for them.
- `AGENTS.md`: bootstrap pointer only; keep it short and do not duplicate policy.

Before editing code, identify whether the task affects any documented area. After editing code, update the matching document using this matrix:

| Change | Required documentation update |
|---|---|
| New Django app/module/package | Add or update the module registry and its responsibility/entry points in `docs/AI_CODEBASE_MAP.md`. |
| New feature or user-facing capability | Add the feature flow, route/API, main symbols and related tests to the map. |
| New/changed route, API, command or worker job | Update entry points and the affected workflow in the map. |
| Changed business workflow | Update the relevant workflow section and add an entry to `docs/AI_CHANGELOG.md`. |
| New model/relationship or migration with architectural impact | Update data/domain notes; record a changelog entry. |
| New external integration or infrastructure service | Update integrations and deployment notes; document secrets only by variable names, never values. |
| Changed AI/MCP/indexing workflow | Update `AI_AGENT_RULES.md`, the map's AI workflow section, and the changelog if behavior changes. |
| Bug fix with no architectural/workflow impact | Update the changelog only when it changes a documented behavior or prevents a recurring agent mistake. |
| Pure style/text/refactor with no behavior impact | No map update required; still review whether a changelog note is useful. |

For every new module or feature, record at minimum: name, purpose, owning app/package, entry points, important symbols, data/integration dependencies, background jobs if any, tests, and the date/change reference. Keep descriptions concise and link to source paths instead of copying source code.

### Documentation update sequence

1. Use graph/search to identify the affected symbols and current documentation section.
2. Implement the code change.
3. Sync the relevant index.
4. Update the map/registry and workflow section.
5. Add a concise dated entry to `docs/AI_CHANGELOG.md` for architecture, workflow, module, integration or agent-policy changes.
6. Verify that all source paths mentioned still exist and that the docs diff matches the code diff.
7. In the final response, explicitly state which documentation was updated or why no update was required.

Never silently rewrite historical entries. If a workflow changes, update its current description and add a new changelog entry explaining the old-to-new transition.

## Tool roles

### CodeGraph

Use CodeGraph for structural questions:

- route → view → service → model flow;
- symbol/class/function search;
- callers and callees;
- trace from A to B;
- impact/blast-radius analysis;
- indexed file and symbol context.

Preferred order: `context` or `search` → `trace`/`callers`/`callees` → `impact` when changing existing behavior.

### Codebase Memory

Use Codebase Memory for semantic and cross-boundary questions:

- when the implementation name is unknown;
- architecture and module discovery;
- code connected to documentation, Docker, deployment, or configuration;
- cross-project or infrastructure relationships.

Do not call both systems for the same question when the first result is sufficient. Summarize graph results; do not paste large graph output into the working context.

### Direct file tools

Use Read/Grep only after narrowing the target. Prefer symbol snippets or line ranges. After an edit, inspect the diff rather than rereading the entire file.

## Context budget

Default budget:

- Initial discovery: one graph context plus at most two focused follow-up queries.
- Small task: at most 3 directly relevant files or roughly 800 source lines.
- Larger task: split into bounded areas; do not load the repository into one context.
- Exceed the budget only when naming the missing evidence and why it is required.

## Prohibited defaults

- Do not read the whole repository, app, or large file at the start.
- Do not grep broadly after the graph already identified the symbol.
- Do not reconstruct a call path with many separate searches when one trace/context query can provide it.
- Do not infer secrets or ignored-file contents from the graph.
- Do not index or expose `.env*`, credentials, media, backups, `.venv`, `.git`, `.codegraph`, build artifacts, or temporary dumps.
- Do not modify code merely to improve indexing.

## Index and repository paths

Workspace root:

```text
D:\Project\PortalJustPlay
```

Local MCP configuration:

```text
D:\Project\PortalJustPlay\.cursor\mcp.json
```

MCP server names in the local Cursor configuration:

- `codegraph`
- `codebase-memory`

If the current client exposes MCP tools, use those servers. If it does not, use the local CLIs from the workspace root where available:

```powershell
codegraph status
codegraph sync
codegraph query <search>
codegraph context <task>
codegraph callers <symbol>
codegraph callees <symbol>
codegraph impact <symbol>
codegraph files

codebase-memory-mcp cli --quiet list_projects
codebase-memory-mcp cli --quiet search_graph --project <project> --name-pattern <pattern>
```

Do not invent MCP tool names. Inspect the server's available tools/help when the client exposes different names.

## Validation

After changes, use the smallest relevant checks first:

```powershell
python manage.py check
python manage.py test --noinput --verbosity=1
python -m compileall -q <changed-python-files>
git diff --check
git status --short
```

Run only applicable commands when the task is documentation/configuration-only. Never claim a test was run if it was not run.

## Response contract

At the end, report briefly:

1. files changed;
2. graph/index context used;
3. tests/checks run and their result;
4. any stale-index, ignored-file, or uncertainty limitation.

## User command

The user may invoke this policy in any vibe-coding tool with:

> Đọc `RULE.md`, làm theo luồng tài liệu mà file này chỉ dẫn, sau đó thực hiện yêu cầu theo đúng workflow graph-first; không đọc toàn bộ file/repository nếu chưa có lý do.

Treat that instruction as mandatory for the task.
