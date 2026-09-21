"""
Comprehensive tests for Tarjoman Error Taxonomy and Failure Semantics (FND-003).

Architecture Zero §24:
  - All public errors are typed.
  - Stable uppercase machine-readable error codes.
  - Deterministic non-zero CLI exit codes.
  - Explicit retryability flag matching §24 table.
  - Structured metadata details (no caller needs to regex match str(e)).
  - Raw source content and secrets are excluded/redacted from error representations.
  - Stable protocol mappings: CLI exit code, HTTP status, and MCP (JSON-RPC) error code.
"""
from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
import unittest

from tarjoman.core.errors import (
    ALL_ERRORS,
    ERROR_BY_CODE,
    ArtifactValidationError,
    CapabilityUnavailableError,
    ConfigurationError,
    JobCancelledError,
    LicensePolicyError,
    MigrationError,
    PolicyViolationError,
    ProviderPermanentError,
    ProviderRateLimitError,
    ProviderTransientError,
    SpeechSynthesisQualityError,
    StructuredOutputError,
    TarjomanError,
    from_dict,
    get_error_class_by_code,
    get_exit_code,
    get_http_status,
    get_mcp_error,
    sanitize_details,
    sanitize_error_message,
)
import tarjoman.core as core_pkg


class TestErrorInheritanceAndTypes(unittest.TestCase):
    """Test inheritance hierarchy and type relationships for all error classes."""

    PUBLIC_ERROR_CLASSES = [
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
    ]

    def test_tarjoman_error_inherits_from_exception(self) -> None:
        """Base TarjomanError must inherit from Python's Exception."""
        self.assertTrue(issubclass(TarjomanError, Exception))
        err = TarjomanError("base error")
        self.assertIsInstance(err, Exception)

    def test_all_12_errors_inherit_from_tarjoman_error(self) -> None:
        """Every public error class from §24 must inherit from TarjomanError."""
        self.assertEqual(len(self.PUBLIC_ERROR_CLASSES), 12)
        for cls in self.PUBLIC_ERROR_CLASSES:
            with self.subTest(cls=cls.__name__):
                self.assertTrue(
                    issubclass(cls, TarjomanError),
                    f"{cls.__name__} must inherit from TarjomanError",
                )
                inst = cls(f"Test message for {cls.__name__}")
                self.assertIsInstance(inst, TarjomanError)
                self.assertIsInstance(inst, Exception)

    def test_error_classes_are_distinct(self) -> None:
        """All 12 error classes must be unique and distinct classes."""
        self.assertEqual(len(set(self.PUBLIC_ERROR_CLASSES)), 12)


