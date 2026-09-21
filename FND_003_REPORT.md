# Work Package FND-003: Error Taxonomy — Completion Report

## 1. Overview
- **Package ID:** FND-003
- **Title:** Error taxonomy
- **Status:** COMPLETED
- **Branch:** `feat/fnd-003-error-taxonomy`
- **Dependencies Verified:** FND-002 (DONE)
- **Architecture References:** `ARCHITECTURE_ZERO.md` §24 (Error taxonomy and failure semantics), §19 (Locked decisions D14, D16, D19), §12.4 (MCP), §16 (Package layout).

---

## 2. Architecture & Design Principles

Following the **codebase-design** principles, the error taxonomy is implemented as a **deep module**:
- **Small Interface:** Callers inspect first-class typed attributes (`err.code`, `err.retryable`, `err.details`, `err.exit_code`, `err.user_action`), use `err.to_dict()`, or pass errors to protocol mappers (`get_exit_code`, `get_http_status`, `get_mcp_error`). No caller or interface ever needs to regex match or substring search `str(e)`.
- **Deep Implementation:**
  - Automatic recursive sanitization strips API keys (OpenAI, Anthropic, AWS, GitHub, HuggingFace), bearer tokens, basic auth credentials, passwords, and private key blocks from both error messages and structured details.
  - Raw source content markers and large source document payloads are systematically excluded.
  - Transparent support for both exception instances and exception classes across all protocol mapping utilities.
  - Full round-trip reconstruction (`from_dict`) restoring serialized payloads back to the exact typed subclass.
- **Layer Law Compliance (D19):** Core error module contains zero dependencies on external provider SDKs, HTTP server frameworks, or UI code. Only Python standard library modules (`json`, `re`, `enum`, `pathlib`, `typing`) are utilized.

---

## 3. Deliverables Implemented

### 3.1 Base Exception (`TarjomanError`)
Defined in `src/tarjoman/core/errors.py`:
- `message: str`: Sanitized human-readable error description.
- `code: str`: Stable uppercase machine-readable error code (`TARJOMAN_ERROR`).
- `retryable: bool`: Explicit retryability flag (default `False`).
- `exit_code: int`: Deterministic non-zero CLI exit code (default `1`).
- `user_action: str`: Remediation guidance string per §24 table.
- `details: Dict[str, Any]`: Sanitized structured metadata dictionary.
- Methods: `to_dict()`, `to_json()`, `__repr__()`, `__str__()`.

### 3.2 All 12 Typed Public Errors (§24)

| # | Class Name | Stable Machine Code | Retryable? | CLI Exit Code | User Action (§24) |
|---|---|---|:---:|:---:|---|
| 1 | `ConfigurationError` | `CONFIGURATION_ERROR` | `False` | `2` | fix config |
| 2 | `PolicyViolationError` | `POLICY_VIOLATION_ERROR` | `False` | `3` | change policy/permission |
| 3 | `LicensePolicyError` | `LICENSE_POLICY_ERROR` | `False` | `4` | use approved model/voice |
| 4 | `CapabilityUnavailableError` | `CAPABILITY_UNAVAILABLE_ERROR` | `False` | `5` | install extra or choose adapter |
| 5 | `ArtifactValidationError` | `ARTIFACT_VALIDATION_ERROR` | `False` | `6` | inspect source/parser |
| 6 | `MigrationError` | `MIGRATION_ERROR` | `False` | `7` | restore/upgrade |
| 7 | `JobCancelledError` | `JOB_CANCELLED_ERROR` | `False` | `8` | expected cancellation |
| 8 | `ProviderTransientError` | `PROVIDER_TRANSIENT_ERROR` | `True` | `10` | retry/fallback if policy allows |
| 9 | `ProviderPermanentError` | `PROVIDER_PERMANENT_ERROR` | `False` | `11` | fix request/provider |
| 10 | `ProviderRateLimitError` | `PROVIDER_RATE_LIMIT_ERROR` | `True` | `12` | wait/backoff |
| 11 | `StructuredOutputError` | `STRUCTURED_OUTPUT_ERROR` | `True` | `13` | model/schema issue |
| 12 | `SpeechSynthesisQualityError` | `SPEECH_SYNTHESIS_QUALITY_ERROR` | `True` | `14` | retry/alternate engine only if allowed |

