# FND-011 Implementation Report: Structured Logging/Provenance

## Work Package

| Field | Value |
|---|---|
| **ID** | FND-011 |
| **Title** | Structured logging/provenance |
| **Phase** | 1 (Foundation) |
| **Status** | DONE |
| **Commit** | `d214b07` on `phase/1-foundation` |

## Dependencies Verified

| Package | Status | Title |
|---|---|---|
| FND-003 | DONE | Error taxonomy |
| FND-004 | DONE | Configuration system |
| FND-006 | DONE | SQLite schema 001 |
| FND-010 | DONE | Versioned behavior and compliance registries |

## Files Changed

| File | Action | Description |
|---|---|---|
| `src/tarjoman/core/logging.py` | NEW | Structured logging module (400 LOC) |
| `src/tarjoman/core/__init__.py` | MODIFIED | Re-exports logging public interface (11 symbols) |
| `tests/test_structured_logging.py` | NEW | 57 tests across 5 test classes |

## Architecture Decisions

No ADR required. The implementation:
- Uses only stdlib (`logging`, `contextvars`, `json`, `re`, `datetime`).
- Lives in the Core layer (`tarjoman.core.logging`).
- Contains no concrete provider/network/UI/server implementation (D19).
- Enforces D16 (privacy: secrets never logged).
- Reuses `sanitize_error_message` from `tarjoman.core.errors` for consistency.
- Does not change any public API, schema, status vocabulary, DB model, or security boundary.

## Implementation Summary

### Secret Redaction Layer

- **`RedactionFilter(logging.Filter)`**: Intercepts all log records. Formats `msg + args` together before redacting, so patterns spanning template and arguments (e.g. `"Bearer %s"` + token arg) are caught. Falls back to separate redaction on formatting errors.
- **`redact_secrets(val: Any) -> Any`**: Recursive redaction for strings, dicts, lists, tuples, and exceptions. Fail-closed: returns `"[REDACTED: redaction error]"` if redaction logic itself errors.
- **Patterns covered**: OpenAI (`sk-...`), Anthropic (`ant-...`, `sk-ant-...`), Bearer tokens, Authorization/API-key/x-api-key/secret/token headers (with optional scheme word like Basic/Bearer), URL query parameter tokens (`?api_key=...`, `?token=...`, `?key=...`, `?secret=...`), GitHub PATs, HuggingFace tokens, AWS access key IDs, private key PEM blocks.

### JSON Formatter

- **`JSONFormatter(logging.Formatter)`**: Single-line JSON with keys: `timestamp` (ISO-8601 UTC), `level`, `logger`, `message`, `correlation_id`, `operation_id`, `job_id`, `project_id`, `provenance`, `exception`, `extra`.
- Final redaction pass on the formatted message for defense-in-depth.

### Text Formatter

- **`TextFormatter(logging.Formatter)`**: `YYYY-MM-DDTHH:MM:SS.mmmZ LEVEL [logger] [correlation_id] message` with redaction.

### Context Tracking (§4.3)

- **`set_correlation_id(id)`** / **`get_correlation_id()`**: ContextVar-based.
- **`set_operation_context(...)`**: Sets operation_id, job_id, project_id, metadata.
- **`bind_provenance(...)`**: Context manager that scopes all provenance fields; restores previous values on exit. Safe for nested use and async tasks.
- **`get_provenance_context()`**: Returns current context as a flat dict.

### Provider Error Sanitizer (§24)

- **`sanitize_provider_error(error, *, context=None)`**: Strips credentials from provider/HTTP/SDK exceptions. Preserves diagnostic info (exception type, status code, failure reason). Uses both `errors.sanitize_error_message` and logging redaction patterns.

### Configuration

- **`configure_logging(*, level, format, stream, handler)`**: Configures the `tarjoman` logger hierarchy. Reads `TARJOMAN_LOG_LEVEL` and `TARJOMAN_LOG_FORMAT` env vars. Always attaches `RedactionFilter`.

## Test Results

### FND-011 Tests: 57 passed

| Class | Tests | Coverage |
|---|---|---|
| `TestSecretRedaction` | 21 | OpenAI/Anthropic keys, Bearer tokens, Authorization headers, URL params, nested structures, exception traces, text formatter, fail-closed |
| `TestJSONLogOption` | 15 | JSON validity, required fields, ISO-8601 timestamps, context from bind_provenance, scoping, nesting, format switching, env vars |
| `TestProviderErrorLeakProtection` | 11 | API keys in error messages/URLs/headers, Bearer tokens, chained exceptions, status codes, text mode |
| `TestContextTracking` | 6 | set/get, bind_provenance yield/restore/partial-override/empty |
| `TestRedactionFilter` | 4 | Filter mechanics on LogRecord (msg, tuple args, dict args, exc_text) |

### Full Suite: 505 passed, 0 failed

```
505 passed, 9 warnings, 115 subtests passed in 4.81s
```

All 448 pre-existing tests pass with zero regressions. All 10 domain benchmarks pass.

## Acceptance Criteria Checklist

- [x] **redaction test**: Proven redaction of API keys (OpenAI, Anthropic, GitHub, AWS, HF), bearer tokens, authorization headers, and URL query parameter secrets across message, extra fields, and multi-line exception stack traces. 21 dedicated tests.
- [x] **JSON log option**: Structured single-line JSON logging with correlation/operation/job/project context verified through `bind_provenance()`. ISO-8601 UTC timestamps validated. Format switching between JSON and text confirmed. 15 dedicated tests.
- [x] **provider error cannot leak API key**: Simulated provider exceptions with embedded API keys in messages, URLs, headers, and chained causes — all verified to never emit raw credentials in logged JSON or text output. 11 dedicated tests.
- [x] All 448 existing tests pass with zero failures.
- [x] All 10 domain benchmarks pass.

## Known Limitations

- Redaction patterns are regex-based; exotic credential formats not matching the documented patterns would require pattern additions.
- The module does not configure third-party library loggers (only the `tarjoman` hierarchy); callers using external libraries should configure those separately.

## Migration/Schema Impact

None.

## Dependency/License Impact

None. Uses only Python stdlib modules.
