"""
Stage 3: Reflection & Human-Emulation Critique Stage for Tarjoman Universal Translation Engine.

Inspects segment.translated_text against segment.source_text along 4 MQM axes:
1. Accuracy: Omissions, missing numbers, corrupted protected tokens, untranslated English fragments.
2. Fluency: Grammar, syntax, and banned calques.
3. Style: Register consistency, un-inverted dialogue tags, em-dash policies.
4. Terminology: Domain-specific terminology adherence.

Updates segment.reflection_critique and refines segment.translated_text.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Tuple

from tarjoman.core.contracts import (
    DomainProfile,
    EmDashPolicy,
    StageResult,
    TextSegment,
)
from tarjoman.stages.anti_calque import AntiCalqueEngine
from tarjoman.stages.base import BaseStage
from tarjoman.stages.stage4_polish import StylisticPolishStage

PERSIAN_TO_ENGLISH_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫", "01234567890123456789.")


class ReflectionEngine(ABC):
    """
    Abstract interface for pluggable reflection critique and refinement engines.
    """

    @abstractmethod
    def reflect(
        self,
        source: str,
        draft: str,
        profile: DomainProfile,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
        """
        Evaluate draft against source text along 4 MQM axes.
        Returns: (critique_text, refined_draft)
        """
        pass


class CallableReflectionEngine(ReflectionEngine):
    """
    Reflection engine wrapping a custom callable (source, draft, profile, metadata) -> (critique, refined).
    """

    def __init__(self, fn: Callable[..., Tuple[str, str]]) -> None:
        self.fn = fn

    def reflect(
        self,
        source: str,
        draft: str,
        profile: DomainProfile,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
        return self.fn(source, draft, profile, metadata or {})


class RuleBasedReflectionEngine(ReflectionEngine):
    """
    Deterministic rule-based reflection engine evaluating draft quality along 4 MQM axes.
    """

    def reflect(
        self,
        source: str,
        draft: str,
        profile: DomainProfile,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
        critiques: List[str] = []
        refined = draft
        meta = metadata or {}
        protected_tokens = meta.get("protected_tokens", {})

        # Axis 1: Accuracy
        # 1.1 Missing numbers
        clean_source = re.sub(r"⟦PROTECTED_\d+⟧", " ", source)
        source_numbers = re.findall(r"\b\d+(?:\.\d+)?\b", clean_source)
        clean_draft = re.sub(r"⟦PROTECTED_\d+⟧", " ", draft)
        draft_eng_digits = clean_draft.translate(PERSIAN_TO_ENGLISH_DIGITS)
        missing_numbers = [num for num in set(source_numbers) if num not in draft_eng_digits]
        if missing_numbers:
            critiques.append(f"[Accuracy] Missing number(s) from source: {', '.join(sorted(missing_numbers))}")

        # 1.2 Protected tokens integrity
        missing_tokens = [tok for tok in protected_tokens if tok not in draft]
        if missing_tokens:
            critiques.append(f"[Accuracy] Protected token(s) missing or altered: {', '.join(missing_tokens)}")

        # 1.3 Untranslated English text (words of 4+ characters, outside protected tokens)
        ascii_words = re.findall(r"\b[A-Za-z]{4,}\b", clean_draft)
        if ascii_words and not profile.typography.isolate_english_terms:
            known_terms = {k.lower() for k in profile.terminology_map.keys()}
            untranslated = [w for w in ascii_words if w.lower() not in known_terms]
            if untranslated:
                critiques.append(f"[Accuracy] Potential untranslated English fragments: {', '.join(untranslated[:5])}")

        # Axis 2: Fluency
        # 2.1 Banned calques
        found_calques: List[str] = []
        for calque in profile.banned_calques:
            if calque in draft:
                found_calques.append(calque)
        if found_calques:
            critiques.append(f"[Fluency] Banned calque(s) detected: {', '.join(found_calques)}")

        # Axis 3: Style
        # 3.1 Dialogue tag inversion check
        if profile.typography.invert_dialogue_tags:
            match = StylisticPolishStage._DIALOGUE_TAG_PATTERN.search(draft)
            if match:
                critiques.append(f"[Style] Un-inverted dialogue speech verb: '{match.group(0).strip()}'")

        # 3.2 Em-dash policy check
        if profile.typography.em_dash_policy == EmDashPolicy.ERADICATE:
            if re.search(r"—|–|--", draft):
                critiques.append("[Style] Em-dash/en-dash found under ERADICATE policy")

        # Axis 4: Terminology
        if profile.terminology_map:
            for en_term, fa_term in profile.terminology_map.items():
                pattern = rf"\b{re.escape(en_term)}\b"
                if re.search(pattern, source, re.IGNORECASE):
                    if fa_term not in draft:
                        critiques.append(f"[Terminology] Expected translation '{fa_term}' for '{en_term}' was not found")

        # Apply deterministic refinements
        # Refinement A: Substitute known English terms with domain terminology
        if profile.terminology_map:
            for en_term, fa_term in profile.terminology_map.items():
                if re.search(rf"\b{re.escape(en_term)}\b", refined, re.IGNORECASE):
                    refined = re.sub(rf"\b{re.escape(en_term)}\b", fa_term, refined, flags=re.IGNORECASE)

        # Refinement B: Dialogue tag inversion if required
        if profile.typography.invert_dialogue_tags:
            refined = StylisticPolishStage.invert_dialogue_tags(refined)

        # Refinement C: Anti-calque elimination
        refined = AntiCalqueEngine.eliminate_calques(refined)

        # Format critique report
        if critiques:
            critique_report = "MQM Reflection Critique:\n" + "\n".join(f"- {c}" for c in critiques)
        else:
            critique_report = "Critique passed: No defects detected across Accuracy, Fluency, Style, Terminology."

        return critique_report, refined


class ReflectionStage(BaseStage):
    """
    Stage 3: Pluggable reflection critique and refinement stage.
    """

    def __init__(self, engine: Optional[ReflectionEngine] = None) -> None:
        self.engine = engine or RuleBasedReflectionEngine()

    def process(self, segments: List[TextSegment], profile: DomainProfile) -> StageResult:
        """
        Process each segment, generate reflection critique, and refine translated_text.
        """
        processed_segments: List[TextSegment] = []

        for seg in segments:
            seg_copy = seg.model_copy()
            if seg.is_protected:
                seg_copy.reflection_critique = "Protected segment - skipped reflection."
                processed_segments.append(seg_copy)
                continue

            critique, refined = self.engine.reflect(
                source=seg.source_text,
                draft=seg.translated_text or seg.source_text,
                profile=profile,
                metadata=seg.metadata,
            )
            seg_copy.reflection_critique = critique
            seg_copy.translated_text = refined
            processed_segments.append(seg_copy)

        return StageResult(
            stage_name="stage3_reflection",
            success=True,
            segments=processed_segments,
            metadata={
                "domain": profile.id.value,
                "engine": self.engine.__class__.__name__,
            },
        )