### 3.3 Protocol & Interface Mappings

#### CLI Exit Codes (`get_exit_code`)
- Guarantees deterministic, non-zero integer CLI exit codes across all error classes and instances.
- Generic exceptions fall back to exit code `1`.
- Guard ensures that even an exit code explicitly configured as `0` defaults to `1`.

#### HTTP Status Codes (`get_http_status`)
- Maps error taxonomy to HTTP status codes for REST/FastAPI adapters (D14):
  - **400 Bad Request:** `ConfigurationError`, `ArtifactValidationError`
  - **403 Forbidden:** `PolicyViolationError`, `LicensePolicyError`
  - **404 Not Found:** `FileNotFoundError`, `KeyError`, errors with `code` containing `"NOT_FOUND"`, or `details["not_found"]=True`
  - **409 Conflict:** `JobCancelledError`
  - **429 Too Many Requests:** `ProviderRateLimitError`
  - **501 Not Implemented:** `CapabilityUnavailableError`
  - **502 Bad Gateway:** `ProviderPermanentError`, `StructuredOutputError`, `SpeechSynthesisQualityError`
  - **503 Service Unavailable:** `ProviderTransientError`
  - **500 Internal Server Error:** `MigrationError`, base `TarjomanError`, generic exceptions
  - Explicit override via `http_status` attribute or `details["http_status"]` is honored.

#### MCP JSON-RPC 2.0 Mapping (`get_mcp_error`)
- Compliant with Model Context Protocol (MCP) and JSON-RPC 2.0 specification:
  - Format: `{"code": int, "message": str, "data": {"code": str, "retryable": bool, "details": dict, "exit_code": int, "user_action": str}}`
  - Standard JSON-RPC Codes:
    - `-32602` (Invalid params): `ConfigurationError`, `ArtifactValidationError`
    - `-32601` (Method not found): `CapabilityUnavailableError`
    - `-32603` (Internal error): `TarjomanError`, generic exceptions
  - Server Error Range (`-32000` to `-32099`):
    - `-32003`: `PolicyViolationError`
    - `-32004`: `LicensePolicyError`
    - `-32007`: `MigrationError`
    - `-32008`: `JobCancelledError`
    - `-32029`: `ProviderRateLimitError`
    - `-32042`: `StructuredOutputError`
    - `-32044`: `SpeechSynthesisQualityError`
    - `-32052`: `ProviderPermanentError`
    - `-32053`: `ProviderTransientError`
  - Explicit custom override via `details["mcp_code"]` is honored.

### 3.4 Secret and Raw-Source Sanitization Subsystem (§24, D16)
- **`sanitize_error_message(message: str) -> str`**:
  - Automatically redacts OpenAI (`sk-...`), Anthropic (`sk-ant-...`), GitHub (`ghp_...`, `github_pat_...`), HuggingFace (`hf_...`), and AWS access keys (`AKIA...`).
  - Redacts Bearer tokens, HTTP Basic Auth credentials embedded in URLs, and AWS secret access keys.
  - Strips PEM private key blocks (`-----BEGIN ... PRIVATE KEY-----`).
  - Redacts key-value secret assignments (`api_key=...`, `password=...`, `secret=...`, `auth=...`).
  - Excludes raw source content tags (`<source>...</source>`, `[source]...[/source]`).
  - Leaves legitimate diagnostic messages untouched (zero false-positive over-redaction).
- **`sanitize_details(details: Dict[str, Any]) -> Dict[str, Any]`**:
  - Recursively traverses nested dicts and lists.
  - Automatically replaces sensitive keys (`api_key`, `secret`, `token`, `password`, `auth`, `credential`, etc.) with `"[REDACTED]"`.
  - Replaces raw source keys (`raw_source`, `source_content`, `source_text`, `source_bytes`) with `"[EXCLUDED: N characters]"`.
  - Serializes Enums, Paths, and datetimes into JSON-safe representations.

