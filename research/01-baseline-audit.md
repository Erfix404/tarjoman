# Baseline Audit — Amirezamky9/tarjoman

**Baseline SHA:** `58e97b802aa3efb318135a5923231c0a08550c4a`  
**Upstream:** Erfix404/tarjoman  
**Observed tests:** 96 test methods across 8 test files.

## What is already good

- Clear five-stage conceptual pipeline.
- Ten Persian translation domains with versionable JSON-like profile data.
- Strong attention to Persian punctuation/ZWNJ/Arabic-vs-Persian characters.
- Protected-span masking for code, math, URLs, and email.
- Composers for bilingual Markdown, HTML, and Typst.
- Book/project memory ideas: resumable cache, termbase, character voice ledger.
- CLI and packaging are small and understandable.
- Unit tests cover many deterministic behaviors.
- Skillpacks demonstrate agent intent for Claude/Hermes/Cursor.

These are worth preserving as concepts.

## Critical findings

### B01 — No production translation backend
`SemanticDraftStage` defaults to `EchoDraftBackend`. `TranslationPipeline()` therefore copies source text unless a caller injects a backend.

The CLI constructs `TranslationPipeline()` without a provider. So the public translate command does not contain a real provider/model path.

**Impact:** current project is a framework/quality toolkit, not yet an operational translation engine.

### B02 — The benchmark can be green without translation
`benchmarks/run_benchmarks.py` constructs `TranslationPipeline()` with the default Echo backend and then asserts the internal audit score.

The audit mostly checks protected tokens, numbers, quotes, and banned Persian calques. English echoed source can therefore satisfy many “quality” checks.

**Impact:** benchmark success is not evidence of translation quality.

### B03 — Documentation/skillpack drift
The Hermes skillpack documents flags/provider behavior such as local/provider/model routing that the current Click CLI does not expose.

**Impact:** users/agents can be instructed to call nonexistent behavior.

### B04 — “MQM score” is not a complete MQM evaluation
Current score is `100 - fixed penalties` for a small rule set. It is useful as lint severity, but not a robust translation-quality metric.

**Impact:** naming can overstate confidence.

### B05 — Regex semantic rewriting is risky
Anti-calque logic contains unconditional transformation patterns. Some Persian phrases require context; replacing them mechanically can change meaning.

**Decision:** safe normalization remains automatic; semantic calque logic becomes diagnostic/revision-driven.

### B06 — Heuristic domain router is narrow
Routing uses weighted keyword regexes. This is deterministic and useful as a fast hint, but confidence is not calibrated and mixed-domain documents are common.

**Decision:** keep heuristics as a cheap first pass; allow explicit profile and optional model classifier.

### B07 — State is file-oriented, not production transactional
Cache/termbase/voice state are JSON/TSV-style local files. Atomic replace helps, but project concurrency, migrations, querying, provenance, fuzzy TM, and multi-process behavior need a real data model.

**Decision:** SQLite WAL + migrations.

### B08 — Cache invalidation is under-specified
Production translation depends on model, prompt, style, glossary, context, and provider. A source-only cache can return stale output after policy changes.

**Decision:** full versioned cache key.

### B09 — No provider reliability layer
No standard timeout, retry, rate-limit, cancellation, concurrency, fallback policy, cost accounting, or provider capability negotiation.

### B10 — No production API/job model
Long documents/audio need persistent status, progress, cancellation, checkpoints, and idempotency.

### B11 — Format support is mainly output composition
The project produces HTML/Typst/bilingual outputs but does not yet have a general ingest/export adapter architecture for DOCX/EPUB/subtitles/structured files.

### B12 — HTML output is not fully offline
Current HTML tests expect external font/CDN references. A privacy/offline profile must not require network resources.

### B13 — Typst output assumes environment capabilities
Font/compiler availability is environmental and should be surfaced as capability checks with graceful fallback.

### B14 — CI is too narrow for production
Current workflow runs unittest + benchmark on Python 3.10–3.13 and a build-on-tag workflow. Missing:
- lint/format,
- type checking,
- coverage,
- security/static checks,
- package install smoke,
- migration tests,
- real-quality eval separation,
- supply-chain/provenance.

### B15 — Release workflow builds but does not prove/install/publish
Build artifacts are useful but a release candidate should be installed/tested from the built wheel in a clean environment.

### B16 — No privacy/provenance contract
Provider use, content logging, secrets, source hashes, prompt versions, and model provenance are not first-class run records.

### B17 — Agent integrations are prompt packs, not stable tool contracts
Skillpacks are useful but should call typed application/MCP tools instead of relying on prose commands that may drift.

## Immediate preservation list

Keep and refactor rather than discard:
- protected-span concept,
- domain/profile knowledge,
- Persian typography tests,
- composers,
- CLI concepts,
- termbase/voice-ledger ideas,
- deterministic route heuristic as optional fast router,
- existing 96 tests as regression input.

## Immediate retirement/relabel list

- Echo as implicit default for real translate command.
- “quality score” as proof of translation quality.
- semantic regex auto-rewrite without context.
- benchmark name/claims that imply real translation.
- documented provider flags that do not exist.

## Foundation conclusion

The repository has a good **language-policy skeleton**. Production work should not rewrite it from zero; it should add missing engineering layers around it and tighten unsafe semantics.
