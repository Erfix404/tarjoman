"""
Persian Markdown & Translation Linter for Tarjoman Universal Engine.

Checks Persian text/markdown files for:
1. Lingering em-dashes and en-dashes ('—', '–')
2. Banned structural and lexical calques ('توسط', 'نقش بازی کردن', 'روی ... حساب کردن', etc.)
3. Unbalanced Persian quotation marks ('«' vs '»')
4. Non-standard Arabic characters ('ي', 'ك') instead of Persian ('ی', 'ک')
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import List, Pattern, Tuple

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
    category: str  # "em-dash", "calque", "quote", "arabic"
    message: str
    snippet: str


BANNED_CALQUE_PATTERNS: List[Tuple[str, Pattern]] = [
    ("توسط (passive-by calque)", re.compile(r"\bتوسط\s+([^\s،.\n]+)", re.UNICODE)),
    ("نقش بازی کردن (play a role calque)", re.compile(r"نقش(?:ی)?(?:\s+[^\n،.]*?)?\s+بازی\s+(?:کردن|کرد|کرده|کرده‌اند|کردند|می‌کند|می‌کرد|کنند|کند)", re.UNICODE)),
    ("روی ... حساب کردن (count on calque)", re.compile(r"روی\s+[^\n،.]+?\s+حساب\s+(?:کردن|کرد|کرده|کردند|می‌کنم|می‌کنی|می‌کند|کنید|کنیم|کن|نکن)", re.UNICODE)),
    ("در پایان روز (at the end of the day calque)", re.compile(r"در پایان روز", re.UNICODE)),
    ("حس ایجاد کردن (makes sense calque)", re.compile(r"حس ایجاد\s+(?:می‌کند|می‌کرد|کرد|کردن)", re.UNICODE)),
    ("یک تصمیم گرفتن (make a decision calque)", re.compile(r"یک\s+تصمیم\s+(?:گرفتن|گرفت|گرفتند|گرفته|می‌گیرد|می‌گیرند)", re.UNICODE)),
    ("آتش گشودن (open fire calque)", re.compile(r"آتش\s+(?:گشودن|گشود|گشودند|گشوده)", re.UNICODE)),
    ("حمام گرفتن (take a bath calque)", re.compile(r"حمام\s+(?:گرفتن|گرفت|گرفتند|می‌گیرد)", re.UNICODE)),
    ("نقطه نظر (point of view calque)", re.compile(r"نقطه[‌\s]?(?:نظر|نظرات|نظرها)", re.UNICODE)),
    ("چراغ سبز نشان دادن (give green light calque)", re.compile(r"چراغ\s+سبز\s+نشان\s+(?:دادن|داد|دادند|می‌دهد)", re.UNICODE)),
    ("به پایان خط رسیدن (reach end of the line calque)", re.compile(r"به پایان خط\s+(?:رسیدن|رسید|رسیدند|می‌رسد)", re.UNICODE)),
    ("به عنوان ... عمل کردن (act as calque)", re.compile(r"به عنوانِ?\s+[^\n،.]+?\s+عمل\s+(?:کردن|کرد|می‌کند|کردند)", re.UNICODE)),
]


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

        # 1. Em-dash and En-dash detection
        for dash_char, name in [("—", "em-dash"), ("–", "en-dash")]:
            if dash_char in line:
                issues.append(
                    LintIssue(
                        line_number=idx,
                        category="em-dash",
                        message=f"Lingering {name} ('{dash_char}') found. Eradicate or adapt into authentic Persian punctuation.",
                        snippet=line.strip(),
                    )
                )

        # 2. Banned Calques
        for calque_name, pattern in BANNED_CALQUE_PATTERNS:
            match = pattern.search(line)
            if match:
                issues.append(
                    LintIssue(
                        line_number=idx,
                        category="calque",
                        message=f"Banned calque detected: '{calque_name}'.",
                        snippet=line.strip(),
                    )
                )

        # 3. Arabic Characters (ي, ك, ى)
        arabic_chars_found = set()
        for ch in ["ي", "ك", "ى"]:
            if ch in line:
                arabic_chars_found.add(ch)
        if arabic_chars_found:
            chars_str = ", ".join(f"'{c}'" for c in sorted(arabic_chars_found))
            issues.append(
                LintIssue(
                    line_number=idx,
                    category="arabic",
                    message=f"Non-standard Arabic characters {chars_str} detected. Normalize to Persian 'ی' and 'ک'.",
                    snippet=line.strip(),
                )
            )

        # Quote counting
        total_opening_quotes += line.count("«")
        total_closing_quotes += line.count("»")

    # 4. Unbalanced Persian quotation marks
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
        lines.append("")

    return "\n".join(lines)
