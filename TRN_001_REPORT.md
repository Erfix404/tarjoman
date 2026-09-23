# TRN-001 Implementation Report: Provider Port/Capabilities

## Work Package

- **ID**: TRN-001
- **Title**: Provider port/capabilities
- **Phase**: 2 — Real translation engine
- **Track**: translation
- **Dependencies verified**: FND-012 (DONE)

## Files Changed

| File | Action | Purpose |
|------|--------|---------|
| `src/tarjoman/core/ports.py` | **Created** | Canonical port contracts: `TaskType`, `ModelRequest`, `ModelResponse`, `ProviderCapabilities`, `ModelProvider` ABC — defined in core per §22.1 dependency rule |
| `src/tarjoman/providers/base.py` | **Created** | Re-exports port contracts from `core.ports` for convenience; public API surface for provider adapters |
| `src/tarjoman/providers/fake.py` | **Created** | `FakeProvider`, `EchoProvider`, `CallableProvider` — test-double providers per §6.2 |
| `src/tarjoman/providers/__init__.py` | **Updated** | Re-exports all port contracts and test providers |
| `src/tarjoman/application/translation_service.py` | **Created** | `TranslationService` — application-layer service with capability validation, policy enforcement, and provenance tracking |
| `src/tarjoman/application/__init__.py` | **Updated** | Re-exports `TranslationService` |
| `tests/test_provider_port.py` | **Created** | 79 tests covering all acceptance criteria |
| `WORKPACKAGES.json` | **Updated** | TRN-001 → DONE, TRN-002 → READY |

## Architecture Decisions

### Port Contract Placement

The `ModelProvider` protocol, `ModelRequest`, `ModelResponse`, `ProviderCapabilities`, and `TaskType` are defined in `tarjoman.core.ports` — a new module under core that sits **outside** the base-core isolation prefixes (`core.contracts`, `core.errors`, `core.config`, `core.logging`). This placement satisfies two architecture constraints simultaneously:

1. **§22.1 dependency direction**: "infrastructure/adapters implement ports defined by core/application" — the canonical definitions live in core, providers re-export and implement them.
2. **Conformance checker boundaries**: `APPLICATION_FORBIDDEN_PREFIXES` blocks `tarjoman.application` from importing `tarjoman.providers`, so the application service imports port types from `tarjoman.core.ports` instead.

`providers/base.py` re-exports all types from `core.ports` so that infrastructure and interface code can import from either location. Type identity is preserved (`providers.base.ModelProvider is core.ports.ModelProvider`).

### No ADR Required

This implementation does not change any architecture-level decision:
- Public API/schema unchanged (new types only)
- No DB/storage changes
- No cache/TM changes
- No security/privacy boundary changes
- Provider ports follow §6.1 exactly
- Error types reuse existing taxonomy (§24)

## Acceptance Criteria Checklist

### ✅ "component is reachable through application services"

`TranslationService` in `tarjoman.application` wraps the `ModelProvider` port:
- `translate_text()` / `translate_text_sync()` — convenience translation methods
- `execute_task()` / `execute_task_sync()` — general task execution
- Tests: `TestTranslationServiceReachability` (6 tests) verifies import paths, sync/async calls, and request construction

### ✅ "fake-provider tests cover success and failure"

**Success coverage** (`TestFakeProviderSuccess`, 16 tests):
- Default text, response queue (FIFO), response map by task_type
- Structured JSON payloads, pre-built ModelResponse objects
- Usage fields, request_id uniqueness, latency_ms population
- Call tracking (call_count, recorded_requests), capabilities, generate_sync

**Failure coverage** (`TestFakeProviderFailure`, 8 tests):
- `fail_always=True` raises on every call
- `fail_on_call=N` raises on Nth call only
- Custom error injection: `ProviderRateLimitError`, `ProviderPermanentError`, `ProviderTransientError`
- Authentication failure (ProviderPermanentError with auth details)
- Timeout failure (ProviderTransientError with timeout details)
- Default failure type verification

**Additional provider tests:**
- `TestEchoProvider` (7 tests): echo text, mandatory §6.3 warning, capabilities, sync
- `TestCallableProvider` (5 tests): sync/async callable, is_local override, capabilities
- `TestCapabilityValidation` (3 tests): unsupported task raises `CapabilityUnavailableError`
- `TestModelProviderABC` (5 tests): ABC instantiation guard, contract requirements

### ✅ "provenance and policy behavior are asserted"

**Provenance** (`TestProvenanceTracking`, 6 tests):
- `bind_provenance()` sets correlation_id, operation_id, and metadata during generation
- Custom correlation_id from request metadata is propagated
- Every response has populated request_id, latency_ms, and usage
- Provenance context is restored after TranslationService calls (nested safety)

**Policy** (`TestPolicyEnforcement`, 10 tests):
- `ProviderPolicy` violation: unapproved provider raises `PolicyViolationError`
- `ProviderPolicy` allowed: approved provider passes
- Empty allowed_providers means no restriction
- `PrivacyPolicy` violation: non-local provider with `allow_external_apis=False` raises
- Local provider passes privacy check even with external APIs forbidden
- Combined policies tested together
- Works with real `ProviderPolicy` and `PrivacyPolicy` from `tarjoman.profiles.models`

## Test Results

```
608 passed, 9 warnings, 124 subtests passed in 7.67s
```

- **529 existing tests**: all pass (zero regressions)
- **79 new TRN-001 tests**: all pass
- **124 domain benchmark subtests**: all pass (10 domains covered)
- **Architecture conformance**: clean (no violations)

## Commands Run

```bash
python3 -m pytest tests/ -v --tb=short     # Full suite: 608 passed
python3 -m pytest tests/test_provider_port.py -v  # TRN-001: 79 passed
python3 -c "from tarjoman.quality import ArchitectureConformanceChecker; ArchitectureConformanceChecker().enforce()"
```

## Migration/Schema Impact

None. No database changes, no storage changes, no configuration changes.

## Dependency/License Impact

No new dependencies. All implementation uses stdlib + pydantic (existing core dependency).

## Benchmark/Eval Impact

None. No evaluation pipeline changes.

## Known Limitations

- Latency simulation in `FakeProvider` uses `asyncio.sleep()` — not suitable for high-precision latency testing.
- `CallableProvider` does not enforce type checking on the callable's return value at construction time.
- `TranslationService.translate_text()` currently builds a single user message; multi-turn context is deferred to TRN-007 (Context builder).
