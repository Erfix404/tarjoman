"""Alias module: `tarjoman.stages.draft` re-exports Stage 2 draft symbols."""
from tarjoman.stages.stage2_draft import (
    STRUCTURAL_GRAMMAR_PROMPT,
    CallableTranslationBackend,
    EchoDraftBackend,
    NeutralLinguisticFraming,
    SemanticDraftStage,
    TranslationBackend,
    sanitize_for_neutral_framing,
)

__all__ = [
    "STRUCTURAL_GRAMMAR_PROMPT",
    "TranslationBackend",
    "CallableTranslationBackend",
    "EchoDraftBackend",
    "NeutralLinguisticFraming",
    "sanitize_for_neutral_framing",
    "SemanticDraftStage",
]
