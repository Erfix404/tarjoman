"""
Typed error taxonomy and failure semantics for Tarjoman.

Architecture Zero §24:
  - All public errors are typed.
  - Stable uppercase machine-readable error codes.
  - Deterministic non-zero CLI exit codes.
  - Explicit retryability flag matching §24 table.
  - Structured metadata details (no caller needs to regex match str(e)).
  - Raw source content and secrets are excluded/redacted from error representations.
  - Stable protocol mappings: CLI exit code, HTTP status, and MCP (JSON-RPC) error code.

Locked decisions enforced here:
  D14 — CLI/Python are core; FastAPI and MCP are optional interfaces.
  D16 — Privacy policy: source content and secrets are not logged or leaked.
  D19 — Core contains no concrete provider/network/UI/server implementation.
"""
from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type, Union

# ---------------------------------------------------------------------------
# Secret & Sensitive Information Redaction Patterns (§24, D16)
# ---------------------------------------------------------------------------

_SECRET_REDACTION_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Private key blocks
    (
        re.compile(
            r"-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+PRIVATE KEY-----"
        ),
        "[REDACTED PRIVATE KEY]",
    ),
    # URL credentials: https://user:pass@example.com
    (
        re.compile(r"(https?://[^\s:/]+):([^\s@]+)@"),
        r"\1:[REDACTED]@",
    ),
    # Bearer tokens
    (
        re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9_\-\.]{16,}\b"),
        r"\1[REDACTED]",
    ),
    # Known key prefixes (OpenAI, Anthropic, GitHub, HuggingFace, AWS)
    (
        re.compile(r"\bsk-[a-zA-Z0-9_\-]{20,}\b"),
        "[REDACTED]",
    ),
    (
        re.compile(r"\bsk-ant-[a-zA-Z0-9_\-]{20,}\b"),
        "[REDACTED]",
    ),
    (
        re.compile(r"\bgh[pousr]_[a-zA-Z0-9]{36,}\b"),
        "[REDACTED]",
    ),
    (
        re.compile(r"\bgithub_pat_[a-zA-Z0-9_]{40,}\b"),
        "[REDACTED]",
    ),
    (
        re.compile(r"\bhf_[a-zA-Z0-9]{34,}\b"),
        "[REDACTED]",
    ),
    (
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "[REDACTED]",
    ),
    # AWS secret access key assignments
    (
        re.compile(r"(?i)\b(aws_secret_access_key\s*[:=]\s*)[A-Za-z0-9/+=]{40}\b"),
        r"\1[REDACTED]",
    ),
    # Key-value secret assignments: api_key=..., password=..., secret=...
    (
        re.compile(
            r"(?i)\b((?:api[_-]?key|secret|password|auth(?:orization)?|access[_-]?token|private[_-]?key)\s*[:=]\s*[\"']?)([a-zA-Z0-9_\-\.]{8,})([\"']?)"
        ),
        r"\1[REDACTED]\3",
    ),
    # Explicit source tags / markers
    (
        re.compile(r"(?i)<source>[\s\S]*?</source>"),
        "[EXCLUDED: raw source content]",
    ),
    (
        re.compile(r"(?i)\[source\][\s\S]*?\[/source\]"),
        "[EXCLUDED: raw source content]",
    ),
    (
        re.compile(
            r"(?i)\b((?:raw[_-]?source|source[_-]?text)\s*[:=]\s*[\"'])([\s\S]*?)([\"'])"
        ),
        r"\1[EXCLUDED: raw source content]\3",
    ),
]

_SENSITIVE_KEY_REGEX = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|auth(?:orization)?|access[_-]?token|private[_-]?key|credential)"
)

_RAW_SOURCE_KEY_REGEX = re.compile(
    r"(?i)(raw[_-]?source|source[_-]?content|source[_-]?text|raw[_-]?text|source_bytes)"
)


