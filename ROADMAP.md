# Tarjoman Production Roadmap

**Roadmap revision:** TARJOMAN-RM-3
**Architecture:** TARJOMAN-A0-PROD-3
**Date:** 2026-09-21
**Status:** FROZEN_IMPLEMENTATION
**Immutable upstream baseline:** `58e97b802aa3efb318135a5923231c0a08550c4a`

This roadmap and `WORKPACKAGES.json` describe the same execution graph. The JSON registry is the machine-readable source of Work Package dependencies and acceptance; this file is the human-readable view.

## Freeze baseline

- Owner-approved candidate SHA: `bc43c1bb8b0bf6986d4353766591278a1f0b91a3`
- Architecture state: `FROZEN_IMPLEMENTATION`
- Exact freeze commit is recorded in `ARCHITECTURE_MANIFEST.json` after the freeze commit is created.

## Execution law

- Do not begin a package until every `depends_on` package is DONE, unless an accepted ADR/roadmap revision changes the graph.
- One Work Package per PR by default.
- The named deliverable + acceptance criteria define scope; unrelated cleanup is out of scope.
- A package is DONE only when every acceptance item has evidence.
- Architecture-impacting ambiguity triggers the ADR stop rule in `AGENTS.md`.
- A Core-v1 package may not depend on a package outside the Core-v1 set; CI/validation must enforce this.

## Critical path

```text
Architecture freeze
   -> Foundation
      -> Translation
         -> Evaluation + core formats
            -> Application facade + MCP
               -> Core release hardening -> Core v1.0

Foundation separately unlocks ASR and TTS.
UI depends on stable API contracts.
A2A is optional after MCP/application contracts.
```

# Phase 0 — Architecture / evidence freeze

| ID | Depends on | Core v1 | Deliverable | Acceptance |
|---|---|:---:|---|---|
| **A0-001** Baseline record | — | YES | Baseline record | named evidence/document exists for Baseline record; result is referenced by the architecture baseline |
| **A0-002** Baseline audit | A0-001 | YES | Baseline audit | named evidence/document exists for Baseline audit; result is referenced by the architecture baseline |
| **A0-003** Translation landscape | A0-002 | YES | Translation landscape | named evidence/document exists for Translation landscape; result is referenced by the architecture baseline |
| **A0-004** Speech research | A0-003 | YES | Speech research | named evidence/document exists for Speech research; result is referenced by the architecture baseline |
| **A0-005** Architecture Zero v3 multi-pass closure | A0-004 | YES | PROD-3 architecture + review ledger + executable roadmap | five review passes are committed; Critical/Major ledger has zero unresolved findings; owner review is the only remaining freeze gate |

# Phase 1 — Foundation

| ID | Depends on | Core v1 | Deliverable | Acceptance |
|---|---|:---:|---|---|
| **FND-001** Repository/package layout | A0-005 | YES | foundation component: Repository/package layout | editable install works,; wheel install works in clean venv,; legacy imports either migrate mechanically or have compatibility shim with removal plan,; no optional heavy import at `import tarjoman` |
| **FND-002** Canonical contracts | FND-001 | YES | foundation component: Canonical contracts | JSON round trip,; schema snapshots,; stable IDs,; validation failures tested |
| **FND-003** Error taxonomy | FND-002 | YES | foundation component: Error taxonomy | no generic error string contract,; CLI nonzero codes stable,; API/MCP mapping table tested later |
| **FND-004** Configuration system | FND-002 | YES | foundation component: Configuration system | precedence matrix tests,; secret redaction tests,; unknown config key policy documented (fail by default for project config) |
| **FND-005** Artifact store | FND-002, FND-004 | YES | foundation component: Artifact store | interrupted write leaves no completed artifact,; dedup by SHA,; filename cannot escape store,; retention/delete tests |
| **FND-006** SQLite schema 001 | FND-002, FND-005 | YES | foundation component: SQLite schema 001 | empty → latest migration,; FK integrity,; WAL/busy timeout,; repository CRUD tests |
| **FND-007** Migration discipline | FND-006 | YES | foundation component: Migration discipline | migration idempotence check,; cannot edit applied migration unnoticed (checksum),; failure rolls back or leaves recoverable state |
| **FND-008** Legacy-state importer | FND-006, FND-007 | YES | foundation component: Legacy-state importer | fixture conversions,; duplicate/conflict policy deterministic,; source files never deleted automatically |
| **FND-009** Persian quality split | FND-001, FND-002 | YES | foundation component: Persian quality split | normalization idempotence tests,; anti-calque rules default diagnostic,; false-positive regression cases |
| **FND-010** Versioned behavior and compliance registries | FND-002, FND-004 | YES | immutable prompt/profile/rule/strategy registry plus model/data/service manifest schemas and license-policy primitives | prompt/profile/rule/strategy content is versioned by immutable ID/checksum; ModelManifest/DataManifest/ServiceManifest schemas represent source revision, license, purpose and redistribution status; unknown license status fails closed under commercial/bundled policy tests; run provenance can reference exact behavior and compliance manifest IDs |
| **FND-011** Structured logging/provenance | FND-003, FND-004, FND-006, FND-010 | YES | foundation component: Structured logging/provenance | redaction test,; JSON log option,; provider error cannot leak API key |
| **FND-012** Architecture-conformance CI | FND-001, FND-002, FND-003, FND-004, FND-005, FND-006, FND-007, FND-008, FND-009, FND-010, FND-011 | YES | foundation component: Architecture-conformance CI | base job installs without speech/eval/server extras,; architecture violations fail CI |

