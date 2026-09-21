# Tarjoman Architecture Zero

**Revision:** TARJOMAN-A0-PROD-3  
**Date:** 2026-09-21  
**Fork:** Amirezamky9/tarjoman  
**Upstream baseline:** `58e97b802aa3efb318135a5923231c0a08550c4a`  
**Architecture branch:** `arch/production-zero`  
**Status:** FROZEN_IMPLEMENTATION  
**Supersedes:** TARJOMAN-A0-PROD-2

> This document is the normative engineering baseline for turning Tarjoman from a promising translation/quality toolkit into a production-grade, Persian-first content transformation engine. Once the owner freezes this revision, implementation changes that contradict a locked decision require an ADR.

## 0. Precedence and change control

When two project documents disagree, use this order:

1. `ARCHITECTURE_ZERO.md`
2. accepted ADRs under `docs/adr/`
3. `ROADMAP.md`
4. `AGENTS.md` (execution summary; cannot override 1–3)
5. current contracts/tests
6. `research/` and `review/`
7. README / historical skillpacks / examples

Research documents are evidence, not normative requirements. Existing README claims that conflict with code or this architecture must be corrected during implementation.

No architecture decision is changed silently. A change must:
- identify the affected decision ID,
- explain the reason and alternatives,
- include migration impact,
- update tests/evals,
- land as an ADR before implementation.

## 1. Product definition

Tarjoman is a **Persian-first localization and knowledge transformation engine**.

Its primary job is not merely “translate a sentence”. It takes text, documents, subtitles, or speech and produces **reliable, natural, reviewable Persian artifacts** while preserving structure, terminology, provenance, and quality evidence.

### 1.1 Primary product surfaces

1. **Translation** — high-quality English → Persian first; architecture supports other source languages and Persian ↔ English adapters.
2. **Persian review/polish** — normalize, lint, improve register, terminology, style, and typography without translating.
3. **Long-form projects** — books, papers, manuals, repositories of documents; resumable with translation memory and terminology consistency.
4. **Document localization** — preserve non-translatable structure and, where the format adapter supports it, formatting.
5. **Audio knowledge** — Persian/multilingual audio or video → timestamped transcript → cleaned Persian → lecture notes / meeting minutes / summary / action items.
6. **Agent-native operation** — deterministic CLI/Python/API plus MCP tools; optional A2A surface for remote-agent collaboration.
7. **Speech output (TTS)** — Persian text/artifacts → pronunciation-aware speech, optional voice cloning, audiobook/podcast/accessibility outputs, always behind model/license/safety policy.

### 1.2 What Tarjoman is not

- Not a new foundation model.
- Not tied to one LLM vendor.
- Not a mandatory cloud service.
- Not a full CAT desktop clone in v1.
- Not a video editor.
- Not an OCR research project; OCR/document parsing is delegated to adapters.
- Not a certification authority for legal/medical translations. High-risk profiles can require human review.

## 2. Architecture principles

### P1 — Lightweight core, heavy features as extras
The base package must not require Torch, Whisper, COMET, LibreOffice, FFmpeg, a web framework, or a database server. Heavy capabilities are optional extras/adapters.

### P2 — Provider-neutral by contract
No business logic imports an OpenAI/Anthropic/Ollama SDK directly. Translation/reflection/summarization call a typed Model Harness.

### P3 — Source content is data
Documents, transcripts, web text, and user-supplied glossaries are untrusted data. They cannot modify system policy or authorize tool actions.

### P4 — Deterministic structure, probabilistic language
Parsing, placeholders, document structure, terminology constraints, run state, caching, and validation are deterministic. LLMs are used only for language tasks where generative behavior is beneficial.

### P5 — Quality is externally measured
A generator must not award itself a production quality score. Rule checks, independent metrics, golden corpora, and human MQM review are separate from generation.

### P6 — Persian is first-class
RTL, ZWNJ, Persian/Arabic Unicode normalization, Persian punctuation, register, mixed Persian-English terms, and Persian typography are core contracts, not UI polish.

### P7 — Every output is traceable
A production artifact records source hash, project/profile versions, provider/model, prompt version, glossary/style versions, timings, token/cost data when available, and quality findings.

### P8 — Resumable and idempotent
Long translation/audio jobs survive interruption. Re-running a completed deterministic stage should not duplicate work.

### P9 — Safe auto-fix
Mechanical Unicode/spacing fixes may be automatic. Semantic rewrites must never be blindly regex-substituted when meaning can change.

### P10 — Interfaces share one core
CLI, Python SDK, FastAPI, MCP, and A2A are adapters over the same application services. They must not reimplement the pipeline.

## 3. High-level architecture

~~~text
 Inputs
 ├─ text / markdown / HTML
 ├─ DOCX / EPUB / subtitles / structured files
 ├─ PDF via parser adapter
 └─ audio / video via ASR adapter
          │
          ▼
  Ingestion + Canonical IR
  - stable segment IDs
  - structure/protected spans
  - language/domain metadata
          │
          ▼
  Project Context Builder
  - style profile
  - glossary / termbase
  - translation memory
  - entities / names / voice ledger
  - document summary / neighboring context
          │
          ▼
  Translation Orchestrator
  - chunk/batch planner
  - model harness
  - candidate / reflection strategy
  - retries / rate limits / cache
          │
          ▼
  Persian Quality Engine
  - deterministic normalization
  - constraint checks
  - terminology checks
  - safe lint + semantic review requests
          │
          ▼
  Independent Evaluation
  - exact invariants
  - chrF/SacreBLEU optional
  - COMET/XCOMET/DocCOMET optional
  - human MQM review sets
          │
          ▼
  Artifact Composer / Exporter
  - text / MD / HTML / Typst
  - bilingual review
  - DOCX/EPUB/subtitle adapters
  - transcript / notes / minutes
          │
          ▼
 Interfaces
 CLI | Python SDK | REST/jobs | MCP | optional A2A
~~~

## 4. Canonical intermediate representation (IR)

All input formats normalize into one canonical representation. **Workspace**, **Project**, **Operation**, **Artifact**, and **Segment Version** are distinct concepts.

### 4.1 Workspace

A `Workspace` is the persistence and trust boundary:
- one SQLite database,
- one content-addressed artifact store,
- one job queue/lease namespace,
- one set of projects,
- one network/license/security policy envelope.

Standalone CLI normally creates one workspace in a project directory. Server mode opens one configured workspace and may host multiple logical projects inside it. Project state is never stored in the user-global config directory.

### 4.2 ProjectSpec

`ProjectSpec` contains durable project defaults:
- project_id,
- name,
- optional default_source_language,
- optional default_target_language,
- default_domain_profile_id,
- default_style_profile_id,
- default_workflow_profile_id,
- privacy_policy_id,
- provider_policy_id,
- review_policy_id,
- created_at / updated_at.

Source/target language defaults are optional. A Persian meeting, a multilingual subtitle file, and a Persian TTS operation do not require a fake translation language pair.

### 4.3 OperationSpec

Every transformation creates an immutable `OperationSpec`:
- operation_id,
- project_id,
- operation_type: translate | review | formalize | summarize | transcribe | synthesize | export | evaluate,
- input_artifact_ids,
- optional source_language / target_language overrides,
- domain_profile_id,
- style_profile_id,
- workflow_profile_id,
- resolved policy IDs,
- strategy ID,
- config snapshot hash.

The OperationSpec is the semantic input to idempotency/cache/provenance.

### 4.4 Artifact

`Artifact` is an immutable logical artifact version:
- artifact_id,
- project_id,
- kind: source_document | translated_document | subtitle | audio | video | transcript_raw | transcript_clean | notes | minutes | speech_plan | synthesized_audio | evaluation_report | other,
- raw_sha256 for imported bytes when applicable,
- canonical_content_hash for parsed/normalized content,
- language_tags[],
- source_uri only as provenance (not required for later access),
- parser/producer name + version,
- parent_artifact_ids[],
- sensitivity / retention metadata,
- segments[] or blob reference.

Imported source files are copied into the managed artifact store by default so a project remains reproducible if the original external path disappears.

### 4.5 Segment

`Segment` is a stable logical location, not mutable translated text:
- segment_id,
- artifact_id,
- structural locator (paragraph/cue/cell/run path),
- source_text,
- source_content_hash,
- language spans / code-switch metadata,
- translatable bool,
- protected_spans[],
- structural_context.