def sanitize_error_message(message: str) -> str:
    """Sanitize error message to ensure no secrets or raw sources leak.

    Enforces Architecture Zero §24 & D16:
      - API keys (OpenAI, Anthropic, AWS, GitHub, HF, etc.) are stripped.
      - Passwords, bearer tokens, and private keys are redacted.
      - Raw source content markers are excluded.
    """
    if not isinstance(message, str):
        message = str(message)

    sanitized = message
    for pattern, replacement in _SECRET_REDACTION_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def _serialize_detail_value(val: Any) -> Any:
    """Serialize a single metadata value into a JSON-safe form."""
    if isinstance(val, Enum):
        return val.value
    if isinstance(val, Path):
        return str(val)
    if hasattr(val, "isoformat") and callable(getattr(val, "isoformat")):
        return val.isoformat()
    return val


def sanitize_details(details: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively sanitize structured metadata details dictionary.

    Redacts sensitive keys (passwords, tokens, keys) and excludes raw source text.
    """
    if not isinstance(details, dict):
        return {}

    sanitized: Dict[str, Any] = {}
    for key, val in details.items():
        key_str = str(key)
        if _SENSITIVE_KEY_REGEX.search(key_str):
            sanitized[key_str] = "[REDACTED]"
        elif _RAW_SOURCE_KEY_REGEX.search(key_str):
            if isinstance(val, str):
                sanitized[key_str] = f"[EXCLUDED: {len(val)} characters]"
            elif isinstance(val, (bytes, bytearray)):
                sanitized[key_str] = f"[EXCLUDED: {len(val)} bytes]"
            else:
                sanitized[key_str] = "[EXCLUDED: raw source content]"
        elif isinstance(val, str):
            sanitized[key_str] = sanitize_error_message(val)
        elif isinstance(val, dict):
            sanitized[key_str] = sanitize_details(val)
        elif isinstance(val, (list, tuple)):
            sanitized_list = []
            for item in val:
                if isinstance(item, dict):
                    sanitized_list.append(sanitize_details(item))
                elif isinstance(item, str):
                    sanitized_list.append(sanitize_error_message(item))
                else:
                    sanitized_list.append(_serialize_detail_value(item))
            sanitized[key_str] = sanitized_list
        else:
            sanitized[key_str] = _serialize_detail_value(val)
    return sanitized


# ---------------------------------------------------------------------------
# Base Exception
# ---------------------------------------------------------------------------

class TarjomanError(Exception):
    """Base exception for all Tarjoman domain and operational errors.

    Architecture Zero §24:
      - All public errors are typed.
      - Stable uppercase machine-readable error codes.
      - Deterministic non-zero CLI exit codes.
      - Explicit retryability flag.
      - Structured metadata details.
      - Automatic secret and raw-source redaction.
    """

    code: str = "TARJOMAN_ERROR"
    retryable: bool = False
    exit_code: int = 1
    user_action: str = "inspect error details"

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        retryable: Optional[bool] = None,
        details: Optional[Dict[str, Any]] = None,
        exit_code: Optional[int] = None,
        user_action: Optional[str] = None,
    ) -> None:
        self.message: str = sanitize_error_message(message)
        self.code: str = code if code is not None else self.__class__.code
        self.retryable: bool = (
            retryable if retryable is not None else self.__class__.retryable
        )
        self.exit_code: int = (
            exit_code if exit_code is not None else self.__class__.exit_code
        )
        self.user_action: str = (
            user_action if user_action is not None else self.__class__.user_action
        )
        self.details: Dict[str, Any] = sanitize_details(details) if details is not None else {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize error to a structured dictionary."""
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
            "exit_code": self.exit_code,
            "user_action": self.user_action,
        }

    def to_json(self, **kwargs: Any) -> str:
        """Serialize error to a JSON string."""
        return json.dumps(self.to_dict(), **kwargs)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"code={self.code!r}, "
            f"message={self.message!r}, "
            f"retryable={self.retryable}, "
            f"exit_code={self.exit_code})"
        )


# ---------------------------------------------------------------------------
# 12 Typed Public Errors (Architecture Zero §24)
# ---------------------------------------------------------------------------