# Phase 2 — Real translation engine

| ID | Depends on | Core v1 | Deliverable | Acceptance |
|---|---|:---:|---|---|
| **TRN-001** Provider port/capabilities | FND-012 | YES | translation component: Provider port/capabilities | component is reachable through application services; fake-provider tests cover success and failure; provenance and policy behavior are asserted |
| **TRN-002** OpenAI-compatible adapter | TRN-001, FND-004 | YES | translation component: OpenAI-compatible adapter | fake HTTP contract server,; structured output path,; timeout/cancel tests,; no SDK dependency required if lightweight HTTP implementation is chosen |
| **TRN-003** Test providers | TRN-001 | YES | translation component: Test providers | normal `translate` without configured real provider fails clearly |
| **TRN-004** Reliability middleware | TRN-001, TRN-003 | YES | translation component: Reliability middleware | 429, timeout, 5xx, malformed response matrix |
| **TRN-005** Provider policy | TRN-001, FND-004 | YES | translation component: Provider policy | local-only cannot reach cloud,; fallback is logged in provenance,; no silent model substitution |
| **TRN-006** Translation strategy registry | TRN-001, FND-010 | YES | translation component: Translation strategy registry | strategy recorded,; critic output typed,; bounded number of model calls |
| **TRN-007** Context builder | FND-010, FND-009, TRN-001 | YES | translation component: Context builder | token-budget deterministic,; context hash stored,; protected content is delimited as data |
| **TRN-008** Glossary enforcement | TRN-007, FND-010 | YES | translation component: Glossary enforcement | approved-term compliance test,; forbidden-term finding,; glossary version invalidates cache |
| **TRN-009** Result Cache + Translation Memory separation | FND-006, FND-010 | YES | separate result-cache repository and authoritative TM repository/services | cache key follows Architecture §7.1; TM promotion follows Architecture §7.2; evicting result cache does not delete TM; model/prompt change misses cache but does not erase approved TM |
| **TRN-010** Async document orchestrator | TRN-002, TRN-004, TRN-005, TRN-006, TRN-007, TRN-008, TRN-009 | YES | translation component: Async document orchestrator | cancel,; resume,; partial provider failure,; no unbounded tasks |
| **TRN-011** Review/revision state | FND-002, FND-006, FND-010 | YES | translation component: Review/revision state | component is reachable through application services; fake-provider tests cover success and failure; provenance and policy behavior are asserted |
| **TRN-012** Core CLI | TRN-010, TRN-011 | YES | translation component: Core CLI | component is reachable through application services; fake-provider tests cover success and failure; provenance and policy behavior are asserted |

# Phase 3 — Evaluation and Persian regression science