class TestErrorContractAndAttributes(unittest.TestCase):
    """Test typed contract fields: code, retryable, exit_code, user_action."""

    EXPECTED_SPECS = {
        ConfigurationError: {
            "code": "CONFIGURATION_ERROR",
            "retryable": False,
            "exit_code": 2,
            "user_action": "fix config",
        },
        PolicyViolationError: {
            "code": "POLICY_VIOLATION_ERROR",
            "retryable": False,
            "exit_code": 3,
            "user_action": "change policy/permission",
        },
        LicensePolicyError: {
            "code": "LICENSE_POLICY_ERROR",
            "retryable": False,
            "exit_code": 4,
            "user_action": "use approved model/voice",
        },
        CapabilityUnavailableError: {
            "code": "CAPABILITY_UNAVAILABLE_ERROR",
            "retryable": False,
            "exit_code": 5,
            "user_action": "install extra or choose adapter",
        },
        ArtifactValidationError: {
            "code": "ARTIFACT_VALIDATION_ERROR",
            "retryable": False,
            "exit_code": 6,
            "user_action": "inspect source/parser",
        },
        MigrationError: {
            "code": "MIGRATION_ERROR",
            "retryable": False,
            "exit_code": 7,
            "user_action": "restore/upgrade",
        },
        JobCancelledError: {
            "code": "JOB_CANCELLED_ERROR",
            "retryable": False,
            "exit_code": 8,
            "user_action": "expected cancellation",
        },
        ProviderTransientError: {
            "code": "PROVIDER_TRANSIENT_ERROR",
            "retryable": True,
            "exit_code": 10,
            "user_action": "retry/fallback if policy allows",
        },
        ProviderPermanentError: {
            "code": "PROVIDER_PERMANENT_ERROR",
            "retryable": False,
            "exit_code": 11,
            "user_action": "fix request/provider",
        },
        ProviderRateLimitError: {
            "code": "PROVIDER_RATE_LIMIT_ERROR",
            "retryable": True,
            "exit_code": 12,
            "user_action": "wait/backoff",
        },
        StructuredOutputError: {
            "code": "STRUCTURED_OUTPUT_ERROR",
            "retryable": True,
            "exit_code": 13,
            "user_action": "model/schema issue",
        },
        SpeechSynthesisQualityError: {
            "code": "SPEECH_SYNTHESIS_QUALITY_ERROR",
            "retryable": True,
            "exit_code": 14,
            "user_action": "retry/alternate engine only if allowed",
        },
    }

    def test_base_error_defaults(self) -> None:
        """Test base TarjomanError default attributes."""
        err = TarjomanError("base failure")
        self.assertEqual(err.code, "TARJOMAN_ERROR")
        self.assertFalse(err.retryable)
        self.assertEqual(err.exit_code, 1)
        self.assertEqual(err.details, {})
        self.assertIsInstance(err.user_action, str)

    def test_12_errors_match_specification(self) -> None:
        """Verify code, retryable, exit_code, and user_action for all 12 errors."""
        for cls, spec in self.EXPECTED_SPECS.items():
            with self.subTest(cls=cls.__name__):
                # Verify class-level attributes
                self.assertEqual(cls.code, spec["code"])
                self.assertEqual(cls.retryable, spec["retryable"])
                self.assertEqual(cls.exit_code, spec["exit_code"])
                self.assertEqual(cls.user_action, spec["user_action"])

                # Verify instance-level attributes
                inst = cls("Sample error")
                self.assertEqual(inst.code, spec["code"])
                self.assertEqual(inst.retryable, spec["retryable"])
                self.assertEqual(inst.exit_code, spec["exit_code"])
                self.assertEqual(inst.user_action, spec["user_action"])
                self.assertEqual(inst.details, {})

    def test_error_code_format(self) -> None:
        """Every error code must be uppercase, alphanumeric with underscores, ending in _ERROR."""
        for cls in self.EXPECTED_SPECS:
            self.assertTrue(cls.code.isupper())
            self.assertTrue(cls.code.endswith("_ERROR"))
            self.assertRegex(cls.code, r"^[A-Z0-9_]+_ERROR$")

    def test_cli_exit_codes_are_positive_and_unique(self) -> None:
        """Every error class must have a positive, non-zero CLI exit code."""
        exit_codes = [cls.exit_code for cls in self.EXPECTED_SPECS]
        for code in exit_codes:
            self.assertGreater(code, 0)
        self.assertEqual(len(exit_codes), len(set(exit_codes)), "Exit codes must be distinct")


class TestNoGenericErrorStringContract(unittest.TestCase):
    """Verify that callers inspect typed fields without parsing error strings."""

    def test_typed_field_inspection(self) -> None:
        """Callers inspect .code, .retryable, .details directly without regex on str(e)."""
        err = ProviderRateLimitError(
            "Rate limit reached on tier-2",
            details={"provider": "anthropic", "retry_after": 60},
        )

        # Inspection requires zero string parsing
        self.assertTrue(err.retryable)
        self.assertEqual(err.code, "PROVIDER_RATE_LIMIT_ERROR")
        self.assertEqual(err.exit_code, 12)
        self.assertEqual(err.details["provider"], "anthropic")
        self.assertEqual(err.details["retry_after"], 60)

    def test_custom_overrides_at_construction(self) -> None:
        """Errors support optional explicit overrides while maintaining typing."""
        err = ConfigurationError(
            "Custom config error",
            code="CUSTOM_CONFIG_ERROR",
            retryable=True,
            exit_code=99,
            details={"key": "max_retries"},
            user_action="check environment variables",
        )
        self.assertEqual(err.code, "CUSTOM_CONFIG_ERROR")
        self.assertTrue(err.retryable)
        self.assertEqual(err.exit_code, 99)
        self.assertEqual(err.details, {"key": "max_retries"})
        self.assertEqual(err.user_action, "check environment variables")

    def test_str_and_repr_behavior(self) -> None:
        """str(e) returns clean message; repr(e) includes structured information."""
        err = ArtifactValidationError("Invalid JSON syntax in segment 10")
        self.assertEqual(str(err), "Invalid JSON syntax in segment 10")
        rep = repr(err)
        self.assertIn("ArtifactValidationError", rep)
        self.assertIn("ARTIFACT_VALIDATION_ERROR", rep)
        self.assertIn("retryable=False", rep)
        self.assertIn("exit_code=6", rep)


