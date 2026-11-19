"""Text-only EPUB extraction and merge workflow for agent-driven book translation."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Set, Union

from tarjoman.composers.epub_roundtrip import EpubRoundtripComposer
from tarjoman.parsers.epub_parser import EpubParser

_MARKER_RE = re.compile(r"^\[#([A-Za-z0-9_.:-]+)\]\s*$")


def _safe_filename(chapter_id: str, idx: int) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", chapter_id).strip("_") or f"chapter_{idx}"
    return f"{idx:02d}_{stem}.md"


def extract_epub_for_translation(
    epub_path: Union[str, Path], out_dir: Union[str, Path]
) -> Dict[str, Any]:
    """Extract chapter text nodes from ``epub_path`` into marker-delimited files."""
    src_path = Path(epub_path)
    target_dir = Path(out_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    parsed = EpubParser().parse(src_path)
    written_files: List[str] = []
    manifest_chapters: List[Dict[str, Any]] = []
    total_nodes = 0

    for idx, chapter in enumerate(parsed.chapters, start=1):
        fname = _safe_filename(chapter.id, idx)
        blocks = [f"[#{node.id}]\n{node.html_content}" for node in chapter.text_nodes]
        out_file = target_dir / fname
        out_file.write_text(("\n\n".join(blocks) + "\n") if blocks else "", encoding="utf-8")
        written_files.append(str(out_file))
        total_nodes += len(chapter.text_nodes)
        manifest_chapters.append(
            {
                "index": idx,
                "id": chapter.id,
                "title": chapter.title,
                "href": chapter.href,
                "file": fname,
                "nodes": len(chapter.text_nodes),
            }
        )

    manifest = {
        "source_epub": str(src_path),
        "metadata": parsed.metadata,
        "total_chapters": len(parsed.chapters),
        "total_nodes": total_nodes,
        "chapters": manifest_chapters,
    }
    (target_dir / "epub_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "source_epub": str(src_path),
        "out_dir": str(target_dir),
        "chapters": len(parsed.chapters),
        "total_nodes": total_nodes,
        "files": written_files,
    }


def _parse_marker_files(
    paths: List[Path], expected_ids: Set[str], non_empty_ids: Set[str]
) -> Dict[str, str]:
    translations: Dict[str, List[str]] = {}
    problems: List[str] = []

    for path in paths:
        current: str | None = None
        text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        for line in text.split("\n"):
            m = _MARKER_RE.match(line.strip())
            if m:
                current = m.group(1)
                if current in translations:
                    problems.append(f"duplicate marker [#{current}] (in {path.name})")
                else:
                    translations[current] = []
                continue
            if current is None:
                if line.strip():
                    problems.append(
                        f"text before first marker in {path.name}: «{line.strip()[:40]}»"
                    )
                continue
            translations[current].append(line)

    unknown = [nid for nid in translations if nid not in expected_ids]
    missing = [nid for nid in expected_ids if nid not in translations]
    empty = [
        nid
        for nid, lines in translations.items()
        if nid in non_empty_ids and not "\n".join(lines).strip()
    ]
    if unknown:
        problems.append(f"unknown markers: {', '.join(f'[#{n}]' for n in unknown[:20])}")
    if missing:
        problems.append(f"missing markers: {', '.join(f'[#{n}]' for n in missing[:20])}")
    if empty:
        problems.append(f"empty translations for non-empty nodes: {', '.join(f'[#{n}]' for n in empty[:20])}")

    if problems:
        raise ValueError("; ".join(problems))

    return {nid: "\n".join(lines).strip() for nid, lines in translations.items()}


def merge_epub_translation(
    source_epub: Union[str, Path],
    translated_path: Union[str, Path],
    output_epub: Union[str, Path],
) -> Dict[str, Any]:
    """Validate translated [#node_id] markers and rebuild an RTL Persian EPUB 3."""
    src_path = Path(source_epub)
    t_path = Path(translated_path)
    out_path = Path(output_epub)

    parsed = EpubParser().parse(src_path)
    expected_ids: Set[str] = set()
    non_empty_ids: Set[str] = set()
    for ch in parsed.chapters:
        for node in ch.text_nodes:
            expected_ids.add(node.id)
            if node.html_content.strip():
                non_empty_ids.add(node.id)

    if t_path.is_file():
        files = [t_path]
    elif t_path.is_dir():
        files = sorted(
            p
            for p in t_path.iterdir()
            if p.is_file() and p.suffix.lower() in {".md", ".txt"}
        )
    else:
        raise FileNotFoundError(f"Translated path not found: {t_path}")

    if not files:
        raise ValueError(f"No .md/.txt translation files found in {t_path}")

    translations = _parse_marker_files(files, expected_ids, non_empty_ids)
    EpubRoundtripComposer().compose(parsed, translations=translations, output_path=out_path)
    return {
        "source_epub": str(src_path),
        "output_epub": str(out_path),
        "chapters": len(parsed.chapters),
        "merged_nodes": len(translations),
    }