| ID | Depends on | Core v1 | Deliverable | Acceptance |
|---|---|:---:|---|---|
| **EVAL-001** Golden-case schema | FND-002, FND-010 | YES | versioned evaluation asset/report for golden-case schema | asset/report is versioned and reproducible; fixture-based test proves the evaluator/report path; evaluation never mutates candidate output |
| **EVAL-002** Golden corpus v1 | EVAL-001 | YES | versioned evaluation asset/report for golden corpus v1 | asset/report is versioned and reproducible; fixture-based test proves the evaluator/report path; evaluation never mutates candidate output |
| **EVAL-003** Hard invariant runner | EVAL-002 | YES | versioned evaluation asset/report for hard invariant runner | asset/report is versioned and reproducible; fixture-based test proves the evaluator/report path; evaluation never mutates candidate output |
| **EVAL-004** Lexical metrics extra | EVAL-002 | YES | versioned evaluation asset/report for lexical metrics extra | asset/report is versioned and reproducible; fixture-based test proves the evaluator/report path; evaluation never mutates candidate output |
| **EVAL-005** COMET/XCOMET extra | EVAL-002 | YES | versioned evaluation asset/report for comet/xcomet extra | COMET/XCOMET remains optional extra; model/license manifest is recorded before download; fixture or mocked smoke proves integration without making PR CI require model download |
| **EVAL-006** Human MQM guide | EVAL-002 | YES | versioned evaluation asset/report for human mqm guide | asset/report is versioned and reproducible; fixture-based test proves the evaluator/report path; evaluation never mutates candidate output |
| **EVAL-007** Blind model bake-off | TRN-012, EVAL-003, EVAL-004, EVAL-005, EVAL-006 | YES | versioned evaluation asset/report for blind model bake-off | asset/report is versioned and reproducible; fixture-based test proves the evaluator/report path; evaluation never mutates candidate output |
| **EVAL-008** Benchmark report schema | EVAL-003, FND-011 | YES | versioned evaluation asset/report for benchmark report schema | asset/report is versioned and reproducible; fixture-based test proves the evaluator/report path; evaluation never mutates candidate output |
| **EVAL-009** Current benchmark rename/fix | EVAL-003, EVAL-008 | YES | versioned evaluation asset/report for current benchmark rename/fix | asset/report is versioned and reproducible; fixture-based test proves the evaluator/report path; evaluation never mutates candidate output |

# Phase 4 — Formats / CAT interoperability

| ID | Depends on | Core v1 | Deliverable | Acceptance |
|---|---|:---:|---|---|
| **FMT-001** TXT/Markdown adapter hardening | FND-012 | YES | format adapter/interchange capability: TXT/Markdown adapter hardening | round-trip fixture covers representative input; protected structure survives exactly or operation fails explicitly; unsupported/corrupt input has a typed failure |
| **FMT-002** HTML structured-text adapter | FMT-001 | YES | format adapter/interchange capability: HTML structured-text adapter | round-trip fixture covers representative input; protected structure survives exactly or operation fails explicitly; unsupported/corrupt input has a typed failure |
| **FMT-003** SRT/VTT adapter | FND-012 | YES | format adapter/interchange capability: SRT/VTT adapter | round-trip fixture covers representative input; protected structure survives exactly or operation fails explicitly; unsupported/corrupt input has a typed failure |
| **FMT-004** ASS subtitle adapter | FMT-003 | no | format adapter/interchange capability: ASS subtitle adapter | round-trip fixture covers representative input; protected structure survives exactly or operation fails explicitly; unsupported/corrupt input has a typed failure |
| **FMT-005** JSON-path adapter | FND-012 | no | format adapter/interchange capability: JSON-path adapter | round-trip fixture covers representative input; protected structure survives exactly or operation fails explicitly; unsupported/corrupt input has a typed failure |
| **FMT-006** DOCX adapter | FND-012 | no | format adapter/interchange capability: DOCX adapter | round-trip fixture covers representative input; protected structure survives exactly or operation fails explicitly; unsupported/corrupt input has a typed failure |
| **FMT-007** EPUB adapter | FND-012 | no | format adapter/interchange capability: EPUB adapter | round-trip fixture covers representative input; protected structure survives exactly or operation fails explicitly; unsupported/corrupt input has a typed failure |
| **FMT-008** PDF extraction adapter | FND-012 | no | format adapter/interchange capability: PDF extraction adapter | round-trip fixture covers representative input; protected structure survives exactly or operation fails explicitly; unsupported/corrupt input has a typed failure |
| **FMT-009** TMX 1.4b import/export | TRN-009 | no | format adapter/interchange capability: TMX 1.4b import/export | round-trip fixture covers representative input; protected structure survives exactly or operation fails explicitly; unsupported/corrupt input has a typed failure |
| **FMT-010** TBX import/export | TRN-008 | no | format adapter/interchange capability: TBX import/export | round-trip fixture covers representative input; protected structure survives exactly or operation fails explicitly; unsupported/corrupt input has a typed failure |
| **FMT-011** XLIFF 2.x minimum useful subset | FND-002 | no | format adapter/interchange capability: XLIFF 2.x minimum useful subset | round-trip fixture covers representative input; protected structure survives exactly or operation fails explicitly; unsupported/corrupt input has a typed failure |
| **FMT-012** Fuzzy TM retrieval | TRN-009, FMT-009 | no | format adapter/interchange capability: Fuzzy TM retrieval | round-trip fixture covers representative input; protected structure survives exactly or operation fails explicitly; unsupported/corrupt input has a typed failure |

