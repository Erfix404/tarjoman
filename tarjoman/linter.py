"""
Persian Markdown & Translation Linter for Tarjoman Universal Engine (v2).

Checks Persian text/markdown files for:
1. Guaranteed ZERO em-dashes: '—', '–', and standalone '--' (CLI flags untouched)
2. Straight/curly quotes that must become Persian guillemets «»
3. Expanded banned structural and lexical calques (Najafi/Samii, incl. وي)
4. Missing ZWNJ after verbal prefixes می/نمی
5. Unbalanced Persian quotation marks ('«' vs '»')
6. Non-standard Arabic characters ('ي', 'ك', 'ى', 'ة', 'ـ')
7. Bidi isolation: unbalanced LRI/RLI/FSI vs PDI, and unisolated Latin
   tokens in Persian sentences (flagged always when they risk bidi
   corruption, or for every bare Latin token when enforce_bidi_isolation
   is set)
8. Heavy ezafe chains: 3+ consecutive explicit ezafe markers
   (TRN-013 structural grammar)
9. Redundant generic article:
   subject + generic predicate (TRN-013 structural grammar)
10. Hekasre detection: ezafe kasre confused with colloquial clitic
11. Tanvin: missing tanvin on Arabic loans, fake tanvin on Persian words

Both this module and the skillpack script sentence-initial «یک» with a generic class
   subject + generic predicate (TRN-013 structural grammar)

Both this module and the skillpack script
(``.claude/skills/tarjoman/scripts/linter.py``) consume the shared pattern
table in ``tarjoman.stages.anti_calque`` — one source of truth.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Pattern, Tuple

from tarjoman.stages.anti_calque import (
    LINT_ARABIC_CHARS,
    LINT_CALQUE_PATTERNS,
    LINT_DOUBLE_HYPHEN_RE,
    LINT_STRAIGHT_QUOTE_RES,
    LINT_ZWNJ_RES,
)
from tarjoman.stages.humanizer import LINT_AI_TELL_PATTERNS


# ---------------------------------------------------------------------------
# Hekasre detection (v2.3.0)
# ---------------------------------------------------------------------------
_HE_NOUNS = set("""خانه خونه نامه برنامه هفته پروژه مدرسه نقشه جمعه قهوه بچه شنبه دقیقه
ثانیه پنجره اندازه سفره کوچه میوه لحظه جمله مرحله نتیجه مقاله هزینه گزینه نمونه زمینه
دسته بسته پوشه شبکه حوزه دوره چهره سلیقه علاقه سابقه تجربه قطعه منطقه فاصله مجموعه
موسسه مسئله مساله وسیله هدیه اجاره اداره اشاره ستاره کناره ساده آماده ایده شماره
اجازه انگیزه اندیشه ترانه بهانه نشانه خاطره پرونده آینده گذشته رابطه ضابطه قاعده
مبادله معامله محاسبه مطالعه مراجعه مصاحبه مقایسه مناقصه مزایده""".split())

_PRON = r'(?:من|تو|ما|شما|او|اون|ایشون|اونا|اینا|خودم|خودت|خودش|این|آن)'

# Tanvin: Arabic loans needing tanvin (v2.3.0)
_TANVIN_NEEDED = {
    "لطفا": "لطفاً", "حتما": "حتماً", "واقعا": "واقعاً", "اصلا": "اصلاً",
    "کاملا": "کاملاً", "مثلا": "مثلاً", "معمولا": "معمولاً",
    "تقریبا": "تقریباً", "دقیقا": "دقیقاً", "فعلا": "فعلاً",
    "قطعا": "قطعاً", "اتفاقا": "اتفاقاً", "احتمالا": "احتمالاً",
    "مخصوصا": "مخصوصاً", "اساسا": "اساساً", "عملا": "عملاً",
    "اولا": "اولاً", "ضمنا": "ضمناً",
}

# Fake tanvin: Persian words wrongly carrying tanvin (v2.3.0)
_FAKE_TANVIN = {
    "گاهاً": "گاهی", "گاها": "گاهی", "دوماً": "دوم اینکه",
    "سوماً": "سوم اینکه", "ناچاراً": "به‌ناچار",
    "زباناً": "به زبان", "تلفناً": "تلفنی", "خواهشاً": "خواهش می‌کنم",
}

_FA_B_L_LINT = r"(?<![؀-ۿ‌])"
_FA_B_R_LINT = r"(?![؀-ۿً-ّ‌])"


#: Common words ending in «ه» that are never a misspelled ezafe (function
#: words, adverbs, verbal nouns). Kept out of hekasre detection.
_HE_NON_EZAFE = set("""همه توجه اینکه آنکه چگونه بلکه گرچه اگرچه هرچه آنچه چنانچه وگرنه
همیشه ویژه نه چه که به البته اتفاقیه روزانه ماهانه سالانه هفتگانه جداگانه آگاهانه""".split())


def find_hekasre(text: str) -> List[Tuple[str, str, str]]:
    """Return [(matched_text, suggestion, tier)] for probable hekasre errors.

    Hekasre is the colloquial habit of writing the ezafe kasre as «ـه»
    («کتابه من» instead of «کتابِ من»). Only a word ending in «ه» directly
    followed by a personal/demonstrative pronoun is flagged: any other
    following word produced constant false positives («باید توجه داشت»،
    «شده است»). Known nouns, function words, past participles (stem ending
    in «د»/«ت»: شده، رفته، گفته) and «ـانه» adverbs are skipped.
    """
    out: List[Tuple[str, str, str]] = []
    for m in re.finditer(r'(?<![‌آ-ی])([آ-ی]{2,})ه\s+(' + _PRON + r')(?![آ-ی])', text):
        stem, nxt = m.group(1), m.group(2)
        whole = stem + "ه"
        if whole in _HE_NOUNS or whole in _HE_NON_EZAFE:
            continue
        if stem.endswith(("د", "ت", "ان")):
            continue
        out.append((m.group(0), f'{stem}ِ {nxt}', 'A'))
    return out

# ANSI Color Codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


@dataclass
class LintIssue:
    line_number: int
    category: str  # "em-dash", "quote-style", "calque", "zwnj", "quote", "arabic", "bidi-isolate", "ezafe-chain", "generic-article", "hekasre", "tanvin"
    message: str
    snippet: str
    suggestion: str = field(default="")


BANNED_CALQUE_PATTERNS: List[Tuple[str, Pattern]] = [
    (name, re.compile(regex, re.UNICODE)) for name, regex in LINT_CALQUE_PATTERNS
]

_STRAIGHT_QUOTE_PATTERNS: List[Pattern] = [
    re.compile(regex, re.UNICODE) for regex in LINT_STRAIGHT_QUOTE_RES
]

_ZWNJ_PATTERNS: List[Pattern] = [
    re.compile(regex, re.UNICODE) for regex in LINT_ZWNJ_RES
]

_DOUBLE_HYPHEN_PATTERN: Pattern = re.compile(LINT_DOUBLE_HYPHEN_RE)

#: Unicode bidi isolates: LRI/RLI/FSI open an isolation, PDI closes it.
_BIDI_OPEN_CHARS = ("\u2066", "\u2067", "\u2068")
_BIDI_CLOSE_CHAR = "\u2069"
_BIDI_ISOLATED_SPAN_RE: Pattern = re.compile("[\u2066-\u2068][^\u2069]*\u2069")
_BIDI_LATIN_TOKEN_RE: Pattern = re.compile(r"[A-Za-z][A-Za-z0-9_./:-]*")
_PERSIAN_CHAR_RE: Pattern = re.compile("[\u0600-\u06FF]")
_INLINE_CODE_SPAN_RE: Pattern = re.compile(r"`[^`\n]+`")


#: TRN-013 structural grammar: a word carrying an explicit ezafe marker
#: (silent-heh ezafe or kasra). Three or more in a row = heavy chain.
_EZAFE_WORD_RE: Pattern = re.compile(
    r"[\u0600-\u06FF\u200c]+?"
    r"(?:[\u0647\u06be](?:\u200c[\u06cc\u064a]|[\u0654\u0674]|[\s][\u06cc\u064a])|[\u0650])"
)
_EZAFE_CHAIN_RE: Pattern = re.compile(
    rf"(?:{_EZAFE_WORD_RE.pattern}\s+){{2,}}{_EZAFE_WORD_RE.pattern}",
    re.UNICODE,
)

#: TRN-013 structural grammar: redundant generic «یک» before a generic
#: class subject at sentence start followed by a generic predicate.
_GENERIC_ARTICLE_RE: Pattern = re.compile(
    r"(?:^|[.؟!؛\n]\s*|«\s*)یک\s+[\u0600-\u06FF\u200c]+\s+"
    r"(?:باید|نباید|می‌تواند|نمی‌تواند|است|هستند|می‌بایست|شاید)\b",
    re.UNICODE,
)


def lint_text(
    content: str, skip_code_blocks: bool = True, enforce_bidi_isolation: bool = False
) -> List[LintIssue]:
    """Analyze Persian text and return list of detected lint issues.

    Args:
        content: The text/markdown content to analyze.
        skip_code_blocks: If True, ignore lines inside fenced code blocks (```).
        enforce_bidi_isolation: If True, every bare Latin token in a Persian
            sentence is flagged; otherwise only tokens risking bidi corruption
            (digits, dots, slashes, or other neutrals inside the token).
    """
    issues: List[LintIssue] = []
    lines = content.splitlines()

    total_opening_quotes = 0
    total_closing_quotes = 0
    in_code_block = False

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            if skip_code_blocks:
                continue

        if skip_code_blocks and in_code_block:
            continue

        # 1. Em-dash, en-dash, and standalone double-hyphen detection.
        for dash_char, name in [("—", "em-dash"), ("–", "en-dash")]:
            if dash_char in line:
                issues.append(
                    LintIssue(
                        line_number=idx,
                        category="em-dash",
                        message=f"Lingering {name} ('{dash_char}') found. Eradicate or adapt into authentic Persian punctuation.",
                        snippet=line.strip(),
                        suggestion="Replace with a Persian comma (،) or parentheses; run AntiCalqueEngine.eliminate_em_dashes().",
                    )
                )
        if _DOUBLE_HYPHEN_PATTERN.search(line):
            issues.append(
                LintIssue(
                    line_number=idx,
                    category="em-dash",
                    message="Lingering standalone double-hyphen ('--') found. It reads as an em-dash in Persian prose.",
                    snippet=line.strip(),
                    suggestion="Replace with a Persian comma (،) or parentheses.",
                )
            )

        # 2. Straight/curly quotes that must become «».
        for qp in _STRAIGHT_QUOTE_PATTERNS:
            match = qp.search(line)
            if match:
                issues.append(
                    LintIssue(
                        line_number=idx,
                        category="quote-style",
                        message=f"Non-Persian quotation marks {match.group(0)[:24]!r} found. Use Persian guillemets «».",
                        snippet=line.strip(),
                        suggestion="Run AntiCalqueEngine.normalize_quotes().",
                    )
                )
                break

        # 3. Banned calques (expanded Najafi/Samii table).
        for calque_name, pattern in BANNED_CALQUE_PATTERNS:
            match = pattern.search(line)
            if match:
                issues.append(
                    LintIssue(
                        line_number=idx,
                        category="calque",
                        message=f"Possible calque: '{calque_name}'. Check the context before changing it.",
                        snippet=line.strip(),
                        suggestion="Rewrite by meaning if it is a calque; keep it if the literal sense is meant.",
                    )
                )

        # 4. Missing ZWNJ after verbal prefixes می/نمی.
        for zp in _ZWNJ_PATTERNS:
            if zp.search(line):
                issues.append(
                    LintIssue(
                        line_number=idx,
                        category="zwnj",
                        message="Missing ZWNJ (نیم‌فاصله) after verbal prefix می/نمی. Write می‌/نمی‌ joined.",
                        snippet=line.strip(),
                        suggestion="Run AntiCalqueEngine.normalize_zwnj().",
                    )
                )
                break

        # 5. Arabic characters (ي, ك, ى, ة, ـ).
        arabic_chars_found = sorted({ch for ch in LINT_ARABIC_CHARS if ch in line})
        if arabic_chars_found:
            chars_str = ", ".join(f"'{c}'" for c in arabic_chars_found)
            issues.append(
                LintIssue(
                    line_number=idx,
                    category="arabic",
                    message=f"Non-standard Arabic characters {chars_str} detected. Normalize to Persian 'ی' and 'ک'.",
                    snippet=line.strip(),
                    suggestion="Run AntiCalqueEngine.standardize_arabic_chars().",
                )
            )

        # 7. Bidi isolation: unbalanced isolates + unisolated Latin tokens.
        # Ceiling: counts only (order not validated); bare-token scan strips
        # already-isolated spans and inline code before matching.
        opens = sum(line.count(ch) for ch in _BIDI_OPEN_CHARS)
        closes = line.count(_BIDI_CLOSE_CHAR)
        if opens != closes:
            issues.append(
                LintIssue(
                    line_number=idx,
                    category="bidi-isolate",
                    message=(
                        f"Unbalanced bidi isolates: {opens} opener(s) "
                        f"(LRI/RLI/FSI) vs {closes} closer(s) (PDI)."
                    ),
                    snippet=line.strip(),
                    suggestion="Close every isolate with U+2069 PDI (⁩).",
                )
            )
        elif _PERSIAN_CHAR_RE.search(line):
            bare = _INLINE_CODE_SPAN_RE.sub("", _BIDI_ISOLATED_SPAN_RE.sub("", line))
            match = _BIDI_LATIN_TOKEN_RE.search(bare)
            if match and (
                enforce_bidi_isolation or re.search(r"[0-9/.:_\-]", match.group(0))
            ):
                issues.append(
                    LintIssue(
                        line_number=idx,
                        category="bidi-isolate",
                        message=(
                            f"Unisolated Latin token {match.group(0)!r} in Persian "
                            "sentence; bidi reordering may corrupt it."
                        ),
                        snippet=line.strip(),
                        suggestion="Wrap in LRI…PDI (U+2066…U+2069) isolates.",
                    )
                )

        # 8. Heavy ezafe chain (TRN-013): 3+ consecutive ezafe markers.
        if _EZAFE_CHAIN_RE.search(line):
            issues.append(
                LintIssue(
                    line_number=idx,
                    category="ezafe-chain",
                    message=(
                        "Heavy ezafe chain (3+ consecutive ezafe linkages) "
                        "found; break with a native connective "
                        "(marbut be / motaalleq be) or a relative clause."
                    ),
                    snippet=line.strip(),
                    suggestion="Run StylisticPolishStage.smooth_ezafe_chains().",
                )
            )

        # 9. Redundant generic article (TRN-013): sentence-initial «یک»
        # with a generic class subject; zero-mark (Ø) is idiomatic.
        if _GENERIC_ARTICLE_RE.search(line):
            issues.append(
                LintIssue(
                    line_number=idx,
                    category="generic-article",
                    message=(
                        "Redundant generic «یک» with a generic class subject; "
                        "Persian idiom uses the zero mark (Ø)."
                    ),
                    snippet=line.strip(),
                    suggestion="Drop «یک» for generic class subjects.",
                )
            )

        # 9b. Suggest-only AI tells (never auto-fixed; meaning decides).
        for tell_label, tell_re, tell_advice in LINT_AI_TELL_PATTERNS:
            tell_match = re.search(tell_re, line)
            if tell_match:
                issues.append(
                    LintIssue(
                        line_number=idx,
                        category="ai-tell",
                        message=f"AI-style phrasing ({tell_label}): «{tell_match.group(0)}».",
                        snippet=line.strip(),
                        suggestion=tell_advice,
                    )
                )

        # 10. Hekasre detection (v2.3.0)
        for hit, fix, tier in find_hekasre(line):
            conf = "likely" if tier == "A" else "possible"
            issues.append(
                LintIssue(
                    line_number=idx,
                    category="hekasre",
                    message=(
                        f"Probable hekasre: \u00ab{hit}\u00bb \u2192 \u00ab{fix}\u00bb ({conf} "
                        f"\u0647\u06a9\u0633\u0631\u0647: ezafe kasre written as \u0640\u0647)"
                    ),
                    snippet=line.strip(),
                    suggestion=f"\u00ab{hit}\u00bb \u2192 \u00ab{fix}\u00bb",
                )
            )

        # 11. Tanvin detection (v2.3.0): missing tanvin on Arabic loans
        for bare, correct in _TANVIN_NEEDED.items():
            if re.search(_FA_B_L_LINT + re.escape(bare) + _FA_B_R_LINT, line):
                issues.append(
                    LintIssue(
                        line_number=idx,
                        category="tanvin",
                        message=f"Missing tanvin: \u00ab{bare}\u00bb should be \u00ab{correct}\u00bb.",
                        snippet=line.strip(),
                        suggestion=f"{bare} \u2192 {correct}",
                    )
                )

        # 12. Fake tanvin on Persian words (v2.3.0)
        for fake, fix in _FAKE_TANVIN.items():
            if fake in line:
                issues.append(
                    LintIssue(
                        line_number=idx,
                        category="tanvin",
                        message=f"Fake tanvin on Persian word: \u00ab{fake}\u00bb \u2192 \u00ab{fix}\u00bb.",
                        snippet=line.strip(),
                        suggestion=f"{fake} \u2192 {fix}",
                    )
                )

        # Quote counting
        total_opening_quotes += line.count("«")
        total_closing_quotes += line.count("»")

    # 6. Unbalanced Persian quotation marks
    if total_opening_quotes != total_closing_quotes:
        issues.append(
            LintIssue(
                line_number=len(lines) if lines else 1,
                category="quote",
                message=(
                    f"Unbalanced Persian quotation marks: {total_opening_quotes} opening '«' "
                    f"vs {total_closing_quotes} closing '»'."
                ),
                snippet=f"Total '«': {total_opening_quotes}, Total '»': {total_closing_quotes}",
            )
        )

    return issues


def format_report(file_path: str, issues: List[LintIssue]) -> str:
    """Format a diagnostic terminal report for lint issues."""
    lines: List[str] = []
    lines.append(f"{BOLD}Tarjoman Persian Linter Report: {file_path}{RESET}")
    lines.append("=" * 60)

    if not issues:
        lines.append(f"{GREEN}{BOLD}[PASSED]{RESET} No linguistic or typographic issues found. Clean Persian text!")
        return "\n".join(lines)

    lines.append(f"{RED}{BOLD}[FAILED]{RESET} Found {len(issues)} issue(s):\n")

    for i, issue in enumerate(issues, start=1):
        cat_badge = f"{YELLOW}[{issue.category.upper()}]{RESET}"
        lines.append(f" {i}. Line {issue.line_number} {cat_badge}: {issue.message}")
        lines.append(f"    {CYAN}Excerpt:{RESET} {issue.snippet}")
        if issue.suggestion:
            lines.append(f"    {GREEN}Fix:{RESET} {issue.suggestion}")
        lines.append("")

    return "\n".join(lines)
