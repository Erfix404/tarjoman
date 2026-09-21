# Work Package FND-010: Versioned Behavior and Compliance Registries — Completion Report

## 1. Executive Summary
- **Package ID:** FND-010
- **Title:** Versioned behavior and compliance registries
- **Phase:** 1 (Foundation)
- **Status:** COMPLETED
- **Branch:** `phase/1-foundation`
- **Dependencies Verified:** FND-002 (DONE), FND-004 (DONE)
- **Downstream Packages Unblocked:**
  - `FND-011` (Structured logging/provenance, PLANNED)
  - `FND-012` (Architecture-conformance CI, PLANNED)
  - `TRN-006` (Translation strategy registry, PLANNED)
  - `TRN-007` (Context builder, PLANNED)
  - `TRN-008` (Glossary enforcement, PLANNED)
  - `TRN-009` (Result Cache + Translation Memory separation, PLANNED)
  - `TRN-011` (Review/revision state, PLANNED)
  - `EVAL-001` (Golden-case schema, PLANNED)
  - `ASR-003` (faster-whisper adapter, PLANNED)
  - `ASR-005` (Diarization port, PLANNED)
  - `TTS-002` (TTS model/voice manifest population and policy tests, PLANNED)
  - `REL-008` (License audit, PLANNED)
- **Architecture References:**
  - `ARCHITECTURE_ZERO.md` §8.4 (Profile taxonomy — names may not be overloaded; high-risk domain defaults: legal and medical require human review by default for APPROVED status)
  - `ARCHITECTURE_ZERO.md` §19 (Locked Decisions):
    - **D11**: Separate registries with independent versions
    - **D12**: High-risk domain review requirements
    - **D13**: In-memory immutability once loaded
    - **D23**: Prompts, profiles, rules, schemas, and strategy versions are immutable identifiers recorded in every run
    - **D27**: Machine-readable ModelManifest and license gate before production use or redistribution
    - **D40**: Distinct types for all profile and policy categories; Capability Bundle is an install grouping, never a content profile
  - `AGENTS.md` (Scope law, non-destructive requirements)
  - `WORKPACKAGES.json` (FND-010 acceptance criteria verified)

---

## 2. Architecture & Design Principles (Codebase Design Skill)

In accordance with the **codebase-design** principles, the versioned profile and compliance subsystem is implemented as **deep modules** placed across a clean architectural seam:

```
┌────────────────────────────────────────────────────────────────────────┐
│                      Tarjoman Profiles Seam                            │
├───────────────────────────────────┬────────────────────────────────────┤
│         Profile Taxonomies        │         Compliance Registries      │
│  (distinct types, immutable D40)  │ (SemVer indexed, fail-closed D11)  │
├───────────────────────────────────┼────────────────────────────────────┤
│ • DomainProfile (11 domains)      │ • DomainProfileRegistry            │
│ • StyleProfile (4 registers)      │ • StyleProfileRegistry             │
│ • WorkflowProfile (7 shapes)      │ • WorkflowProfileRegistry          │
│ • ReviewPolicy (strict / standard)│ • ReviewPolicyRegistry             │
│ • PrivacyPolicy / ProviderPolicy  │ • ComplianceRegistry               │
│ • LicensePolicy                   │ • CapabilityBundleRegistry         │
│ • CapabilityBundle (install-only) │ • ManifestRegistry                 │
│ • Model / Data / Service Manifest │ • Generic VersionedRegistry[T]     │
└───────────────────────────────────┴────────────────────────────────────┘
```

### Depth and Seam Discipline
1. **Small Interface, Deep Implementation:**
   Callers interact with concise methods (`get(id, version=None)`, `list_all()`, `contains(id)`). Hidden behind this interface are:
   - Full Pydantic v2 schema validation.
   - Automatic semantic version parsing (`packaging.version.parse`) and latest-version resolution.
   - In-memory immutability enforcement (`freeze()` locks mutation, Pydantic `frozen=True` locks instances).
   - Deterministic SHA-256 content checksums on all entities (`compute_content_hash`).
   - High-risk domain governance cross-referenced against `ReviewPolicy`.
   - Fail-closed license gates rejecting unknown or unapproved licenses.

2. **D40 Distinct Type Invariant:**
   The word “profile” is never overloaded. Each category has its own distinct type and independent registry:
   - `DomainProfile` (subject matter)
   - `StyleProfile` (language presentation)
   - `WorkflowProfile` (transformation shape)
   - `ReviewPolicy` (human approval rules)
   - `PrivacyPolicy`, `ProviderPolicy`, `LicensePolicy` (compliance boundaries)
   - `CapabilityBundle` (install/release grouping — explicitly validated to never be a content profile)

3. **High-Risk Domain Default Governance (§8.4, D12):**
   - High-risk domains (`legal`, `medical`) default to `is_high_risk=True` and point to `high_risk_strict` review policy.
   - Under `high_risk_strict`, `requires_human_approval_for_approved_status=True` and `allow_auto_approval=False`.
   - Automated approval of high-risk translations is blocked unless an explicit owner override is provided with a mandatory `override_reason` recorded in audit provenance (`create_provenance_reference`).