# Phase 5 — Speech input / ASR / knowledge

| ID | Depends on | Core v1 | Deliverable | Acceptance |
|---|---|:---:|---|---|
| **ASR-001** Media ingest | FND-005, FND-012 | no | ASR/knowledge capability: Media ingest | typed artifact/provenance is produced; failure/cancel path is tested; heavy dependency remains optional and license manifest is enforced where relevant |
| **ASR-002** ASR port | FND-002 | no | ASR/knowledge capability: ASR port | typed artifact/provenance is produced; failure/cancel path is tested; heavy dependency remains optional and license manifest is enforced where relevant |
| **ASR-003** faster-whisper adapter | ASR-001, ASR-002, FND-010 | no | ASR/knowledge capability: faster-whisper adapter | typed artifact/provenance is produced; failure/cancel path is tested; heavy dependency remains optional and license manifest is enforced where relevant |
| **ASR-004** ASR language policy | ASR-002 | no | ASR/knowledge capability: ASR language policy | typed artifact/provenance is produced; failure/cancel path is tested; heavy dependency remains optional and license manifest is enforced where relevant |
| **ASR-005** Diarization port | ASR-002, FND-010 | no | ASR/knowledge capability: Diarization port | typed artifact/provenance is produced; failure/cancel path is tested; heavy dependency remains optional and license manifest is enforced where relevant |
| **ASR-006** Transcript artifact lineage | ASR-003, FND-005 | no | ASR/knowledge capability: Transcript artifact lineage | typed artifact/provenance is produced; failure/cancel path is tested; heavy dependency remains optional and license manifest is enforced where relevant |
| **ASR-007** Persian spoken normalization | ASR-006, FND-009 | no | ASR/knowledge capability: Persian spoken normalization | typed artifact/provenance is produced; failure/cancel path is tested; heavy dependency remains optional and license manifest is enforced where relevant |
| **ASR-008** Spoken→written formalizer | ASR-007, TRN-001, TRN-005 | no | ASR/knowledge capability: Spoken→written formalizer | typed artifact/provenance is produced; failure/cancel path is tested; heavy dependency remains optional and license manifest is enforced where relevant |
| **ASR-009** Lecture-notes transform | ASR-008 | no | ASR/knowledge capability: Lecture-notes transform | typed artifact/provenance is produced; failure/cancel path is tested; heavy dependency remains optional and license manifest is enforced where relevant |
| **ASR-010** Meeting-minutes transform | ASR-008 | no | ASR/knowledge capability: Meeting-minutes transform | typed artifact/provenance is produced; failure/cancel path is tested; heavy dependency remains optional and license manifest is enforced where relevant |
| **ASR-011** Subtitle from transcript | ASR-006, FMT-003 | no | ASR/knowledge capability: Subtitle from transcript | typed artifact/provenance is produced; failure/cancel path is tested; heavy dependency remains optional and license manifest is enforced where relevant |
| **ASR-012** ASR eval | ASR-003, ASR-006, EVAL-001 | no | ASR/knowledge capability: ASR eval | typed artifact/provenance is produced; failure/cancel path is tested; heavy dependency remains optional and license manifest is enforced where relevant |

# Phase 6 — Speech output / Persian TTS