class ConfigurationError(TarjomanError):
    """Configuration syntax, missing key, or invalid setting."""

    code: str = "CONFIGURATION_ERROR"
    retryable: bool = False
    exit_code: int = 2
    user_action: str = "fix config"


class PolicyViolationError(TarjomanError):
    """Operation violates configured privacy, security, or network policy."""

    code: str = "POLICY_VIOLATION_ERROR"
    retryable: bool = False
    exit_code: int = 3
    user_action: str = "change policy/permission"


class LicensePolicyError(TarjomanError):
    """Model, voice, or artifact license is unapproved or incompatible."""

    code: str = "LICENSE_POLICY_ERROR"
    retryable: bool = False
    exit_code: int = 4
    user_action: str = "use approved model/voice"


class CapabilityUnavailableError(TarjomanError):
    """Optional extra, adapter, or model capability is not installed or configured."""

    code: str = "CAPABILITY_UNAVAILABLE_ERROR"
    retryable: bool = False
    exit_code: int = 5
    user_action: str = "install extra or choose adapter"


class ArtifactValidationError(TarjomanError):
    """Corrupted, malformed, or unparseable input/intermediate artifact."""

    code: str = "ARTIFACT_VALIDATION_ERROR"
    retryable: bool = False
    exit_code: int = 6
    user_action: str = "inspect source/parser"


class MigrationError(TarjomanError):
    """Database, schema, or storage migration failure."""

    code: str = "MIGRATION_ERROR"
    retryable: bool = False
    exit_code: int = 7
    user_action: str = "restore/upgrade"


class JobCancelledError(TarjomanError):
    """Job was cancelled by operator or timeout."""

    code: str = "JOB_CANCELLED_ERROR"
    retryable: bool = False
    exit_code: int = 8
    user_action: str = "expected cancellation"


class ProviderTransientError(TarjomanError):
    """Temporary upstream provider failure (e.g. 503, connection drop)."""

    code: str = "PROVIDER_TRANSIENT_ERROR"
    retryable: bool = True
    exit_code: int = 10
    user_action: str = "retry/fallback if policy allows"


class ProviderPermanentError(TarjomanError):
    """Unrecoverable upstream provider rejection (e.g. 401, 404, invalid model)."""

    code: str = "PROVIDER_PERMANENT_ERROR"
    retryable: bool = False
    exit_code: int = 11
    user_action: str = "fix request/provider"


class ProviderRateLimitError(TarjomanError):
    """Upstream provider quota or rate limit exceeded."""

    code: str = "PROVIDER_RATE_LIMIT_ERROR"
    retryable: bool = True
    exit_code: int = 12
    user_action: str = "wait/backoff"


class StructuredOutputError(TarjomanError):
    """Model output failed schema validation or repair."""

    code: str = "STRUCTURED_OUTPUT_ERROR"
    retryable: bool = True
    exit_code: int = 13
    user_action: str = "model/schema issue"


class SpeechSynthesisQualityError(TarjomanError):
    """Synthesized speech failed automated quality evaluation thresholds."""

    code: str = "SPEECH_SYNTHESIS_QUALITY_ERROR"
    retryable: bool = True
    exit_code: int = 14
    user_action: str = "retry/alternate engine only if allowed"


# ---------------------------------------------------------------------------
# Registries and Lookup Tables
# ---------------------------------------------------------------------------

ALL_ERRORS: Tuple[Type[TarjomanError], ...] = (
    TarjomanError,
    ConfigurationError,
    PolicyViolationError,
    LicensePolicyError,
    CapabilityUnavailableError,
    ArtifactValidationError,
    MigrationError,
    JobCancelledError,
    ProviderTransientError,
    ProviderPermanentError,
    ProviderRateLimitError,
    StructuredOutputError,
    SpeechSynthesisQualityError,
)

ERROR_BY_CODE: Dict[str, Type[TarjomanError]] = {
    cls.code: cls for cls in ALL_ERRORS
}


