"""
Suggest terminology candidates from an English source text.

Before a long book is translated, its names and recurring terms should be
decided once and kept in the termbase. Finding them by hand is slow and easy
to skip. ``extract_candidates`` lists capitalised names and phrases that recur
in the text, so a person or an agent can review the list and record the
translations with ``tarjoman book terms --add``.

This is deliberately simple and deterministic: it does not use a language
model or an external NER library. It only proposes; it never writes a term.
A single capitalised word that only ever starts a sentence is ignored, because
that capital tells us nothing. A name that also appears mid-sentence is kept.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set

_RUN_RE = re.compile(r"[A-Z][A-Za-z'’-]*(?:[ \t]+(?:of|the|de|von|van|al|bin|ibn)?[ \t]*[A-Z][A-Za-z'’-]*)*")
_CONNECTORS = {"of", "the", "de", "von", "van", "al", "bin", "ibn"}
_SENTENCE_START_RE = re.compile(r"(?:^|[.!?\"“”]\s+|\n\s*)$")

#: Capitalised function words and common sentence openers that are not terms.
STOPWORDS: Set[str] = {
    "A", "An", "The", "And", "But", "Or", "Nor", "So", "Yet", "For", "If", "When", "While",
    "Then", "Than", "That", "This", "These", "Those", "There", "Here", "It", "Its", "I", "We",
    "You", "He", "She", "They", "Me", "Him", "Her", "Us", "Them", "My", "Your", "His", "Our",
    "Their", "In", "On", "At", "By", "To", "Of", "From", "With", "Without", "As", "Into",
    "Yes", "No", "Oh", "Well", "Now", "Still", "Just", "Only", "Not", "Let", "Do", "Did",
    "Is", "Was", "Are", "Were", "Be", "Have", "Had", "Has", "What", "Who", "Why", "How",
    "Where", "Which", "All", "Some", "Any", "Each", "Every", "Once", "After", "Before",
    "Chapter", "Part", "Book", "Volume", "Contents", "Mr", "Mrs", "Ms", "Dr",
}


@dataclass
class Candidate:
    term: str
    count: int
    example: str


def _is_sentence_start(text: str, pos: int) -> bool:
    return bool(_SENTENCE_START_RE.search(text[max(0, pos - 4) : pos]))


def extract_candidates(
    text: str,
    min_count: int = 3,
    max_items: int = 200,
    known: Optional[Iterable[str]] = None,
) -> List[Candidate]:
    """Return recurring capitalised terms, most frequent first.

    ``known`` terms (already in the termbase) are left out, case-insensitively.
    """
    known_fold = {k.casefold() for k in (known or [])}
    counts: Counter = Counter()
    mid_sentence: Counter = Counter()
    example: Dict[str, str] = {}
    for m in _RUN_RE.finditer(text):
        raw = m.group(0)
        tokens = list(re.finditer(r"\S+", raw))
        i = 0
        while i < len(tokens) and (tokens[i].group() in STOPWORDS or tokens[i].group() in _CONNECTORS):
            i += 1
        if i >= len(tokens):
            continue
        pos = m.start() + tokens[i].start()
        raw = raw[tokens[i].start() :]
        words = raw.split()
        term = re.sub(r"\s+", " ", raw).strip()
        if len(words) == 1 and (term in STOPWORDS or len(term) < 3):
            continue
        if term.casefold() in known_fold:
            continue
        counts[term] += 1
        if len(words) > 1 or not _is_sentence_start(text, pos):
            mid_sentence[term] += 1  # a single word needs one non-initial use to count
        if term not in example:
            start = max(0, pos - 30)
            example[term] = re.sub(r"\s+", " ", text[start : m.end() + 30]).strip()
    out = [
        Candidate(term=t, count=c, example=example[t])
        for t, c in counts.most_common()
        if c >= min_count and mid_sentence[t] > 0
    ]
    out.sort(key=lambda c: (-c.count, c.term))
    return out[:max_items]


def candidates_to_tsv(candidates: List[Candidate]) -> str:
    rows = ["english_term\tcount\texample"]
    rows += [f"{c.term}\t{c.count}\t{c.example}" for c in candidates]
    return "\n".join(rows) + "\n"