| ID | Depends on | Core v1 | Deliverable | Acceptance |
|---|---|:---:|---|---|
| **TTS-001** TTS contracts | FND-002 | no | TTS capability: TTS contracts | typed speech artifact/provenance is produced or research status is explicit; pronunciation/quality or policy failure path is tested; heavy dependency/model remains optional and license-gated |
| **TTS-002** TTS model/voice manifest population and policy tests | FND-010, FND-006 | no | TTS-specific model/voice manifest entries and license-policy test fixtures | every benchmarked TTS model/voice has a manifest with exact source/revision/license evidence; commercial/noncommercial/research and bundled/user-supplied modes are tested; Pocket Farsi v2 remains blocked from commercial bundled profile unless licensing changes |
| **TTS-003** SpeechTextNormalizer | FND-009, TTS-001 | no | TTS capability: SpeechTextNormalizer | written source artifact unchanged,; golden speech-normalization cases |
| **TTS-004** Pronunciation lexicon | FND-006, TTS-003 | no | TTS capability: Pronunciation lexicon | typed speech artifact/provenance is produced or research status is explicit; pronunciation/quality or policy failure path is tested; heavy dependency/model remains optional and license-gated |
| **TTS-005** G2P port | TTS-001, TTS-004 | no | TTS capability: G2P port | curated Ezafe/names/English-term suite,; G2P failures surfaced, not silently dropped |
| **TTS-006** SpeechPlanner | TTS-003, TTS-005 | no | TTS capability: SpeechPlanner | engine max budget never exceeded,; deterministic plan snapshot tests,; long unpunctuated text bounded |
| **TTS-007** Lightweight fixed-voice candidate bake-off | TTS-002, TTS-006 | no | TTS capability: Lightweight fixed-voice candidate bake-off | typed speech artifact/provenance is produced or research status is explicit; pronunciation/quality or policy failure path is tested; heavy dependency/model remains optional and license-gated |
| **TTS-008** Pocket Farsi ONNX research adapter | TTS-001, TTS-002 | no | TTS capability: Pocket Farsi ONNX research adapter | typed speech artifact/provenance is produced or research status is explicit; pronunciation/quality or policy failure path is tested; heavy dependency/model remains optional and license-gated |
| **TTS-009** Heavy multilingual/voice-clone candidate | TTS-001, TTS-002 | no | TTS capability: Heavy multilingual/voice-clone candidate | typed speech artifact/provenance is produced or research status is explicit; pronunciation/quality or policy failure path is tested; heavy dependency/model remains optional and license-gated |
| **TTS-010** Voice profile/reference pipeline | TTS-001, FND-005 | no | TTS capability: Voice profile/reference pipeline | typed speech artifact/provenance is produced or research status is explicit; pronunciation/quality or policy failure path is tested; heavy dependency/model remains optional and license-gated |
| **TTS-011** Voice-clone consent policy | TTS-002, TTS-010 | no | TTS capability: Voice-clone consent policy | typed speech artifact/provenance is produced or research status is explicit; pronunciation/quality or policy failure path is tested; heavy dependency/model remains optional and license-gated |
| **TTS-012** Acoustic quality gate | TTS-001, TTS-006 | no | TTS capability: Acoustic quality gate | typed speech artifact/provenance is produced or research status is explicit; pronunciation/quality or policy failure path is tested; heavy dependency/model remains optional and license-gated |
| **TTS-013** Audio post-processing | TTS-012 | no | TTS capability: Audio post-processing | typed speech artifact/provenance is produced or research status is explicit; pronunciation/quality or policy failure path is tested; heavy dependency/model remains optional and license-gated |
| **TTS-014** Reproducibility | TTS-001 | no | TTS capability: Reproducibility | typed speech artifact/provenance is produced or research status is explicit; pronunciation/quality or policy failure path is tested; heavy dependency/model remains optional and license-gated |
| **TTS-015** TTS eval suite | TTS-001, TTS-006, TTS-012, EVAL-001 | no | TTS capability: TTS eval suite | typed speech artifact/provenance is produced or research status is explicit; pronunciation/quality or policy failure path is tested; heavy dependency/model remains optional and license-gated |
| **TTS-016** CLI | TTS-001, TTS-003, TTS-004 | no | TTS capability: CLI | typed speech artifact/provenance is produced or research status is explicit; pronunciation/quality or policy failure path is tested; heavy dependency/model remains optional and license-gated |
| **TTS-017** Audiobook/voice artifact composer | TTS-006, TTS-013, TTS-016 | no | TTS capability: Audiobook/voice artifact composer | typed speech artifact/provenance is produced or research status is explicit; pronunciation/quality or policy failure path is tested; heavy dependency/model remains optional and license-gated |

