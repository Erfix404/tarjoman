"""
Structured logging, provenance context tracking, and fail-closed secret redaction.

Architecture Zero references:
  §4.3  — OperationSpec & provenance: correlation/operation/job/project IDs.
  §23.2 — Secrets: API keys/tokens never in logs; redaction applies to
           exception text and provider HTTP traces.
  §24   — Error taxonomy: provider errors are sanitized before logging/raising.
  §25.5 — Structured audit trails: JSON-formatted logging with provenance.

Locked decisions enforced here:
  D16 — Privacy: secrets and raw source content are never logged.
  D19 — Core contains no concrete provider/network/UI/server implementation.

Work Package: FND-011 — Structured logging/provenance.
"""
from __future__ import annotations

import contextlib
import copy
import datetime
import json
import logging
import os
import re
import traceback
from contextvars import ContextVar
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

from tarjoman.core.errors import sanitize_error_message

# ---------------------------------------------------------------------------
# Context Variables (§4.3 — OperationSpec & provenance tracking)
# ---------------------------------------------------------------------------

_correlation_id: ContextVar[Optional[str]] = ContextVar(
    "tarjoman_correlation_id", default=None
)
_operation_id: ContextVar[Optional[str]] = ContextVar(
    "tarjoman_operation_id", default=None
)
_job_id: ContextVar[Optional[str]] = ContextVar("tarjoman_job_id", default=None)
_project_id: ContextVar[Optional[str]] = ContextVar(
    "tarjoman_project_id", default=None
)
_provenance_metadata: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "tarjoman_provenance_metadata", default=None
)


def set_correlation_id(cid: str) -> None:
    """Set the active correlation ID for the current async/thread context."""
    _correlation_id.set(cid)


def get_correlation_id() -> Optional[str]:
    """Return the active correlation ID, or None if unset."""
    return _correlation_id.get()


