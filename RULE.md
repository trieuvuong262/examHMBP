# Repository AI Rule Bootstrap — PortalJustPlay

> **Single entry point:** Before doing any work in this repository, read this file first. Do not ask the user to list every policy/map file; this file routes you to the next documents.

## Required reading order

1. `RULE.md` — this bootstrap and decision gate.
2. `AI_AGENT_RULES.md` — detailed universal policy: transparency, approval gate, graph-first workflow, context budget, validation and response contract.
3. `docs/AI_CODEBASE_MAP.md` — current architecture, module registry, feature/workflow registry and entry points.
4. `docs/AI_CHANGELOG.md` — recent architecture, workflow, module and agent-policy changes when the task touches an existing documented area.
5. Client-specific rules only when using that client:
   - Cursor: `.cursor/rules/ai-context-optimization.mdc`, `.cursor/rules/codegraph-workflow.mdc` if present.
   - Kiro: `.kiro/steering/codegraph-workflow.md`, `.kiro/steering/execution-preferences.md`.

## Mandatory first response

Before reading source, editing, running commands, indexing, or changing configuration, announce a concise plan:

```text
Plan: <what will be done>
Why: <reason/evidence>
Scope: <files/tools/commands>
Expected: <validation/result>
```

Do not reveal private chain-of-thought. Report only the observable plan, assumptions, risks and decisions.

## Mandatory approval gate

Stop and ask the user before coding if any one condition applies:

- more than 10 files are expected to be created or updated;
- the task requires deciding correctness, choosing materially different implementations, or defining acceptance criteria;
- a business/technical workflow changes;
- security, permissions, privacy, credentials, data exposure or compliance is affected;
- agent policy, repository rules, MCP/indexing policy or development workflow changes;
- an existing feature's behavior, scope or user-facing contract changes.

For the approval question, include the affected scope, estimated file count, options, risks and validation strategy. Context reading needed to prepare the plan is allowed only after announcing it. Do not code, migrate, make broad configuration changes or run destructive actions until the user answers. If the scope crosses a gate during implementation, stop and ask again.

## Task instruction

After following the reading order and approval gate, perform the request using the graph-first workflow. Keep context narrow, update living documentation when the change affects documented architecture/workflows, and report files, graph/index context, checks and limitations at the end.

## Short user prompt

Use this prompt in any AI coding tool:

> Đọc `RULE.md`, làm theo luồng tài liệu mà file này chỉ dẫn, rồi xử lý yêu cầu theo graph-first workflow. Trước khi hành động hãy nêu plan; nếu gặp approval gate thì dừng và hỏi tôi trước khi code.

`AGENTS.md` and client-specific rules may point here, but this file is the canonical bootstrap entry point.
