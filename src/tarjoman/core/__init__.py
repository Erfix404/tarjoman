"""
Tarjoman Core Module - Data Contracts, Interfaces, and Error Taxonomy.
"""

from tarjoman.core.contracts import (
    AuditFinding,
    AuditReport,
    BookManifest,
    DomainProfile,
    DomainType,
    EmDashPolicy,
    StageResult,
    TextSegment,
    TypographicRules,
)
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

__all__ = [
    # Contracts
    "DomainType",
    "EmDashPolicy",
    "TypographicRules",
    "DomainProfile",
    "TextSegment",
    "StageResult",
    "AuditFinding",
    "AuditReport",
    "BookManifest",
    "TranslationPipeline",
    # Error Taxonomy (§24)
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


def __getattr__(name: str):
    if name == "TranslationPipeline":
        from tarjoman.core.pipeline import TranslationPipeline
        return TranslationPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