### 3.5 Serialization & Rehydration
- **`to_dict()` & `to_json()`**: Full serialization containing all typed fields.
- **`from_dict(data)`**: Deserializes dictionary back to the exact typed subclass using `ERROR_BY_CODE` registry.
- **`get_error_class_by_code(code)`**: Case-insensitive and whitespace-tolerant code lookup.

### 3.6 Module Re-Exports
All 12 error classes, base `TarjomanError`, registries, and mapping functions are exported from:
- `tarjoman.core.errors`
- `tarjoman.core` (unified public core interface)

---

## 4. Verification & Test Evidence

### 4.1 New Error Taxonomy Test Suite (`tests/test_error_taxonomy.py`)
- **Total Tests:** 44 test methods, 115 subtests, 100% PASS in 0.61s.
- **Test Categories:**
  1. `TestErrorInheritanceAndTypes` (3 tests): Verifies all 12 errors inherit from `TarjomanError`, `TarjomanError` inherits from `Exception`, and all 12 classes are distinct.
  2. `TestErrorContractAndAttributes` (4 tests): Verifies exact code strings, retryable flags, CLI exit codes, and user actions for all 12 classes against §24 table.
  3. `TestNoGenericErrorStringContract` (3 tests): Verifies typed field access without string parsing, custom override construction, and str/repr formatting.
  4. `TestCLIExitCodeMapping` (5 tests): Verifies `get_exit_code` across instances, classes, base error, generic exceptions, and zero-exit guards.
  5. `TestHTTPStatusMapping` (5 tests): Verifies `get_http_status` across all 12 classes/instances, NotFound variants (404), explicit overrides, and 500 fallback.
  6. `TestMCPErrorMapping` (4 tests): Verifies `get_mcp_error` JSON-RPC 2.0 structure, code mapping table, class inputs, custom overrides, and generic exceptions.
  7. `TestSecretAndSourceSanitization` (12 tests): Verifies redaction of OpenAI, Anthropic, Bearer, AWS, GitHub, HF tokens, URL credentials, private keys, raw source markers, recursive details sanitization, constructor auto-sanitization, and non-secret message preservation.
  8. `TestSerializationAndRehydration` (4 tests): Verifies `to_dict()`, `to_json()`, `from_dict()` round-trip reconstruction, and unknown code fallback.
  9. `TestRegistriesAndExports` (4 tests): Verifies `ALL_ERRORS`, `ERROR_BY_CODE`, `get_error_class_by_code`, and top-level re-exports in `tarjoman.core`.

### 4.2 Full Regression Test Suite
- Ran: `.venv/bin/pytest`
- Result: **230 passed, 0 failures, 9 warnings** (186 existing tests + 44 new tests).

### 4.3 10-Domain Benchmark Suite
- Ran: `.venv/bin/python benchmarks/run_benchmarks.py`
- Result: **10/10 Domain Verification Benchmarks PASSED** in 0.69s across literary, scientific, philosophy, legal, technical, medical, media, financial, classical, and transcreation domains.

---

## 5. Acceptance Criteria Checklist

- [x] All 12 public errors from `ARCHITECTURE_ZERO.md` §24 implemented with typed fields.
- [x] `no generic error string contract`: code, message, retryable, details, and exit_code are first-class typed attributes.
- [x] `CLI nonzero codes stable`: deterministic non-zero CLI exit code for every error class.
- [x] `API/MCP mapping table`: HTTP status and MCP error mapping functions implemented and thoroughly tested.
- [x] Raw source/secret sanitization enforced in error formatting.
- [x] All 186 existing tests in `tests/` pass with zero failures (230 total tests passing).
- [x] All 10 domain benchmarks in `benchmarks/run_benchmarks.py` pass.

---

## 6. Files Changed
- `src/tarjoman/core/errors.py`: New module implementing base exception, 12 public error subclasses, sanitization, serialization, and protocol mappers.
- `src/tarjoman/core/__init__.py`: Re-exported all error classes and helper functions.
- `tests/test_error_taxonomy.py`: New comprehensive test suite (44 tests, 115 subtests).
- `WORKPACKAGES.json`: Promoted FND-003 status from `READY` to `DONE`.
- `FND_003_REPORT.md`: This completion report.
