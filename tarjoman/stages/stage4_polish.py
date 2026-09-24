"""
Stage 4: Stylistic and Typographic Polish Stage for Tarjoman Universal Translation Engine.

Enforces:
- Guaranteed ZERO em-dash policy (paired dashes -> parentheses, lone -> Persian comma)
- Persian quotation marks («...»)
- Dialogue tag inversion for literary register
- Strict ZWNJ for Persian affixes and clitics
- Arabic character standardization (ي -> ی, ك -> ک)
- Punctuation and spacing hygiene
- Anti-calque transformations (Najafi/Samii, original + v2 rules)

Super-Skill v2: typography and calque handling delegate to
:class:`tarjoman.stages.anti_calque.AntiCalqueEngine` as the single source of
truth; verbatim spans (code, math, URLs, emails) are masked before normalization
so technical content is never corrupted.
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
from tarjoman.stages.anti_calque import (
    LRI,
    PDI,
    AntiCalqueEngine,
    mask_verbatim_spans,
    restore_verbatim_spans,
)
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

    # -------------------------------------------------------------------------
    # Delegating primitives (single source of truth: AntiCalqueEngine)
    # -------------------------------------------------------------------------

    @classmethod
    def standardize_arabic_chars(cls, text: str) -> str:
        """Normalize Arabic kaf and ya to Persian characters."""
        return AntiCalqueEngine.standardize_arabic_chars(text)

    @classmethod
    def apply_em_dash_policy(cls, text: str, policy: EmDashPolicy) -> str:
        """
        Handle em-dashes, en-dashes, and standalone double hyphens.

        - ERADICATE: ZERO em-dash policy — paired dashes become parentheses,
          lone dashes become Persian commas.
        - ADAPT: convert to a spaced hyphen.
        - PRESERVE: keep as-is (explicit opt-in only).
        """
        if policy == EmDashPolicy.PRESERVE:
            return text
        elif policy == EmDashPolicy.ERADICATE:
            return AntiCalqueEngine.eliminate_em_dashes(text)
        elif policy == EmDashPolicy.ADAPT:
            # Convert to spaced hyphen (standalone -- preserved when attached
            # to tokens, e.g. CLI flags).
            text = re.sub(r"\s*[—–]\s*", " - ", text)
            text = re.sub(r"(?<!\S)--(?!\S)", " - ", text)
            return text
        return text

    @classmethod
    def enforce_persian_quotes(cls, text: str) -> str:
        """Convert straight/curly quotes to Persian guillemets «...»."""
        return AntiCalqueEngine.normalize_quotes(text)

    @classmethod
    def enforce_strict_zwnj(cls, text: str) -> str:
        """
        Apply strict Zero-Width Non-Joiner (ZWNJ) rules to Persian affixes:
        - Prefixes: می‌, نمی‌, ب‌, ن‌
        - Plural suffixes: ‌ها, ‌های
        - Comparative suffixes: تر, ‌ترین
        - Pronominal clitics: ‌ام, ‌ات, ‌اش, ‌مان, ‌تان, ‌شان
        - Indefinite suffix: ‌ه‌ای, silent-heh ezafe: ‌ه‌ی
        """
        return AntiCalqueEngine.normalize_zwnj(text)

    @classmethod
    def isolate_bidi(cls, text: str) -> str:
        """
        Wrap LTR spans (Latin words, digits, math, URLs) in bidi isolates
        (U+2066 LRI … U+2069 PDI) so RTL rendering never corrupts them.
        Verbatim spans (code/math/URLs) are excluded — they carry their own
        directionality in composers. ASCII-only runs (e.g. Typst markup) are
        left untouched so composer output stays parseable.
        """
        if not text:
            return text
        if re.search(r"[؀-ۿ]", text) is None:
            return text
        masked, table = mask_verbatim_spans(text)

        def _wrap(m: re.Match) -> str:
            span = m.group(0)
            # Leave placeholder sentinels (PROTECTED / VERBATIM) untouched so
            # the audit's exact-match check and token restoration keep working.
            if span.startswith("\u27e6"):
                return span
            if span.startswith(LRI):
                return span
            return f"{LRI}{span}{PDI}"

        # Latin runs, digit runs (incl. Persian digits), and parenthesized LTR.
        # The leading alternative keeps bracketed placeholders intact.
        masked = re.sub(r"\u27e6[^\u27e6\u27e7\s]*\u27e7|[A-Za-z][A-Za-z0-9_./:@-]*", _wrap, masked)
        masked = re.sub(rf"(?<!{LRI})[0-9۰-۹]+(?:[./:][0-9۰-۹]+)+", _wrap, masked)
        return restore_verbatim_spans(masked, table)

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
        Verbatim spans (code, math, URLs) are masked before normalization
        so technical content is never corrupted, then restored.
        """
        if not text:
            return text

        typo = profile.typography if profile else TypographicRules()

        # Mask verbatim spans first so typography never touches code/math/URLs.
        masked, verbatim_table = mask_verbatim_spans(text)

        # 1. Arabic character standardization (ي -> ی, ك -> ک)
        result = cls.standardize_arabic_chars(masked)

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

        # 8. Optional bidi isolation for LTR spans
        if typo.isolate_english_terms:
            result = cls.isolate_bidi(result)

        # 9. Punctuation hygiene
        result = cls.clean_punctuation_hygiene(result)

        # Restore verbatim spans untouched.
        return restore_verbatim_spans(result, verbatim_table)

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