def get_error_class_by_code(code: str) -> Optional[Type[TarjomanError]]:
    """Look up a typed TarjomanError class by its stable machine code."""
    return ERROR_BY_CODE.get(code.upper().strip())


def from_dict(data: Dict[str, Any]) -> TarjomanError:
    """Reconstruct a typed TarjomanError from a serialized dictionary."""
    if not isinstance(data, dict):
        return TarjomanError(str(data))

    code = data.get("code", "TARJOMAN_ERROR")
    cls = get_error_class_by_code(code) or TarjomanError
    message = data.get("message", "")
    retryable = data.get("retryable")
    details = data.get("details", {})
    exit_code = data.get("exit_code")
    user_action = data.get("user_action")

    return cls(
        message,
        code=code,
        retryable=retryable,
        details=details,
        exit_code=exit_code,
        user_action=user_action,
    )


# ---------------------------------------------------------------------------
# Protocol Mappings (CLI, HTTP, MCP / JSON-RPC)
# ---------------------------------------------------------------------------

_HTTP_STATUS_MAP: Dict[Type[TarjomanError], int] = {
    ConfigurationError: 400,
    ArtifactValidationError: 400,
    PolicyViolationError: 403,
    LicensePolicyError: 403,
    CapabilityUnavailableError: 501,
    JobCancelledError: 409,
    ProviderTransientError: 503,
    ProviderPermanentError: 502,
    ProviderRateLimitError: 429,
    StructuredOutputError: 502,
    SpeechSynthesisQualityError: 502,
    MigrationError: 500,
    TarjomanError: 500,
}

_MCP_CODE_MAP: Dict[Type[TarjomanError], int] = {
    ConfigurationError: -32602,        # Invalid params
    ArtifactValidationError: -32602,   # Invalid params
    CapabilityUnavailableError: -32601,# Method/Capability not found
    PolicyViolationError: -32003,       # Server error: Policy violation
    LicensePolicyError: -32004,        # Server error: License policy error
    MigrationError: -32007,            # Server error: Migration error
    JobCancelledError: -32008,         # Server error: Job cancelled
    ProviderRateLimitError: -32029,    # Server error: Rate limited
    StructuredOutputError: -32042,     # Server error: Structured output error
    SpeechSynthesisQualityError: -32044,# Server error: Speech synthesis quality error
    ProviderPermanentError: -32052,    # Server error: Provider permanent error
    ProviderTransientError: -32053,    # Server error: Provider transient error
    TarjomanError: -32603,             # Internal error
}


def get_exit_code(err: Any) -> int:
    """Return deterministic non-zero CLI exit code for an error.

    Accepts an exception instance, exception class, or generic object.
    Always returns a non-zero integer.
    """
    if isinstance(err, TarjomanError):
        return err.exit_code if err.exit_code != 0 else 1
    if isinstance(err, type) and issubclass(err, TarjomanError):
        code = getattr(err, "exit_code", 1)
        return code if code != 0 else 1
    return 1


def get_http_status(err: Any) -> int:
    """Map an error to an HTTP status code.

    Mapping rules:
      - 400: ConfigurationError, ArtifactValidationError
      - 403: PolicyViolationError, LicensePolicyError
      - 404: NotFound variants (FileNotFoundError, KeyError, or details/code with not_found)
      - 409: JobCancelledError
      - 429: ProviderRateLimitError
      - 501: CapabilityUnavailableError
      - 502: ProviderPermanentError, StructuredOutputError, SpeechSynthesisQualityError
      - 503: ProviderTransientError
      - 500: MigrationError, generic TarjomanError, or unexpected exceptions
      - Custom overrides via `http_status` or details are honored.
    """
    # 1. Direct explicit override attribute or details
    if hasattr(err, "http_status"):
        custom = getattr(err, "http_status")
        if isinstance(custom, int) and 100 <= custom <= 599:
            return custom

    if isinstance(err, TarjomanError) and "http_status" in err.details:
        custom = err.details["http_status"]
        if isinstance(custom, int) and 100 <= custom <= 599:
            return custom

    # 2. NotFound variants
    if isinstance(err, (FileNotFoundError, KeyError)) or (
        isinstance(err, type) and issubclass(err, (FileNotFoundError, KeyError))
    ):
        return 404

    err_code = getattr(err, "code", "")
    if isinstance(err_code, str) and "NOT_FOUND" in err_code:
        return 404

    if isinstance(err, TarjomanError) and err.details.get("not_found"):
        return 404

    # 3. Class-based mapping table
    target_cls = err if isinstance(err, type) else err.__class__
    if target_cls in _HTTP_STATUS_MAP:
        return _HTTP_STATUS_MAP[target_cls]

    for registered_cls, status in _HTTP_STATUS_MAP.items():
        if isinstance(err, registered_cls) or (
            isinstance(err, type) and issubclass(err, registered_cls)
        ):
            return status

    return 500