Stable segment IDs are based on artifact identity + structural locator, **not text alone**, so repeated identical paragraphs remain distinct. Content hashes are separate and used for cache/TM matching.

### 4.6 SegmentVersion

Generated/reviewed text lives in immutable `SegmentVersion` records:
- segment_version_id,
- segment_id,
- kind: source | draft | revised | human_edit | approved,
- text,
- parent_version_id,
- strategy/provider/model/prompt/profile versions,
- glossary/context/result-cache hashes,
- author: system | model | human principal,
- created_at,
- findings/provenance.

A new edit/version never overwrites historical text.

### 4.7 ProtectedSpan

`ProtectedSpan` includes:
- span_id,
- type: code | url | email | math | placeholder | citation | tag | timestamp | speaker | other,
- original_text,
- integrity_policy: exact | normalized | mapped.

Placeholder tokens are collision-resistant and scoped to the operation/segment. Finalization fails if a required placeholder is missing, duplicated unexpectedly, altered, or unresolved. Silent “best effort” restoration is forbidden.

### 4.8 RunRecord and canonical status vocabulary

All job/run interfaces use exactly:

`QUEUED | RUNNING | WAITING_REVIEW | SUCCEEDED | FAILED | CANCELLED`

`RunRecord` stores:
- run_id / job_id / operation_id / project_id,
- status,
- stage checkpoints,
- resolved config hash,
- provider/model,
- prompt/profile/rule/strategy IDs,
- started/finished timestamps,
- usage/cost/latency metadata,
- typed error + retry metadata.

No alternative public status spelling such as `completed` is permitted.

### 4.9 Language modeling rule

Language is attached to artifacts/segments/operations, not assumed globally from the project. BCP-47-style tags are preferred where practical (`fa`, `en`, variants when needed). Mixed-language spans may be tagged without splitting the artifact solely for language reasons.

Stable IDs, raw hashes, canonical hashes, and immutable versions are mandatory so caching, review, resume, and audit remain trustworthy.

## 5. Runtime pipeline versus evaluation pipeline

The existing “5-pass” idea remains a translation strategy, but **runtime generation and comparative evaluation are different pipelines**.

### 5.1 Runtime transformation pipeline

1. **Ingest / protect**  
   Parse structure, copy managed source artifact, protect non-translatable spans, create stable segments.

2. **Analyze / plan**  
   Resolve operation/domain/style/workflow policies; build glossary/entities/context and chunk plan.

3. **Generate**  
   Produce a draft or other requested transformation through the selected strategy/provider.

4. **Review / revise**  
   Create typed semantic/style/terminology findings and, where strategy allows, a bounded revision.

5. **Normalize / validate / finalize**  
   Apply only safe Persian normalization; restore protected spans; enforce hard invariants; persist immutable versions/artifacts and provenance.

The production runtime may run **reference-free hard checks** and task-specific policy gates. It does **not** require BLEU/COMET/human MQM on every user request.

### 5.2 Evaluation pipeline

Evaluation consumes completed candidate artifacts and frozen evaluation cases:
- exact invariants,
- reference metrics where references exist,
- optional COMET/XCOMET/DocCOMET,
- blind comparative review,
- human MQM/release review.

Evaluation never mutates the candidate it scores. A correction suggested by evaluation becomes a new operation/version.

### 5.3 Strategy rule

`direct-v1`, `reflect-revise-v1`, and future strategies are bounded implementations over the same stages/contracts. No hidden stage skipping or unlimited self-reflection loops are allowed.

## 6. Model Harness

### 6.1 Required interface

Application code calls capabilities, not vendors:

~~~python
class ModelProvider(Protocol):
    async def generate(self, request: ModelRequest) -> ModelResponse: ...
    def capabilities(self) -> ProviderCapabilities: ...
~~~

`ModelRequest` includes:
- task_type: translate | critique | revise | summarize | extract_terms | formalize
- source/target language
- messages / structured context
- required output schema
- temperature / seed when supported
- timeout
- privacy class

`ModelResponse` includes:
- text / structured payload
- provider + model
- usage
- finish reason
- latency
- request ID
- warnings

### 6.2 Built-in provider order

**P0 implementation priority**
1. `OpenAICompatibleProvider` — covers OpenRouter, 9router-style gateways, Ollama OpenAI compatibility, LM Studio, vLLM, and many hosted providers.
2. `AnthropicProvider` — optional direct adapter where native features are needed.
3. `CallableProvider` — test/custom integration.
4. `EchoProvider` — test-only; never a production default.

**Later optional adapters**
- local NMT / LibreTranslate-compatible service,
- Hugging Face / CTranslate2 NMT,
- specialized enterprise providers.

### 6.3 Fail-fast rule

`tarjoman translate` must never silently echo source text. If no real backend/model is configured, it exits with a clear configuration error unless the user explicitly selects `--backend echo` for testing.

### 6.4 Harness responsibilities

- timeout + bounded retry with exponential backoff,
- provider rate-limit handling,
- concurrency semaphore,
- cancellation,
- circuit-breaker behavior for repeatedly failing providers,
- usage/cost accounting,
- structured-output validation,
- capability validation before a run,
- provider fallback only when policy explicitly allows it,
- no secrets in logs.

## 7. Context, result cache, terminology, and translation memory

**Result Cache and Translation Memory are intentionally different systems.**

### 7.1 Result Cache

The result cache is a reproducibility/performance optimization for generated work.

Cache key includes:
- canonical source/input hash,
- operation type,
- source/target language,
- strategy version,
- provider + model,
- prompt/rule/domain/style/workflow versions,
- hard-glossary hash,
- relevant context hash,
- generation parameters/seed where material.

A relevant change must miss the cache. Cache entries can be evicted without losing approved translation history.

### 7.2 Translation Memory (TM)

TM is a durable bilingual memory of reusable translation decisions. It is **not** a provider-response cache.

A TM unit stores:
- source text + language,
- target text + language,
- project/domain/style metadata,
- source artifact/segment provenance,
- review state and author,
- created/updated versions,
- optional quality/approval notes.

Default promotion policy:
- human-approved segment versions may enter authoritative TM,
- reviewed model output may enter TM only if project policy explicitly permits,
- raw model drafts never become authoritative TM merely because they were cached.

### 7.3 Exact and fuzzy reuse

Exact TM lookup can suggest/auto-apply according to review policy. Fuzzy TM retrieval returns scored candidates plus provenance; it does not silently replace the current segment.

Context/model/prompt are **not** part of TM identity. They belong to provenance and can help rank whether an old TM unit is appropriate.

### 7.4 Terminology

Terms have:
- source term,
- approved target(s),
- domain/language,
- status: suggested | approved | forbidden,
- morphology/inflection policy,
- notes/source,
- version.

Approved terms are hard constraints only when the term is applicable to that segment under its matching/inflection policy. The validator reports applicability and compliance rather than forcing a literal form where Persian grammar requires an approved variant.

### 7.5 Long-form context

For books/manuals/documents:
- document/project summary,
- neighboring segments,
- approved glossary,
- named entities,
- character voice/register ledger where applicable,
- retrieved TM candidates.

Context is bounded by a deterministic budget and its selection/hash is stored in provenance.

### 7.6 Professional interoperability

Progressively support:
- TMX 1.4b for TM interchange,
- TBX for termbases,
- XLIFF 2.x for localization interchange.

The internal schema must preserve information needed for these exports without making any one standard the internal database format.

## 8. Persian Quality Engine

Split **normalization**, **linting**, and **semantic revision**.

### 8.1 Auto-fix safe layer
Allowed automatic operations:
- Arabic/Persian Kaf/Yeh normalization,
- ZWNJ normalization under tested rules,
- punctuation spacing,
- quote balancing suggestions,
- duplicate whitespace,
- digit policy by profile,
- Unicode direction/isolate hygiene,
- safe protected-token restoration.

### 8.2 Diagnostic layer
Flag, do not blindly rewrite:
- suspicious calques,
- passive constructions,
- awkward dialogue attribution,
- terminology inconsistencies,
- untranslated fragments,
- style/register mismatch,
- ambiguous number/unit handling.

Current regex anti-calque rules are retained initially as **detectors**. Semantic substitution moves to a revision engine or explicitly reviewed rule.

