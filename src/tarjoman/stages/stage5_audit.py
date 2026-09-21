"""
Stage 5: Quality Audit Stage for Tarjoman Universal Translation Engine.

Analyzes polished segments against source segments across 4 core dimensions:
1. Missing numbers/digits from source (MQM-NUM-OMISSION)
2. Unbalanced Persian quotation marks « vs » (MQM-PUNCT-QUOTES)
3. Banned calques remaining in text (MQM-CALQUE-BANNED)
4. Protected tokens intact (MQM-PROTECTED-TOKEN-LOST)

Computes MQM penalty score, calculates quality_score (0.0 - 100.0), and generates AuditReport.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from tarjoman.core.contracts import (
    AuditFinding,
    AuditReport,
    DomainProfile,
    StageResult,
    TextSegment,
)
from tarjoman.stages.base import BaseStage
from tarjoman.stages.stage1_pre_analysis import PreAnalysisStage

PERSIAN_TO_ENGLISH_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫", "01234567890123456789.")

SEVERITY_WEIGHTS: Dict[str, float] = {
    "critical": 10.0,
    "major": 5.0,
    "minor": 1.0,
}


class AuditStage(BaseStage):
    """
    Stage 5: Audits translations against source segments, generating an MQM-based AuditReport.
    """

    def __init__(
        self,
        pass_threshold: float = 80.0,
        restore_tokens: bool = False,
    ) -> None:
        self.pass_threshold = pass_threshold
        self.restore_tokens = restore_tokens

    def audit(self, segments: List[TextSegment], profile: DomainProfile) -> AuditReport:
        """
        Audit polished segments against source text and domain profile constraints.
        """
        findings: List[AuditFinding] = []
        omission_count = 0
        banned_calque_count = 0

        for seg in segments:
            if seg.is_protected:
                continue

            target_text = (
                seg.polished_text
                if seg.polished_text is not None
                else (seg.translated_text or "")
            )
            protected_tokens = seg.metadata.get("protected_tokens", {})

            # 1. Protected tokens intact check
            for token, original in protected_tokens.items():
                if token not in target_text and original not in target_text:
                    findings.append(
                        AuditFinding(
                            rule_id="MQM-PROTECTED-TOKEN-LOST",
                            severity="critical",
                            segment_id=seg.id,
                            message=f"Protected token '{token}' ({original[:30]}) is missing or altered",
                            excerpt=token,
                        )
                    )
                    omission_count += 1

            # 2. Missing numbers/digits from source
            clean_source = re.sub(r"⟦PROTECTED_\d+⟧", " ", seg.source_text)
            source_numbers = re.findall(r"\b\d+(?:\.\d+)?\b", clean_source)

            # Build text for number inspection (with tokens restored to avoid false omissions)
            inspected_target = PreAnalysisStage.restore_tokens(target_text, protected_tokens)
            normalized_target = inspected_target.translate(PERSIAN_TO_ENGLISH_DIGITS)

            for num in set(source_numbers):
                pattern = rf"(?<!\d){re.escape(num)}(?!\d)"
                if not re.search(pattern, normalized_target):
                    findings.append(
                        AuditFinding(
                            rule_id="MQM-NUM-OMISSION",
                            severity="critical",
                            segment_id=seg.id,
                            message=f"Source number '{num}' is missing in translation",
                            excerpt=num,
                        )
                    )
                    omission_count += 1

            # 3. Unbalanced Persian quotation marks « vs »
            count_open = target_text.count("«")
            count_close = target_text.count("»")
            if count_open != count_close:
                findings.append(
                    AuditFinding(
                        rule_id="MQM-PUNCT-QUOTES",
                        severity="major",
                        segment_id=seg.id,
                        message=f"Unbalanced Persian quotation marks: {count_open} opening « vs {count_close} closing »",
                        excerpt=target_text[:80],
                    )
                )

            # 4. Banned calques remaining in text
            if profile.banned_calques:
                for calque in profile.banned_calques:
                    if calque in target_text:
                        findings.append(
                            AuditFinding(
                                rule_id="MQM-CALQUE-BANNED",
                                severity="major",
                                segment_id=seg.id,
                                message=f"Banned calque found in translation: '{calque}'",
                                excerpt=calque,
                            )
                        )
                        banned_calque_count += 1

        # Compute penalties and quality score
        total_penalty = sum(SEVERITY_WEIGHTS.get(f.severity, 1.0) for f in findings)
        quality_score = max(0.0, min(100.0, round(100.0 - total_penalty, 2)))
        has_critical = any(f.severity == "critical" for f in findings)
        passed = (quality_score >= self.pass_threshold) and not has_critical

        return AuditReport(
            passed=passed,
            quality_score=quality_score,
            omission_count=omission_count,
            banned_calque_count=banned_calque_count,
            findings=findings,
        )

    def process(self, segments: List[TextSegment], profile: DomainProfile) -> StageResult:
        """
        Run audit and optionally restore tokens on polished_text.
        """
        report = self.audit(segments, profile)
        output_segments: List[TextSegment] = []

        for seg in segments:
            seg_copy = seg.model_copy()
            if self.restore_tokens and seg_copy.metadata.get("protected_tokens"):
                tokens = seg_copy.metadata["protected_tokens"]
                if seg_copy.polished_text:
                    seg_copy.polished_text = PreAnalysisStage.restore_tokens(
                        seg_copy.polished_text, tokens
                    )
                if seg_copy.translated_text:
                    seg_copy.translated_text = PreAnalysisStage.restore_tokens(
                        seg_copy.translated_text, tokens
                    )
            output_segments.append(seg_copy)

        return StageResult(
            stage_name="stage5_audit",
            success=report.passed,
            segments=output_segments,
            metadata={
                "domain": profile.id.value,
                "quality_score": report.quality_score,
                "omission_count": report.omission_count,
                "banned_calque_count": report.banned_calque_count,
                "findings_count": len(report.findings),
            },
            warnings=[f"[{f.severity.upper()}] {f.message}" for f in report.findings],
        )
