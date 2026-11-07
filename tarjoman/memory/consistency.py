"""
Cross-chapter consistency checks for book translation projects.

These checks are read-only and report findings for the translator to judge:

- Terminology: a termbase entry whose English term appears in the source
  chapter, but whose Persian equivalent is missing from the translation.
- Character names: a character whose English name appears in the source,
  but whose recorded Persian name is missing from the translation.
- Register mix: dialogue that mixes standard written verb forms
  («می‌خواهم»، «می‌توانم») with colloquial ones («می‌خوام»، «می‌تونم»)
  in the same chapter, which reads as an inconsistent voice.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

#: Standard (written) forms and their colloquial counterparts. Used only to
#: detect a chapter that uses both styles in dialogue.
REGISTER_PAIRS: Tuple[Tuple[str, str], ...] = (
    ("می‌خواهم", "می‌خوام"),
    ("می‌خواهی", "می‌خوای"),
    ("می‌خواهد", "می‌خواد"),
    ("می‌توانم", "می‌تونم"),
    ("می‌توانی", "می‌تونی"),
    ("می‌تواند", "می‌تونه"),
    ("می‌دانم", "می‌دونم"),
    ("نمی‌دانم", "نمی‌دونم"),
    ("می‌گویم", "می‌گم"),
    ("می‌گوید", "می‌گه"),
    ("می‌روم", "می‌رم"),
    ("می‌رود", "می‌ره"),
    ("می‌شود", "می‌شه"),
    ("بگذار", "بذار"),
    ("آن‌ها", "اونا"),
)

_DIALOGUE_RE = re.compile(r"«([^»]*)»")
_FA_LEFT = r"(?<![؀-ۿ‌])"
_FA_RIGHT = r"(?![؀-ۿ‌])"


@dataclass
class ConsistencyFinding:
    category: str  # "term" | "character" | "register"
    message: str


def _word_re(word: str) -> "re.Pattern[str]":
    return re.compile(_FA_LEFT + re.escape(word) + _FA_RIGHT)


def check_terms(source: str, target: str, terms: Dict[str, str]) -> List[ConsistencyFinding]:
    """Report termbase entries used in the source but not rendered as recorded."""
    findings: List[ConsistencyFinding] = []
    for en_term, fa_term in sorted(terms.items()):
        if not en_term or not fa_term:
            continue
        if re.search(rf"\b{re.escape(en_term)}\b", source, re.IGNORECASE) and fa_term not in target:
            findings.append(
                ConsistencyFinding(
                    "term",
                    f"«{en_term}» appears in the source but «{fa_term}» is not in the translation.",
                )
            )
    return findings


def check_characters(
    source: str, target: str, characters: Iterable[Tuple[str, str]]
) -> List[ConsistencyFinding]:
    """Report characters named in the source whose Persian name is missing."""
    findings: List[ConsistencyFinding] = []
    for name, fa_name in characters:
        if not name or not fa_name:
            continue
        if re.search(rf"\b{re.escape(name)}\b", source) and fa_name not in target:
            findings.append(
                ConsistencyFinding(
                    "character",
                    f"«{name}» appears in the source but its recorded name «{fa_name}» is not in the translation.",
                )
            )
    return findings


def check_register_mix(target: str) -> List[ConsistencyFinding]:
    """Report dialogue that mixes standard and colloquial forms of the same verbs."""
    dialogue = "\n".join(_DIALOGUE_RE.findall(target))
    if not dialogue:
        return []
    standard_hits: List[str] = []
    colloquial_hits: List[str] = []
    for standard, colloquial in REGISTER_PAIRS:
        if _word_re(standard).search(dialogue):
            standard_hits.append(standard)
        if _word_re(colloquial).search(dialogue):
            colloquial_hits.append(colloquial)
    if standard_hits and colloquial_hits:
        return [
            ConsistencyFinding(
                "register",
                "Dialogue mixes standard forms ("
                + "، ".join(standard_hits[:4])
                + ") with colloquial forms ("
                + "، ".join(colloquial_hits[:4])
                + "). Check each character's register in the style sheet.",
            )
        ]
    return []


def check_chapter(
    source: str,
    target: str,
    terms: Dict[str, str],
    characters: Iterable[Tuple[str, str]],
) -> List[ConsistencyFinding]:
    """Run every consistency check on one chapter."""
    return (
        check_terms(source, target, terms)
        + check_characters(source, target, characters)
        + check_register_mix(target)
    )