def set_operation_context(
    *,
    operation_id: Optional[str] = None,
    job_id: Optional[str] = None,
    project_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Set operation-level context for structured log enrichment (§4.3)."""
    if operation_id is not None:
        _operation_id.set(operation_id)
    if job_id is not None:
        _job_id.set(job_id)
    if project_id is not None:
        _project_id.set(project_id)
    if metadata is not None:
        _provenance_metadata.set(metadata)


def get_provenance_context() -> Dict[str, Any]:
    """Return the current provenance context as a flat dictionary."""
    ctx: Dict[str, Any] = {}
    cid = _correlation_id.get()
    if cid is not None:
        ctx["correlation_id"] = cid
    oid = _operation_id.get()
    if oid is not None:
        ctx["operation_id"] = oid
    jid = _job_id.get()
    if jid is not None:
        ctx["job_id"] = jid
    pid = _project_id.get()
    if pid is not None:
        ctx["project_id"] = pid
    meta = _provenance_metadata.get()
    if meta is not None:
        ctx["metadata"] = meta
    return ctx


@contextlib.contextmanager
def bind_provenance(
    *,
    correlation_id: Optional[str] = None,
    operation_id: Optional[str] = None,
    job_id: Optional[str] = None,
    project_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Generator[Dict[str, Any], None, None]:
    """Context manager to scope provenance context to a block.

    Restores previous values on exit, safe for nested use and async tasks.

    Usage::

        with bind_provenance(correlation_id="req-123", job_id="job-456"):
            logger.info("Processing started")
            # JSON log output will include correlation_id and job_id
    """
    tokens = []
    if correlation_id is not None:
        tokens.append((_correlation_id, _correlation_id.set(correlation_id)))
    if operation_id is not None:
        tokens.append((_operation_id, _operation_id.set(operation_id)))
    if job_id is not None:
        tokens.append((_job_id, _job_id.set(job_id)))
    if project_id is not None:
        tokens.append((_project_id, _project_id.set(project_id)))
    if metadata is not None:
        tokens.append((_provenance_metadata, _provenance_metadata.set(metadata)))
    try:
        yield get_provenance_context()
    finally:
        for var, token in tokens:
            var.reset(token)


# ---------------------------------------------------------------------------
# Secret Redaction (§23.2 — fail-closed, never leak keys/tokens)
# ---------------------------------------------------------------------------

_LOG_SECRET_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Anthropic-style keys (must precede generic sk- pattern)
    (re.compile(r"\bsk-ant-[a-zA-Z0-9_\-]{20,}\b"), "[REDACTED]"),
    (re.compile(r"\bant-[a-zA-Z0-9_\-]{20,}\b"), "[REDACTED]"),
    # OpenAI-style keys
    (re.compile(r"\bsk-[a-zA-Z0-9_\-]{20,}\b"), "[REDACTED]"),
    # Bearer tokens
    (
        re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/\-]+=*"),
        r"\1[REDACTED]",
    ),
    # Authorization / API key headers (key: value or key=value)
    # Matches "Authorization: Basic <token>", "Authorization: Bearer <token>",
    # "api_key=value", "x-api-key: value", etc.  The optional scheme word
    # (Basic, Bearer, …) is consumed along with the credential value.
    (
        re.compile(
            r"(?i)((?:Authorization|api[_\-]?key|x-api-key|secret|token)"
            r"\s*[:=]\s*['\"]?)(?:[A-Za-z]+\s+)?[^\s'\",;]+"
        ),
        r"\1[REDACTED]",
    ),
    # URL query parameter tokens
    (
        re.compile(r"([?&](?:api[_\-]?key|key|token|secret)=)[^&\s]+"),
        r"\1[REDACTED]",
    ),
    # GitHub PAT / fine-grained tokens
    (re.compile(r"\bgh[pousr]_[a-zA-Z0-9]{36,}\b"), "[REDACTED]"),
    (re.compile(r"\bgithub_pat_[a-zA-Z0-9_]{40,}\b"), "[REDACTED]"),
    # HuggingFace tokens
    (re.compile(r"\bhf_[a-zA-Z0-9]{34,}\b"), "[REDACTED]"),
    # AWS access key IDs
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED]"),
    # Private key blocks
    (
        re.compile(
            r"-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]*?"
            r"-----END [A-Z ]+PRIVATE KEY-----"
        ),
        "[REDACTED PRIVATE KEY]",
    ),
]


def _redact_string(val: str) -> str:
    """Apply all secret redaction patterns to a string."""
    result = val
    for pattern, replacement in _LOG_SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def redact_secrets(val: Any) -> Any:
    """Recursively redact secrets from arbitrary values.

    Handles strings, dicts, lists, tuples, exceptions, and tracebacks.
    Fail-closed: if redaction itself fails, replaces the value entirely.
    """
    try:
        return _redact_inner(val)
    except Exception:
        # Fail-closed: if redaction logic itself errors, suppress the value
        return "[REDACTED: redaction error]"


def _redact_inner(val: Any) -> Any:
    """Inner recursive redaction (not fail-closed; caller catches)."""
    if isinstance(val, str):
        return _redact_string(val)
    if isinstance(val, dict):
        return {k: _redact_inner(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        redacted = [_redact_inner(item) for item in val]
        return type(val)(redacted)
    if isinstance(val, BaseException):
        # Redact the exception's string representation
        redacted_args = tuple(_redact_inner(a) for a in val.args)
        return type(val)(*redacted_args) if redacted_args else val
    return val


def _redact_traceback_text(tb_text: str) -> str:
    """Redact secrets from formatted traceback text."""
    return _redact_string(tb_text)


# ---------------------------------------------------------------------------
# Redaction Filter (attached to logging handlers)
# ---------------------------------------------------------------------------

class RedactionFilter(logging.Filter):
    """Logging filter that redacts secrets from all log record fields (§23.2).

    Intercepts ``record.msg``, ``record.args``, ``record.exc_info``,
    ``record.exc_text``, and any ``extra`` fields to ensure no API keys,
    bearer tokens, or other credentials reach log output.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Format the full message (template + args) then redact as one string.
        # This catches secrets that span template and args (e.g. the template
        # contains "Authorization: Bearer %s" and the arg is the raw token).
        try:
            if record.args:
                if isinstance(record.msg, str):
                    formatted = record.msg % record.args
                else:
                    formatted = str(record.msg)
                record.msg = _redact_string(formatted)
                record.args = None
            elif isinstance(record.msg, str):
                record.msg = _redact_string(record.msg)
            elif record.msg is not None:
                record.msg = redact_secrets(record.msg)
        except (TypeError, ValueError, KeyError):
            # Fallback: redact template and args separately
            if isinstance(record.msg, str):
                record.msg = _redact_string(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {
                        k: redact_secrets(v) for k, v in record.args.items()
                    }
                elif isinstance(record.args, tuple):
                    record.args = tuple(redact_secrets(a) for a in record.args)

        # Redact cached exception text
        if record.exc_text:
            record.exc_text = _redact_string(record.exc_text)

        # Redact exc_info tuple (type, value, traceback)
        if record.exc_info and record.exc_info[1] is not None:
            exc_type, exc_val, exc_tb = record.exc_info
            redacted_val = redact_secrets(exc_val)
            record.exc_info = (exc_type, redacted_val, exc_tb)

        # Redact any extra fields set via logger.info("msg", extra={...})
        # Standard LogRecord attributes that are NOT user extras:
        _standard = {
            "name", "msg", "args", "created", "relativeCreated", "exc_info",
            "exc_text", "stack_info", "lineno", "funcName", "sinfo",
            "filename", "module", "pathname", "levelname", "levelno",
            "process", "processName", "thread", "threadName", "msecs",
            "message", "asctime", "taskName",
        }
        for attr in list(record.__dict__):
            if attr.startswith("_") or attr in _standard:
                continue
            val = getattr(record, attr)
            if isinstance(val, (str, dict, list, tuple)):
                setattr(record, attr, redact_secrets(val))

        return True  # Always pass the record through; we only mutate


# ---------------------------------------------------------------------------
# JSON Formatter (§25.5 — Structured audit trails)
# ---------------------------------------------------------------------------

class JSONFormatter(logging.Formatter):
    """Produces single-line JSON log records with provenance context.

    Output keys:
      timestamp, level, logger, message, correlation_id, operation_id,
      job_id, project_id, provenance, exception, extra.
    """

    _STANDARD_ATTRS = frozenset({
        "name", "msg", "args", "created", "relativeCreated", "exc_info",
        "exc_text", "stack_info", "lineno", "funcName", "sinfo",
        "filename", "module", "pathname", "levelname", "levelno",
        "process", "processName", "thread", "threadName", "msecs",
        "message", "asctime", "taskName",
    })

    def format(self, record: logging.LogRecord) -> str:
        # Ensure record.message is populated and redacted post-formatting.
        # RedactionFilter runs before formatting (msg template + args separately),
        # so patterns that span template and args (e.g. "Bearer %s") need a
        # final redaction pass on the fully-assembled message.
        record.message = _redact_string(record.getMessage())

        # Build the JSON payload
        payload: Dict[str, Any] = {
            "timestamp": datetime.datetime.fromtimestamp(
                record.created, tz=datetime.timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.message,
            "correlation_id": _correlation_id.get(),
            "operation_id": _operation_id.get(),
            "job_id": _job_id.get(),
            "project_id": _project_id.get(),
        }

        # Provenance metadata
        meta = _provenance_metadata.get()
        payload["provenance"] = meta if meta else None

        # Exception info
        if record.exc_info and record.exc_info[1] is not None:
            exc_text = self.formatException(record.exc_info)
            payload["exception"] = _redact_string(exc_text)
        elif record.exc_text:
            payload["exception"] = _redact_string(record.exc_text)
        else:
            payload["exception"] = None

        # Extra fields (non-standard attributes)
        extra: Dict[str, Any] = {}
        for attr, val in record.__dict__.items():
            if attr.startswith("_") or attr in self._STANDARD_ATTRS:
                continue
            extra[attr] = val
        payload["extra"] = extra if extra else None

        return json.dumps(payload, default=str, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Text Formatter (human-readable with redaction for CLI/dev)
# ---------------------------------------------------------------------------

class TextFormatter(logging.Formatter):
    """Human-readable formatter with timestamps, context, and redaction.

    Format: ``YYYY-MM-DDTHH:MM:SS.sssZ LEVEL [logger] [correlation_id] message``
    """

    def format(self, record: logging.LogRecord) -> str:
        record.message = _redact_string(record.getMessage())
        ts = datetime.datetime.fromtimestamp(
            record.created, tz=datetime.timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        cid = _correlation_id.get()
        cid_part = f" [{cid}]" if cid else ""

        line = f"{ts} {record.levelname:<8} [{record.name}]{cid_part} {record.message}"

        if record.exc_info and record.exc_info[1] is not None:
            exc_text = self.formatException(record.exc_info)
            line += "\n" + _redact_string(exc_text)
        elif record.exc_text:
            line += "\n" + _redact_string(record.exc_text)

        return line


# ---------------------------------------------------------------------------
# Provider Error Sanitizer (§24 — sanitized details)
# ---------------------------------------------------------------------------

def sanitize_provider_error(
    error: BaseException,
    *,
    context: Optional[str] = None,
) -> str:
    """Sanitize a provider/HTTP/SDK error, stripping credentials.

    Returns a redacted string suitable for logging or wrapping in a
    typed TarjomanError. Preserves diagnostic info (status codes,
    failure reasons) while ensuring no API key, bearer token, or
    authorization header leaks.

    Args:
        error: The raw exception from a provider SDK or HTTP client.
        context: Optional context label (e.g. "OpenAI translate call").

    Returns:
        A redacted, single-string error description.
    """
    parts: List[str] = []
    if context:
        parts.append(f"[{context}]")

    # Type information
    parts.append(f"{type(error).__name__}:")

    # Redact the error message
    msg = sanitize_error_message(str(error))
    msg = _redact_string(msg)
    parts.append(msg)

    # If the error has response/status attributes (common in HTTP libs),
    # include the status code but redact everything else
    status = getattr(error, "status_code", None) or getattr(error, "status", None)
    if status is not None:
        parts.append(f"(status={status})")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Logging Configuration (§25.5)
# ---------------------------------------------------------------------------

def configure_logging(
    *,
    level: Optional[str] = None,
    format: Optional[str] = None,  # noqa: A002 — shadows builtin intentionally
    stream: Any = None,
    handler: Optional[logging.Handler] = None,
) -> logging.Logger:
    """Configure the ``tarjoman`` logger hierarchy with redaction and formatting.

    Args:
        level: Log level name (DEBUG, INFO, WARNING, ERROR). Falls back to
               ``TARJOMAN_LOG_LEVEL`` env var, then ``INFO``.
        format: ``"json"`` or ``"text"``. Falls back to ``TARJOMAN_LOG_FORMAT``
                env var, then ``"text"``.
        stream: Output stream for the default StreamHandler. Ignored if
                ``handler`` is provided.
        handler: Explicit handler to attach instead of creating a StreamHandler.

    Returns:
        The configured ``tarjoman`` root logger.
    """
    resolved_level = (
        level
        or os.environ.get("TARJOMAN_LOG_LEVEL")
        or "INFO"
    ).upper()

    resolved_format = (
        format
        or os.environ.get("TARJOMAN_LOG_FORMAT")
        or "text"
    ).lower()

    root = logging.getLogger("tarjoman")
    root.setLevel(getattr(logging, resolved_level, logging.INFO))

    # Remove existing handlers to allow clean reconfiguration
    root.handlers.clear()

    # Create handler
    if handler is not None:
        h = handler
    else:
        import sys
        h = logging.StreamHandler(stream or sys.stderr)

    # Attach formatter
    if resolved_format == "json":
        h.setFormatter(JSONFormatter())
    else:
        h.setFormatter(TextFormatter())

    # Attach redaction filter (fail-closed: always present)
    h.addFilter(RedactionFilter())

    root.addHandler(h)
    root.propagate = False

    return root


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    # Formatters
    "JSONFormatter",
    "TextFormatter",
    # Redaction
    "RedactionFilter",
    "redact_secrets",
    # Provider error sanitization
    "sanitize_provider_error",
    # Context / Provenance
    "bind_provenance",
    "set_correlation_id",
    "get_correlation_id",
    "set_operation_context",
    "get_provenance_context",
    # Configuration
    "configure_logging",
]
