# Pass 5 — Scope control and current standards

## Findings closed

- **R32 Critical — roadmap ordering could imply Core v1 waits for ASR/TTS/UI/A2A.**  
  Fixed: Core v1 critical path separated from optional capability tracks.

- **R33 Major — current MCP long-task support was not mapped.**  
  Fixed: MCP 2026-07-28 Tasks extension maps to Tarjoman's own job engine; no duplicate state store.

- **R34 Major — A2A could be interpreted as required for agent support.**  
  Fixed: A2A optional after core; MCP is primary tool interface. Current A2A 0.3 task/discovery semantics remain compatible with a later adapter.

- **R35 Major — legal/medical “high-risk profile” lacked an approval default.**  
  Fixed: draft generation allowed; APPROVED requires human review by default, explicit audited override possible.

- **R36 Critical — single-user vs multi-user server assumptions conflicted with lightweight goal.**  
  Fixed: single-tenant workspace with scoped principals/tokens in v1; full human IAM deferred.

- **R37 Major — release maturity was global rather than capability-scoped.**  
  Fixed: Core/ASR/TTS/UI maturity and release gates are independent but share versioned core contracts.

## External standards checked
- MCP 2026-07-28: stateless protocol core; Tasks moved to extension.
- A2A latest official page reviewed: 0.3.0.
- SQLite official WAL/Backup behavior.
- OWASP upload/SSRF guidance.

## Verdict
The project remains ambitious but no longer forces optional speech/UI/agent-to-agent scope into the first production core release.
