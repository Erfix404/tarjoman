"""
Tarjoman Core Module - Data Contracts, Interfaces, Error Taxonomy, and Configuration.
"""

from tarjoman.core.config import (
    KNOWN_CONFIG_FIELDS,
    ConfigLoader,
    TarjomanConfig,
    dump_toml,
    find_secrets_in_dict,
    get_default_user_config_path,
    load_config,
    parse_env_vars,
)
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
    # Configuration System (§23, FND-004)
    "TarjomanConfig",
    "ConfigLoader",
    "load_config",
    "dump_toml",
    "parse_env_vars",
    "find_secrets_in_dict",
    "get_default_user_config_path",
    "KNOWN_CONFIG_FIELDS",
]


def __getattr__(name: str):
    if name == "TranslationPipeline":
        from tarjoman.core.pipeline import TranslationPipeline
        return TranslationPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
