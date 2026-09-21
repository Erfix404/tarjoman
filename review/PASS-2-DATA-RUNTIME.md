# Pass 2 — Data, jobs, recovery, and concurrency

## Findings closed

- **R09 Critical — persistent job runner was delayed until API phase even though translation resume depended on it.**  
  Fixed: job engine moved to Foundation; API only exposes it.

- **R10 Critical — multi-process SQLite scheduler ownership was undefined.**  
  Fixed: atomic claims/leases + one scheduler owner per workspace in v1; no duplicate Uvicorn schedulers.

- **R11 Major — content-addressed deletion could delete shared bytes.**  
  Fixed: workspace-scoped reachability/reference-aware GC.

- **R12 Major — live WAL database backup method undefined.**  
  Fixed: consistent SQLite online snapshot + artifact manifest + restore verification. SQLite's official backup API supports consistent snapshots of live databases.

- **R13 Major — imported external source could disappear.**  
  Fixed: managed-source copy into artifact store by default.

- **R14 Major — protected placeholder loss/duplication had no fail-closed rule.**  
  Fixed: exact placeholder integrity; finalization fails on missing/duplicate/unresolved required spans.

- **R15 Major — approval invalidation/history semantics unclear.**  
  Fixed: immutable versions, active lineage invalidation, historical audit retained.

- **R16 Major — idempotency lacked material-operation identity.**  
  Fixed: immutable inputs + material resolved config define internal identity.

## Verdict
Single-node architecture is coherent. Distributed scheduler/storage remains deliberately deferred.
