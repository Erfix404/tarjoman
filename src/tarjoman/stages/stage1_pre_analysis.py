"""
Stage 1: Pre-Analysis and Token Protection Stage for Tarjoman Universal Translation Engine.

Masks:
- Fenced code blocks (```...```)
- LaTeX display math ($$...$$)
- Inline code (`...`)
- LaTeX inline math ($...$)
- URLs (http://... / https://...)
- Email addresses

Tokens are replaced with ⟦PROTECTED_n⟧ sentinels.
Maps are stored in segment.metadata["protected_tokens"] = {token: original_content}.
Splits multi-paragraph source text into distinct TextSegments.
Provides restore_tokens helper method.
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from tarjoman.core.contracts import DomainProfile, StageResult, TextSegment
from tarjoman.stages.base import BaseStage


class PreAnalysisStage(BaseStage):
    """
    Stage 1: Masks sensitive elements (code, math, links, emails) and splits text into segments.
    """

    TOKEN_PATTERN = re.compile(r"⟦PROTECTED_\d+⟧")

    # Ordered list of protection patterns
    PROTECTION_PATTERNS: List[Tuple[str, re.Pattern]] = [
        # 1. Fenced code blocks with optional language identifier
        ("fenced_code", re.compile(r"```[\s\S]*?```")),
        # 2. LaTeX display math ($$...$$)
        ("display_math", re.compile(r"\$\$[\s\S]*?\$\$")),
        # 3. Inline code (`...`)
        ("inline_code", re.compile(r"`[^`\n]+`")),
        # 4. LaTeX inline math ($...$) - not preceded or followed by other dollar signs or digits, avoiding currency like $50
        ("inline_math", re.compile(r"(?<![\$\\\w])\$(?![\$\d\s])([^\$\n]+?)(?<![\\\s])\$")),
        # 5. URLs (avoiding trailing punctuation)
        ("url", re.compile(r"https?://[^\s<>\"'()]+(?<![.,;:!?])")),
        # 6. Email addresses
        ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ]

    def __init__(self, split_paragraphs: bool = True) -> None:
        self.split_paragraphs = split_paragraphs

    def mask_text(self, text: str, start_index: int = 0) -> Tuple[str, Dict[str, str]]:
        """
        Mask all protected patterns in the input text with ⟦PROTECTED_n⟧.
        Returns: (masked_text, token_map)
        """
        if not text:
            return text, {}

        token_map: Dict[str, str] = {}
        counter = start_index
        masked_text = text

        for _name, pattern in self.PROTECTION_PATTERNS:
            def _repl(match: re.Match) -> str:
                nonlocal counter
                token = f"⟦PROTECTED_{counter}⟧"
                counter += 1
                token_map[token] = match.group(0)
                return token

            masked_text = pattern.sub(_repl, masked_text)

        return masked_text, token_map

    @classmethod
    def restore_tokens(cls, text: str, token_map: Dict[str, str]) -> str:
        """
        Restore masked tokens back to their original content.
        """
        if not text or not token_map:
            return text

        def _replace(match: re.Match) -> str:
            token = match.group(0)
            return token_map.get(token, token)

        # Standard token restoration via regex
        restored = cls.TOKEN_PATTERN.sub(_replace, text)

        # Fallback for any custom tokens not matching TOKEN_PATTERN
        for token, original in sorted(token_map.items(), key=lambda x: len(x[0]), reverse=True):
            if token in restored:
                restored = restored.replace(token, original)

        return restored

    def process(self, segments: List[TextSegment], profile: DomainProfile) -> StageResult:
        """
        Process incoming segments:
        - Mask protected elements in each segment's source_text
        - Store protected tokens mapping in segment.metadata["protected_tokens"]
        - Split multi-paragraph segments if split_paragraphs is True
        """
        output_segments: List[TextSegment] = []
        global_token_index = 0

        for seg in segments:
            if seg.is_protected:
                output_segments.append(seg.model_copy())
                continue

            masked_text, token_map = self.mask_text(seg.source_text, start_index=global_token_index)
            global_token_index += len(token_map)

            if self.split_paragraphs and ("\n\n" in masked_text or "\r\n\r\n" in masked_text):
                paragraphs = [p.strip() for p in re.split(r"(?:\r?\n\s*){2,}", masked_text) if p.strip()]
            else:
                paragraphs = [masked_text.strip()] if masked_text.strip() else [masked_text]

            if len(paragraphs) <= 1:
                seg_copy = seg.model_copy()
                seg_copy.source_text = paragraphs[0] if paragraphs else ""
                seg_copy.metadata = {
                    **seg.metadata,
                    "protected_tokens": token_map,
                }
                output_segments.append(seg_copy)
            else:
                for p in paragraphs:
                    # Filter only tokens present in this paragraph
                    p_tokens = {tok: orig for tok, orig in token_map.items() if tok in p}
                    new_seg = TextSegment(
                        id=len(output_segments) + 1,
                        source_text=p,
                        metadata={
                            **seg.metadata,
                            "protected_tokens": p_tokens,
                            "parent_segment_id": seg.id,
                        },
                    )
                    output_segments.append(new_seg)

        # Ensure sequential segment IDs
        for i, s in enumerate(output_segments, start=1):
            s.id = i

        return StageResult(
            stage_name="stage1_pre_analysis",
            success=True,
            segments=output_segments,
            metadata={"domain": profile.id.value, "total_segments": len(output_segments)},
        )
