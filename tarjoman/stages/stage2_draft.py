"""
Stage 2: Semantic Draft Stage for Tarjoman Universal Translation Engine.

Provides:
- TranslationBackend (ABC): Base contract for LLM or rule-based backends.
- CallableTranslationBackend: Wraps an arbitrary callable (prompt, system_prompt) -> str.
- EchoDraftBackend: Deterministic backend for testing and offline runs.
- NeutralLinguisticFraming / sanitize_for_neutral_framing: strips commercial
  book metadata (titles, publisher boilerplate, copyright, ISBNs) and wraps
  prompts as neutral linguistic-analysis chunks.
- SemanticDraftStage: Translates source text into translated_text for each segment.
"""
from __future__ import annotations

import re
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


ISBN_PATTERN = (
    r"(?:ISBN(?:-1[03])?:?\s*)?(?=[0-9X]{10}|(?=(?:[0-9]+[-\s]){3})[-\s0-9X]{13}|"
    r"97[89][0-9]{10}|(?=(?:[0-9]+[-\s]){4})[-\s0-9]{17})"
    r"(?:97[89][- ]?(?:[0-9][- ]?){9}[0-9]|[0-9][- 0-9X]*[0-9X])"
)

_BOILERPLATE_PATTERNS = (
    r"all rights reserved",
    r"copyright\s*(?:©|\(c\)|\d{4}).*",
    r"published by\s+.*",
    r"penguin books|harpercollins|random house|simon & schuster|macmillan|hachette",
    r"printed in\s+.*",
    r"library of congress.*",
)


class NeutralLinguisticFraming:
    """Strips commercial metadata and wraps text as neutral linguistic chunks."""

    def sanitize(self, text: str) -> str:
        cleaned = re.sub(ISBN_PATTERN, "", text, flags=re.IGNORECASE)
        for pattern in _BOILERPLATE_PATTERNS:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        return re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    def wrap(self, text: str) -> str:
        return (
            "Translate the following linguistic text excerpt accurately "
            f"into standard literary Persian:\n\n{text}"
        )


def sanitize_for_neutral_framing(text: str) -> str:
    """Convenience function applying NeutralLinguisticFraming sanitization."""
    return NeutralLinguisticFraming().sanitize(text)


class SemanticDraftStage(BaseStage):
    """
    Stage 2: Generates initial semantic draft translations using a TranslationBackend.
    """

    def __init__(
        self,
        backend: Optional[TranslationBackend] = None,
        neutral_framing: bool = True,
    ) -> None:
        self.backend = backend or EchoDraftBackend()
        self.neutral_framing = neutral_framing
        self._framing = NeutralLinguisticFraming()

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
                prompt = seg.source_text
                if self.neutral_framing:
                    prompt = self._framing.sanitize(prompt)
                seg_copy.translated_text = self.backend.translate(
                    prompt=prompt,
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
