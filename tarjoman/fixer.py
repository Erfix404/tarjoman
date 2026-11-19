"""Safe orthography-only auto-fixer for Persian text and Markdown.

Applies only mechanical, non-semantic repairs while shielding code blocks,
inline code, LaTeX math/commands, URLs, emails, HTML tags, and localization
placeholders byte-for-byte:

1. Arabic character normalization (ي/ك/ى/ة and tatweel between Persian letters)
2. Look-alike joiners (soft hyphen, ZWSP, ZWJ, BOM) -> real ZWNJ (U+200C)
3. Missing ZWNJ (spaced می/نمی, closed-list glued colloquial verbs, detached
   plurals/superlatives, silent-heh + ای, duplicate/spaced ZWNJ)
4. Tanvin repair (missing tanvin on standard Arabic loans + fake Persian tanvin)
5. Unambiguous context-free misspellings (reused from tarjoman.linter)
6. Latin punctuation next to Persian words (, ; ? -> ، ؛ ؟) and Persian decimal
   mark between Persian digits (۹.۵ -> ۹٫۵)
7. Horizontal whitespace around Persian punctuation and inside «» / ()

Never touches calques, AI tells, em-dashes, straight quotes, or hekasre.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Pattern, Tuple

from tarjoman.linter import (
    _DETACHED_SUFFIX_RE,
    _FA_B_L_LINT,
    _FA_B_R_LINT,
    _FA_LETTER,
    _FAKE_TANVIN,
    _FAKE_ZWNJ_RE,
    _GLUED_MI_RE,
    _MISSPELLINGS,
    _MISSPELLING_RE,
    _TANVIN_NEEDED,
)
from tarjoman.stages.anti_calque import ARABIC_CHAR_MAP, ZWNJ

_VERBATIM_SPECS: Tuple[Pattern[str], ...] = (
    # Fenced code blocks (``` or ~~~)
    re.compile(
        r"^[ \t]*(`{3,}|~{3,})[^\n]*\n(?:[\s\S]*?\n)?[ \t]*\1[^\n]*$",
        re.MULTILINE,
    ),
    re.compile(r"```[\s\S]*?```"),
    # LaTeX display math and verbatim/math environments
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
    # Inline code and inline LaTeX math
    re.compile(r"`[^`\n]+`"),
    re.compile(r"(?<![\$\\\w])\$(?![\$\d\s])([^\$\n]+?)(?<![\\\s])\$"),
    # URLs and emails
    re.compile(r"https?://[^\s<>\"'()«»]+(?<![.,;:!?])"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    # HTML/XML comments and tags
    re.compile(r"<!--[\s\S]*?-->|<\/?[A-Za-z][A-Za-z0-9:-]*(?:\s+[^>\n]*)?\/?>"),
    # Localization placeholders: {{var}}, {count}, %s, %(name)s
    re.compile(
        r"\{\{[^}\n]+\}\}|(?<!\{)\{[A-Za-z_][A-Za-z0-9_]*(?::[^}\n]+)?\}(?!\})"
        r"|%(?:\([A-Za-z_][A-Za-z0-9_]*\))?[#0\- +]*\d*(?:\.\d+)?[sdifuxXeEgG]"
    ),
)

_TOKEN_PREFIX = "\u27e6FIX_"
_TOKEN_SUFFIX = "\u27e7"
_TOKEN_RESTORE_RE = re.compile(r"\u27e6FIX_(\d+)\u27e7")

_ARABIC_TRANS = str.maketrans(ARABIC_CHAR_MAP)
_ARABIC_CHARS_RE = re.compile("[" + "".join(re.escape(c) for c in ARABIC_CHAR_MAP) + "]")
_TATWEEL_BETWEEN_FA_RE = re.compile(r"(?<=[\u0621-\u06CC])\u0640+(?=[\u0621-\u06CC])")

_SPACED_MI_RE = re.compile(r"(?<![\u0621-\u06CC\u200c])(ن?می)[ \t]+([آ-ی])")
_HEH_EY_EXCLUSIONS = frozenset({"به", "که", "چه", "نه", "سه", "ده", "مه"})
_HEH_EY_RE = re.compile(r"(?<![\u0621-\u06CC\u200c])([\u0621-\u06CC]+ه)[ \t]+ای(?![\u0621-\u06CC\u200c])")
_DUP_ZWNJ_RE = re.compile(r"\u200c{2,}")
_SPACE_AROUND_ZWNJ_RE = re.compile(r"[ \t]+\u200c|\u200c[ \t]+")

_TANVIN_NEEDED_PATTERNS = tuple(
    (re.compile(_FA_B_L_LINT + re.escape(bare) + _FA_B_R_LINT), correct)
    for bare, correct in _TANVIN_NEEDED.items()
)
_FAKE_TANVIN_PATTERNS = tuple(
    (re.compile(_FA_B_L_LINT + re.escape(fake) + _FA_B_R_LINT), fix)
    for fake, fix in _FAKE_TANVIN.items()
)

_LATIN_PUNCT_MAP = {",": "،", ";": "؛", "?": "؟"}
_LATIN_PUNCT_AFTER_FA_RE = re.compile(r"(?<=[\u0621-\u06CC])[ \t]*([,;?])(?!\d)")
_PERSIAN_DECIMAL_DOT_RE = re.compile(r"(?<=[۰-۹])\.(?=[۰-۹])")

_SPACE_BEFORE_PUNCT_RE = re.compile(f"({_FA_LETTER}[)»]?)[ \\t]+([،؛؟])")
_SPACE_BEFORE_DOT_RE = re.compile(
    f"({_FA_LETTER}[)»]?)[ \\t]+([.!])(?![.!])(?=[ \\t]|$)", re.MULTILINE
)
_SPACE_AFTER_OPEN_GUILLEMET_RE = re.compile(f"«[ \\t]+(?={_FA_LETTER})")
_SPACE_BEFORE_CLOSE_GUILLEMET_RE = re.compile(f"({_FA_LETTER}[.!؟]?)[ \\t]+»")
_SPACE_AFTER_OPEN_PAREN_RE = re.compile(f"\\([ \\t]+(?={_FA_LETTER})")
_SPACE_BEFORE_CLOSE_PAREN_RE = re.compile(f"(?<={_FA_LETTER})[ \\t]+\\)")


@dataclass
class FixResult:
    """Result of running :func:`fix_text`."""

    text: str
    changed: bool
    counts: Dict[str, int] = field(default_factory=dict)

    @property
    def total_fixes(self) -> int:
        return sum(self.counts.values())

    def to_dict(self, file_path: Optional[str] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "changed": self.changed,
            "total_fixes": self.total_fixes,
            "counts": dict(self.counts),
        }
        if file_path is not None:
            payload["file"] = file_path
        return payload


def _protect_verbatim(text: str) -> Tuple[str, List[str]]:
    tokens: List[str] = []

    def _stash(match: re.Match) -> str:
        idx = len(tokens)
        tokens.append(match.group(0))
        return f"{_TOKEN_PREFIX}{idx}{_TOKEN_SUFFIX}"

    masked = text
    for pattern in _VERBATIM_SPECS:
        masked = pattern.sub(_stash, masked)
    return masked, tokens


def _restore_verbatim(text: str, tokens: List[str]) -> str:
    if not tokens:
        return text
    return _TOKEN_RESTORE_RE.sub(lambda m: tokens[int(m.group(1))], text)


def _sub_count(pattern: Pattern[str], repl: Any, text: str) -> Tuple[str, int]:
    return pattern.subn(repl, text)


def fix_text(text: str) -> FixResult:
    """Apply safe, idempotent orthography-only fixes to Persian text."""
    if not text:
        return FixResult(text=text, changed=False, counts={})

    masked, tokens = _protect_verbatim(text)
    counts: Dict[str, int] = {}

    def _add(cat: str, n: int) -> None:
        if n > 0:
            counts[cat] = counts.get(cat, 0) + n

    # 1. Arabic character normalization + tatweel between Persian letters
    masked, n = _sub_count(
        _ARABIC_CHARS_RE, lambda m: m.group(0).translate(_ARABIC_TRANS), masked
    )
    _add("arabic", n)
    masked, n = _sub_count(_TATWEEL_BETWEEN_FA_RE, "", masked)
    _add("arabic", n)

    # 2. Fake joiners -> real ZWNJ
    masked, n = _sub_count(_FAKE_ZWNJ_RE, ZWNJ, masked)
    _add("fake-zwnj", n)

    # 3. Missing ZWNJ (verbal prefixes, glued colloquial stems, detached suffixes, ه‌ای)
    masked, n = _sub_count(_SPACED_MI_RE, rf"\1{ZWNJ}\2", masked)
    _add("zwnj", n)
    masked, n = _sub_count(_GLUED_MI_RE, lambda m: f"{m.group(1)}{ZWNJ}{m.group(2)}", masked)
    _add("zwnj", n)
    # Restrict detached suffix joining to horizontal spaces (never cross newlines).
    detached_horiz_re = re.compile(
        _DETACHED_SUFFIX_RE.pattern.replace(r"\s(", r"[ \t]+("),
        _DETACHED_SUFFIX_RE.flags,
    )
    masked, n = _sub_count(detached_horiz_re, rf"{ZWNJ}\1", masked)
    _add("zwnj", n)

    def _fix_heh_ey(match: re.Match) -> str:
        word = match.group(1)
        if word in _HEH_EY_EXCLUSIONS:
            return match.group(0)
        return f"{word}{ZWNJ}ای"

    before_heh = masked
    masked = _HEH_EY_RE.sub(_fix_heh_ey, masked)
    if masked != before_heh:
        # Count actual substitutions excluding skipped exclusions
        changed_heh = sum(
            1 for m in _HEH_EY_RE.finditer(before_heh) if m.group(1) not in _HEH_EY_EXCLUSIONS
        )
        _add("zwnj", changed_heh)

    masked, n = _sub_count(_DUP_ZWNJ_RE, ZWNJ, masked)
    _add("zwnj", n)
    masked, n = _sub_count(_SPACE_AROUND_ZWNJ_RE, ZWNJ, masked)
    _add("zwnj", n)

    # 4. Tanvin (missing on Arabic loans + fake Persian tanvin)
    for pat, correct in _TANVIN_NEEDED_PATTERNS:
        masked, n = _sub_count(pat, correct, masked)
        _add("tanvin", n)
    for pat, fix in _FAKE_TANVIN_PATTERNS:
        masked, n = _sub_count(pat, fix, masked)
        _add("tanvin", n)

    # 5. Unambiguous misspellings
    masked, n = _sub_count(
        _MISSPELLING_RE, lambda m: _MISSPELLINGS[m.group(1)], masked
    )
    _add("spelling", n)

    # 6. Latin punctuation and decimal separator
    masked, n = _sub_count(
        _LATIN_PUNCT_AFTER_FA_RE, lambda m: _LATIN_PUNCT_MAP[m.group(1)], masked
    )
    _add("punct", n)
    masked, n = _sub_count(_PERSIAN_DECIMAL_DOT_RE, "٫", masked)
    _add("punct", n)

    # 7. Spacing inside «» / () first, then spaces before punctuation marks
    masked, n = _sub_count(_SPACE_AFTER_OPEN_GUILLEMET_RE, "«", masked)
    _add("punct-space", n)
    masked, n = _sub_count(_SPACE_BEFORE_CLOSE_GUILLEMET_RE, r"\1»", masked)
    _add("punct-space", n)
    masked, n = _sub_count(_SPACE_AFTER_OPEN_PAREN_RE, "(", masked)
    _add("punct-space", n)
    masked, n = _sub_count(_SPACE_BEFORE_CLOSE_PAREN_RE, ")", masked)
    _add("punct-space", n)
    masked, n = _sub_count(_SPACE_BEFORE_PUNCT_RE, r"\1\2", masked)
    _add("punct-space", n)
    masked, n = _sub_count(_SPACE_BEFORE_DOT_RE, r"\1\2", masked)
    _add("punct-space", n)

    restored = _restore_verbatim(masked, tokens)
    return FixResult(text=restored, changed=(restored != text), counts=counts)


def format_fix_summary(file_path: str, result: FixResult) -> str:
    """Format a concise human-readable summary of safe orthography fixes."""
    if not result.changed:
        return f"{file_path}: clean (0 orthography fixes needed)."
    breakdown = ", ".join(f"{cat}={count}" for cat, count in sorted(result.counts.items()))
    return f"{file_path}: applied {result.total_fixes} orthography fix(es) ({breakdown})."