class TestCLIExitCodeMapping(unittest.TestCase):
    """Test get_exit_code mapping function and deterministic non-zero codes."""

    def test_exit_codes_for_all_instances(self) -> None:
        """get_exit_code returns the exact non-zero code for every instance."""
        for cls in TestErrorContractAndAttributes.EXPECTED_SPECS:
            inst = cls("test")
            self.assertEqual(get_exit_code(inst), cls.exit_code)
            self.assertGreater(get_exit_code(inst), 0)

    def test_exit_codes_for_all_classes(self) -> None:
        """get_exit_code works when passed the exception class itself."""
        for cls in TestErrorContractAndAttributes.EXPECTED_SPECS:
            self.assertEqual(get_exit_code(cls), cls.exit_code)
            self.assertGreater(get_exit_code(cls), 0)

    def test_exit_code_for_base_tarjoman_error(self) -> None:
        """Base TarjomanError maps to exit code 1."""
        self.assertEqual(get_exit_code(TarjomanError("generic")), 1)
        self.assertEqual(get_exit_code(TarjomanError), 1)

    def test_exit_code_for_generic_python_exceptions(self) -> None:
        """Standard Python exceptions map safely to 1 (non-zero)."""
        self.assertEqual(get_exit_code(ValueError("bad value")), 1)
        self.assertEqual(get_exit_code(RuntimeError("runtime issue")), 1)
        self.assertEqual(get_exit_code(KeyError("missing")), 1)
        self.assertEqual(get_exit_code(None), 1)
        self.assertEqual(get_exit_code("some string"), 1)

    def test_exit_code_zero_guard(self) -> None:
        """Even if an error has exit_code=0 configured, get_exit_code guarantees non-zero."""
        err = TarjomanError("zero exit test", exit_code=0)
        self.assertEqual(get_exit_code(err), 1)


