"""Poetic adapter for literary translation (Pack C).

Detects English poetic passages (poems, songs, hymns, riddles, couplets)
and formats/adapts them into rhythmic Persian verse (موزون و مقفا).
"""
from __future__ import annotations

import re
from typing import List

_POETIC_KEYWORDS = (
    "song", "verse", "riddle", "poem", "chant", "hymn", "ballad",
    "chorus", "stanza", "couplet", "ode", "lullaby",
)

_VERSE_CLASSIFIERS = (
    ("riddle", ("riddle", "what am i", "guess", "speak without a mouth", "معما", "چیستم")),
    ("song", ("song", "sing", "chorus", "lullaby", "ترانه", "سرود", "آواز")),
    ("hymn", ("hymn", "chant", "praise", "hallowed", "glory", "مناجات", "نیایش")),
    ("poem", ("poem", "verse", "ballad", "ode", "stanza", "couplet", "شعر", "بیت", "مثنوی")),
)


class PoeticAdapter:
    """Heuristic detector and formatter for poetic passages."""

    def is_poetic(self, text: str) -> bool:
        """Heuristic: short broken lines, rhyme repetition, or poetic keywords."""
        if not text or not text.strip():
            return False
        lowered = text.lower()
        if any(k in lowered for k in _POETIC_KEYWORDS):
            return True
        lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
        if len(lines) >= 2:
            # Short line breaks: mostly short lines => likely verse.
            shorts = sum(1 for ln in lines if len(ln.split()) <= 10)
            if shorts / len(lines) >= 0.6:
                return True
            # Rhyme pattern: repeated line endings (last 2 letters of last word).
            endings = [
                re.sub(r"[^\w]", "", ln.split()[-1].lower())[-2:]
                for ln in lines if ln.split()
            ]
            if len(endings) >= 2 and len(set(endings)) < len(endings):
                return True
        return False

    def classify_verse_type(self, text: str) -> str:
        """Return one of: poem, song, hymn, riddle, prose."""
        lowered = text.lower()
        for verse_type, keywords in _VERSE_CLASSIFIERS:
            if any(k in lowered for k in keywords):
                return verse_type
        return "prose" if not self.is_poetic(text) else "poem"

    def extract_stanzas(self, text: str) -> List[List[str]]:
        """Split text into stanzas (blank-line separated) of verse lines."""
        stanzas: List[List[str]] = []
        current: List[str] = []
        for line in text.strip().splitlines():
            if line.strip():
                current.append(line.strip())
            elif current:
                stanzas.append(current)
                current = []
        if current:
            stanzas.append(current)
        return stanzas

    def adapt_to_persian_verse(
        self, text: str, form: str = "couplet", rhythm_hint: str = "fa'ulun"
    ) -> str:
        """Render text as a structured rhythmic Persian verse template.

        Ceiling: deterministic template, not LLM generation; an LLM-backed
        verse composer would replace this when quality demands it.
        """
        lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
        body = "\n".join(f"مصرع {i + 1}: {ln}" for i, ln in enumerate(lines))
        return (
            f"[قالب: {form} | وزن: {rhythm_hint}]\n{body}"
            if body else f"[قالب: {form} | وزن: {rhythm_hint}]"
        )

    def format_bilingual_verse(self, en_verse: str, fa_verse: str) -> str:
        """Align English and Persian verse lines side by side."""
        en_lines = [ln.strip() for ln in en_verse.strip().splitlines() if ln.strip()]
        fa_lines = [ln.strip() for ln in fa_verse.strip().splitlines() if ln.strip()]
        width = max(len(en_lines), len(fa_lines))
        rows = []
        for i in range(width):
            en = en_lines[i] if i < len(en_lines) else ""
            fa = fa_lines[i] if i < len(fa_lines) else ""
            rows.append(f"EN: {en}\nFA: {fa}")
        return "\n---\n".join(rows)
