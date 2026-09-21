"""
5-Pass Human-Emulation Reflection Pipeline for Tarjoman Universal Translation Engine.

Wires the complete 5-stage translation workflow:
Pass 1: PreAnalysisStage - Sensitive element masking (code, math, links, emails)
Pass 2: SemanticDraftStage - Initial semantic draft translation
Pass 3: ReflectionStage - 4-axis MQM critique and refinement
Pass 4: StylisticPolishStage - Persian typography, dialogue tag inversion, anti-calque
Pass 5: AuditStage - Quality checks (numbers, quotes, calques, token integrity)

Restores protected tokens ensuring formulas, code, links, and numbers survive intact.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from tarjoman.core.contracts import AuditReport, DomainProfile, TextSegment
from tarjoman.stages.stage1_pre_analysis import PreAnalysisStage
from tarjoman.stages.stage2_draft import SemanticDraftStage, TranslationBackend
from tarjoman.stages.stage3_reflection import ReflectionStage
from tarjoman.stages.stage4_polish import StylisticPolishStage
from tarjoman.stages.stage5_audit import AuditStage


class TranslationPipeline:
    """
    Orchestrates the 5-pass human-emulation reflection pipeline.
    """

    def __init__(
        self,
        stage1: Optional[PreAnalysisStage] = None,
        stage2: Optional[SemanticDraftStage] = None,
        stage3: Optional[ReflectionStage] = None,
        stage4: Optional[StylisticPolishStage] = None,
        stage5: Optional[AuditStage] = None,
        backend: Optional[TranslationBackend] = None,
    ) -> None:
        self.stage1 = stage1 or PreAnalysisStage()
        self.stage2 = stage2 or SemanticDraftStage(backend=backend)
        self.stage3 = stage3 or ReflectionStage()
        self.stage4 = stage4 or StylisticPolishStage()
        self.stage5 = stage5 or AuditStage()

    def run(
        self,
        raw_text: str,
        profile: DomainProfile,
    ) -> Tuple[List[TextSegment], AuditReport]:
        """
        Execute the 5-pass translation pipeline on raw source text.
        Returns: (final_segments, audit_report)
        """
        # Pass 1: Pre-Analysis (Token Masking and Paragraph Splitting)
        initial_segment = TextSegment(id=1, source_text=raw_text)
        s1_result = self.stage1.process([initial_segment], profile)
        segments = s1_result.segments

        # Pass 2: Semantic Initial Drafting
        s2_result = self.stage2.process(segments, profile)
        segments = s2_result.segments

        # Pass 3: Reflection & Critique
        s3_result = self.stage3.process(segments, profile)
        segments = s3_result.segments

        # Pass 4: Stylistic & Typographic Polish
        s4_result = self.stage4.process(segments, profile)
        segments = s4_result.segments

        # Pass 5: Quality Audit
        audit_report = self.stage5.audit(segments, profile)

        # Restore protected tokens at the end of pipeline
        final_segments: List[TextSegment] = []
        for seg in segments:
            seg_copy = seg.model_copy()
            tokens = seg_copy.metadata.get("protected_tokens", {})
            if tokens:
                if seg_copy.polished_text is not None:
                    seg_copy.polished_text = PreAnalysisStage.restore_tokens(
                        seg_copy.polished_text, tokens
                    )
                if seg_copy.translated_text is not None:
                    seg_copy.translated_text = PreAnalysisStage.restore_tokens(
                        seg_copy.translated_text, tokens
                    )
            final_segments.append(seg_copy)

        return final_segments, audit_report

    def translate_text(self, raw_text: str, profile: DomainProfile) -> str:
        """
        End-to-end convenience method: runs full pipeline and returns polished translated text.
        """
        segments, _ = self.run(raw_text, profile)
        return "\n\n".join(seg.polished_text or "" for seg in segments)