class TestHTTPStatusMapping(unittest.TestCase):
    """Test get_http_status mapping table per Architecture Zero §24."""

    EXPECTED_HTTP_STATUSES = {
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

    def test_all_12_errors_http_status_instances(self) -> None:
        """Verify HTTP status code mapping for instances of all errors."""
        for cls, status in self.EXPECTED_HTTP_STATUSES.items():
            with self.subTest(cls=cls.__name__):
                inst = cls("test")
                self.assertEqual(get_http_status(inst), status)

    def test_all_12_errors_http_status_classes(self) -> None:
        """Verify HTTP status code mapping when passing the class directly."""
        for cls, status in self.EXPECTED_HTTP_STATUSES.items():
            with self.subTest(cls=cls.__name__):
                self.assertEqual(get_http_status(cls), status)

    def test_not_found_variants_map_to_404(self) -> None:
        """Errors representing missing resources must map to HTTP 404."""
        self.assertEqual(get_http_status(FileNotFoundError("file.txt not found")), 404)
        self.assertEqual(get_http_status(KeyError("profile")), 404)

        err_with_code = ArtifactValidationError("Artifact missing", code="ARTIFACT_NOT_FOUND")
        self.assertEqual(get_http_status(err_with_code), 404)

        err_with_detail = ConfigurationError("Config not found", details={"not_found": True})
        self.assertEqual(get_http_status(err_with_detail), 404)

    def test_explicit_http_status_override(self) -> None:
        """Errors with custom http_status in details or attribute are honored."""
        err_detail = ConfigurationError("Unprocessable entity", details={"http_status": 422})
        self.assertEqual(get_http_status(err_detail), 422)

        err_attr = TarjomanError("Teapot error")
        err_attr.http_status = 418  # type: ignore[attr-defined]
        self.assertEqual(get_http_status(err_attr), 418)

    def test_generic_python_exception_fallback(self) -> None:
        """Generic non-Tarjoman exceptions fall back to HTTP 500."""
        self.assertEqual(get_http_status(RuntimeError("crash")), 500)
        self.assertEqual(get_http_status(Exception("unknown")), 500)
        self.assertEqual(get_http_status("non-exception"), 500)


class TestMCPErrorMapping(unittest.TestCase):
    """Test get_mcp_error JSON-RPC 2.0 compliant dictionary mapping."""

    EXPECTED_MCP_CODES = {
        ConfigurationError: -32602,       # Invalid params
        ArtifactValidationError: -32602,  # Invalid params
        CapabilityUnavailableError: -32601,  # Method not found
        PolicyViolationError: -32003,      # Policy violation
        LicensePolicyError: -32004,       # License policy error
        MigrationError: -32007,           # Migration error
        JobCancelledError: -32008,        # Job cancelled
        ProviderRateLimitError: -32029,   # Rate limit
        StructuredOutputError: -32042,    # Structured output error
        SpeechSynthesisQualityError: -32044,  # Speech synthesis quality error
        ProviderPermanentError: -32052,   # Provider permanent error
        ProviderTransientError: -32053,   # Provider transient error
        TarjomanError: -32603,            # Internal error
    }

    def test_mcp_error_structure_and_codes(self) -> None:
        """Every error produces a JSON-RPC compliant object with code, message, data."""
        for cls, expected_code in self.EXPECTED_MCP_CODES.items():
            with self.subTest(cls=cls.__name__):
                inst = cls("Failed operation", details={"step": "verify"})
                mcp = get_mcp_error(inst)

                self.assertIn("code", mcp)
                self.assertIn("message", mcp)
                self.assertIn("data", mcp)

                self.assertEqual(mcp["code"], expected_code)
                self.assertIsInstance(mcp["code"], int)
                self.assertEqual(mcp["message"], "Failed operation")

                data = mcp["data"]
                self.assertEqual(data["code"], cls.code)
                self.assertEqual(data["retryable"], cls.retryable)
                self.assertEqual(data["details"], {"step": "verify"})
                self.assertEqual(data["exit_code"], cls.exit_code)

    def test_mcp_error_with_class_input(self) -> None:
        """get_mcp_error handles class inputs gracefully."""
        for cls, expected_code in self.EXPECTED_MCP_CODES.items():
            with self.subTest(cls=cls.__name__):
                mcp = get_mcp_error(cls)
                self.assertEqual(mcp["code"], expected_code)
                self.assertIsInstance(mcp["code"], int)
                self.assertIn("data", mcp)

    def test_mcp_error_custom_override(self) -> None:
        """Explicit custom mcp_code in details is honored."""
        err = ConfigurationError("Custom code", details={"mcp_code": -32099})
        mcp = get_mcp_error(err)
        self.assertEqual(mcp["code"], -32099)

    def test_mcp_error_generic_exception(self) -> None:
        """Standard Python exceptions map to JSON-RPC -32603 Internal Error."""
        err = RuntimeError("Unexpected server panic")
        mcp = get_mcp_error(err)
        self.assertEqual(mcp["code"], -32603)
        self.assertEqual(mcp["message"], "Unexpected server panic")
        self.assertEqual(mcp["data"]["code"], "INTERNAL_ERROR")
        self.assertFalse(mcp["data"]["retryable"])


class TestSecretAndSourceSanitization(unittest.TestCase):
    """Test sanitization of secrets, tokens, API keys, and raw source exclusion (§24, D16)."""

    def test_openai_api_key_redaction(self) -> None:
        """OpenAI sk- keys must be redacted."""
        msg = "Failed with sk-proj-1234567890abcdef1234567890 key"
        sanitized = sanitize_error_message(msg)
        self.assertNotIn("sk-proj-1234567890abcdef1234567890", sanitized)
        self.assertIn("[REDACTED]", sanitized)

    def test_anthropic_api_key_redaction(self) -> None:
        """Anthropic sk-ant- keys must be redacted."""
        msg = "Auth error for sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890"
        sanitized = sanitize_error_message(msg)
        self.assertNotIn("sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890", sanitized)
        self.assertIn("[REDACTED]", sanitized)

    def test_bearer_token_redaction(self) -> None:
        """Bearer tokens must be redacted."""
        msg = "Authorization header: Bearer abcdef1234567890abcdef"
        sanitized = sanitize_error_message(msg)
        self.assertNotIn("abcdef1234567890abcdef", sanitized)
        self.assertIn("Bearer [REDACTED]", sanitized)

    def test_aws_access_and_secret_key_redaction(self) -> None:
        """AWS access key IDs and secret access keys must be redacted."""
        msg = "AWS access AKIAIOSFODNN7EXAMPLE and aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        sanitized = sanitize_error_message(msg)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", sanitized)
        self.assertNotIn("wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", sanitized)
        self.assertIn("[REDACTED]", sanitized)

    def test_github_and_huggingface_token_redaction(self) -> None:
        """GitHub and HuggingFace personal access tokens must be redacted."""
        msg_gh = "GitHub sync failed for ghp_abcdefghijklmnopqrstuvwxyz0123456789"
        sanitized_gh = sanitize_error_message(msg_gh)
        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz0123456789", sanitized_gh)
        self.assertIn("[REDACTED]", sanitized_gh)

        msg_hf = "Model download error hf_abcdefghijklmnopqrstuvwxyz0123456789"
        sanitized_hf = sanitize_error_message(msg_hf)
        self.assertNotIn("hf_abcdefghijklmnopqrstuvwxyz0123456789", sanitized_hf)
        self.assertIn("[REDACTED]", sanitized_hf)

    def test_password_and_secret_assignments_redacted(self) -> None:
        """Assignments like password=..., api_key=..., secret=... must be redacted."""
        msg = 'Connection string: api_key="secretKey12345", password=\'superSecretPassword\''
        sanitized = sanitize_error_message(msg)
        self.assertNotIn("secretKey12345", sanitized)
        self.assertNotIn("superSecretPassword", sanitized)
        self.assertIn("[REDACTED]", sanitized)

    def test_url_credentials_redacted(self) -> None:
        """HTTP Basic Auth credentials in URLs must be redacted."""
        msg = "Failed POST https://service_user:super_secret_pwd@api.openai.com/v1/chat"
        sanitized = sanitize_error_message(msg)
        self.assertNotIn("super_secret_pwd", sanitized)
        self.assertIn("https://service_user:[REDACTED]@api.openai.com/v1/chat", sanitized)

    def test_private_key_block_redacted(self) -> None:
        """PEM private key blocks must be redacted completely."""
        pem = (
            "Error loading key:\n"
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEowIBAAKCAQEA0Y7b45Q...secret key content...\n"
            "-----END RSA PRIVATE KEY-----\n"
            "Corrupted key format"
        )
        sanitized = sanitize_error_message(pem)
        self.assertNotIn("secret key content", sanitized)
        self.assertIn("[REDACTED PRIVATE KEY]", sanitized)

    def test_raw_source_marker_exclusion(self) -> None:
        """Explicit raw source blocks/markers are excluded from error messages."""
        msg = "Parser failed on <source>Sensitive confidential text that should not appear</source>"
        sanitized = sanitize_error_message(msg)
        self.assertNotIn("Sensitive confidential text", sanitized)
        self.assertIn("[EXCLUDED: raw source content]", sanitized)

        msg_bb = "Failed segment [source]Another secret manuscript[/source]"
        sanitized_bb = sanitize_error_message(msg_bb)
        self.assertNotIn("Another secret manuscript", sanitized_bb)
        self.assertIn("[EXCLUDED: raw source content]", sanitized_bb)

    def test_details_sanitization_recursive(self) -> None:
        """sanitize_details redacts sensitive keys and excludes raw source across nested structures."""
        details = {
            "api_key": "sk-12345678901234567890",
            "password": "my_db_password_123",
            "raw_source": "This is raw source document text with confidential data.",
            "source_bytes": b"\x00\x01\x02\x03\x04",
            "safe_param": "literary",
            "nested": {
                "secret_token": "token_value_987654321",
                "nested_message": "Error with api_key=sk-ant-12345678901234567890",
            },
            "item_list": [
                {"token": "secret_in_list_12345"},
                "Normal string with Bearer eyJhbGciOi1234567890",
            ],
        }

        sanitized = sanitize_details(details)

        self.assertEqual(sanitized["api_key"], "[REDACTED]")
        self.assertEqual(sanitized["password"], "[REDACTED]")
        self.assertTrue(sanitized["raw_source"].startswith("[EXCLUDED:"))
        self.assertEqual(sanitized["source_bytes"], "[EXCLUDED: 5 bytes]")
        self.assertEqual(sanitized["safe_param"], "literary")

        # Nested dict
        self.assertEqual(sanitized["nested"]["secret_token"], "[REDACTED]")
        self.assertNotIn("sk-ant-12345678901234567890", sanitized["nested"]["nested_message"])
        self.assertIn("[REDACTED]", sanitized["nested"]["nested_message"])

        # Nested list
        self.assertEqual(sanitized["item_list"][0]["token"], "[REDACTED]")
        self.assertIn("Bearer [REDACTED]", sanitized["item_list"][1])

    def test_automatic_sanitization_in_error_constructor(self) -> None:
        """TarjomanError automatically sanitizes message and details on instantiation."""
        err = ConfigurationError(
            "Failed authentication with sk-proj-1234567890abcdef1234567890",
            details={
                "api_key": "sk-proj-1234567890abcdef1234567890",
                "raw_source": "Sensitive user input manuscript",
            },
        )

        self.assertNotIn("sk-proj-1234567890abcdef1234567890", err.message)
        self.assertNotIn("sk-proj-1234567890abcdef1234567890", str(err))
        self.assertIn("[REDACTED]", err.message)

        self.assertEqual(err.details["api_key"], "[REDACTED]")
        self.assertTrue(err.details["raw_source"].startswith("[EXCLUDED:"))

    def test_safe_messages_not_over_redacted(self) -> None:
        """Legitimate error messages must not be falsely redacted."""
        safe_msgs = [
            "Configuration file 'tarjoman.toml' is missing required section 'domain'",
            "Token limit 4096 exceeded for prompt context",
            "Key 'model_id' is required for provider execution",
            "Secret sharing is disabled in policy profile",
            "Segment locator 'seg:001' not found in workspace",
        ]
        for msg in safe_msgs:
            with self.subTest(msg=msg):
                self.assertEqual(sanitize_error_message(msg), msg)


