#!/usr/bin/env python3
"""
Persian Markdown & Translation Linter for Tarjoman (Super-Skill v2).

Standalone stdlib-only skillpack script. Consumes the shared pattern table in
``tarjoman.stages.anti_calque`` when the package is importable, and falls back
to a vendored copy of the same table when run outside the repo checkout.

Checks Persian text/markdown files for:
1. Guaranteed ZERO em-dashes: '—', '–', and standalone '--' (CLI flags untouched)
2. Straight/curly quotes that must become Persian guillemets «»
3. Expanded banned structural and lexical calques (Najafi/Samii, incl. وي)
4. Missing ZWNJ after verbal prefixes می/نمی
5. Unbalanced Persian quotation marks ('«' vs '»')
6. Non-standard Arabic characters ('ي', 'ك', 'ى', 'ة', 'ـ')

Exit codes:
- 0: Clean / PASSED
- 1: Issues detected / FAILED
- 2: File access error / Invalid arguments
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from typing import List, Pattern, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


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
    category: str  # "em-dash", "quote-style", "calque", "zwnj", "quote", "arabic"
    message: str
    snippet: str
    suggestion: str = field(default="")


def _load_shared_tables() -> Tuple[
    List[Tuple[str, str]], str, Tuple[str, ...], Tuple[str, ...]
]:
    """Load shared patterns from tarjoman.stages.anti_calque when available."""
    try:
        repo_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        from tarjoman.stages import anti_calque as ac

        return (
            list(ac.LINT_CALQUE_PATTERNS),
            ac.LINT_DOUBLE_HYPHEN_RE,
            tuple(ac.LINT_STRAIGHT_QUOTE_RES),
            tuple(ac.LINT_ZWNJ_RES),
        )
    except Exception:
        return None, None, None, None


_SHARED = _load_shared_tables()

# Vendored fallback (mirrors tarjoman/stages/anti_calque.py tables).
_FALLBACK_CALQUES: List[Tuple[str, str]] = [
    ("توسط (passive-by calque)", r"\bتوسط\b"),
    ("به‌وسیله/از سوی (passive-by calque)", r"\bبه\s*وسیله[‌ی]?\b|\bاز\s+سوی\b"),
    (
        "نقش بازی کردن (play a role calque)",
        r"نقش(?:ی)?(?:\s+[^\n،.]*)?\s+بازی\s+(?:کردن|کرد|کرده|کرده‌اند|کردند|می‌کند|می‌کرد|کنند|کند)",
    ),
    (
        "روی ... حساب کردن (count on calque)",
        r"روی\s+[^\n،.]+?\s+حساب\s+(?:کردن|کرد|کرده|کردند|می‌کنم|می‌کنی|می‌کند|کنید|کنیم|کن|نکن)",
    ),
    (
        "به عنوان ... عمل کردن (act as calque)",
        r"به\s*عنوانِ?\s+[^\n،.]+?\s+عمل\s+(?:کردن|کرد|می‌کند|کردند)",
    ),
    ("در پایان روز (at the end of the day calque)", r"در پایان روز"),
    ("حس ایجاد کردن (makes sense calque)", r"حس ایجاد\s+(?:می‌کند|می‌کرد|کرد|کردن)"),
    (
        "یک تصمیم گرفتن (make a decision calque)",
        r"یک\s+تصمیم\s+(?:گرفتن|گرفت|گرفتند|گرفته|می‌گیرد|می‌گیرند)",
    ),
    ("آتش گشودن (open fire calque)", r"آتش\s+(?:گشودن|گشود|گشودند|گشوده)"),
    ("حمام گرفتن (take a bath calque)", r"حمام\s+(?:گرفتن|گرفت|گرفتند|می‌گیرد)"),
    ("نقطه نظر (point of view calque)", r"نقطه[‌\s\-]?(?:نظر|نظرات|نظرها)"),
    (
        "چراغ سبز نشان دادن (give green light calque)",
        r"چراغ\s+سبز\s+نشان\s+(?:دادن|داد|دادند|می‌دهد)",
    ),
    (
        "به پایان خط رسیدن (reach end of the line calque)",
        r"به پایان خط\s+(?:رسیدن|رسید|رسیدند|می‌رسد)",
    ),
    ("به اجرا درآوردن (execute calque)", r"به\s+اجرا\s+درآورد\w*|به\s+اجرا\s+در(?:آورد|آورده|می‌آورد)\w*"),
    (
        "به کار گرفتن (utilize calque)",
        r"به\s+کار\s+(?:گرفتن|گرفت\w*|می‌گیرد|می‌گیرند|بگیرد|بگیرند)",
    ),
    ("اعمال کردن (apply calque)", r"اعمال\s+(?:کردن|کرد\w*|می‌کند|می‌کنند)"),
    ("به عمل آوردن (perform calque)", r"به\s+عمل\s+آورد\w*|به\s+عمل\s+(?:آورد|آورده|می‌آورد)\w*"),
    ("اقدام/مبادرت به (proceed calque)", r"(?:اقدام|مبادرت)\s+به\b"),
    (
        "مورد استفاده قرار دادن/گرفتن (use calque)",
        r"مورد\s+استفاده\s+قرار\s+(?:داد\w*|ده\w*|گرفت\w*|گیر\w*)",
    ),
    (
        "تحت ... قرار دادن (under-coverage calque)",
        r"تحت\s+(?:پوشش|حمایت|درمان|نظارت|فشار|تعقیب|پیگرد)\s+قرار\s+داد\w*",
    ),
    ("در اختیار قرار دادن (provide calque)", r"در\s+اختیار\s+قرار\s+داد\w*"),
    ("دارای بودن (possess calque)", r"\bدارای\b"),
    ("می‌باشد (copula calque)", r"\bن?می‌باش(?:م|ی|یم|ید|ند)?\b"),
    (
        "گردید (archaic passive calque)",
        r"\bن?می‌گرد(?:د|ند)\b|\bگردید(?:ند)?\b|\bگردیده(?: است|‌اند)?\b|\bب?گردد\b|\bگردیدن\b",
    ),
    (
        "در رابطه با/در ارتباط با/در خصوص (regarding calque)",
        r"در\s+(?:رابطه|ارتباط)\s+با|در\s+خصوص",
    ),
    (
        "جهت به‌معنای برای (purpose calque)",
        r"(?<!از جهت)(?<!بدین جهت)(?<!همین جهت)(?<!این جهت)(?<!آن جهت)(?<!چه جهت)\bجهت\b",
    ),
    ("در حالی که جدا نوشته شده (orthography)", r"\bدر\s+حالی\s+که\b"),
    ("از آنجایی که (orthography)", r"از\s+آنجایی\s+که"),
    ("بنا بر این جدا نوشته شده (orthography)", r"\bبنا\s+بر\s+این\b"),
    ("عنوان کردن (mention calque)", r"\bعنوان\s+(?:کرد\w*|می‌کن\w*|کن\w*)\b"),
    ("قلمداد/تلقی کردن (consider calque)", r"(?:قلمداد|تلقی)\s+(?:کرد\w*|می‌کن\w*)\b"),
    ("وی به‌جای او (pronoun calque)", r"\bوی\b"),
]
_FALLBACK_DOUBLE_HYPHEN = r"(?<!\S)--(?!\S)"
_FALLBACK_QUOTES = (
    r'"[^"\n]+"',
    r"(?<!\w)'[^'\n]+?'(?!\w)",
    r"[“”][^“”\n]+[“”]",
    r"(?<!\w)[‘’][^‘’\n]+[‘’](?!\w)",
)
_FALLBACK_ZWNJ = (r"\bمی\s+[آ-ی]", r"\bنمی\s+[آ-ی]")

_CALQUE_TABLE = _SHARED[0] if _SHARED[0] else _FALLBACK_CALQUES
_DOUBLE_HYPHEN_RE = _SHARED[1] if _SHARED[1] else _FALLBACK_DOUBLE_HYPHEN
_QUOTE_RES = _SHARED[2] if _SHARED[2] else _FALLBACK_QUOTES
_ZWNJ_RES = _SHARED[3] if _SHARED[3] else _FALLBACK_ZWNJ
_ARABIC_CHARS = ("ي", "ك", "ى", "ة", "ـ")

BANNED_CALQUE_PATTERNS: List[Tuple[str, Pattern]] = [
    (name, re.compile(regex, re.UNICODE)) for name, regex in _CALQUE_TABLE
]

_STRAIGHT_QUOTE_PATTERNS: List[Pattern] = [
    re.compile(regex, re.UNICODE) for regex in _QUOTE_RES
]

_ZWNJ_PATTERNS: List[Pattern] = [
    re.compile(regex, re.UNICODE) for regex in _ZWNJ_RES
]

_DOUBLE_HYPHEN_PATTERN: Pattern = re.compile(_DOUBLE_HYPHEN_RE)


def lint_text(content: str, skip_code_blocks: bool = True) -> List[LintIssue]:
    """Analyze Persian text and return list of detected lint issues.

    Args:
        content: The text/markdown content to analyze.
        skip_code_blocks: If True, ignore lines inside fenced code blocks (```).
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
                        suggestion="Replace with a Persian comma (،) or parentheses.",
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
                        message=(
                            "Non-Persian quotation marks "
                            f"{match.group(0)[:24]!r} found. Use Persian guillemets «»."
                        ),
                        snippet=line.strip(),
                        suggestion="Convert to «...».",
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
                        message=f"Banned calque detected: '{calque_name}'.",
                        snippet=line.strip(),
                        suggestion="Rewrite with AntiCalqueEngine.eliminate_calques().",
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
                        suggestion="Join with ZWNJ: می‌رود، نمی‌داند.",
                    )
                )
                break

        # 5. Arabic characters (ي, ك, ى, ة, ـ).
        arabic_chars_found = sorted({ch for ch in _ARABIC_CHARS if ch in line})
        if arabic_chars_found:
            chars_str = ", ".join(f"'{c}'" for c in arabic_chars_found)
            issues.append(
                LintIssue(
                    line_number=idx,
                    category="arabic",
                    message=f"Non-standard Arabic characters {chars_str} detected. Normalize to Persian 'ی' and 'ک'.",
                    snippet=line.strip(),
                    suggestion="Normalize: ي→ی، ك→ک.",
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Tarjoman Linter: Enforces Persian typography, zero em-dash, quote balance, and anti-calque purity."
    )
    parser.add_argument("file", help="Path to Persian Markdown or text file to lint")
    parser.add_argument(
        "--skip-code-blocks",
        dest="skip_code_blocks",
        action="store_true",
        default=True,
        help="Skip linting content inside fenced code blocks (default: True)",
    )
    parser.add_argument(
        "--no-skip-code-blocks",
        dest="skip_code_blocks",
        action="store_false",
        help="Do not skip content inside fenced code blocks",
    )
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"{RED}Error: File not found: {args.file}{RESET}", file=sys.stderr)
        return 2

    try:
        with open(args.file, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as exc:
        print(f"{RED}Error reading file {args.file}: {exc}{RESET}", file=sys.stderr)
        return 2

    issues = lint_text(content, skip_code_blocks=args.skip_code_blocks)
    report = format_report(args.file, issues)
    print(report)

    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
