r"""
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
- latex: LaTeX math ($...$, $$...$$, \[...\], \(...\), environments) or key
  commands (\cite, \ref, \label, \url, \href, \includegraphics) changed.
- placeholder: localization placeholder ({{var}}, {name}, %(key)s, %s, %d)
  mismatch outside code spans.
- headings: Markdown ATX heading count mismatch outside code blocks.
- tables: Markdown table separator/column structure mismatch outside code blocks.

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

_LATEX_STRUCT_PATTERNS = (
    re.compile(r"\$\$[\s\S]*?\$\$"),
    re.compile(
        r"\\begin\{(equation|align|alignat|gather|multline|flalign|eqnarray|displaymath|math|"
        r"verbatim|lstlisting|minted|tikzpicture|algorithmic)(\*?)\}[\s\S]*?\\end\{\1\2\}"
    ),
    re.compile(r"\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)"),
    re.compile(
        r"\\(?:cite[a-zA-Z]*|ref|eqref|autoref|cref|Cref|pageref|label|url|nocite|"
        r"bibliography|bibliographystyle|includegraphics|input|include|usepackage|href)\*?"
        r"(?:\[[^\]\n]*\])*\{[^{}\n]*\}"
    ),
    # Inline math: avoid matching currency like $1,250 or $50
    re.compile(r"(?<![\$\\\w])\$(?![\$\d\s])([^\$\n]+?)(?<![\\\s])\$"),
)
_PLACEHOLDER_RE = re.compile(
    r"\{\{[^}\n]+\}\}|(?<!\{)\{[A-Za-z_][A-Za-z0-9_]*(?::[^}\n]+)?\}(?!\})"
    r"|%(?:\([A-Za-z_][A-Za-z0-9_]*\))?[#0\- +]*\d*(?:\.\d+)?[sdifuxXeEgG]"
)
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+\S", re.MULTILINE)
_TABLE_SEP_RE = re.compile(
    r"^\s*\|?(?:\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?\s*$", re.MULTILINE
)

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


def _extract_latex_tokens(text: str) -> List[str]:
    cleaned = _strip_code(text)
    tokens: List[str] = []
    for pat in _LATEX_STRUCT_PATTERNS:
        def _stash(m: "re.Match[str]") -> str:
            tokens.append(m.group(0))
            return " "

        cleaned = pat.sub(_stash, cleaned)
    return tokens


def check_latex(source: str, target: str) -> List[FidelityFinding]:
    target_tokens = _extract_latex_tokens(target)
    missing: List[str] = []
    for tok in _extract_latex_tokens(source):
        if tok in target_tokens:
            target_tokens.remove(tok)
        else:
            missing.append(tok)
    if not missing:
        return []
    shown = ", ".join(dict.fromkeys(m[:40] for m in missing[:6]))
    return [FidelityFinding("latex", f"LaTeX math or command(s) missing or altered: {shown}")]


def check_placeholders(source: str, target: str) -> List[FidelityFinding]:
    src_tokens = _PLACEHOLDER_RE.findall(_strip_code(source))
    tgt_tokens = _PLACEHOLDER_RE.findall(_strip_code(target))
    if not src_tokens and not tgt_tokens:
        return []
    pool = list(tgt_tokens)
    missing: List[str] = []
    for tok in src_tokens:
        if tok in pool:
            pool.remove(tok)
        else:
            missing.append(tok)
    findings: List[FidelityFinding] = []
    if missing:
        findings.append(
            FidelityFinding(
                "placeholder",
                "Missing or altered placeholder(s): " + " ".join(dict.fromkeys(missing)),
            )
        )
    if pool:
        findings.append(
            FidelityFinding(
                "placeholder",
                "Extra placeholder(s) not present in source: " + " ".join(dict.fromkeys(pool)),
            )
        )
    return findings


def check_headings(source: str, target: str) -> List[FidelityFinding]:
    src_count = len(_HEADING_RE.findall(_FENCE_RE.sub(" ", source)))
    tgt_count = len(_HEADING_RE.findall(_FENCE_RE.sub(" ", target)))
    if src_count > 0 and src_count != tgt_count:
        return [
            FidelityFinding(
                "headings",
                f"Source has {src_count} Markdown heading(s), translation has {tgt_count}.",
            )
        ]
    return []


def _table_signatures(text: str) -> List[int]:
    stripped = _FENCE_RE.sub(" ", text)
    return [
        len(row.strip().strip("|").split("|"))
        for row in _TABLE_SEP_RE.findall(stripped)
    ]


def check_tables(source: str, target: str) -> List[FidelityFinding]:
    src_tables = _table_signatures(source)
    tgt_tables = _table_signatures(target)
    if not src_tables:
        return []
    if len(src_tables) != len(tgt_tables):
        return [
            FidelityFinding(
                "tables",
                f"Source has {len(src_tables)} Markdown table(s), translation has {len(tgt_tables)}.",
            )
        ]
    if src_tables != tgt_tables:
        return [
            FidelityFinding(
                "tables",
                f"Markdown table column counts differ (source={src_tables}, translation={tgt_tables}).",
            )
        ]
    return []


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
        + check_latex(source, target)
        + check_placeholders(source, target)
        + check_headings(source, target)
        + check_tables(source, target)
    )