class TestSerializationAndRehydration(unittest.TestCase):
    """Test to_dict, to_json, and from_dict round-trip reconstruction."""

    class SampleEnum(Enum):
        TEST_VAL = "test_val"

    def test_to_dict_keys_and_values(self) -> None:
        """to_dict produces all required keys with typed values."""
        err = ProviderRateLimitError(
            "Rate limit exceeded",
            details={"provider": "gemini", "status_code": 429},
        )
        d = err.to_dict()

        self.assertEqual(d["code"], "PROVIDER_RATE_LIMIT_ERROR")
        self.assertEqual(d["message"], "Rate limit exceeded")
        self.assertTrue(d["retryable"])
        self.assertEqual(d["exit_code"], 12)
        self.assertEqual(d["user_action"], "wait/backoff")
        self.assertEqual(d["details"], {"provider": "gemini", "status_code": 429})

    def test_to_json_valid_json(self) -> None:
        """to_json produces parseable JSON string."""
        err = CapabilityUnavailableError(
            "Typst PDF compiler not found",
            details={"path": Path("/usr/local/bin/typst"), "enum": self.SampleEnum.TEST_VAL},
        )
        json_str = err.to_json()
        parsed = json.loads(json_str)

        self.assertEqual(parsed["code"], "CAPABILITY_UNAVAILABLE_ERROR")
        self.assertFalse(parsed["retryable"])
        self.assertEqual(parsed["exit_code"], 5)
        self.assertEqual(parsed["details"]["path"], "/usr/local/bin/typst")
        self.assertEqual(parsed["details"]["enum"], "test_val")

    def test_from_dict_reconstructs_exact_subclass(self) -> None:
        """from_dict reconstructs the exact typed subclass matching the code."""
        for cls in TestErrorContractAndAttributes.EXPECTED_SPECS:
            with self.subTest(cls=cls.__name__):
                original = cls("Test message", details={"key": "val"})
                serialized = original.to_dict()

                reconstructed = from_dict(serialized)
                self.assertIsInstance(reconstructed, cls)
                self.assertEqual(reconstructed.code, original.code)
                self.assertEqual(reconstructed.message, original.message)
                self.assertEqual(reconstructed.retryable, original.retryable)
                self.assertEqual(reconstructed.exit_code, original.exit_code)
                self.assertEqual(reconstructed.user_action, original.user_action)
                self.assertEqual(reconstructed.details, original.details)

    def test_from_dict_unknown_code_fallback(self) -> None:
        """from_dict falls back to TarjomanError when code is unrecognized."""
        data = {
            "code": "UNKNOWN_FUTURE_ERROR",
            "message": "Future error occurred",
            "retryable": True,
            "exit_code": 88,
            "details": {"future": True},
        }
        reconstructed = from_dict(data)
        self.assertIsInstance(reconstructed, TarjomanError)
        self.assertEqual(reconstructed.code, "UNKNOWN_FUTURE_ERROR")
        self.assertTrue(reconstructed.retryable)
        self.assertEqual(reconstructed.exit_code, 88)


