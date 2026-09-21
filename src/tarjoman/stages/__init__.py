"""
Translation and processing stages for Tarjoman Universal Translation Engine.
"""
from tarjoman.stages.anti_calque import AntiCalqueEngine
from tarjoman.stages.base import BaseStage
from tarjoman.stages.stage1_pre_analysis import PreAnalysisStage
from tarjoman.stages.stage2_draft import (
    CallableTranslationBackend,
    EchoDraftBackend,
    SemanticDraftStage,
    TranslationBackend,
)
from tarjoman.stages.stage3_reflection import (
    CallableReflectionEngine,
    ReflectionEngine,
    ReflectionStage,
    RuleBasedReflectionEngine,
)
from tarjoman.stages.stage4_polish import StylisticPolishStage
from tarjoman.stages.stage5_audit import AuditStage

__all__ = [
    "BaseStage",
    "PreAnalysisStage",
    "TranslationBackend",
    "CallableTranslationBackend",
    "EchoDraftBackend",
    "SemanticDraftStage",
    "ReflectionEngine",
    "CallableReflectionEngine",
    "RuleBasedReflectionEngine",
    "ReflectionStage",
    "AntiCalqueEngine",
    "StylisticPolishStage",
    "AuditStage",
]