---

## 3. Implemented Components

### 3.1 Profile Models (`src/tarjoman/profiles/models.py`)
- **`VersionedEntity`**: Base Pydantic model (`frozen=True`, `extra="forbid"`) with `compute_checksum()` generating deterministic `sha256:...` content hashes.
- **`DomainProfile`**: Represents subject matter domains. Prepopulated for 11 domains (10 standard + `general`). Automatically defaults `is_high_risk=True` and `default_review_policy_id="high_risk_strict"` for legal and medical.
- **`StyleProfile`**: Represents presentation styles (`formal`, `neutral`, `conversational`, `literary`), digit policy (`persian`, `english`, `preserve`), punctuation, and loanword rules.
- **`WorkflowProfile`**: Represents transformation pipelines (`translation`, `subtitle`, `meeting`, `lecture_notes`, `formal_minutes`, `audiobook`, `polish_only`).
- **`ReviewPolicy`**: Enforces human review requirements, auto-approval gates, and override policies.
- **`PrivacyPolicy`**, **`ProviderPolicy`**, **`LicensePolicy`**: Encode security, external network egress, provider cost quotas, and license constraints.
- **`CapabilityBundle`**: Release/install capability grouping (`core`, `asr`, `tts`, `server`). Strictly enforces `is_content_profile is False` (raises `ValidationError` if set to `True`).
- **`ModelManifest`**, **`DataManifest`**, **`ServiceManifest`**: Machine-readable external component manifests tracking source revision, license, purpose, and redistribution status.
- **`evaluate_manifest_license` & `enforce_license_gate`**: Evaluates manifests against policy; fails closed (raising `LicensePolicyError`) if license status is unknown, unapproved, or incompatible with commercial context.
- **`ProvenanceReference` & `create_provenance_reference`**: Captures tamper-evident execution lineage including entity type, version, content checksum, and mandatory high-risk override justifications.

### 3.2 Registry Engine (`src/tarjoman/profiles/registry.py`)
- **`RegistryError`**: Subclass of `TarjomanError` (`code="REGISTRY_ERROR"`, `exit_code=2`).
- **`VersionedRegistry[T]`**: Generic thread-safe registry with multi-version storage `(id, version)`, duplicate protection, SemVer latest-version resolution, and `freeze()` immutability.
- **Specialized Registries**: `DomainProfileRegistry`, `StyleProfileRegistry`, `WorkflowProfileRegistry`, `ReviewPolicyRegistry`, `ComplianceRegistry`, `CapabilityBundleRegistry`, `ManifestRegistry`.
- **Prepopulated Defaults**: Built-in registries initialized with production-grade configurations, enriched with terminology from `src/tarjoman/domains/registry/`, and frozen by default.
- **Convenience Accessors & Singletons**: `get_domain_registry()`, `get_style_registry()`, `get_workflow_registry()`, `get_review_policy_registry()`, `get_compliance_registry()`, `get_capability_registry()`, `get_manifest_registry()`, `reset_registries()`.
- **Compliance Resolvers**: `resolve_domain_review_policy()` and `assert_high_risk_compliance()`.

### 3.3 Package Re-Exports (`src/tarjoman/profiles/__init__.py`)
Clean public surface re-exporting all 42 symbols for seamless application and core consumption.

---

## 4. Verification Evidence & Acceptance Checklist

### 4.1 Acceptance Criteria Checklist
- [x] **`registry schema validation`**:
  - Pydantic models validate all attributes and reject missing/invalid fields.
  - Duplicate registration with the same ID and version raises `RegistryError`.
  - Multiple versions of the same entity register successfully and resolve independently.
  - Latest version resolution handles SemVer ordering (e.g. 2.0.0 > 1.1.0 > 1.0.0).
  - Immutability after `freeze()` verified: attempting to register on a frozen registry raises `RegistryError`.
  - In-memory model immutability verified: modifying attributes on profile instances raises error.
- [x] **`profile lookup tests`**:
  - Lookup all 11 domains (`general`, `literary`, `scientific`, `philosophy`, `legal`, `technical`, `medical`, `media`, `financial`, `classical`, `transcreation`) verified.
  - Lookup all 4 style profiles (`formal`, `neutral`, `conversational`, `literary`) verified.
  - Lookup all 7 workflow profiles verified.
  - Lookup all review policies and compliance policies verified.
  - Lookup with unknown ID or version raises typed `RegistryError`.
  - `contains()`, `list_all()`, and `list_versions()` verified.
- [x] **`high-risk domain default assertions`**:
  - `legal` has `is_high_risk=True` and `default_review_policy_id="high_risk_strict"`.
  - `medical` has `is_high_risk=True` and `default_review_policy_id="high_risk_strict"`.
  - `legal` and `medical` point to review policy requiring human approval for APPROVED status (`requires_human_approval_for_approved_status=True`, `allow_auto_approval=False`).
  - Non-high-risk domains allow auto-approval (`requires_human_approval_for_approved_status=False`, `allow_auto_approval=True`).
  - High-risk override requires mandatory explicit `override_reason` in provenance audit trail; missing reason fails closed with `PolicyViolationError`.
