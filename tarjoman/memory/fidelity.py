"""
Fidelity checks: did the translation keep everything the source had?

A fluent translation can still silently drop a sentence, summarize a long
paragraph, or lose a number. These checks compare a source text with its
translation mechanically and report what looks missing. They never change
the text; every finding is a hint for the translator to verify.

Checks:

- paragraphs: the translation has a different number of paragraphs.
- length: a paragraph (or the whole text) is much shorter than its source,
  which usually means an omission or a summary.
- number: a number from the source (2+ digits, or with a decimal point) is
  not in the translation. Persian and Arabic-Indic digits are normalized.
- citation: a citation or footnote marker ([12], [^3]) is missing.
- url: a URL or e-mail address is missing or changed.
- code: inline code or a fenced code block was changed or dropped.

The idea of explicit completeness checks (never summarize, keep numbers,
citation markers and paragraph order) is adapted from Kaman AI Translator
(MIT, https://github.com/Mohammad-Hasan-Kaman/kaman-ai-translator).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫", "01234567890123456789.")

_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>()«»\"']+|[\w.+-]+@[\w-]+\.[\w.]+")
_CITATION_RE = re.compile(r"\[\^?\d+[a-z]?\]")
_NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*(?![\w])")

#: Below this many characters a source paragraph is too short to judge.
MIN_PARAGRAPH_CHARS = 80
#: A translated paragraph shorter than this fraction of its source is flagged.
MIN_LENGTH_RATIO = 0.45


@dataclass
class FidelityFinding:
    category: str  # paragraphs | length | number | citation | url | code
    message: str


def _normalize_digits(text: str) -> str:
    return text.translate(_DIGIT_MAP).replace("٬", "")


def _strip_code(text: str) -> str:
    return _INLINE_CODE_RE.sub(" ", _FENCE_RE.sub(" ", text))


def split_paragraphs(text: str) -> List[str]:
    """Split on blank lines; a fenced code block counts as one paragraph."""
    placeholders: List[str] = []

    def _keep(m: "re.Match[str]") -> str:
        placeholders.append(m.group(0))
        return f"\x00{len(placeholders) - 1}\x00"

    masked = _FENCE_RE.sub(_keep, text.replace("\r\n", "\n"))
    paras = [p.strip() for p in re.split(r"\n\s*\n", masked) if p.strip()]
    return [re.sub(r"\x00(\d+)\x00", lambda m: placeholders[int(m.group(1))], p) for p in paras]


def _numbers(text: str) -> List[str]:
    out = []
    for raw in _NUMBER_RE.findall(_normalize_digits(_strip_code(_URL_RE.sub(" ", text)))):
        bare = raw.replace(",", "")
        # Single digits are often written as words («سه»، «فصل سوم»).
        if len(bare.replace(".", "")) >= 2 or "." in bare:
            out.append(bare)
    return out


def check_paragraphs(source: str, target: str) -> List[FidelityFinding]:
    src, tgt = split_paragraphs(source), split_paragraphs(target)
    findings: List[FidelityFinding] = []
    if len(src) != len(tgt):
        findings.append(
            FidelityFinding(
                "paragraphs",
                f"Source has {len(src)} paragraph(s), translation has {len(tgt)}. "
                "Check for a dropped, merged or split paragraph.",
            )
        )
        return findings
    for i, (s, t) in enumerate(zip(src, tgt), start=1):
        s_len, t_len = len(_strip_code(s).strip()), len(_strip_code(t).strip())
        if s_len >= MIN_PARAGRAPH_CHARS and t_len < s_len * MIN_LENGTH_RATIO:
            findings.append(
                FidelityFinding(
                    "length",
                    f"Paragraph {i} is {t_len} chars vs {s_len} in the source "
                    f"(ratio {t_len / s_len:.2f}). Possible omission or summary: «{t[:40]}…»",
                )
            )
    return findings


def check_overall_length(source: str, target: str) -> List[FidelityFinding]:
    s_len, t_len = len(_strip_code(source).strip()), len(_strip_code(target).strip())
    if s_len >= MIN_PARAGRAPH_CHARS * 3 and t_len < s_len * MIN_LENGTH_RATIO:
        return [
            FidelityFinding(
                "length",
                f"Translation is {t_len} chars vs {s_len} in the source "
                f"(ratio {t_len / s_len:.2f}). The text may have been summarized.",
            )
        ]
    return []


def check_numbers(source: str, target: str) -> List[FidelityFinding]:
    target_nums = _numbers(target)
    pool = list(target_nums)
    missing: List[str] = []
    for n in _numbers(source):
        if n in pool:
            pool.remove(n)
        else:
            missing.append(n)
    if not missing:
        return []
    shown = "، ".join(dict.fromkeys(missing))
    return [
        FidelityFinding(
            "number",
            f"Number(s) in the source not found in the translation: {shown}. "
            "Check they were kept (or deliberately written out / converted).",
        )
    ]


def _missing_tokens(regex: "re.Pattern[str]", source: str, target: str) -> List[str]:
    target_tokens = regex.findall(_normalize_digits(target))
    missing = []
    for tok in regex.findall(_normalize_digits(source)):
        if tok in target_tokens:
            target_tokens.remove(tok)
        else:
            missing.append(tok)
    return list(dict.fromkeys(missing))


def check_citations(source: str, target: str) -> List[FidelityFinding]:
    missing = _missing_tokens(_CITATION_RE, _strip_code(source), _strip_code(target))
    if not missing:
        return []
    return [FidelityFinding("citation", "Citation/footnote marker(s) missing: " + " ".join(missing))]


def check_urls(source: str, target: str) -> List[FidelityFinding]:
    missing = _missing_tokens(_URL_RE, source, target)
    if not missing:
        return []
    return [FidelityFinding("url", "URL/e-mail missing or changed: " + " ".join(missing))]


def check_code(source: str, target: str) -> List[FidelityFinding]:
    findings: List[FidelityFinding] = []
    for fence in _FENCE_RE.findall(source):
        if fence not in target:
            first = fence.strip("`").strip().splitlines()[0:1]
            findings.append(
                FidelityFinding(
                    "code",
                    "Code block changed or missing (code must stay byte-for-byte): "
                    + (first[0][:50] if first else "```"),
                )
            )
    src_inline = _INLINE_CODE_RE.findall(_FENCE_RE.sub(" ", source))
    tgt_inline = _INLINE_CODE_RE.findall(_FENCE_RE.sub(" ", target))
    missing = [c for c in dict.fromkeys(src_inline) if c not in tgt_inline]
    if missing:
        findings.append(FidelityFinding("code", "Inline code changed or missing: " + " ".join(missing[:6])))
    return findings


def check_fidelity(source: str, target: str) -> List[FidelityFinding]:
    """Run every fidelity check. Returns an empty list when nothing looks lost."""
    findings = check_paragraphs(source, target)
    if not any(f.category == "length" for f in findings):
        findings += check_overall_length(source, target)
    return (
        findings
        + check_numbers(source, target)
        + check_citations(source, target)
        + check_urls(source, target)
        + check_code(source, target)
    )
