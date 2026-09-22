"""
Tarjoman Quality Package — Architecture Zero §8, §19 (D09), §22.2.

Deterministic Persian normalization (safe, idempotent auto-fix layer)
and non-destructive diagnostic calque detection (typed findings).
"""
from __future__ import annotations

from tarjoman.quality.calque_detector import (
    CalqueDetector,
    QualityFinding,
    detect_calques,
)
from tarjoman.quality.conformance import (
    ALL_RULES,
    CANONICAL_JOB_STATES,
    HEAVY_TOP_LEVEL_MODULES,
    RULE_CORE_ISOLATION,
    RULE_DATABASE_INVARIANTS,
    RULE_INTERFACE_ISOLATION,
    RULE_LAYER_DIRECTION,
    RULE_NO_HEAVY_BASE_IMPORTS,
    RULE_SECRET_REDACTION,
    ArchitectureConformanceChecker,
    ArchitectureViolation,
    ArchitectureViolationError,
    format_report,
)
from tarjoman.quality.normalizer import (
    PersianNormalizer,
    normalize_persian,
)

__all__ = [
    "PersianNormalizer",
    "normalize_persian",
    "CalqueDetector",
    "detect_calques",
    "QualityFinding",
    "ArchitectureConformanceChecker",
    "ArchitectureViolation",
    "ArchitectureViolationError",
    "format_report",
    "ALL_RULES",
    "CANONICAL_JOB_STATES",
    "HEAVY_TOP_LEVEL_MODULES",
    "RULE_CORE_ISOLATION",
    "RULE_INTERFACE_ISOLATION",
    "RULE_NO_HEAVY_BASE_IMPORTS",
    "RULE_DATABASE_INVARIANTS",
    "RULE_SECRET_REDACTION",
    "RULE_LAYER_DIRECTION",
]