def get_mcp_error(err: Any) -> Dict[str, Any]:
    """Map an error to a JSON-RPC 2.0 compliant MCP error dictionary.

    Returns:
      {
        "code": int,
        "message": str,
        "data": {
          "code": str,
          "retryable": bool,
          "details": dict
        }
      }
    """
    # Determine JSON-RPC code
    target_cls = err if isinstance(err, type) else err.__class__
    mcp_code = -32603  # Default JSON-RPC internal error

    # Allow custom override in details
    if isinstance(err, TarjomanError) and "mcp_code" in err.details:
        custom_code = err.details["mcp_code"]
        if isinstance(custom_code, int):
            mcp_code = custom_code
        else:
            mcp_code = _MCP_CODE_MAP.get(target_cls, -32603)
    elif target_cls in _MCP_CODE_MAP:
        mcp_code = _MCP_CODE_MAP[target_cls]
    else:
        for registered_cls, rcode in _MCP_CODE_MAP.items():
            if isinstance(err, registered_cls) or (
                isinstance(err, type) and issubclass(err, registered_cls)
            ):
                mcp_code = rcode
                break

    # Determine message and structured data
    if isinstance(err, TarjomanError):
        message = err.message
        data = {
            "code": err.code,
            "retryable": err.retryable,
            "details": err.details,
            "exit_code": err.exit_code,
            "user_action": err.user_action,
        }
    elif isinstance(err, type) and issubclass(err, TarjomanError):
        message = getattr(err, "code", err.__name__)
        data = {
            "code": getattr(err, "code", "TARJOMAN_ERROR"),
            "retryable": getattr(err, "retryable", False),
            "details": {},
            "exit_code": getattr(err, "exit_code", 1),
            "user_action": getattr(err, "user_action", "inspect error details"),
        }
    elif isinstance(err, Exception):
        message = sanitize_error_message(str(err))
        data = {
            "code": "INTERNAL_ERROR",
            "retryable": False,
            "details": {},
            "exit_code": 1,
            "user_action": "inspect error details",
        }
    else:
        message = sanitize_error_message(str(err))
        data = {
            "code": "INTERNAL_ERROR",
            "retryable": False,
            "details": {},
            "exit_code": 1,
            "user_action": "inspect error details",
        }

    return {
        "code": mcp_code,
        "message": message,
        "data": data,
    }


__all__ = [
    # Base Exception
    "TarjomanError",
    # 12 Typed Public Errors
    "ConfigurationError",
    "PolicyViolationError",
    "LicensePolicyError",
    "CapabilityUnavailableError",
    "ArtifactValidationError",
    "MigrationError",
    "JobCancelledError",
    "ProviderTransientError",
    "ProviderPermanentError",
    "ProviderRateLimitError",
    "StructuredOutputError",
    "SpeechSynthesisQualityError",
    # Registry & Utilities
    "ALL_ERRORS",
    "ERROR_BY_CODE",
    "get_error_class_by_code",
    "from_dict",
    "sanitize_error_message",
    "sanitize_details",
    # Protocol Mappings
    "get_exit_code",
    "get_http_status",
    "get_mcp_error",
]