### 8.3 Persian NLP adapters

Optional adapters may use Hazm, DadmaTools, Parsivar, or other libraries behind Tarjoman-owned interfaces. No single external NLP library becomes a core architectural dependency.

### 8.4 Profile taxonomy — names may not be overloaded

The word “profile” is split into explicit types:

**DomainProfile** — subject matter:
- general, literary, scientific, philosophy, legal, technical, medical, media, financial, classical, transcreation.

**StyleProfile** — language presentation:
- formal/neutral/conversational/literary,
- audience,
- digit/punctuation/loanword policy,
- terminology/style guidance.

**WorkflowProfile** — transformation shape:
- translation,
- subtitle,
- meeting,
- lecture_notes,
- formal_minutes,
- audiobook,
- polish_only.

**ReviewPolicy** — approval/human-review requirements.

**PrivacyPolicy / ProviderPolicy / LicensePolicy** — security/runtime eligibility.

**Capability Bundle** — release/install grouping such as core/asr/tts/server; it is never called a content “profile”.

High-risk domain defaults:
- legal and medical can generate drafts,
- `APPROVED` status requires human review by default,
- a project owner may explicitly override that default, and the override is stored in provenance/audit history.

Each profile/policy has an immutable schema/version ID.


## 9. Evaluation architecture

### 9.1 Four independent layers

1. **Invariant tests** — placeholders, numbers, units, URLs, code, math, tags, timestamps, speakers.
2. **Text metrics** — chrF++ / SacreBLEU where a reference exists.
3. **Neural MT evaluation** — optional COMET/XCOMET; DocCOMET for document context where appropriate.
4. **Human MQM** — release-gate samples reviewed with minor/major/critical errors.

No single scalar score is allowed to hide critical findings.

### 9.2 Golden corpus

Create a versioned `evals/golden/` corpus with:
- all existing 10 domains,
- short and long context,
- idioms,
- mixed Persian/English technical terms,
- numbers/dates/currency/units,
- code/math/URLs/HTML,
- dialogue,
- tables/list structures,
- subtitles,
- meeting/lecture transcript samples,
- adversarial prompt-injection text,
- known calque traps,
- human reference translations where licensing permits.

### 9.3 Release quality gates

For a release candidate:
- 100% protected-span round trip on invariant suite.
- 100% preservation of required numbers/units/identifiers.
- 100% compliance for **applicable** hard-glossary constraints in the deterministic test set, including approved morphology/inflection variants.
- zero silent source echo in real translation mode.
- no new critical MQM finding in golden regression set.
- metric non-regression against frozen baseline; statistically compare systems when sample size permits.
- human review on a representative release sample before claiming “publication-grade”.

The current internal `100 - penalty` score may remain as a lint severity indicator but is renamed so it is not confused with translation quality.

## 10. Document and structured-file architecture

Every format is an adapter implementing:

~~~python
class IngestAdapter(Protocol):
    def detect(self, path: Path) -> bool: ...
    def ingest(self, path: Path) -> Artifact: ...

class ExportAdapter(Protocol):
    def export(self, artifact: Artifact, destination: Path) -> None: ...
~~~

### 10.1 Format rollout

**Phase 1:** TXT, Markdown, HTML/plain structured text  
**Phase 2:** SRT, VTT, ASS; JSON path-selected values  
**Phase 3:** DOCX and EPUB with formatting preservation  
**Phase 4:** PPTX/XLSX  
**PDF:** parser-driven extraction/reflow first; exact layout preservation is a separate capability and must not be falsely promised.

Inline tags/formatting are represented as protected/structural spans. Only translatable text reaches an LLM.

## 11. Audio and meeting/lecture module

Audio is an optional extra; it must not make the core install heavy.

### 11.1 ASR adapter

Initial recommended adapter:
- faster-whisper
- configurable model/device/compute type
- language auto-detect or explicit `fa`
- timestamps
- VAD option

Optional diarization adapter:
- WhisperX + a diarization backend, or another compatible local engine.
- Diarization is not required for single-speaker lecture mode.

### 11.2 Audio workflow

~~~text
audio/video
  → decode
  → ASR segments + timestamps
  → optional diarization / speaker labels
  → Persian normalization
  → optional spoken→written formalization
  → transcript artifact
  → template transform
      ├─ lecture notes
      ├─ meeting minutes
      ├─ executive summary
      ├─ decisions + action items
      └─ subtitle export
~~~

### 11.3 Lecture notes template

Outputs:
- title/metadata,
- structured outline,
- concepts/definitions,
- examples,
- key claims,
- formulas/technical terms preserved,
- questions raised,
- concise review section,
- timestamp links back to transcript where available.

### 11.4 Meeting template

Outputs:
- participants/speakers when known,
- agenda/topics,
- decisions,
- action items with owner/due date only when explicitly supported,
- open questions,
- risks/follow-ups,
- full timestamped transcript,
- formal Persian minutes option.

Never invent owners, due dates, or decisions absent from the transcript.

## 12. Interfaces

### 12.1 CLI
Primary lightweight interface:
- `tarjoman translate`
- `tarjoman review`
- `tarjoman lint`
- `tarjoman eval`
- `tarjoman project ...`
- `tarjoman glossary ...`
- `tarjoman tm ...`
- `tarjoman compose ...`
- `tarjoman transcribe ...` (ASR extra)
- `tarjoman speak ...` / `tarjoman pronunciation ...` (TTS extra)
- `tarjoman serve` (server extra)
- `tarjoman mcp` (MCP extra)

### 12.2 Python SDK
Typed application-service API; integrations never need to spawn the CLI.

### 12.3 REST / jobs
Optional FastAPI adapter:
- versioned `/v1` endpoints,
- persistent long-job API,
- idempotency,
- progress/cancel,
- OpenAPI generated from application contracts,
- loopback bind by default.

### 12.4 MCP
Tarjoman targets the current tested MCP specification/SDK at implementation time and records that protocol revision in its compatibility matrix.

As of Architecture Zero review (2026-09-21), MCP `2026-07-28` has a stateless core and long-running Tasks extension. Tarjoman maps its **existing core job engine** to MCP task semantics where supported; MCP is not a second job database.

Initial capabilities:
- translate,
- review,
- project create/status,
- glossary upsert,
- TM search,
- eval run,
- transcribe,
- notes/minutes generate,
- speak,
- export.

Large artifacts are returned by resource/artifact handle, not giant inline payloads.

### 12.5 A2A
A2A remains optional for an independently deployed Tarjoman agent. As of this review, A2A 0.3 defines discovery and task collaboration. It is **not** on Core v1 critical path; Python/CLI/MCP cover normal assistant/tool integration.

### 12.6 Interface equivalence
Interfaces may differ in transport/auth UX but must call the same application use cases. No CLI-only, API-only, or MCP-only business logic is permitted.

## 13. Security, privacy, network, and threat model

### 13.1 Default posture
- local workspace storage,
- no telemetry by default,
- no raw source/transcript/audio in normal logs,
- secrets only through environment/keyring/secret provider,
- cloud/model/network use is explicit policy.

### 13.2 NetworkPolicy is global, not provider-only

`local_only` forbids **all** unapproved egress:
- LLM providers,
- remote OCR/document services,
- model/font/CDN downloads,
- telemetry/update checks,
- remote TTS/ASR,
- arbitrary URL fetches.

`cloud_allowed` and `restricted` enumerate allowed adapters/destinations. Every network-capable adapter asks the same NetworkPolicy gate.

Model/font assets required for offline artifacts must be local/package-managed; generated HTML defaults self-contained/offline.

### 13.3 SSRF and provider endpoint rule

Custom provider base URLs are trusted administrator/project configuration, never arbitrary untrusted per-request URLs in server/MCP calls. Server mode may optionally enforce hostname allowlists. Redirect policy and special/private address access are controlled; unknown URL schemes are rejected.

### 13.4 Prompt injection

Retrieved/source content is data:
- translation/review model requests do not enable arbitrary tool calls,
- source text cannot grant permissions or alter Network/License/Privacy policy,
- side-effectful agent actions require application policy/authorization, not a sentence in a document,
- structured response validation happens before persistence.

### 13.5 File/parser boundary

Untrusted file ingestion:
- size/count/decompression limits,
- path traversal/symlink rejection,
- MIME + parser validation,
- temporary workspace quotas,
- generated names rather than trusting uploaded names,
- artifacts stored outside any directly served web root.