- [x] **`manifest & fail-closed license policy`**:
  - Unknown license status fails closed with `LicensePolicyError`.
  - Research-only models (e.g. `nimaone/persian_tts`) fail under commercial context.
  - Approved commercial models pass the license gate.
- [x] **`D40 CapabilityBundle separation`**:
  - `CapabilityBundle.is_content_profile` is strictly False.
  - Declaring a capability bundle as a content profile raises `ValidationError`.
- [x] **Regression & Benchmark Verification**:
  - 448 tests passing (426 existing + 22 new), 0 failures.
  - All 10 domain benchmarks passing (10/10).

### 4.2 Test Execution Output
```
============================= test session starts ==============================
platform linux -- Python 3.13.5, pytest-9.1.1, pluggy-1.6.0
rootdir: /opt/data/projects/tarjoman
configfile: pyproject.toml
collected 448 items

tests/test_5pass_pipeline.py ..................                          [  4%]
tests/test_anti_calque.py ................                               [  7%]
tests/test_artifact_store.py ........................................... [ 17%]
...............                                                          [ 20%]
tests/test_canonical_contracts.py ...................................... [ 29%]
....................................................                     [ 40%]
tests/test_cli.py ...........                                            [ 43%]
tests/test_composers.py .......................                          [ 48%]
tests/test_config_system.py ....................................         [ 56%]
tests/test_contracts.py ....                                             [ 57%]
tests/test_error_taxonomy.py ........................................... [ 66%]
.                                                                        [ 66%]
tests/test_legacy_importer.py ..................                         [ 70%]
tests/test_memory_cache.py .............                                 [ 73%]
tests/test_migration_discipline.py ...................                   [ 78%]
tests/test_persian_quality_split.py .................................... [ 86%]
..                                                                       [ 86%]
tests/test_router_10_domains.py .....                                    [ 87%]
tests/test_skillpacks.py ......                                          [ 89%]
tests/test_sqlite_schema.py ...........................                  [ 95%]
tests/test_versioned_registries.py ......................                [100%]

======================= 448 passed, 9 warnings in 4.24s ========================
```

### 4.3 10-Domain Verification Benchmark Output
```
================================================================================
      TARJOMAN UNIVERSAL ENGINE: 10-DOMAIN COMPREHENSIVE BENCHMARK       
================================================================================
Executing 5-pass reflection, MQM audit, and 3-format publishing across 10 domains...

Domain          | Persian Title              | Conf   | Score  | Audit  | Bi-MD  | HTML   | PDF      | Time  
-------------------------------------------------------------------------------------------------------------
literary        | ادبی، رمان و داستان        | 93%    | 100.0  | PASS   | YES    | YES    | YES      | 0.05s 
scientific      | علمی، دانشگاهی و مقالات    | 95%    | 100.0  | PASS   | YES    | YES    | YES      | 0.04s 
philosophy      | فلسفه، اندیشه و علوم انسانی | 95%    | 100.0  | PASS   | YES    | YES    | YES      | 0.04s 
legal           | حقوقی، قراردادها و اسناد رسمی | 96%    | 100.0  | PASS   | YES    | YES    | YES      | 0.04s 
technical       | فنی، نرم‌افزار و مهندسی    | 96%    | 100.0  | PASS   | YES    | YES    | YES      | 0.10s 
medical         | پزشکی، بالینی و داروسازی   | 96%    | 100.0  | PASS   | YES    | YES    | YES      | 0.04s 
media           | رسانه‌ای، اخبار و ژورنالیسم | 95%    | 100.0  | PASS   | YES    | YES    | YES      | 0.05s 
financial       | اقتصاد، مالی و بازرگانی    | 95%    | 100.0  | PASS   | YES    | YES    | YES      | 0.04s 
classical       | متون کهن، تاریخی و متون مقدس | 96%    | 100.0  | PASS   | YES    | YES    | YES      | 0.04s 
transcreation   | بازآفرینی خلاق، برندینگ و تبلیغات | 94%    | 100.0  | PASS   | YES    | YES    | YES      | 0.05s 
-------------------------------------------------------------------------------------------------------------

[SUCCESS] All 10 Domain Verification Benchmarks PASSED (10/10) in 0.50s!
```

---

## 5. Artifacts and Files Changed
- `src/tarjoman/profiles/models.py` (New): Profile, compliance, and manifest models with content checksums and license gates.
- `src/tarjoman/profiles/registry.py` (New): Generic `VersionedRegistry[T]`, specialized typed registries, defaults, and singletons.
- `src/tarjoman/profiles/__init__.py` (Updated): Public API re-exports for the profiles package.
- `tests/test_versioned_registries.py` (New): 22 comprehensive unit and integration tests.
- `WORKPACKAGES.json` (Updated): `FND-010` status marked `DONE`.
- `FND_010_REPORT.md` (New): This report.

---

## 6. Conclusion
Work Package FND-010 has been implemented in strict alignment with Architecture Zero §8.4, Locked Decisions D11, D12, D13, D23, D27, D40, and the codebase design deep-module discipline. All acceptance criteria are verified with executable tests and zero regressions.