# Phase 7 — Agent and server interfaces

| ID | Depends on | Core v1 | Deliverable | Acceptance |
|---|---|:---:|---|---|
| **API-001** Application-service facade | FND-012, TRN-012 | YES | interface capability: Application-service facade | interface calls application services only; contract/auth/failure behavior is tested; no duplicate business/job state is introduced |
| **API-002** Job API adapter over foundation scheduler | API-001, FND-006 | no | application/API adapter exposing existing SQLite job engine | does not create a second job table/state machine; job status uses canonical enum; claim/lease semantics remain owned by foundation job engine |
| **API-003** FastAPI extra | API-001, FND-004, FND-005, FND-006 | no | interface capability: FastAPI extra | interface calls application services only; contract/auth/failure behavior is tested; no duplicate business/job state is introduced |
| **API-004** OpenAPI contract | API-003 | no | interface capability: OpenAPI contract | interface calls application services only; contract/auth/failure behavior is tested; no duplicate business/job state is introduced |
| **API-005** Idempotency/progress/cancel | API-002, API-003 | no | interface capability: Idempotency/progress/cancel | interface calls application services only; contract/auth/failure behavior is tested; no duplicate business/job state is introduced |
| **MCP-001** Official MCP SDK integration | API-001 | YES | interface capability: Official MCP SDK integration | tool/resource schemas pass contract tests; result matches application-service semantics; policy and artifact-handle rules are enforced |
| **MCP-002** Core tools | MCP-001, TRN-012 | YES | interface capability: Core tools | tool/resource schemas pass contract tests; result matches application-service semantics; policy and artifact-handle rules are enforced |
| **MCP-003** Large artifact resources | MCP-002, FND-005 | YES | interface capability: Large artifact resources | tool/resource schemas pass contract tests; result matches application-service semantics; policy and artifact-handle rules are enforced |
| **MCP-004** Policy/security tests | MCP-002, TRN-005, FND-004 | YES | interface capability: Policy/security tests | tool/resource schemas pass contract tests; result matches application-service semantics; policy and artifact-handle rules are enforced |
| **A2A-001** Optional remote-agent adapter | MCP-004, API-001 | no | interface capability: Optional remote-agent adapter | adapter maps to application/job state without duplicate source of truth; agent-card/task contract tests pass; feature remains optional |

# Phase 8 — Review UX

| ID | Depends on | Core v1 | Deliverable | Acceptance |
|---|---|:---:|---|---|
| **UI-001** Source/target segment review | API-004, TRN-011 | no | UI capability: Source/target segment review | UI consumes generated API contracts; no business logic is duplicated; RTL/accessibility/failure state for the feature is covered |
| **UI-002** Findings + glossary/TM pane | UI-001, TRN-008, TRN-009 | no | UI capability: Findings + glossary/TM pane | UI consumes generated API contracts; no business logic is duplicated; RTL/accessibility/failure state for the feature is covered |
| **UI-003** Project/job dashboard | API-005 | no | UI capability: Project/job dashboard | UI consumes generated API contracts; no business logic is duplicated; RTL/accessibility/failure state for the feature is covered |
| **UI-004** Audio transcript timeline | UI-003, ASR-006 | no | UI capability: Audio transcript timeline | UI consumes generated API contracts; no business logic is duplicated; RTL/accessibility/failure state for the feature is covered |
| **UI-005** Pronunciation/TTS preview editor | UI-003, TTS-004, TTS-016 | no | UI capability: Pronunciation/TTS preview editor | UI consumes generated API contracts; no business logic is duplicated; RTL/accessibility/failure state for the feature is covered |
| **UI-006** Voice/reference consent and retention controls | UI-003, TTS-010, TTS-011 | no | UI capability: Voice/reference consent and retention controls | UI consumes generated API contracts; no business logic is duplicated; RTL/accessibility/failure state for the feature is covered |
| **UI-007** RTL/accessibility | UI-001 | no | UI capability: RTL/accessibility | UI consumes generated API contracts; no business logic is duplicated; RTL/accessibility/failure state for the feature is covered |
| **UI-008** API-generated client only | API-004, UI-001 | no | UI capability: API-generated client only | UI consumes generated API contracts; no business logic is duplicated; RTL/accessibility/failure state for the feature is covered |