Archive/document adapters must defend against zip bombs and external entity/network resolution.

### 13.6 External process runner

FFmpeg, Typst, LibreOffice, or other binaries:
- execute with argument arrays, never `shell=True`,
- have timeout/cancellation,
- run in controlled temp/output directories,
- receive no secrets unless required,
- capture bounded logs,
- capability/version checked before use.

### 13.7 Data at rest — explicit scope

Tarjoman v1 **does not claim application-level content encryption by default**. Sensitive deployments must use OS/disk/volume encryption and filesystem permissions. If application-level encrypted workspaces are later added, that requires an ADR and migration/recovery design.

Secret storage via OS keyring is separate from content-at-rest encryption.

### 13.8 Deletion/retention

Deleting a logical artifact removes references immediately. Content-addressed blobs are garbage-collected only when no live artifact reference remains and retention policy permits deletion. Derived audio/embeddings/cache entries tied to deleted voice/source artifacts follow the same lineage cleanup policy.

### 13.9 Threat-model boundary

v1 protects against:
- accidental leakage through logs/config,
- path traversal/upload abuse,
- prompt-injected tool authorization,
- uncontrolled network egress,
- unauthorized remote API use,
- dependency/model-license mistakes.

v1 does not claim protection from:
- a fully compromised OS account/root,
- malicious local administrators,
- hardware/firmware compromise,
- forensic recovery from an unencrypted disk.

## 14. Reliability, performance, and observability

### 14.1 Resumability
Each long job checkpoints stage + segment state. Atomic artifact writes use temp-file + replace semantics.

### 14.2 Concurrency
- bounded async worker pool,
- per-provider semaphore,
- configurable max in-flight requests,
- backpressure rather than unbounded task creation,
- deterministic output ordering independent of completion order.

### 14.3 Retry rules
Retry only transient failures: rate limits, timeouts, selected 5xx/network errors. Validation/semantic failures go through a bounded correction path, not infinite retries.

### 14.4 Structured logs
Every log record can include:
- run_id / project_id / segment_id,
- stage,
- provider/model,
- latency,
- retry count,
- cache hit,
- quality finding counts.

### 14.5 Metrics
Optional server metrics:
- job latency,
- provider latency/error rate,
- tokens/cost,
- cache hit rate,
- quality finding rate,
- ASR real-time factor when audio enabled.

## 15. Packaging and technology

### 15.1 Primary language
Keep **Python** as the orchestration/core language. It already fits the codebase and AI/NLP ecosystem.

Rust/TypeScript are allowed only where they solve a concrete boundary problem (desktop/audio capture/UI), not as a rewrite goal.

### 15.2 Target Python
Production target: Python 3.11–3.13 initially. Reassess 3.10 compatibility before release rather than carrying it automatically.

### 15.3 Optional extras

Target packaging shape:

- `tarjoman` — core, CLI, deterministic Persian quality, SQLite state
- `tarjoman[llm]` — HTTP/provider adapters
- `tarjoman[docs]` — document adapters
- `tarjoman[asr]` — faster-whisper/audio-input tooling
- `tarjoman[tts]` — speech synthesis engines/G2P adapters
- `tarjoman[speech]` — convenience extra for ASR + TTS
- `tarjoman[eval]` — SacreBLEU/COMET/TTS-eval stack
- `tarjoman[server]` — FastAPI/Uvicorn
- `tarjoman[mcp]` — MCP server
- `tarjoman[all]` — convenience only

Heavy optional libraries must not leak into base imports.

## 16. Target repository layout

~~~text
tarjoman/
├─ ARCHITECTURE_ZERO.md
├─ ROADMAP.md
├─ research/
├─ docs/
│  └─ adr/
├─ src/tarjoman/
│  ├─ application/
│  ├─ core/
│  │  ├─ contracts/
│  │  ├─ pipeline/
│  │  └─ policies/
│  ├─ providers/
│  ├─ quality/
│  ├─ profiles/
│  ├─ memory/
│  ├─ ingest/
│  ├─ export/
│  ├─ audio/          # imported only with extra
│  ├─ evals/          # lightweight interfaces; heavy impl optional
│  ├─ interfaces/
│  │  ├─ cli/
│  │  ├─ api/
│  │  ├─ mcp/
│  │  └─ a2a/
│  └─ prompts/
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  ├─ contract/
│  └─ security/
├─ evals/
│  ├─ golden/
│  └─ reports/
└─ .github/workflows/
~~~

Migration to `src/` layout happens once in Foundation Phase; avoid repeated reshuffles.

## 17. CI/CD and supply-chain requirements

Pull requests eventually run:
1. format/lint,
2. static type checks,
3. unit tests,
4. contract tests,
5. security/static checks,
6. package build,
7. offline deterministic benchmark,
8. golden eval smoke subset.

Scheduled/manual workflows run expensive provider/COMET/audio evaluations so pull requests do not require secrets or GPUs.

Releases:
- version from one source of truth,
- changelog/release notes,
- build sdist + wheel,
- install smoke test in clean env,
- optional Sigstore/package provenance,
- dependency vulnerability scan,
- SBOM for packaged server/desktop distributions.

`main` should be branch-protected after the first production CI gates exist.

## 18. Versioning and compatibility policy

Version domains are distinct:

1. **Package version** — Semantic Versioning for released Tarjoman code.
2. **DB schema version** — monotonically increasing migrations/checksums.
3. **IR/schema version** — serialized contract compatibility.
4. **REST API version** — URL/media contract, initially `v1`.
5. **MCP/A2A compatibility** — tested protocol/SDK revision matrix.
6. **Prompt/profile/rule/strategy IDs** — immutable behavior versions.
7. **Model/Data/Service manifests** — immutable source revision/hash + reviewed policy.
8. **Golden corpus version** — frozen benchmark data revision.

Before package 1.0, breaking Python/CLI behavior is allowed only when roadmap/notes make it explicit. Once Core v1.0 ships, public contracts follow SemVer and migration policy.

A workspace created by a released version must either:
- open directly,
- migrate through tested forward migrations,
- or fail read-only with a precise compatibility message.

Silent downgrade, silent destructive migration, and opening a newer unsupported schema for writing are forbidden.

## 19. Locked decision ledger

