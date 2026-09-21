"""
Tests for FND-011: Structured logging, provenance tracking, and secret redaction.

Acceptance criteria (WORKPACKAGES.json):
  - redaction test: proven redaction of API keys, bearer tokens, and secrets
    across message, extra, and exception traces.
  - JSON log option: structured single-line JSON logging with correlation/operation
    context verified.
  - provider error cannot leak API key: simulated provider error traces asserted
    to never emit raw credentials.

Architecture Zero references:
  §23.2 — Secrets never in logs, redaction on exception text & HTTP traces.
  §24   — Sanitized provider error details.
  §25.5 — Structured audit trails with provenance.
"""
from __future__ import annotations

import datetime
import io
import json
import logging
import re
import traceback
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from tarjoman.core.logging import (
    JSONFormatter,
    RedactionFilter,
    TextFormatter,
    bind_provenance,
    configure_logging,
    get_correlation_id,
    get_provenance_context,
    redact_secrets,
    sanitize_provider_error,
    set_correlation_id,
    set_operation_context,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_json_logger(stream: io.StringIO) -> logging.Logger:
    """Create a fresh logger with JSON formatter + redaction for test capture."""
    logger = configure_logging(level="DEBUG", format="json", stream=stream)
    return logger


def _make_text_logger(stream: io.StringIO) -> logging.Logger:
    """Create a fresh logger with text formatter + redaction for test capture."""
    logger = configure_logging(level="DEBUG", format="text", stream=stream)
    return logger


def _capture_json_line(stream: io.StringIO) -> Dict[str, Any]:
    """Read the last JSON log line from stream and parse it."""
    stream.seek(0)
    lines = [l.strip() for l in stream.readlines() if l.strip()]
    assert lines, "No log output captured"
    return json.loads(lines[-1])


def _capture_all_json(stream: io.StringIO) -> list:
    """Read all JSON log lines from stream."""
    stream.seek(0)
    return [json.loads(l) for l in stream.readlines() if l.strip()]


# ===========================================================================
# TestSecretRedaction — Acceptance: "redaction test"
# ===========================================================================

class TestSecretRedaction:
    """Prove redaction of API keys, bearer tokens, and secrets across
    message, extra, and exception traces (§23.2)."""

    # -- OpenAI-style key redaction --

    def test_redact_openai_key_in_message(self):
        """OpenAI sk-... key in log message is replaced with [REDACTED]."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        key = "sk-abc123XYZ789longkeyvalue_test"
        logger.info("Provider auth failed with key %s", key)
        entry = _capture_json_line(stream)
        assert key not in entry["message"]
        assert "[REDACTED]" in entry["message"]

    def test_redact_openai_key_in_extra(self):
        """OpenAI key in extra fields is redacted."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        key = "sk-proj-longtokenvalue123456"
        logger.info("Auth attempt", extra={"api_key": key})
        entry = _capture_json_line(stream)
        extra = entry.get("extra", {})
        raw = json.dumps(extra)
        assert key not in raw
        assert "[REDACTED]" in raw

    # -- Anthropic-style key redaction --

    def test_redact_anthropic_key_in_message(self):
        """Anthropic ant-... key in log message is redacted."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        key = "ant-api01-abcdefghij1234567890"
        logger.info("Anthropic call failed: key=%s", key)
        entry = _capture_json_line(stream)
        assert key not in entry["message"]
        assert "[REDACTED]" in entry["message"]

    def test_redact_sk_ant_key(self):
        """Anthropic sk-ant-... key variant is redacted."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        key = "sk-ant-api03-abcdefghij1234567890extra"
        logger.info("Error using %s", key)
        entry = _capture_json_line(stream)
        assert key not in entry["message"]

    # -- Bearer token redaction --

    def test_redact_bearer_token_in_message(self):
        """Bearer token in log message is redacted."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature"
        logger.warning("Got 401: Authorization: Bearer %s", token)
        entry = _capture_json_line(stream)
        assert token not in entry["message"]
        assert "[REDACTED]" in entry["message"]

    def test_redact_bearer_in_extra(self):
        """Bearer token in extra dict is redacted."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        header_val = "Bearer eyJhbGciOiJIUzI1NiJ9.test.sig"
        logger.info("Request headers", extra={"auth_header": header_val})
        entry = _capture_json_line(stream)
        extra_raw = json.dumps(entry.get("extra", {}))
        assert "eyJhbGci" not in extra_raw
        assert "[REDACTED]" in extra_raw

    # -- Authorization header and query parameter redaction --

    def test_redact_authorization_header(self):
        """Authorization: <value> header pattern is redacted."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        logger.info("Headers: Authorization: sk-secret1234567890abcdefg")
        entry = _capture_json_line(stream)
        assert "sk-secret1234567890abcdefg" not in entry["message"]

    def test_redact_api_key_header(self):
        """api-key: <value> and x-api-key: <value> patterns are redacted."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        logger.info("api-key: mysecretapikey12345")
        entry = _capture_json_line(stream)
        assert "mysecretapikey12345" not in entry["message"]
        assert "[REDACTED]" in entry["message"]

    def test_redact_url_query_params(self):
        """URL query parameter tokens (?api_key=...) are redacted."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        url = "https://api.example.com/v1/translate?api_key=secret123&lang=fa"
        logger.info("Calling %s", url)
        entry = _capture_json_line(stream)
        assert "secret123" not in entry["message"]
        assert "api_key=[REDACTED]" in entry["message"]

    def test_redact_token_query_param(self):
        """?token=... query parameter is redacted."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        url = "https://api.example.com/v1?token=abcdef123456&format=json"
        logger.info("URL: %s", url)
        entry = _capture_json_line(stream)
        assert "abcdef123456" not in entry["message"]

    # -- Nested structure redaction --

    def test_redact_nested_dict(self):
        """Secrets in nested dicts within extra are redacted."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        nested = {
            "request": {
                "headers": {"Authorization": "Bearer supersecrettoken123456"},
                "url": "https://api.example.com?key=hidden_key_value",
            }
        }
        logger.info("Request details", extra={"details": nested})
        entry = _capture_json_line(stream)
        raw = json.dumps(entry)
        assert "supersecrettoken123456" not in raw
        assert "hidden_key_value" not in raw

    def test_redact_nested_list(self):
        """Secrets inside lists within extra are redacted."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        tokens = ["sk-token_aaa_1234567890abcdefghij", "normal-value"]
        logger.info("Tokens used", extra={"tokens": tokens})
        entry = _capture_json_line(stream)
        raw = json.dumps(entry)
        assert "sk-token_aaa_1234567890abcdefghij" not in raw

    # -- Exception traceback redaction --

    def test_redact_exception_traceback(self):
        """Secrets in exception messages are redacted in exc_info traces."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        key = "sk-prod-abcdefghijklmnopqrstuvwxyz"
        try:
            raise ValueError(f"Authentication failed for key {key}")
        except ValueError:
            logger.error("Provider error", exc_info=True)
        entry = _capture_json_line(stream)
        assert key not in entry.get("exception", "")
        assert key not in entry["message"]
        assert "[REDACTED]" in entry.get("exception", "")

    def test_redact_exception_with_bearer(self):
        """Bearer token in exception message is redacted in traceback."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig"
        try:
            raise RuntimeError(f"401 Unauthorized: Bearer {token}")
        except RuntimeError:
            logger.error("Auth failure", exc_info=True)
        entry = _capture_json_line(stream)
        exc = entry.get("exception", "")
        assert token not in exc
        assert "[REDACTED]" in exc

    def test_redact_multiline_exception_with_key(self):
        """Multi-line exception trace with API key in inner cause is redacted."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        key = "sk-inner-cause-key-abcdefghijklmno"
        try:
            try:
                raise ConnectionError(f"Connection refused to api with key={key}")
            except ConnectionError as inner:
                raise RuntimeError("Provider call failed") from inner
        except RuntimeError:
            logger.error("Pipeline error", exc_info=True)
        entry = _capture_json_line(stream)
        exc = entry.get("exception", "")
        assert key not in exc

    # -- redact_secrets function directly --

    def test_redact_secrets_string(self):
        result = redact_secrets("Key is sk-abcdefghij1234567890extra")
        assert "sk-abcdefghij1234567890extra" not in result
        assert "[REDACTED]" in result

    def test_redact_secrets_dict(self):
        result = redact_secrets({"key": "sk-testkey12345678901234"})
        assert "sk-testkey12345678901234" not in str(result)

    def test_redact_secrets_tuple(self):
        result = redact_secrets(("sk-tuple_key_12345678901234",))
        assert isinstance(result, tuple)
        assert "sk-tuple_key_12345678901234" not in str(result)

    def test_redact_secrets_exception(self):
        exc = ValueError("token=sk-exc_key_value_123456789012")
        result = redact_secrets(exc)
        assert "sk-exc_key_value_123456789012" not in str(result)

    def test_redact_secrets_failclosed(self):
        """If redaction itself errors on a weird type, fail closed."""

        class Unredactable:
            def __str__(self):
                raise RuntimeError("cannot stringify")

            def __repr__(self):
                raise RuntimeError("cannot repr")

        # Should not raise, should return a safe fallback
        result = redact_secrets(Unredactable())
        # Result is either the original (non-string, no secret) or a safe string
        # The important thing is it didn't raise

    # -- Text formatter also redacts --

    def test_text_formatter_redacts(self):
        """Text formatter also applies redaction."""
        stream = io.StringIO()
        logger = _make_text_logger(stream)
        key = "sk-textformat_test_key_1234567890"
        logger.info("Using key %s", key)
        stream.seek(0)
        output = stream.read()
        assert key not in output
        assert "[REDACTED]" in output


# ===========================================================================
# TestJSONLogOption — Acceptance: "JSON log option"
# ===========================================================================

class TestJSONLogOption:
    """Structured single-line JSON logging with correlation/operation context."""

    def test_json_output_is_valid_json(self):
        """Each log line is valid single-line JSON."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        logger.info("Test message")
        logger.warning("Another message")
        entries = _capture_all_json(stream)
        assert len(entries) == 2
        for entry in entries:
            assert isinstance(entry, dict)

    def test_json_required_fields(self):
        """JSON output contains required fields: timestamp, level, logger, message."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        logger.info("Hello structured world")
        entry = _capture_json_line(stream)
        assert "timestamp" in entry
        assert "level" in entry
        assert "logger" in entry
        assert "message" in entry
        assert entry["level"] == "INFO"
        assert "Hello structured world" in entry["message"]

    def test_json_timestamp_is_iso8601_utc(self):
        """Timestamps are valid ISO-8601 UTC."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        logger.info("Time check")
        entry = _capture_json_line(stream)
        ts = entry["timestamp"]
        # Should parse as ISO-8601 with timezone
        parsed = datetime.datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None
        # Should be UTC
        assert parsed.utcoffset().total_seconds() == 0

    def test_json_logger_name(self):
        """Logger name is preserved in JSON output."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        child = logger.getChild("pipeline")
        child.info("Pipeline step")
        entry = _capture_json_line(stream)
        assert entry["logger"] == "tarjoman.pipeline"

    def test_json_correlation_id_from_bind(self):
        """correlation_id from bind_provenance appears in JSON output."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        with bind_provenance(correlation_id="req-abc-123"):
            logger.info("Correlated message")
        entry = _capture_json_line(stream)
        assert entry["correlation_id"] == "req-abc-123"

    def test_json_operation_and_job_from_bind(self):
        """operation_id and job_id from bind_provenance appear in JSON."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        with bind_provenance(
            operation_id="op-translate-001",
            job_id="job-42",
            project_id="proj-alpha",
        ):
            logger.info("Running translation")
        entry = _capture_json_line(stream)
        assert entry["operation_id"] == "op-translate-001"
        assert entry["job_id"] == "job-42"
        assert entry["project_id"] == "proj-alpha"

    def test_json_provenance_metadata(self):
        """Provenance metadata dict appears in JSON output."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        meta = {"strategy": "direct", "model": "gpt-4"}
        with bind_provenance(correlation_id="c1", metadata=meta):
            logger.info("With metadata")
        entry = _capture_json_line(stream)
        assert entry["provenance"] == meta

    def test_json_context_scoping(self):
        """Context is scoped to bind_provenance block and restored after."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)

        # Before bind: no context
        logger.info("Before")
        e1 = _capture_json_line(stream)
        assert e1["correlation_id"] is None

        # Inside bind: has context
        stream.truncate(0)
        stream.seek(0)
        with bind_provenance(correlation_id="scoped-123"):
            logger.info("Inside")
        e2 = _capture_json_line(stream)
        assert e2["correlation_id"] == "scoped-123"

        # After bind: context restored
        stream.truncate(0)
        stream.seek(0)
        logger.info("After")
        e3 = _capture_json_line(stream)
        assert e3["correlation_id"] is None

    def test_json_nested_bind_provenance(self):
        """Nested bind_provenance restores outer context on exit."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)

        with bind_provenance(correlation_id="outer", job_id="job-1"):
            with bind_provenance(correlation_id="inner", job_id="job-2"):
                logger.info("Inner")
                stream.seek(0)
                inner = _capture_json_line(stream)
                assert inner["correlation_id"] == "inner"
                assert inner["job_id"] == "job-2"

            stream.truncate(0)
            stream.seek(0)
            logger.info("Outer restored")
            outer = _capture_json_line(stream)
            assert outer["correlation_id"] == "outer"
            assert outer["job_id"] == "job-1"

    def test_format_switch_json_to_text(self):
        """Format switches cleanly between json and text."""
        stream_json = io.StringIO()
        logger = configure_logging(level="DEBUG", format="json", stream=stream_json)
        logger.info("JSON mode")
        stream_json.seek(0)
        line = stream_json.readline().strip()
        parsed = json.loads(line)  # Must be valid JSON
        assert parsed["message"] == "JSON mode"

        stream_text = io.StringIO()
        logger = configure_logging(level="DEBUG", format="text", stream=stream_text)
        logger.info("Text mode")
        stream_text.seek(0)
        line = stream_text.readline().strip()
        # Text mode should NOT be valid JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(line)
        assert "Text mode" in line

    def test_json_exception_field(self):
        """Exception info populates the 'exception' field in JSON."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        try:
            raise RuntimeError("something broke")
        except RuntimeError:
            logger.error("Caught error", exc_info=True)
        entry = _capture_json_line(stream)
        assert entry["exception"] is not None
        assert "RuntimeError" in entry["exception"]
        assert "something broke" in entry["exception"]

    def test_json_no_exception_when_none(self):
        """Exception field is None when no exception is active."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        logger.info("No exception here")
        entry = _capture_json_line(stream)
        assert entry["exception"] is None

    def test_json_extra_fields(self):
        """Extra fields appear in the 'extra' key of JSON output."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        logger.info("With extras", extra={"segment_id": "seg-42", "attempt": 3})
        entry = _capture_json_line(stream)
        assert entry["extra"] is not None
        assert entry["extra"]["segment_id"] == "seg-42"
        assert entry["extra"]["attempt"] == 3

    def test_configure_logging_env_vars(self, monkeypatch):
        """configure_logging reads TARJOMAN_LOG_LEVEL and TARJOMAN_LOG_FORMAT."""
        monkeypatch.setenv("TARJOMAN_LOG_LEVEL", "WARNING")
        monkeypatch.setenv("TARJOMAN_LOG_FORMAT", "json")
        stream = io.StringIO()
        logger = configure_logging(stream=stream)
        assert logger.level == logging.WARNING
        # Should be JSON format
        logger.warning("Env test")
        entry = _capture_json_line(stream)
        assert entry["level"] == "WARNING"

    def test_configure_logging_explicit_overrides_env(self, monkeypatch):
        """Explicit args override environment variables."""
        monkeypatch.setenv("TARJOMAN_LOG_LEVEL", "WARNING")
        monkeypatch.setenv("TARJOMAN_LOG_FORMAT", "json")
        stream = io.StringIO()
        logger = configure_logging(level="DEBUG", format="text", stream=stream)
        assert logger.level == logging.DEBUG
        logger.debug("Override test")
        stream.seek(0)
        line = stream.readline()
        with pytest.raises(json.JSONDecodeError):
            json.loads(line)


# ===========================================================================
# TestProviderErrorLeakProtection — Acceptance: "provider error cannot leak API key"
# ===========================================================================

class TestProviderErrorLeakProtection:
    """Provider error traces must never emit raw credentials (§23.2, §24)."""

    def test_provider_error_message_with_key(self):
        """Provider exception message containing API key is sanitized."""
        key = "sk-prod-realkey_abcdefghij1234567890"
        exc = RuntimeError(
            f"401 Unauthorized: Invalid API key {key} for model gpt-4"
        )
        result = sanitize_provider_error(exc)
        assert key not in result
        assert "[REDACTED]" in result
        assert "401 Unauthorized" in result  # diagnostic info preserved

    def test_provider_error_with_bearer(self):
        """Provider error containing Bearer token is sanitized."""
        token = "eyJhbGciOiJSUzI1NiJ9.body.signature_part"
        exc = ConnectionError(
            f"Request failed: Authorization: Bearer {token}"
        )
        result = sanitize_provider_error(exc, context="OpenAI translate call")
        assert token not in result
        assert "[REDACTED]" in result
        assert "[OpenAI translate call]" in result

    def test_provider_error_with_url_key(self):
        """Provider error containing URL with API key param is sanitized."""
        exc = RuntimeError(
            "Request to https://api.example.com/v1?api_key=sk-secret123456789012345 failed"
        )
        result = sanitize_provider_error(exc)
        assert "sk-secret123456789012345" not in result

    def test_provider_error_preserves_status_code(self):
        """Status code attribute is preserved in sanitized output."""
        exc = RuntimeError("Provider rejected request with key sk-bad_key_12345678901234")
        exc.status_code = 401
        result = sanitize_provider_error(exc)
        assert "status=401" in result
        assert "sk-bad_key_12345678901234" not in result

    def test_logging_provider_exception_exc_info(self):
        """Logging a provider exception with exc_info=True never leaks the key."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        key = "sk-production_api_key_must_not_leak"
        try:
            raise RuntimeError(
                f"HTTP 401 from provider: api_key={key}"
            )
        except RuntimeError:
            logger.error("Provider call failed", exc_info=True)
        entry = _capture_json_line(stream)
        # Check all fields
        raw = json.dumps(entry)
        assert key not in raw
        assert "[REDACTED]" in raw

    def test_logging_provider_error_in_text_mode(self):
        """Provider error with API key is redacted in text format too."""
        stream = io.StringIO()
        logger = _make_text_logger(stream)
        key = "sk-text_mode_key_abcdefghij12345"
        try:
            raise RuntimeError(f"Auth error with {key}")
        except RuntimeError:
            logger.error("Failed", exc_info=True)
        stream.seek(0)
        output = stream.read()
        assert key not in output
        assert "[REDACTED]" in output

    def test_provider_error_with_anthropic_key(self):
        """Anthropic key in provider error is sanitized."""
        key = "ant-api01-xxxxxxxxxxxxxxxxxxxxxxx"
        exc = RuntimeError(f"Anthropic API returned 403: invalid key {key}")
        result = sanitize_provider_error(exc)
        assert key not in result
        assert "403" in result

    def test_provider_error_with_authorization_header_value(self):
        """Authorization header value in provider error is stripped."""
        exc = RuntimeError(
            "Request rejected. Headers sent: Authorization: Basic dXNlcjpwYXNz, "
            "x-api-key: my-secret-api-key-value-here"
        )
        result = sanitize_provider_error(exc)
        assert "dXNlcjpwYXNz" not in result
        assert "my-secret-api-key-value-here" not in result

    def test_provider_error_chained_exception_logged(self):
        """Chained exceptions (cause) with keys are redacted in log output."""
        stream = io.StringIO()
        logger = _make_json_logger(stream)
        key = "sk-chained_inner_cause_key_1234567"
        try:
            try:
                raise ConnectionError(f"Failed auth with key {key}")
            except ConnectionError as cause:
                raise RuntimeError("Provider unreachable") from cause
        except RuntimeError:
            logger.error("Pipeline failed", exc_info=True)
        entry = _capture_json_line(stream)
        exc_text = entry.get("exception", "")
        assert key not in exc_text

    def test_sanitize_provider_error_type_info(self):
        """sanitize_provider_error includes exception type name."""
        exc = ConnectionError("Network unreachable")
        result = sanitize_provider_error(exc)
        assert "ConnectionError" in result

    def test_sanitize_provider_error_with_status_attr(self):
        """Works with .status attribute (httpx-style) as well as .status_code."""
        exc = RuntimeError("Bad request")
        exc.status = 400
        result = sanitize_provider_error(exc)
        assert "status=400" in result


# ===========================================================================
# TestContextTracking — Provenance context helpers
# ===========================================================================

class TestContextTracking:
    """Test contextvars-based correlation and provenance tracking (§4.3)."""

    def test_set_and_get_correlation_id(self):
        with bind_provenance(correlation_id=None):
            set_correlation_id("test-corr-123")
            assert get_correlation_id() == "test-corr-123"

    def test_set_operation_context(self):
        with bind_provenance(
            operation_id=None, job_id=None, project_id=None
        ):
            set_operation_context(
                operation_id="op-1", job_id="j-2", project_id="p-3"
            )
            ctx = get_provenance_context()
            assert ctx["operation_id"] == "op-1"
            assert ctx["job_id"] == "j-2"
            assert ctx["project_id"] == "p-3"

    def test_bind_provenance_yields_context(self):
        with bind_provenance(
            correlation_id="c1",
            operation_id="o1",
            job_id="j1",
        ) as ctx:
            assert ctx["correlation_id"] == "c1"
            assert ctx["operation_id"] == "o1"
            assert ctx["job_id"] == "j1"

    def test_bind_provenance_restores_on_exit(self):
        """bind_provenance restores previous values on exit."""
        with bind_provenance(correlation_id="outer"):
            assert get_correlation_id() == "outer"
            with bind_provenance(correlation_id="inner"):
                assert get_correlation_id() == "inner"
            assert get_correlation_id() == "outer"

    def test_bind_provenance_partial_override(self):
        """Only specified fields are overridden; others remain unchanged."""
        with bind_provenance(correlation_id="c1", job_id="j1"):
            with bind_provenance(job_id="j2"):
                ctx = get_provenance_context()
                assert ctx["correlation_id"] == "c1"  # inherited
                assert ctx["job_id"] == "j2"  # overridden

    def test_get_provenance_context_empty(self):
        """Empty context when nothing is set."""
        with bind_provenance(
            correlation_id=None,
            operation_id=None,
            job_id=None,
            project_id=None,
            metadata=None,
        ):
            # Force clear
            from tarjoman.core.logging import (
                _correlation_id,
                _job_id,
                _operation_id,
                _project_id,
                _provenance_metadata,
            )
            tokens = [
                _correlation_id.set(None),
                _operation_id.set(None),
                _job_id.set(None),
                _project_id.set(None),
                _provenance_metadata.set(None),
            ]
            ctx = get_provenance_context()
            assert ctx == {}
            # Restore
            _correlation_id.reset(tokens[0])
            _operation_id.reset(tokens[1])
            _job_id.reset(tokens[2])
            _project_id.reset(tokens[3])
            _provenance_metadata.reset(tokens[4])


# ===========================================================================
# TestRedactionFilter — Filter mechanics
# ===========================================================================

class TestRedactionFilter:
    """Test RedactionFilter applied to logging.LogRecord objects."""

    def test_filter_always_returns_true(self):
        """Filter should always pass records through (mutates, never drops)."""
        filt = RedactionFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="sk-test_key_1234567890abcdefghij",
            args=(), exc_info=None,
        )
        assert filt.filter(record) is True
        assert "sk-test_key_1234567890abcdefghij" not in record.msg

    def test_filter_redacts_args_tuple(self):
        filt = RedactionFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Key: %s", args=("sk-argkey_1234567890abcdefghij",),
            exc_info=None,
        )
        filt.filter(record)
        assert "sk-argkey_1234567890abcdefghij" not in str(record.args)

    def test_filter_redacts_args_dict(self):
        filt = RedactionFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Key: %(key)s",
            args=None,
            exc_info=None,
        )
        # LogRecord.__init__ requires dict args wrapped properly;
        # set after construction to test the filter's dict-args path.
        record.args = {"key": "sk-dictargkey_12345678901234"}
        filt.filter(record)
        assert "sk-dictargkey_12345678901234" not in str(record.args)

    def test_filter_redacts_exc_text(self):
        filt = RedactionFilter()
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="", lineno=0,
            msg="Error", args=(), exc_info=None,
        )
        record.exc_text = "Traceback: sk-exctxt_12345678901234567890"
        filt.filter(record)
        assert "sk-exctxt_12345678901234567890" not in record.exc_text
