"""
Stage 2: Semantic Draft Stage for Tarjoman Universal Translation Engine.

Provides:
- TranslationBackend (ABC): Base contract for LLM or rule-based backends.
- CallableTranslationBackend: Wraps an arbitrary callable (prompt, system_prompt) -> str.
- EchoDraftBackend: Deterministic backend for testing and offline runs.
- SemanticDraftStage: Translates source text into translated_text for each segment.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, List, Optional

from tarjoman.core.contracts import DomainProfile, StageResult, TextSegment
from tarjoman.stages.base import BaseStage


class TranslationBackend(ABC):
    """
    Abstract base class for all translation backends (LLM, API, or local engine).
    """

    @abstractmethod
    def translate(self, prompt: str, system_prompt: str) -> str:
        """
        Translate the given prompt/source text using the domain system prompt.
        """
        pass


class CallableTranslationBackend(TranslationBackend):
    """
    Wraps a custom callable (prompt: str, system_prompt: str) -> str.
    """

    def __init__(self, fn: Callable[[str, str], str]) -> None:
        self.fn = fn

    def translate(self, prompt: str, system_prompt: str) -> str:
        return self.fn(prompt, system_prompt)


class EchoDraftBackend(TranslationBackend):
    """
    Deterministic backend for dry runs, testing, and baseline pipelines.
    Optionally prepends a prefix or echoes the prompt as-is.
    """

    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix

    def translate(self, prompt: str, system_prompt: str) -> str:
        if self.prefix:
            return f"{self.prefix}{prompt}"
        return prompt


class SemanticDraftStage(BaseStage):
    """
    Stage 2: Generates initial semantic draft translations using a TranslationBackend.
    """

    def __init__(self, backend: Optional[TranslationBackend] = None) -> None:
        self.backend = backend or EchoDraftBackend()

    def process(self, segments: List[TextSegment], profile: DomainProfile) -> StageResult:
        """
        Translate each non-protected segment's source_text using the backend,
        populating segment.translated_text.
        """
        processed_segments: List[TextSegment] = []

        for seg in segments:
            seg_copy = seg.model_copy()
            if seg.is_protected:
                seg_copy.translated_text = seg.source_text
            else:
                seg_copy.translated_text = self.backend.translate(
                    prompt=seg.source_text,
                    system_prompt=profile.system_prompt,
                )
            processed_segments.append(seg_copy)

        return StageResult(
            stage_name="stage2_draft",
            success=True,
            segments=processed_segments,
            metadata={
                "domain": profile.id.value,
                "backend": self.backend.__class__.__name__,
            },
        )