| ID | Decision |
|---|---|
| D01 | Tarjoman becomes a Persian-first content transformation engine, not only a regex translation script. |
| D02 | Python remains the core language; no rewrite for fashion. |
| D03 | Base installation stays lightweight; heavy AI/audio/eval/server features are extras. |
| D04 | Canonical IR separates ingestion/export from translation logic. |
| D05 | Real model backend is mandatory for real translation; Echo is test-only. |
| D06 | OpenAI-compatible provider is first implementation priority; vendor adapters stay behind one harness. |
| D07 | SQLite WAL is the production local state/TM/termbase store. |
| D08 | Translation memory, glossary, style profiles, prompts, and provenance are versioned. |
| D09 | Regex anti-calque rules become diagnostics by default; unsafe semantic auto-rewrites are removed. |
| D10 | Quality evaluation is independent from generation and includes external metrics + human MQM. |
| D11 | File formats are adapters over one IR; structure is never entrusted blindly to an LLM. |
| D12 | PDF exact-layout preservation is not promised until a dedicated fidelity pipeline proves it. |
| D13 | Audio/meeting/lecture capability is an optional module over the same artifact pipeline. |
| D14 | CLI/Python are core; FastAPI and MCP are optional interfaces over shared services. |
| D15 | MCP is the primary agent-tool protocol; A2A is optional for remote-agent identity/collaboration. |
| D16 | Privacy policy is enforced in the Model Harness; source content is not logged by default. |
| D17 | Long jobs are resumable, idempotent, bounded-concurrency jobs. |
| D18 | Architecture changes after freeze require ADRs. |
| D19 | Module dependencies follow Core <- Application <- Infrastructure/Adapters <- Interfaces; reverse imports are forbidden. |
| D20 | SQLite stores transactional metadata; large/binary artifacts live in a content-addressed filesystem store, not DB BLOBs. |
| D21 | Configuration precedence is CLI > environment > project config > user config > defaults; secrets never live in project config. |
| D22 | v1 uses a SQLite-backed single-node persistent job engine; Redis/Celery/Kafka are forbidden unless an ADR proves need. |
| D23 | Prompts, profiles, rules, schemas, and strategy versions are immutable identifiers recorded in every run. |
| D24 | TTS is an optional provider-neutral speech-output module; it never becomes a mandatory base dependency. |
| D25 | Persian speech normalization, pronunciation lexicon, G2P, speech planning, synthesis, and audio post-processing are separate contracts. |
| D26 | `nimaone/persian_tts` / pocket-tts-farsi-v2 is research/non-commercial by default; it is never bundled into a commercial production profile without an explicit compatible license. |
| D27 | Every external model/voice/dataset must have a machine-readable ModelManifest and pass a license gate before production use or redistribution. |
| D28 | Voice cloning requires explicit capability enablement, reference-audio consent/ownership attestation, provenance, and retention controls. |
| D29 | TTS quality is independently evaluated for pronunciation/intelligibility, naturalness, speaker similarity when relevant, long-form stability, latency/RTF, memory, and failure rate. |
| D30 | Patterns from external repos may be independently reimplemented; code is not copied when repository/model licensing is absent, incompatible, or unclear. |
| D31 | Raw audio/transcript/source text is immutable evidence; cleaned/formalized/synthesized artifacts are versioned derivatives with lineage. |
| D32 | Optional plugins are registered explicitly; import-time plugin discovery and surprise network/model downloads are forbidden. |
| D33 | Architecture-conformance tests enforce dependency direction, optional-dependency isolation, no direct provider SDK in core, and no network in deterministic tests. |
| D34 | One implementation work package per PR by default; architecture-changing code is blocked until its ADR is accepted. |
| D35 | Provider/model fallback is explicit policy; silent fallback to a different model, cloud, language, or quality tier is forbidden. |
| D36 | Workspace is the persistence/trust boundary; project state is not split between user-global and project-local databases. |
| D37 | Result Cache and Translation Memory are separate systems with different keys, lifecycle, and authority. |
| D38 | Canonical public job status vocabulary is QUEUED/RUNNING/WAITING_REVIEW/SUCCEEDED/FAILED/CANCELLED. |
| D39 | Runtime transformation does deterministic validation; comparative/reference evaluation is an out-of-band pipeline. |
| D40 | DomainProfile, StyleProfile, WorkflowProfile, Review/Privacy/Provider/License policies, and Capability Bundles are distinct types. |
| D41 | Server v1 is single-tenant per workspace with scoped high-entropy API principals/tokens; full multi-user IAM/passwords are deferred. |
| D42 | A single workspace has one authoritative scheduler lease domain; embedded server mode uses one scheduler owner, not multiple Uvicorn schedulers. |
| D43 | Content-addressed artifact blobs are workspace-scoped, reference-counted/reachability-GC'd, and backed up with a consistent DB snapshot manifest. |
| D44 | NetworkPolicy covers all egress, not only LLM providers; local_only means no hidden CDN/model/OCR/telemetry network path. |
| D45 | Custom network endpoints are trusted configuration, not untrusted request parameters; server-mode SSRF controls apply. |
| D46 | v1 third-party runtime plugins are not auto-loaded; built-in/explicit adapters only. A third-party plugin ABI requires a later ADR/security review. |
| D47 | License eligibility depends on deployment purpose and distribution mode, not the word “production”; unknown status never auto-passes. |
| D48 | Core v1.0 is not blocked by ASR, TTS, Web UI, or A2A; those are separately gated capability tracks. |
| D49 | High-risk legal/medical outputs require human approval by default before APPROVED status; explicit policy overrides are audited. |
| D50 | MCP long-running Tasks map onto the core Tarjoman job engine; protocol adapters never become a second source of job truth. |

## 20. Release milestones and production definitions

### 20.1 Core v1.0 — critical path

Core v1.0 can ship when:
- real provider translation works end-to-end; no silent echo,
- Workspace/SQLite/artifact store/migrations/result cache/TM are proven,
- deterministic Persian constraints and golden regression suite exist,
- at least one optional external MT metric integration is available,
- human MQM release review has been performed,
- TXT/MD/HTML/SRT/VTT are reliable; DOCX ships only if its fidelity gate passes,
- long translation jobs resume after crash/cancel,
- provenance/redacted logging/policy gates are complete,
- CLI/Python and MCP core paths pass conformance; REST server conformance is required only when the server capability is shipped,
- clean wheel install and release/security/license checks pass.

**Core v1.0 does not wait for ASR, TTS, Web UI, or A2A.**

### 20.2 ASR/Knowledge capability release

ASR is advertised only after:
- media ingestion safety,
- Persian ASR evaluation,
- transcript lineage,
- resume/recovery,
- meeting/lecture evidence links,
- model/data license manifests,
- capability-specific release hardening.

### 20.3 TTS capability release

TTS is advertised only after:
- at least one license-eligible engine for the intended deployment purpose,
- pronunciation/G2P/speech-plan tests,
- listening/intelligibility/long-form/runtime report,
- reference-voice retention/provenance/consent policy where cloning exists,
- capability-specific release hardening.

### 20.4 UI and A2A

Web UI and A2A may ship in later minor releases without delaying Core v1. MCP remains the primary agent-tool surface.

### 20.5 “Production-ready” is capability-scoped

A release may be:
- Core: production-ready,
- ASR: experimental,
- TTS: unavailable,
without contradiction. README/badges must state capability maturity separately.

## 21. Deferred, not ambiguous

Intentionally deferred:
- Web UI framework until REST/application contracts stabilize.
- Desktop/Tauri client.
- Exact PDF-layout reconstruction.
- Full multi-user human IAM/password/session product.
- Distributed scheduler/Redis/Celery/Kafka/Postgres.
- Third-party plugin ABI/sandbox.
- Default frontier cloud model.
- Default diarization engine until bake-off/license review.
- Application-level encrypted workspace format.
- Custom model training/fine-tuning.
- A2A as a Core v1 requirement.

The default action is **do not implement deferred work early**. A coding agent may create an ADR proposal when measured evidence justifies pulling one forward.

## 22. Implementation architecture: layers and dependency law

This section turns the conceptual architecture into rules that coding agents can test.

### 22.1 Layers

~~~text
┌─────────────────────────────────────────────────────────┐
│ Interfaces: CLI / REST / MCP / A2A / future Web UI     │
└──────────────────────────────┬──────────────────────────┘
                               │ calls
┌──────────────────────────────▼──────────────────────────┐
│ Application: use-cases, jobs, orchestration, services  │
└──────────────────────────────┬──────────────────────────┘
                               │ depends on ports/contracts
┌──────────────────────────────▼──────────────────────────┐
│ Core: IR, policies, state machines, pure quality rules │
└──────────────────────────────▲──────────────────────────┘
                               │ implemented by
┌──────────────────────────────┴──────────────────────────┐
│ Infrastructure/Adapters: DB, providers, files, ASR/TTS │
└─────────────────────────────────────────────────────────┘
~~~

Dependency rule:
- `core` imports only stdlib + explicitly approved lightweight schema/runtime dependencies.
- `application` may import `core`, never concrete infrastructure.
- `infrastructure/adapters` implement ports defined by core/application.
- `interfaces` call application services and may compose adapters at startup.
- adapters do not call CLI/API/MCP code.
- one interface never imports another interface.
- provider SDKs, FastAPI, MCP SDK, Whisper, ONNX Runtime, COMET and document libraries are never imported by base-core modules.

CI must enforce this with import-boundary tests.

### 22.2 Package ownership

| Package | Owns | Must not own |
|---|---|---|
| `core.contracts` | stable IR/data contracts | network, DB sessions, provider clients |
| `core.policies` | privacy/license/retry/routing decisions | provider-specific code |
| `core.quality` | deterministic Persian normalization + typed findings | model calls |
| `application` | use cases and transaction boundaries | HTTP framework |
| `providers` | LLM provider adapters | business decisions |
| `storage` | SQLite repositories + blob store | UI behavior |
| `ingest/export` | file format transformations | translation strategy |
| `speech.asr` | ASR ports/adapters | meeting summaries |
| `speech.tts` | TTS ports/adapters | translation decisions |
| `interfaces.*` | input/output protocol mapping | duplicate core logic |

## 23. Configuration and secret contract

### 23.1 Precedence

Highest wins:

