"""
Persian Normalization Layer — Architecture Zero §8.1.

Deterministic, auto-fix safe text normalization for Persian translation.
Guarantees strict idempotence: normalize(normalize(text)) == normalize(text).

Operations enforced:
- Arabic Kaf/Yeh/Teh-Marbuta/Heh-Yeh standardization
- Strict Zero-Width Non-Joiner (ZWNJ) normalization (deduplication, prefix/suffix handling)
- Spacing and punctuation hygiene
- Zero em-dash policy (conversion to Persian syntactic commas or parentheses)
- Directional isolate and whitespace hygiene
- Protected code block preservation
"""
from __future__ import annotations

import re
from typing import List, Optional


class PersianNormalizer:
    """Auto-fix safe Persian text normalizer.

    Enforces deterministic, idempotent normalization rules per Architecture Zero §8.1:
    - Arabic Kaf/Yeh/Teh-Marbuta/Heh-Yeh normalization
    - Strict ZWNJ normalization (deduplication, prefix/suffix handling)
    - Punctuation and spacing hygiene
    - Zero em-dash policy (conversion to Persian syntactic commas or parentheses)
    - Directional and whitespace hygiene
    - Preservation of code blocks / technical tokens
    - Strict idempotence invariant: normalize(normalize(text)) == normalize(text)
    """

    ZWNJ: str = "‌"

    # Invisible bidirectional formatting characters
    _BIDI_CHARS: str = (
        "‎‏"  # LRM, RLM
        "‪‫‬‭‮"  # LRE, RLE, PDF, LRO, RLO
        "⁦⁧⁨⁩"  # LRI, RLI, FSI, PDI
        "﻿"  # BOM / zero-width no-break space
    )

    # Translation table for Arabic characters to Persian standards
    _ARABIC_TRANS = str.maketrans({
        "ك": "ک",  # Arabic Kaf -> Persian Keheh
        "ي": "ی",  # Arabic Yeh -> Persian Yeh
        "ى": "ی",  # Arabic Alef Maksura -> Persian Yeh
        "ة": "ه",  # Arabic Teh Marbuta -> Persian Heh
        "ۀ": "هٔ",  # Heh with Yeh above -> Heh + Arabic Hamza Above
        "ـ": "",   # Decorative Kashida / Tatweel removal
        "٠": "۰",  # Arabic-Indic digits to Persian digits
        "١": "۱",
        "٢": "۲",
        "٣": "۳",
        "٤": "۴",
        "٥": "۵",
        "٦": "۶",
        "٧": "۷",
        "٨": "۸",
        "٩": "۹",
    })

    _PERSIAN_DIGITS_TRANS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    _ENGLISH_DIGITS_TRANS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")

    def __init__(
        self,
        *,
        normalize_arabic: bool = True,
        normalize_zwnj: bool = True,
        normalize_punctuation: bool = True,
        convert_em_dash: bool = True,
        em_dash_target: str = "comma",
        normalize_whitespace: bool = True,
        normalize_direction: bool = True,
        convert_digits: Optional[str] = None,
        preserve_code_blocks: bool = True,
    ) -> None:
        self.normalize_arabic = normalize_arabic
        self.normalize_zwnj = normalize_zwnj
        self.normalize_punctuation = normalize_punctuation
        self.convert_em_dash = convert_em_dash
        self.em_dash_target = em_dash_target
        self.normalize_whitespace = normalize_whitespace
        self.normalize_direction = normalize_direction
        self.convert_digits = convert_digits
        self.preserve_code_blocks = preserve_code_blocks

    def normalize(self, text: str) -> str:
        """Apply deterministic, idempotent normalization to the given text."""
        if not text:
            return text

        # 1. Protect code blocks if requested
        code_blocks: List[str] = []
        if self.preserve_code_blocks:
            def _extract_code(m: re.Match) -> str:
                code_blocks.append(m.group(0))
                return f"\x00__TARJOMAN_CODE_{len(code_blocks) - 1}__\x00"

            text = re.sub(r"```[\s\S]*?```|`[^`\n]+`", _extract_code, text)

        # 2. Arabic character normalization (ك -> ک, ي -> ی, ة -> ه, ۀ -> هٔ)
        if self.normalize_arabic:
            text = text.translate(self._ARABIC_TRANS)

        # 3. Directional isolate & invisible formatting hygiene
        if self.normalize_direction:
            text = re.sub(f"[{self._BIDI_CHARS}]", "", text)

        # 4. Zero em-dash conversion (enforces zero em-dash policy)
        if self.convert_em_dash:
            if self.em_dash_target == "parentheses":
                # Balanced parenthetical dashes -> parentheses
                text = re.sub(r"\s*[—–]\s*([^—–\n]+?)\s*[—–]\s*", r" (\1) ", text)
            else:
                # Balanced parenthetical dashes -> balanced Persian syntactic commas
                text = re.sub(r"\s*[—–]\s*([^—–\n]+?)\s*[—–]\s*", r"، \1، ", text)
            # Remaining em-dashes, en-dashes, or double-hyphens -> Persian comma
            text = re.sub(r"\s*[—–]\s*|\s*--\s*", "، ", text)

        # 5. Persian quotation marks enforcement («...»)
        if self.normalize_punctuation:
            text = re.sub(r'"([^"\n]+)"', r"«\1»", text)
            text = re.sub(r'“([^”\n]+)”', r"«\1»", text)
            text = re.sub(r'«\s+', "«", text)
            text = re.sub(r'\s+»', "»", text)

        # 6. Strict ZWNJ normalization
        if self.normalize_zwnj:
            z = self.ZWNJ

            # Deduplicate multiple consecutive ZWNJs
            text = re.sub(f"{z}{{2,}}", z, text)

            # Clean spaces adjacent to ZWNJ between Persian letters
            text = re.sub(rf"([آ-یء-ي])\s+{z}([آ-یء-ي])", rf"\1{z}\2", text)
            text = re.sub(rf"([آ-یء-ي]){z}\s+([آ-یء-ي])", rf"\1{z}\2", text)
            text = re.sub(rf"\s+{z}|{z}\s+", z, text)

            # Remove isolated ZWNJ at word boundaries / punctuation
            text = re.sub(rf"(^|[\s.,،؛:!؟?«»()\[\]]){z}+", r"\1", text)
            text = re.sub(rf"{z}+([\s.,،؛:!؟?«»()\[\]]|$)", r"\1", text)

            # Verbal prefixes: می‌ and نمی‌
            text = re.sub(r"(?<![آ-یء-ي])(ن?می)\s+([آ-یء-ي])", rf"\1{z}\2", text)

            # Suffixes:
            # - Plurals: ها, های, هایم, هایت, هایش, هایمان, هایتان, هایشان
            text = re.sub(
                r"([آ-یء-ي])\s+(های(?:م|ت|ش|مان|تان|شان)?|ها)(?![آ-یء-ي])",
                rf"\1{z}\2",
                text,
            )
            # - Comparatives: تر, ترین
            text = re.sub(r"([آ-یء-ي])\s+(ترین|تر)(?![آ-یء-ي])", rf"\1{z}\2", text)
            # - Indefinite suffix after Heh: خانه‌ای, پرنده‌ای
            text = re.sub(r"([آ-یء-ي]ه)\s+(ای|اند|ایم|اید)(?![آ-یء-ي])", rf"\1{z}\2", text)
            # - Pronominal clitics: ام, ات, اش, مان, تان, شان
            text = re.sub(r"([آ-یء-ي])\s+(ام|ات|اش|مان|تان|شان)(?![آ-یء-ي])", rf"\1{z}\2", text)
            # - Derivational affixes: مند, وار, ساز, سازی, پذیر, ناپذیر, شناس, شناسی, گرا, گرایی
            text = re.sub(
                r"([آ-یء-ي])\s+(مند|واری|وار|ساز|سازی|پذیر|ناپذیر|شناس|شناسی|گرا|گرایی)(?![آ-یء-ي])",
                rf"\1{z}\2",
                text,
            )

            # Final ZWNJ deduplication and cleanup
            text = re.sub(f"{z}{{2,}}", z, text)
            text = re.sub(rf"(^|[\s.,،؛:!؟?«»()\[\]]){z}+", r"\1", text)
            text = re.sub(rf"{z}+([\s.,،؛:!؟?«»()\[\]]|$)", r"\1", text)

        # 7. Spacing and punctuation hygiene
        if self.normalize_punctuation:
            # Duplicate commas
            text = re.sub(r"[،,]{2,}", "،", text)
            # Duplicate periods (except ellipsis ...)
            text = re.sub(r"(?<!\.)\.\.(?!\.)", ".", text)
            # Clean space before punctuation marks
            text = re.sub(r"\s+([،,.:;؛!؟?])", r"\1", text)
            # Space after Persian comma and ASCII comma (except between digits)
            text = re.sub(r"([،,])([^\s\d»«)\]}\"'\n،,])", r"\1 \2", text)
            # Space after colon before Persian letters, English letters, or opening quote
            text = re.sub(r":([آ-یء-يa-zA-Z«])", r": \1", text)
            # Space after semi-colon
            text = re.sub(r"([؛;])([^\s»«)\]}\"'\n])", r"\1 \2", text)
            # Space after sentence-ending punctuation (.!؟) before letters or opening quote/paren
            text = re.sub(r"([.؟!])([آ-یء-يa-zA-Z«(])", r"\1 \2", text)
            # Space before opening guillemet
            text = re.sub(r"([آ-یء-ي0-9a-zA-Z])«", r"\1 «", text)
            # Space after closing guillemet
            text = re.sub(r"»([آ-یء-ي0-9a-zA-Z])", r"» \1", text)
            # Clean spaces inside parentheses
            text = re.sub(r"\(\s+", "(", text)
            text = re.sub(r"\s+\)", ")", text)
            text = re.sub(r"([آ-یء-ي0-9a-zA-Z])\(", r"\1 (", text)
            text = re.sub(r"\)([آ-یء-ي0-9a-zA-Z])", r") \1", text)
            # Clean comma immediately before sentence-ending punctuation
            text = re.sub(r"[،,]\s*([.؟!])", r"\1", text)

        # 8. Digit conversion
        if self.convert_digits == "persian":
            text = text.translate(self._PERSIAN_DIGITS_TRANS)
        elif self.convert_digits == "english":
            text = text.translate(self._ENGLISH_DIGITS_TRANS)

        # 9. Whitespace hygiene
        if self.normalize_whitespace:
            text = re.sub(r"[ \t]+", " ", text)
            lines = [line.strip() for line in text.splitlines()]
            text = "\n".join(lines).strip()
            text = re.sub(r"\n{3,}", "\n\n", text)

        # 10. Restore code blocks
        if self.preserve_code_blocks and code_blocks:
            for idx, block in enumerate(code_blocks):
                text = text.replace(f"\x00__TARJOMAN_CODE_{idx}__\x00", block)

        return text


def normalize_persian(
    text: str,
    *,
    normalize_arabic: bool = True,
    normalize_zwnj: bool = True,
    normalize_punctuation: bool = True,
    convert_em_dash: bool = True,
    em_dash_target: str = "comma",
    normalize_whitespace: bool = True,
    normalize_direction: bool = True,
    convert_digits: Optional[str] = None,
    preserve_code_blocks: bool = True,
) -> str:
    """Normalize Persian text safely and idempotently.

    Architecture Zero §8.1:
    Strict idempotence invariant: normalize_persian(normalize_persian(text)) == normalize_persian(text).
    """
    normalizer = PersianNormalizer(
        normalize_arabic=normalize_arabic,
        normalize_zwnj=normalize_zwnj,
        normalize_punctuation=normalize_punctuation,
        convert_em_dash=convert_em_dash,
        em_dash_target=em_dash_target,
        normalize_whitespace=normalize_whitespace,
        normalize_direction=normalize_direction,
        convert_digits=convert_digits,
        preserve_code_blocks=preserve_code_blocks,
    )
    return normalizer.normalize(text)