class TestRegistriesAndExports(unittest.TestCase):
    """Test ALL_ERRORS registry, ERROR_BY_CODE, and module exports."""

    def test_all_errors_tuple_contents(self) -> None:
        """ALL_ERRORS must contain all 12 public errors plus TarjomanError (13 total)."""
        self.assertEqual(len(ALL_ERRORS), 13)
        self.assertIn(TarjomanError, ALL_ERRORS)
        for cls in TestErrorContractAndAttributes.EXPECTED_SPECS:
            self.assertIn(cls, ALL_ERRORS)

    def test_error_by_code_lookup(self) -> None:
        """ERROR_BY_CODE maps every stable machine code to its class."""
        self.assertEqual(len(ERROR_BY_CODE), 13)
        for cls in ALL_ERRORS:
            self.assertEqual(ERROR_BY_CODE[cls.code], cls)

    def test_get_error_class_by_code_case_insensitive(self) -> None:
        """get_error_class_by_code handles case and whitespace cleanly."""
        self.assertEqual(
            get_error_class_by_code("configuration_error"), ConfigurationError
        )
        self.assertEqual(
            get_error_class_by_code("  PROVIDER_RATE_LIMIT_ERROR  "),
            ProviderRateLimitError,
        )
        self.assertIsNone(get_error_class_by_code("NONEXISTENT_ERROR"))

    def test_re_exports_from_core_package(self) -> None:
        """All error classes and helpers must be directly importable from tarjoman.core."""
        expected_exports = [
            "TarjomanError",
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
            "ALL_ERRORS",
            "ERROR_BY_CODE",
            "get_error_class_by_code",
            "from_dict",
            "sanitize_error_message",
            "sanitize_details",
            "get_exit_code",
            "get_http_status",
            "get_mcp_error",
        ]
        for name in expected_exports:
            with self.subTest(symbol=name):
                self.assertTrue(
                    hasattr(core_pkg, name),
                    f"tarjoman.core must export {name}",
                )
                self.assertIn(name, core_pkg.__all__)


if __name__ == "__main__":
    unittest.main()
