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
- De-AI humanization: 18 AI-Tells (T1-T18), tanvin repair, fake tanvin correction
- Code & Markdown table shielding (v2.3.0)

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
from tarjoman.stages.humanizer import PersianHumanizer


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
        - Prefixes: می‌, نمی‌
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

    # A word carrying an explicit ezafe marker: silent-heh ezafe
    # (X-heh + ZWNJ/space + yeh, or heh + hamza-above/U+0674) or a word
    # ending in kasra (U+0650).
    _EZAFE_WORD_RE = (
        r"[\u0600-\u06FF\u200c]+?"
        r"(?:[\u0647\u06be](?:\u200c[\u06cc\u064a]|[\u0654\u0674]|[\s][\u06cc\u064a])|[\u0650])"
    )

    # Three or more consecutive ezafe-marked words = heavy chain.
    _EZAFE_CHAIN_RE = None  # built lazily (class-level re with interpolation)

    @classmethod
    def _ezafe_chain_pattern(cls) -> "re.Pattern[str]":
        if cls._EZAFE_CHAIN_RE is None:
            cls._EZAFE_CHAIN_RE = re.compile(
                rf"(?:{cls._EZAFE_WORD_RE}\s+){{2,}}{cls._EZAFE_WORD_RE}",
                re.UNICODE,
            )
        return cls._EZAFE_CHAIN_RE

    @classmethod
    def _strip_ezafe_suffix(cls, word: str) -> str:
        """Return *word* with its trailing ezafe marker removed."""
        if word.endswith("\u0650"):
            return word[:-1]
        if re.search(r"[\u0647\u06be][\u0654\u0674]$", word):
            return word[:-1]
        m = re.search(r"([\u0647\u06be])(?:\u200c[\u06cc\u064a]|[\s][\u06cc\u064a])$", word)
        if m:
            return word[: m.start()] + m.group(1)
        return word

    @classmethod
    def smooth_ezafe_chains(cls, text: str) -> str:
        """
        Smooth heavy consecutive ezafe chains (3+ linkages).

        A chain of three or more ezafe-marked words (e.g. ``NP1-ez NP2-ez NP3``)
        creates cognitive heaviness (thoqal-e kalam) in Persian. The chain is
        broken after its second link by stripping that link's ezafe marker and
        inserting the native relational connective ``\u0645\u0631\u0628\u0648\u0637 \u0628\u0647``
        ("morbut be" / related to)::

            W1-ez W2-ez W3 [-ez ...]  ->  W1-ez W2 \u0645\u0631\u0628\u0648\u0637 \u0628\u0647 W3 ...

        Guarantees:

        - verbatim spans (code, math, URLs, emails) are masked before scanning
          and restored afterwards, so technical content is never corrupted;
        - legitimate short 1-2 ezafe phrases are left untouched;
        - empty / non-Persian input is returned unchanged.
        """
        if not text:
            return text
        if re.search(r"[\u0600-\u06FF]", text) is None:
            return text
        masked, table = mask_verbatim_spans(text)

        def _break_chain(m: "re.Match[str]") -> str:
            words = m.group(0).split()
            if len(words) < 3:
                return m.group(0)
            head = words[0] + " " + cls._strip_ezafe_suffix(words[1])
            rest = " ".join(words[2:])
            return f"{head} \u0645\u0631\u0628\u0648\u0637 \u0628\u0647 {rest}"

        smoothed = cls._ezafe_chain_pattern().sub(_break_chain, masked)
        return restore_verbatim_spans(smoothed, table)

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

        # 4b. Ezafe chain smoothing (TRN-013): break heavy 3+ ezafe chains
        # with a native relational connective; verbatim-safe, 1-2 link
        # phrases untouched.
        result = cls.smooth_ezafe_chains(result)

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

        # Restore verbatim spans (anti-calque/typo stage).
        result = restore_verbatim_spans(result, verbatim_table)

        # 10. De-AI humanization (v2.3.0): eradicate AI tells, repair tanvin,
        # correct fake tanvin. PersianHumanizer.humanize() shields code/tables
        # internally, so it is safe to run on the restored text.
        result = PersianHumanizer.humanize(result)

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