1. explicit CLI/API call arguments,
2. environment variables,
3. project `tarjoman.toml`,
4. user config under OS application-data directory,
5. packaged defaults.

No hidden current-working-directory config lookup beyond the explicit project file.

### 23.2 Secrets

API keys/tokens:
- environment variable or OS keyring/secret provider only,
- never written to project TOML, SQLite run payloads, logs, benchmark reports, or exported artifacts,
- redaction applies to exception text and provider HTTP traces.

### 23.3 Reproducibility snapshot

Each run stores a redacted resolved-config snapshot hash plus:
- provider/model,
- strategy ID,
- prompt/profile/rule versions,
- glossary/TM/context hashes,
- random seed where supported,
- package version and schema version.

## 24. Error taxonomy and failure semantics

Public errors are typed:

| Error | Retry? | User action |
|---|---:|---|
| `ConfigurationError` | no | fix config |
| `PolicyViolationError` | no | change policy/permission |
| `LicensePolicyError` | no | use approved model/voice |
| `CapabilityUnavailableError` | no | install extra or choose adapter |
| `ProviderRateLimitError` | bounded | wait/backoff |
| `ProviderTransientError` | bounded | retry/fallback if policy allows |
| `ProviderPermanentError` | no | fix request/provider |
| `StructuredOutputError` | one bounded repair path | model/schema issue |
| `ArtifactValidationError` | no | inspect source/parser |
| `MigrationError` | no automatic destructive repair | restore/upgrade |
| `JobCancelledError` | no | expected cancellation |
| `SpeechSynthesisQualityError` | bounded per configured policy | retry/alternate engine only if allowed |

Rules:
- no blanket `except Exception: pass` in production paths,
- no infinite retry,
- errors crossing CLI/API/MCP are mapped to stable machine codes,
- raw source content is excluded from normal error messages.

## 25. Workspace and storage architecture

### 25.1 Workspace layout

A workspace is explicit:

~~~text
<workspace-root>/
  tarjoman.toml                 # workspace/project defaults; no secrets
  .tarjoman/
    state.sqlite3               # workspace metadata/jobs/projects/TM/etc.
    artifacts/
      sha256/
        ab/
          <full-sha256>
    tmp/
    locks/
    backups/
  exports/
~~~

User-global application data stores user preferences/provider aliases/keyring references only; **never project/TM/job state**.

Server mode opens exactly one workspace root per process in v1. That workspace may contain multiple logical Project records.

### 25.2 Managed source rule

On ingestion, source bytes are copied to the artifact store by default and hashed. External source paths/URLs are provenance only. A future linked-source mode requires an explicit option and cannot be the default reproducibility path.

### 25.3 Artifact blob lifecycle

SQLite stores metadata/text-sized records; large binaries remain files.

Each blob:
- SHA-256,
- byte size,
- MIME,
- producer/version,
- parent lineage,
- retention/sensitivity.

Deduplication is **within one workspace**, not global across unrelated workspaces.

Deletion:
1. logical artifact row becomes deleted/tombstoned according to audit policy,
2. references from live derivatives are checked,
3. blob GC removes unreferenced bytes only after retention rules permit,
4. cache/derived voice state tied solely to deleted input is removed.

### 25.4 Atomic writes

1. create temp file inside workspace temp/store filesystem,
2. stream + enforce size quota + hash,
3. flush/fsync where supported,
4. validate expected format/size,
5. atomic rename into content-addressed location,
6. commit metadata transaction.

No DB row points to a partial “completed” blob.

### 25.5 Database rules

- numbered immutable SQL migrations with checksums,
- `PRAGMA foreign_keys=ON`,
- WAL for local same-host workspace,
- explicit busy timeout,
- repository layer owns SQL,
- migration lock before schema changes,
- network filesystem storage is unsupported for WAL workspace DB in v1.

### 25.6 Consistent backup

Do not naïvely copy a live WAL database.

Backup procedure:
1. create consistent SQLite snapshot using the supported online backup mechanism (or equivalent tested safe method),
2. record snapshot DB hash/schema version,
3. copy/reconcile all referenced artifact blobs into backup set,
4. write backup manifest with artifact hashes/counts,
5. verify restore into a temporary workspace before marking a backup verified when running release/recovery tests.

Restore never overwrites a live workspace without explicit operator action.

## 26. Persistent job engine

The job engine is **foundation infrastructure**, not an API-only feature.

### 26.1 States

`QUEUED → RUNNING → {WAITING_REVIEW | SUCCEEDED | FAILED | CANCELLED}`

Cancellation is cooperative and persisted. A cancelled job never later flips to SUCCEEDED unless explicitly retried as a new attempt/run.

### 26.2 Atomic claim / lease

Each runnable job has:
- job_id,
- state,
- priority,
- created_at,
- claim_token / lease_owner,
- lease_expires_at,
- attempt,
- idempotency identity.

Claiming is one atomic DB transaction/compare-and-set. Only the owner of the current claim token may heartbeat/complete that attempt.

Expired RUNNING leases are recovered according to the stage's resumability policy.

### 26.3 Scheduler topology

v1 rule:
- one authoritative scheduler owner per workspace,
- embedded FastAPI server mode runs one scheduler process/owner,
- do not launch multiple Uvicorn worker processes each with its own scheduler,
- CPU/GPU work may execute in bounded worker threads/subprocesses managed by that scheduler,
- multi-scheduler/distributed execution requires an ADR + concurrency proof.

### 26.4 Checkpoints

Every resumable stage stores:
- input identity/hash,
- output identity/hash,
- implementation version,
- state,
- attempts,
- timestamps,
- typed last error,
- provider/device metadata if relevant.

A stage is reused only when its input/config/version hashes still match.

### 26.5 Idempotency

Operation identity = workspace/project + operation type + immutable input IDs/hashes + resolved material config.

External API idempotency keys map to that internal identity and have documented retention. Repeating a request must return/reuse the same in-flight/succeeded operation where policy permits rather than creating duplicate billable work.

### 26.6 Concurrency and backpressure

- bounded queue admission,
- bounded worker pool,
- per-provider semaphore,
- per-device speech semaphore,
- deterministic output ordering,
- no unbounded task fan-out,
- explicit cancellation/timeouts.

## 27. Segment, approval, and TM promotion state

Logical segment workflow:

`PENDING → DRAFTED → REVIEW_REQUIRED → REVIEWED → APPROVED`

Rules:
- each transition creates/points to immutable SegmentVersion records,
- changing source creates a new source version and invalidates active downstream approval,
- changing a **material** glossary/style/workflow/review policy creates a new required evaluation/review lineage,
- historical approvals remain audit history but are not treated as active for changed inputs,
- only policy-eligible reviewed/approved target versions can promote to authoritative TM,
- high-risk legal/medical domain defaults require human principal approval for APPROVED,
- auto-approval policies and overrides are explicit and provenance-recorded.

## 28. Prompt, rule, and profile registry

IDs are immutable, e.g.:
- `translate.fa.v1`
- `critique.fa.mqm.v2`
- `profile.technical.fa.v3`
- `rules.persian-normalize.v2`
- `strategy.reflect-1.v1`

Editing behavior creates a new version ID. Old project runs remain reproducible.

Prompt templates are code-reviewed assets, not user-writable arbitrary templates in production mode unless the project is explicitly in custom-prompt mode.

## 29. Capability registry and plugin boundary

Optional components register explicit capability metadata:
- capability_id,
- package/version,
- operations/languages/formats,
- hardware/network requirements,
- dependency extra,
- license/policy manifest IDs.

### 29.1 v1 adapter policy

Core v1 supports:
- built-in adapters shipped with Tarjoman,
- explicitly configured first-party optional packages.

Core v1 does **not** scan/import arbitrary third-party Python entry points/plugins at startup.

A public third-party plugin ABI requires a later ADR covering:
- versioning,
- signature/provenance,
- permissions,
- filesystem/network access,
- dependency isolation/sandboxing,
- failure containment.

Missing optional capability returns `CapabilityUnavailableError` and exact install/config guidance. No surprise model/package download occurs at import or startup.

## 30. Model, dataset, service, and license compliance registry

Every external model/voice/dataset/service has a manifest.

