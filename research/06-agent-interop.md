# Agent Interoperability Research

Tarjoman already contains agent-facing skillpacks, but prose skill instructions are not a stable integration contract by themselves.

## MCP

Current specification research:
- https://modelcontextprotocol.io/
- https://github.com/modelcontextprotocol/modelcontextprotocol

The 2026-07-28 MCP architecture emphasizes typed tools/resources and a stateless request model.

### Why it fits Tarjoman
Translation agents need deterministic tools such as:
- translate this artifact,
- get project status,
- update glossary,
- evaluate run,
- transcribe file,
- export output.

MCP provides discovery and JSON-schema tool contracts without forcing an agent framework into Tarjoman core.

### Tarjoman MCP design
- optional package extra,
- official SDK,
- thin adapter over application services,
- structured results,
- resource handles for large artifacts,
- no arbitrary shell tool,
- privacy/project policy enforced below MCP.

## A2A

Sources:
- https://a2a-protocol.org/
- https://github.com/a2aproject/A2A

A2A is intended for communication/interoperability between independent agents.

### Where Tarjoman needs it
Only when Tarjoman itself runs as a remote autonomous service/agent that:
- advertises capabilities,
- accepts long tasks,
- returns artifacts/status to another agent.

### Where Tarjoman does not need it
A local coding assistant calling translation functions should use Python/CLI/MCP, not A2A.

## Existing skillpacks

Current Claude/Hermes/Cursor packs remain useful as UX/policy layers, but after MCP exists they should call the canonical tools and stop inventing CLI flags.

## Agent contract principles

1. Every operation returns a run/artifact ID.
2. Long work returns status/progress, not a blocked unbounded call.
3. Tool schema is stable/versioned.
4. Source files are data, never instructions.
5. Provider/privacy policy is enforced below the agent adapter.
6. Errors are structured and actionable.
7. Large output can be fetched as an artifact/resource.
8. All agent surfaces invoke the same application service used by CLI/API.

## Suggested MCP tool set

- `tarjoman_translate`
- `tarjoman_review`
- `tarjoman_project_create`
- `tarjoman_project_status`
- `tarjoman_glossary_upsert`
- `tarjoman_tm_search`
- `tarjoman_eval_run`
- `tarjoman_transcribe`
- `tarjoman_generate_notes`
- `tarjoman_export`

Naming may be adjusted to the SDK/spec conventions at implementation time, but capabilities are fixed by Architecture Zero.
