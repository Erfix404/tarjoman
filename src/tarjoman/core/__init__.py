"""
Tarjoman Core Module - Data Contracts and Interfaces.
"""

from tarjoman.core.contracts import (
    DomainType,
    EmDashPolicy,
    TypographicRules,
    DomainProfile,
    TextSegment,
    StageResult,
    AuditFinding,
    AuditReport,
    BookManifest,
)

__all__ = [
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
]


def __getattr__(name: str):
    if name == "TranslationPipeline":
        from tarjoman.core.pipeline import TranslationPipeline
        return TranslationPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