Required fields as applicable:
- immutable ID + source URL/provider + revision/hash,
- task/languages,
- code license,
- model-weight license,
- dataset/training provenance statement,
- service Terms/Privacy URL for remote APIs,
- commercial_use: allowed | forbidden | unknown,
- redistribution: allowed | forbidden | unknown,
- remote-code requirement,
- network requirement,
- attribution obligations,
- reviewed_at + evidence.

### 30.1 Purpose-aware license gate

License policy evaluates at least:
- deployment_purpose: `commercial | noncommercial | research`,
- distribution_mode: `bundled | user_supplied | remote_service`.

Rules:
- `unknown` never auto-passes,
- commercial deployments require commercial eligibility,
- noncommercial production may use NC assets only when all terms are satisfied and manifest policy allows,
- research mode is explicit and cannot be mislabeled production-commercial,
- bundling/redistribution may be forbidden even when local use is allowed,
- a permissive child card never overrides restrictive base/model/data lineage.

### 30.2 Supply-chain rule

Model acquisition is an explicit install/prepare operation:
- pinned revision,
- expected hash/manifest,
- remote custom code disabled by default,
- no download during normal import/startup,
- artifact/license manifest persisted before activation.

## 31. Speech-output (TTS) architecture

TTS is a first-class optional output subsystem, but it is not coupled to translation.

~~~text
Text/Artifact
  → SpeechTextNormalizer
  → PronunciationResolver
      ├─ project pronunciation lexicon
      ├─ named-entity overrides
      └─ G2P adapter
  → SpeechPlanner
      ├─ sentence/phrase boundaries
      ├─ pause plan
      ├─ chunk/token budget
      ├─ pace/style hints
      └─ language/code-switch spans
  → TtsEngine
      ├─ fixed/multi-speaker
      └─ optional voice-cloning reference
  → AudioQualityGate
  → AudioPostProcessor
  → AudioArtifact + provenance
~~~

### 31.1 TTS contracts

`TtsEngine`:

~~~python
class TtsEngine(Protocol):
    def capabilities(self) -> TtsCapabilities: ...
    async def synthesize(self, request: TtsRequest) -> TtsResult: ...
~~~

`TtsCapabilities` declares:
- languages,
- voice cloning yes/no,
- streaming yes/no,
- seed/determinism support,
- sample rates,
- max recommended text/chunk,
- GPU/CPU requirements,
- supported reference-audio duration,
- license manifest ID.

`TtsRequest` includes:
- normalized speech text or phoneme plan,
- language,
- voice profile,
- pace/style,
- seed,
- output format,
- privacy/license policy.

`TtsResult` includes:
- audio artifact,
- sample rate/channels/duration,
- engine/model/version,
- seed,
- pronunciation plan hash,
- quality-gate results,
- usage/latency/RTF,
- warnings.

### 31.2 Speech normalization is not publication normalization

Before TTS, text may require:
- number verbalization,
- currency/date/time reading,
- abbreviations/acronyms,
- URLs/emails policy,
- Latin technical-term pronunciation,
- punctuation-to-prosody mapping,
- optional Persian diacritics/phoneme hints.

The original written artifact is never modified by speech normalization.

### 31.3 Pronunciation lexicon

Project-level dictionary:

`surface form → normalized reading → optional phonemes → language tag → notes/status`

Priority:
1. explicit segment override,
2. approved project pronunciation lexicon,
3. named-entity dictionary,
4. G2P,
5. engine-native fallback.

Manual phoneme editing learned from `nimaone/persian_tts` becomes a durable pronunciation override, not a one-off UI hack.

### 31.4 Long-form speech planner

The planner, not the model, owns:
- sentence splitting,
- phrase packing,
- max token/phoneme budget,
- punctuation pauses,
- paragraph/chapter gaps,
- deterministic chunk order,
- retry boundaries.

Engine-specific constraints are capability data, not hardcoded global constants.

### 31.5 Voice profiles

A voice profile may be:
- built-in fixed voice,
- engine speaker ID,
- user reference audio,
- reusable derived speaker embedding if the engine/license permits.

Reference audio rules:
- content type/size/duration validation before full decode,
- mono/sample-rate conversion in controlled temp storage,
- explicit retention policy,
- original reference hash recorded,
- deletion removes derived cache/embedding where applicable.

## 32. TTS engines: adoption policy

### 32.1 `nimaone/persian_tts` / Pocket-TTS Farsi v2 ONNX

**What we adopt as engineering patterns**
- pure ONNX CPU path without Torch,
- explicit G2P stage,
- model package manifest,
- word/phrase-aware chunk planning,
- reference-voice caching,
- reproducible seed,
- bounded parallel chunk generation,
- bounded retry after acoustic-quality heuristics,
- loudness/silence stitching,
- manual pronunciation correction.

**What we do not adopt directly**
- no production bundling of the current Pocket Farsi v2 weights under CC-BY-NC-4.0,
- no code copy from the repository while its own repository license is not explicit,
- no unauthenticated demo-server design,
- no full-file upload read without byte limits,
- no global engine lock as final concurrency architecture,
- no in-memory-only result store as production artifact storage.

A future adapter can support a user-supplied Pocket ONNX package in `research/noncommercial` mode if license policy allows.

### 32.2 Commercial-capable candidates to benchmark

Candidates are not defaults until bake-off and license review:

- **MOSS-TTS v1.5** — model card lists Persian among 31 languages and Apache-2.0; strong long-form/voice-cloning features, but ~8.5B parameters / large weight footprint make it a heavy GPU/server profile, not a lightweight default.
- **Persian Piper/ONNX voices** — attractive fixed-voice CPU profile; each voice's exact model/data license and quality must be recorded before approval.
- **ManaTTS-derived Persian models** — some published weights report CC0; useful commercial-compatible baseline candidates if quality/fidelity pass.
- other new Persian models may enter only through the same manifest/bake-off process.

Models based on XTTS-v2/CPML or MMS CC-BY-NC remain non-commercial unless their legal status changes.

## 33. Voice-cloning safety and consent

Voice cloning is an opt-in capability, never the anonymous default.

Production requirements:
- feature disabled unless project/admin enables it,
- request records that user asserts authorization to use the reference voice,
- public unauthenticated endpoint cannot create persistent cloned voice profiles,
- retention/deletion policy for reference audio and derived embeddings,
- provenance flag `voice_cloned=true` in generated audio metadata/report,
- engine-provided watermarking is preserved when available,
- rate/size limits and abuse controls in server mode,
- logs never contain raw voice bytes.

Tarjoman does not claim biometric identity verification; it records provenance and enforces product policy.

## 34. TTS quality evaluation

A TTS release is evaluated independently from synthesis.

### 34.1 Persian pronunciation suite
Must cover:
- Ezafe,
- ambiguous unvowelled words,
- Arabic/Persian names,
- English technical terms in Persian,
- numbers/dates/currency,
- acronyms,
- ZWNJ compounds,
- punctuation/prosody,
- long unpunctuated sentences,
- domain terminology.

### 34.2 Metrics

Record at minimum:
- ASR-backtranscription WER/CER as an intelligibility signal,
- pronunciation error rate on curated lexicon cases,
- human MOS/naturalness sample,
- speaker similarity for clone engines,
- long-form repetition/runaway/truncation rate,
- duration/pace error,
- first-audio latency,
- RTF,
- peak RAM/VRAM,
- cold-start time,
- failure/retry rate.

UTMOS or another learned metric may be secondary evidence, not the sole release gate.

### 34.3 Determinism
Where seed is supported:
- same engine/model/voice/text/seed must reproduce within defined tolerance,
- engine changes require a new implementation/model version.

## 35. Speech artifact lineage

Examples:

~~~text
source_document
  └─ translated_fa_v4
      ├─ speech_plan_v2
      │   └─ wav_v1
      └─ audiobook_mp3_v1

meeting_audio_raw
  └─ transcript_raw
      └─ transcript_clean
          ├─ minutes_v3
          └─ spoken_summary_script
              └─ tts_audio_v2
~~~

Every derivative points to parent artifact IDs and configuration hashes.

## 36. Server/API security and principal model

### 36.1 v1 tenancy

Server v1 is **single-tenant per workspace**. It is not a SaaS IAM system.

Remote/API actors are `Principals` authenticated by high-entropy API tokens:
- token secret displayed/stored only at creation,
- only a cryptographic hash + metadata is stored,
- scopes: read / write / admin plus optional project restrictions,
- revocation/expiry supported.

