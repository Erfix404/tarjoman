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
]
