"""
Stage 4: Stylistic and Typographic Polish Stage for Tarjoman Universal Translation Engine.

Enforces:
- Em-dash policies (ERADICATE, ADAPT, PRESERVE)
- Persian quotation marks («...»)
- Dialogue tag inversion for literary register
- Strict ZWNJ for Persian affixes and clitics
- Arabic character standardization (ي -> ی, ك -> ک)
- Punctuation and spacing hygiene
- Anti-calque transformations
"""
from __future__ import annotations

import re
from typing import List, Optional

from tarjoman.core.contracts import (
    DomainProfile,
    EmDashPolicy,
    StageResult,
    TextSegment,
    TypographicRules,
)
from tarjoman.stages.anti_calque import AntiCalqueEngine
from tarjoman.stages.base import BaseStage


class StylisticPolishStage(BaseStage):
    """
    Stage 4 polisher enforcing typographic rules, stylistic norms, and anti-calque corrections.
    """

    def __init__(self, restore_tokens: bool = False) -> None:
        self.restore_tokens = restore_tokens

    # Persian dialogue speech verbs
    _SPEECH_VERBS = (
        r"(?:گفت|پرسید|پاسخ داد|زمزمه کرد|فریاد زد|غرولند کرد|نالید|داد زد|"
        r"پوزخند زد|با تعجب گفت|ادامه داد|افزود|خندید|تکرار کرد|طعنه زد)(?:ند|م|ی|یم|ید)?"
    )

    _DIALOGUE_TAG_PATTERN = re.compile(
        rf"«([^»\n]+)»\s*([؀-ۿ\s‌]+?)\s*({_SPEECH_VERBS})(?:\.|$)",
        re.UNICODE,
    )

    @classmethod
    def standardize_arabic_chars(cls, text: str) -> str:
        """
        Normalize Arabic kaf and ya to Persian characters.
        """
        return text.replace("ي", "ی").replace("ك", "ک")

    @classmethod
    def apply_em_dash_policy(cls, text: str, policy: EmDashPolicy) -> str:
        """
        Handle em-dashes and en-dashes according to domain typographic policy.
        """
        if policy == EmDashPolicy.PRESERVE:
            return text
        elif policy == EmDashPolicy.ERADICATE:
            # Replace em-dashes, en-dashes, and double hyphens with Persian comma
            return re.sub(r"\s*[—–]\s*|\s*--\s*", "، ", text)
        elif policy == EmDashPolicy.ADAPT:
            # Convert to spaced hyphen
            return re.sub(r"\s*[—–]\s*|\s*--\s*", " - ", text)
        return text

    @classmethod
    def enforce_persian_quotes(cls, text: str) -> str:
        """
        Convert English/ASCII double quotes and curly quotes to Persian quotes «...».
        """
        # ASCII quotes
        text = re.sub(r'"([^"\n]+)"', r"«\1»", text)
        # Curly quotes “...” and ”...“
        text = re.sub(r'["“”]([^"“”\n]+)["“”]', r"«\1»", text)
        # Clean internal space in Persian quotes
        text = re.sub(r"«\s+", "«", text)
        text = re.sub(r"\s+»", "»", text)
        return text

    @classmethod
    def invert_dialogue_tags(cls, text: str) -> str:
        """
        Invert quote-first dialogue tags to subject-first Persian syntax:
        «...» هری گفت. -> هری گفت: «...»
        """
        def _invert(m: re.Match) -> str:
            quote = m.group(1).strip()
            subject = m.group(2).strip()
            verb = m.group(3).strip()

            # If quote ends with a comma from English translation, strip and append period
            if quote.endswith(("،", ",")):
                quote = quote[:-1].strip() + "."
            elif not quote.endswith((".", "!", "؟", "…")):
                quote = quote + "."

            return f"{subject} {verb}: «{quote}»"

        return cls._DIALOGUE_TAG_PATTERN.sub(_invert, text)

    @classmethod
    def enforce_strict_zwnj(cls, text: str) -> str:
        """
        Apply strict Zero-Width Non-Joiner (ZWNJ) rules to Persian affixes:
        - Prefix: می‌, نمی‌
        - Plural suffix: ‌ها, ‌های
        - Comparative suffix: تر, ‌ترین
        - Pronominal clitics: ‌ام, ‌ات, ‌اش, ‌مان, ‌تان, ‌شان
        - Indefinite suffix: ‌ه‌ای
        """
        zwnj = "‌"

        # 1. Verbal prefixes: می‌, نمی‌
        text = re.sub(r"(?<![آ-یء-ي])(ن?می)\s+([آ-یء-ي])", rf"\1{zwnj}\2", text)

        # 2. Plural suffixes: ‌ها, ‌های
        text = re.sub(r"([آ-یء-ي])\s+(های|ها)(?![آ-یء-ي])", rf"\1{zwnj}\2", text)

        # 3. Comparative suffixes: تر, ‌ترین
        text = re.sub(r"([آ-یء-ي])\s+(ترین|تر)(?![آ-یء-ي])", rf"\1{zwnj}\2", text)

        # 4. Pronominal clitics: ‌ام, ‌ات, ‌اش, ‌مان, ‌تان, ‌شان
        text = re.sub(
            r"([آ-یء-ي])\s+(ام|ات|اش|مان|تان|شان)(?![آ-یء-ي])",
            rf"\1{zwnj}\2",
            text,
        )

        # 5. Indefinite suffix: ‌ه‌ای
        text = re.sub(r"([آ-یء-ي]ه)\s+ای(?![آ-یء-ي])", rf"\1{zwnj}ای", text)

        # Clean duplicate ZWNJs
        text = re.sub(rf"{zwnj}{{2,}}", zwnj, text)

        # Clean spacing around ZWNJ
        text = re.sub(rf"\s+{zwnj}|{zwnj}\s+", zwnj, text)

        return text

    @classmethod
    def clean_punctuation_hygiene(cls, text: str) -> str:
        """
        Punctuation hygiene:
        - Remove duplicate commas
        - Remove space before punctuation marks
        - Ensure space after commas and colons
        - Remove duplicate spaces
        """
        # Duplicate commas
        text = re.sub(r"[،,]{2,}", "،", text)

        # Clean space before punctuation
        text = re.sub(r"\s+([،,.:;!؟?])", r"\1", text)

        # Ensure space after Persian comma
        text = re.sub(r"([،,])([^\s\d»«])", r"\1 \2", text)

        # Ensure space after colon (unless within numbers or URLs)
        text = re.sub(r"(:)([^\s\d»/])", r"\1 \2", text)

        # Clean multiple spaces
        text = re.sub(r"[ ]{2,}", " ", text)

        # Clean duplicate periods (excluding ellipsis)
        text = re.sub(r"(?<!\.)\.\.(?!\.)", ".", text)

        # Strip leading comma or trailing unwanted spaces
        text = re.sub(r"^[،\s]+", "", text)

        return text.strip()

    @classmethod
    def polish(cls, text: str, profile: Optional[DomainProfile] = None) -> str:
        """
        Apply complete polishing pipeline to a single text string.
        """
        if not text:
            return text

        typo = profile.typography if profile else TypographicRules()

        # 1. Arabic character standardization (ي -> ی, ك -> ک)
        result = cls.standardize_arabic_chars(text)

        # 2. Strict ZWNJ (normalize verbal prefixes before anti-calque)
        if typo.strict_zwnj:
            result = cls.enforce_strict_zwnj(result)

        # 3. Anti-calque elimination
        result = AntiCalqueEngine.eliminate_calques(result)

        # 4. Em-dash handling
        result = cls.apply_em_dash_policy(result, typo.em_dash_policy)

        # 5. Persian quotes enforcement
        if typo.enforce_persian_quotes:
            result = cls.enforce_persian_quotes(result)

        # 6. Dialogue tag inversion (literary fiction)
        if typo.invert_dialogue_tags:
            result = cls.invert_dialogue_tags(result)

        # 7. Strict ZWNJ
        if typo.strict_zwnj:
            result = cls.enforce_strict_zwnj(result)

        # 8. Punctuation hygiene
        result = cls.clean_punctuation_hygiene(result)

        return result

    def process(self, segments: List[TextSegment], profile: DomainProfile) -> StageResult:
        """
        Process all segments and return StageResult with polished_text populated.
        """
        processed_segments: List[TextSegment] = []
        warnings: List[str] = []

        for seg in segments:
            if seg.is_protected:
                seg_copy = seg.model_copy()
                seg_copy.polished_text = seg.translated_text or seg.source_text
                processed_segments.append(seg_copy)
                continue

            text_to_polish = (
                seg.translated_text
                if seg.translated_text is not None
                else seg.source_text
            )
            polished = self.polish(text_to_polish, profile)

            if self.restore_tokens and seg.metadata.get("protected_tokens"):
                from tarjoman.stages.stage1_pre_analysis import PreAnalysisStage
                polished = PreAnalysisStage.restore_tokens(
                    polished, seg.metadata["protected_tokens"]
                )

            seg_copy = seg.model_copy()
            seg_copy.polished_text = polished
            processed_segments.append(seg_copy)

        return StageResult(
            stage_name="stage4_polish",
            success=True,
            segments=processed_segments,
            metadata={"domain": profile.id.value},
            warnings=warnings,
        )