# Phase 9 — Production hardening / release

| ID | Depends on | Core v1 | Deliverable | Acceptance |
|---|---|:---:|---|---|
| **REL-001** Branch protection + required checks | FND-012 | YES | release evidence for branch protection + required checks | evidence report/drill is committed or attached; failure condition is demonstrated before pass; release gate is machine-checkable where practical |
| **REL-002** Clean wheel/sdist install matrix | TRN-012, EVAL-009, FMT-001, FMT-002, FMT-003, MCP-004 | YES | release evidence for clean wheel/sdist install matrix | evidence report/drill is committed or attached; failure condition is demonstrated before pass; release gate is machine-checkable where practical |
| **REL-003** Migration upgrade fixtures | FND-007, FND-008 | YES | release evidence for migration upgrade fixtures | evidence report/drill is committed or attached; failure condition is demonstrated before pass; release gate is machine-checkable where practical |
| **REL-004** Backup/export/recovery drill | FND-005, FND-006, FND-007 | YES | release evidence for backup/export/recovery drill | evidence report/drill is committed or attached; failure condition is demonstrated before pass; release gate is machine-checkable where practical |
| **REL-005** Provider outage/rate-limit drill | TRN-004, TRN-005 | YES | release evidence for provider outage/rate-limit drill | evidence report/drill is committed or attached; failure condition is demonstrated before pass; release gate is machine-checkable where practical |
| **REL-006** Job crash/restart drill | TRN-010, FND-006 | YES | release evidence for job crash/restart drill | evidence report/drill is committed or attached; failure condition is demonstrated before pass; release gate is machine-checkable where practical |
| **REL-007** Security review | FND-012, MCP-004 | YES | release evidence for security review | evidence report/drill is committed or attached; failure condition is demonstrated before pass; release gate is machine-checkable where practical |
| **REL-008** License audit | FND-010, FND-012 | YES | license/SBOM audit for assets actually bundled or enabled by the release profile | all bundled runtime dependencies/models/voices/datasets have reviewed license evidence; unknown or incompatible assets block the affected release capability; NOTICE/SBOM inputs are generated from the reviewed manifests |
| **REL-009** Performance/soak | TRN-010, FMT-001, FMT-002, FMT-003 | YES | release evidence for performance/soak | evidence report/drill is committed or attached; failure condition is demonstrated before pass; release gate is machine-checkable where practical |
| **REL-010** Human MQM release review | EVAL-006, EVAL-007 | YES | release evidence for human mqm release review | evidence report/drill is committed or attached; failure condition is demonstrated before pass; release gate is machine-checkable where practical |
| **REL-011** TTS listening/pronunciation release review | TTS-015 | no | release evidence for tts listening/pronunciation release review | evidence report/drill is committed or attached; failure condition is demonstrated before pass; release gate is machine-checkable where practical |
| **REL-012** Documentation truth audit | TRN-012, MCP-004 | YES | release evidence for documentation truth audit | evidence report/drill is committed or attached; failure condition is demonstrated before pass; release gate is machine-checkable where practical |
| **REL-013** Release provenance/SBOM | REL-002, REL-008 | YES | release evidence for release provenance/sbom | evidence report/drill is committed or attached; failure condition is demonstrated before pass; release gate is machine-checkable where practical |
| **REL-014** Recovery/rollback release procedure | REL-003, REL-004, REL-006, REL-012, REL-013 | YES | release evidence for recovery/rollback release procedure | evidence report/drill is committed or attached; failure condition is demonstrated before pass; release gate is machine-checkable where practical |

# Release-track gates

## Core v1.0
Every package with `required_for_core_v1=true` must be DONE. Validation must prove none depends on an optional-track package.

## ASR capability
ASR packages plus applicable security/license/recovery release evidence must be DONE before ASR is advertised production-ready.

## TTS capability
TTS packages applicable to the selected engine plus TTS license/evaluation/release evidence must be DONE before TTS is advertised production-ready.

## UI / A2A
Ship independently after dependencies and capability-specific gates pass.

# Deferred infrastructure
Redis, Celery, Kafka, Postgres, Kubernetes, distributed schedulers, third-party plugin ABI, application-level encrypted workspaces, exact PDF reconstruction, and custom model training require evidence + ADR before entering an active package.
