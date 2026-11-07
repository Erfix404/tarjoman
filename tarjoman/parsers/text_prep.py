"""
Clean text extracted from a PDF before translating it.

Text copied out of a PDF (``pdftotext``, a reader's "copy", OCR) carries
noise that a translator should never see: running headers and footers
repeated on every page, bare page numbers, words broken across lines with a
hyphen, and paragraphs hard-wrapped into short lines. Translating that noise
wastes effort and produces garbage («فصل ۳ ... ۱۴۷» in the middle of a
sentence).

``prepare_text`` fixes the safe cases and reports what it did:

- Page breaks are form feeds (``\\f``), as ``pdftotext`` writes them. When
  they are present, a short line repeated at the top or bottom of at least a
  quarter of the pages is a running header/footer and is removed; so are
  page-number-only lines at a page edge.
- ``exam-`` + ``ple`` across a line break is rejoined to ``example``.
- Hard-wrapped lines inside a paragraph are joined with a space. Blank lines,
  headings (``#``), list items and fenced code are left alone.

The header/footer and de-hyphenation approach is adapted from Kaman AI
Translator (MIT, https://github.com/Mohammad-Hasan-Kaman/kaman-ai-translator).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Set

_PAGE_NUMBER_RE = re.compile(
    r"^\s*(?:page\s+|p\.\s*|صفحه\s+)?[-–—(\[]?\s*[\d۰-۹]+\s*[-–—)\]]?\s*$", re.IGNORECASE
)
_HYPHEN_BREAK_RE = re.compile(r"([A-Za-z]{2,})-\n([a-z]{2,})")
_BLOCK_START_RE = re.compile(r"^\s*(?:#|[-*+•]\s|\d+[.)]\s|>|\||```)")

EDGE_LINES = 2
MIN_HEADER_PAGES = 3
MIN_HEADER_RATIO = 0.25
MAX_HEADER_LEN = 80


@dataclass
class PrepReport:
    pages: int = 0
    removed_headers: Dict[str, int] = field(default_factory=dict)
    removed_page_numbers: int = 0
    rejoined_hyphens: int = 0
    joined_lines: int = 0

    def summary(self) -> str:
        parts = [f"pages: {self.pages}"]
        if self.removed_headers:
            parts.append(
                "removed running header/footer lines: "
                + "; ".join(f"«{k}» ×{v}" for k, v in sorted(self.removed_headers.items()))
            )
        parts.append(f"page-number lines removed: {self.removed_page_numbers}")
        parts.append(f"hyphenated words rejoined: {self.rejoined_hyphens}")
        parts.append(f"wrapped lines joined: {self.joined_lines}")
        return "\n".join(parts)


def _norm(line: str) -> str:
    # Digits vary between pages («Chapter 3 · 147»), so compare without them.
    return re.sub(r"[\d۰-۹]+", "#", " ".join(line.split()).casefold())


def _edge_indexes(lines: List[str]) -> List[int]:
    nonempty = [i for i, ln in enumerate(lines) if ln.strip()]
    return sorted(set(nonempty[:EDGE_LINES] + nonempty[-EDGE_LINES:]))


def _find_running_lines(pages: List[List[str]]) -> Set[str]:
    counts: Dict[str, int] = {}
    for lines in pages:
        seen: Set[str] = set()
        for i in _edge_indexes(lines):
            key = _norm(lines[i])
            if key and len(key) <= MAX_HEADER_LEN and key not in seen:
                seen.add(key)
                counts[key] = counts.get(key, 0) + 1
    threshold = max(MIN_HEADER_PAGES, int(len(pages) * MIN_HEADER_RATIO))
    return {k for k, v in counts.items() if v >= threshold}


def _strip_page_noise(pages: List[List[str]], report: PrepReport) -> List[str]:
    running = _find_running_lines(pages) if len(pages) >= MIN_HEADER_PAGES else set()
    out: List[str] = []
    for lines in pages:
        edges = set(_edge_indexes(lines))
        for i, line in enumerate(lines):
            if i in edges and _PAGE_NUMBER_RE.match(line):
                report.removed_page_numbers += 1
                continue
            if i in edges and _norm(line) in running:
                key = " ".join(line.split())
                report.removed_headers[key] = report.removed_headers.get(key, 0) + 1
                continue
            out.append(line)
        # A page break ends the paragraph only when the page ends a sentence;
        # otherwise the paragraph continues on the next page.
        while out and not out[-1].strip():
            out.pop()
        if out and out[-1].rstrip().endswith((".", "!", "?", ":", "\"", "”", "»", "؟")):
            out.append("")
    return out


def _unwrap(lines: List[str], report: PrepReport) -> List[str]:
    out: List[str] = []
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence or not stripped:
            out.append(line if in_fence else "")
            continue
        prev = out[-1] if out else ""
        if (
            prev.strip()
            and not prev.lstrip().startswith(("#", "```"))
            and not _BLOCK_START_RE.match(line)
            and not prev.rstrip().endswith(("  ", "\\"))
        ):
            out[-1] = prev.rstrip() + " " + stripped
            report.joined_lines += 1
        else:
            out.append(line.rstrip())
    return out


def prepare_text(text: str, unwrap: bool = True) -> "tuple[str, PrepReport]":
    """Return (clean_text, report). Never touches fenced code blocks' content."""
    report = PrepReport()
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    raw_pages = text.split("\f")
    # pdftotext ends the file with a form feed: drop the empty last "page".
    if len(raw_pages) > 1 and not raw_pages[-1].strip():
        raw_pages = raw_pages[:-1]
    report.pages = len(raw_pages)
    pages = [p.split("\n") for p in raw_pages]

    if len(pages) > 1:
        lines = _strip_page_noise(pages, report)
    else:
        lines = pages[0]

    joined = "\n".join(lines)
    joined, n = _HYPHEN_BREAK_RE.subn(r"\1\2", joined)
    report.rejoined_hyphens = n
    lines = joined.split("\n")

    if unwrap:
        lines = _unwrap(lines, report)

    clean = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"
    return clean, report
