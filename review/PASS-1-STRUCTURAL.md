# Pass 1 — Structural consistency

## Lens
Can two competent coding agents read the architecture and implement materially different core semantics?

## Findings closed

- **R01 Critical — Result Cache vs Translation Memory conflated.**  
  Fixed: separate identity, lifecycle, authority, and promotion policy.

- **R02 Major — public job state used both `completed` and `SUCCEEDED`.**  
  Fixed: one canonical six-state enum.

- **R03 Critical — state location contradicted itself (user app-data vs project `.tarjoman`).**  
  Fixed: Workspace is the storage/trust boundary; user-global data contains only preferences/secret references.

- **R04 Major — ProjectSpec forced one source/target pair.**  
  Fixed: optional project defaults + per-operation/artifact/segment language metadata.

- **R05 Major — “profile” meant domain, meeting workflow, release bundle, and license mode.**  
  Fixed: DomainProfile / StyleProfile / WorkflowProfile / policies / Capability Bundle.

- **R06 Major — COMET/reference metrics were inside runtime finalization.**  
  Fixed: deterministic runtime validation is separate from out-of-band comparative evaluation.

- **R07 Major — mutable Segment fields obscured review history.**  
  Fixed: logical Segment + immutable SegmentVersion.

- **R08 Major — source hash semantics ambiguous.**  
  Fixed: raw/canonical/segment/config/context hash domains explicitly distinct.

## Verdict
Structural semantics are now deterministic enough for implementation; remaining choices are adapter internals or later benchmark decisions.