No username/password/session UI is required for Core v1. Multi-user human IAM is deferred.

### 36.2 Binding/TLS

- default bind: loopback,
- unauthenticated mode allowed only on loopback and must be explicit,
- non-loopback production deployment requires authentication and TLS termination,
- recommended v1 network deployment is behind a trusted reverse proxy/TLS endpoint,
- direct public plaintext FastAPI exposure is not a supported production configuration.

### 36.3 Request boundary

- body/upload limits before full read,
- bounded multipart/temp quota,
- MIME/decoder validation,
- rate/concurrency limits for expensive work,
- job IDs for long work,
- authorized artifact-ID downloads,
- no arbitrary filesystem path access,
- provider base URL/model registry changes are admin/config operations, not normal untrusted job parameters.

### 36.4 MCP modes

- local stdio MCP inherits local OS/workspace access,
- remote MCP uses the same principal/auth/network policy as the server,
- MCP Tasks (where enabled) map to Tarjoman job IDs/state.

## 37. Testing pyramid and conformance

### PR-gating deterministic suite
- unit tests,
- contract/schema tests,
- DB migration tests,
- artifact round-trip tests,
- provider fake-server tests,
- dependency-boundary tests,
- security tests,
- CLI/API/MCP equivalence tests,
- optional-dependency import tests.

### Scheduled/opt-in expensive suite
- real provider translation evals,
- COMET/XCOMET,
- ASR benchmarks,
- TTS acoustic benchmarks,
- GPU/server profiles,
- human review exports.

No secret-dependent test is required for a normal fork contributor PR.

## 38. Coding-agent implementation protocol

Every coding-agent task must name one roadmap Work Package ID.

Before editing, the agent must read:
1. `ARCHITECTURE_ZERO.md`,
2. accepted ADRs,
3. the work package in `ROADMAP.md`,
4. relevant research file(s),
5. current tests/contracts.

### 38.1 Required PR evidence

A work-package PR includes:
- scope and IDs,
- files changed,
- contracts/schema changed,
- migration impact,
- tests added/changed,
- commands/tests executed,
- benchmark/eval impact where relevant,
- documentation updated,
- known limitations,
- confirmation that no locked decision was changed.

### 38.2 Forbidden agent shortcuts

Without an accepted ADR, an agent must not:
- rewrite Python core in another language,
- add Redis/Celery/Kafka/Postgres,
- put provider SDK calls in core/application business rules,
- make Torch/Whisper/COMET/FastAPI mandatory base dependencies,
- change public schema silently,
- modify an old migration after release,
- log source text/secrets by default,
- silently fallback to cloud or another model,
- use a model whose manifest license is unknown/non-commercial in production profile,
- “fix” semantic Persian with unconditional regex replacements,
- let an LLM translate raw document markup/timecodes/identifiers without structural protection,
- store large binaries in SQLite,
- bypass job checkpoints for long operations,
- document flags/features that lack executable tests.

### 38.3 Ambiguity protocol

If implementation encounters a case not determined by architecture:
- if it is internal and does not affect public behavior/data/security/license, choose the simplest implementation and document it in the PR;
- if it affects API/schema/data migration/security/privacy/license/model behavior/caching/public semantics, stop that work package and propose an ADR.
No architecture-level guess is permitted.

## 39. Definition of Done for every work package

A package is DONE only when:
- acceptance criteria pass,
- tests cover success + at least one failure path,
- errors are typed,
- logs/provenance are adequate,
- optional dependency isolation is preserved,
- docs reflect actual behavior,
- no TODO/FIXME remains for an acceptance criterion,
- no architecture violation exists,
- migrations are tested if data changed,
- benchmark/eval baseline is updated when observable quality/performance changes.

“Code written” is not DONE.

## 40. Release profiles

Tarjoman can release capability profiles independently while sharing one versioned core:

### Core profile
Translation, Persian quality, project/TM/glossary, deterministic formats.

### ASR profile
Core + speech input/transcription/meeting/lecture derivatives.

### TTS profile
Core + pronunciation/G2P/TTS engines and speech-output evals.

### Agent/server profile
Core + persistent jobs + REST/MCP.

A broken optional speech engine blocks that profile, not an unrelated base-package security fix. Compatibility and schema remain coordinated by the same release version.


## 41. Network and external-resource enforcement

A central `NetworkGate` receives:
- operation/project policy,
- adapter identity,
- destination class/host,
- data sensitivity,
- requested purpose.

Adapters may not open network sockets directly outside the approved client/gate abstraction except explicitly audited low-level implementations.

`local_only` test suites run with network disabled/blocked and fail if an adapter attempts egress.

## 42. Hashing and canonicalization rules

Different hashes have different meanings:
- `raw_sha256` — exact imported bytes,
- `canonical_content_hash` — parser-defined normalized logical content,
- `segment_source_hash` — exact canonical source segment text + structural semantics as defined by schema version,
- `config_hash` — canonical serialized material configuration with secrets removed,
- `context_hash` — ordered selected context/TM/glossary references and their versions.

No code may substitute one hash domain for another.

Canonical serialization used for hashes is versioned and deterministic.

## 43. Composition root and dependency injection

Concrete adapters are created only at application composition roots (CLI startup, server startup, tests). Application/core code receives ports/interfaces.

This prevents:
- provider SDK imports in use cases,
- accidental network/model loading at import,
- interface-specific business behavior.

Tests can replace every external adapter with a fake through the same port.

## 44. External model/provider semantic fallback

Fallback policy must specify:
- allowed provider/model sequence,
- which error classes trigger fallback,
- whether quality/cost tier change is allowed,
- whether user confirmation is required,
- whether context/prompts are compatible.

A fallback produces a provenance event. Language fallback, cloud escalation, or noncommercial model substitution is never implicit.

## 45. Protected content and parser fidelity contract

Every ingest adapter defines:
- what structure is editable,
- what is protected exact,
- what is mapped/normalized,
- unsupported constructs.

If parser/exporter cannot prove safe round-trip of required structure, it fails or marks the artifact unsupported/degraded. It does not “let the LLM try”.

## 46. Backup, export, and portability

Workspace backup and project export are different:
- **workspace backup** restores operational state/jobs/artifacts for recovery,
- **project export** creates a portable project package containing project metadata, approved TM/termbase, selected artifacts, provenance, and manifest without secrets/runtime tokens.

Import validates hashes/schema/license metadata before activation.

## 47. Architecture conformance automation

CI/static checks eventually assert:
- no forbidden layer imports,
- no heavy optional packages imported by base import,
- no direct network clients outside approved adapters,
- no `shell=True` production call,
- no direct provider SDK in core/application,
- migrations immutable/checksummed,
- public status enum exactly canonical,
- docs commands correspond to registered CLI commands,
- architecture/roadmap revisions match `ARCHITECTURE_MANIFEST.json`.

## 48. Scope control and release tracks

Tracks share Foundation but are not one giant sequential release:

~~~text
Foundation
   ├─ Translation/Core ── Evaluation ── Formats ── API/MCP ── Core v1
   ├─ ASR/Knowledge --------------------------------------> ASR capability release
   ├─ TTS ------------------------------------------------> TTS capability release
   └─ UI -------------------------------------------------> later UI release
A2A is optional after core agent contracts stabilize.
~~~

Work may run in parallel only when roadmap dependencies are DONE and resource conflicts are managed externally.

## 49. Freeze protocol

Architecture status values:
- `DRAFT`
- `OWNER_FREEZE_CANDIDATE`
- `FROZEN_IMPLEMENTATION`
- `SUPERSEDED`

Freeze criteria satisfied on 2026-09-21 by explicit owner approval. The immutable freeze commit is recorded in `ARCHITECTURE_MANIFEST.json`. Any post-freeze contradiction requires an accepted ADR.

After freeze, contradictions require ADR.

## 50. Architecture Zero review result

Revision PROD-3 incorporates five independent review passes recorded under `review/`:
1. structural consistency,
2. data/runtime/recovery,
3. security/privacy/license,
4. coding-agent executability,
5. scope/current protocol standards.

All discovered Critical/Major issues are either resolved in this architecture or explicitly deferred with a non-implementation default. Remaining uncertainty is product/model selection work gated by later benchmark/manifest packages, not an unowned architecture decision.
