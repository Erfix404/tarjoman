"""Smart context builder for long-form book translation chunks.

Instead of flooding an agent's context window with the entire termbase and
character bible across dozens of chapters, :func:`build_book_context` returns
only the glossary terms, character profiles, scene state, pending cascades, and
recent translation tail relevant to the current source chunk.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from tarjoman.memory.character_bible import CharacterBible
from tarjoman.memory.fidelity import split_paragraphs
from tarjoman.memory.scene_continuity import SceneContinuityTracker
from tarjoman.memory.termbase import Termbase


def _load_terms_tsv(project: Path) -> Dict[str, str]:
    path = project / "terms.tsv"
    terms: Dict[str, str] = {}
    if not path.exists():
        return terms
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith(("english_term\t", "#")):
            continue
        cols = line.split("\t")
        if len(cols) >= 2 and cols[0].strip() and cols[1].strip():
            terms[cols[0].strip()] = cols[1].strip()
    return terms


def _extract_style_excerpt(style_path: Path, max_chars: int = 1200) -> str:
    if not style_path.exists():
        return ""
    keep_headings = (
        "## سبک و سطح زبان",
        "## برچسب‌های تکرارشونده",
        "## تصمیم‌های ثابت",
    )
    lines = style_path.read_text(encoding="utf-8").splitlines()
    selected: List[str] = []
    capturing = False
    for line in lines:
        if line.startswith("## "):
            capturing = any(line.startswith(h) for h in keep_headings)
            if capturing:
                selected.append(line)
            continue
        if capturing and line.strip():
            selected.append(line)
    excerpt = "\n".join(selected).strip()
    if len(excerpt) > max_chars:
        return excerpt[:max_chars].rstrip() + "…"
    return excerpt


def build_book_context(
    project_dir: Union[str, Path],
    source_chunk: str,
    previous_translation: Optional[str] = None,
    tail_paragraphs: int = 2,
) -> Dict[str, Any]:
    """Assemble minimal, chunk-relevant book memory for an agent turn."""
    project = Path(project_dir)

    merged_terms = _load_terms_tsv(project)
    cascades: List[Dict[str, Any]] = []
    db_path = project / "terms.db"
    if db_path.exists():
        termbase = Termbase(db_path=db_path)
        try:
            merged_terms.update(termbase.get_all_terms())
            for ev in termbase.pending_cascades():
                cascades.append(
                    {
                        "en_term": ev.en_term,
                        "old_fa_term": ev.old_fa_term,
                        "new_fa_term": ev.new_fa_term,
                        "affected_segments": [list(p) for p in ev.affected_segments],
                    }
                )
        finally:
            termbase.close()

    matched_terms: List[Dict[str, str]] = []
    for en_term, fa_term in sorted(merged_terms.items()):
        if re.search(rf"\b{re.escape(en_term)}\b", source_chunk, re.IGNORECASE):
            matched_terms.append({"en": en_term, "fa": fa_term})

    matched_characters: List[Dict[str, Any]] = []
    bible_path = project / "characters.json"
    if bible_path.exists():
        bible = CharacterBible(bible_path=bible_path)
        for char in bible.list_characters():
            if re.search(rf"\b{re.escape(char.name)}\b", source_chunk, re.IGNORECASE):
                matched_characters.append(
                    {
                        "name": char.name,
                        "persian_name": char.persian_name,
                        "tone": char.tone,
                        "default_address": char.default_address,
                        "gender": char.gender,
                        "speech_quirks": list(char.speech_quirks),
                        "notes": char.notes,
                    }
                )

    scene_data: Optional[Dict[str, Any]] = None
    scene_path = project / "scene_state.json"
    if scene_path.exists():
        tracker = SceneContinuityTracker(state_path=scene_path)
        current = tracker.get_current_state()
        if current is not None:
            scene_data = current.to_dict()

    previous_tail = ""
    if previous_translation and tail_paragraphs > 0:
        paras = split_paragraphs(previous_translation)
        if paras:
            previous_tail = "\n\n".join(paras[-tail_paragraphs:])

    style_excerpt = _extract_style_excerpt(project / "style.md")

    return {
        "project": str(project),
        "matched_terms": matched_terms,
        "matched_characters": matched_characters,
        "scene": scene_data,
        "pending_cascades": cascades,
        "previous_tail": previous_tail,
        "style_excerpt": style_excerpt,
    }
