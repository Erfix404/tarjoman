"""
Book Translation Manifest for Tarjoman Long-Form Projects (Super-Skill v2).

Content-hash-based (SHA-256) manifest management for resumable multi-chapter
book translation:

- :func:`sha256_text`: deterministic content hashing.
- :class:`ChunkRecord`: per-chunk metadata (hash, status, word counts).
- :class:`ChapterRecord`: per-chapter metadata aggregating chunk records.
- :class:`BookManifestManager`: manifest lifecycle — add chapters/chunks,
  update statuses, skip already-translated hashes, serialize to ``manifest.json``.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

MANIFEST_VERSION = "2.0"

CHUNK_STATUS_PENDING = "pending"
CHUNK_STATUS_TRANSLATED = "translated"
CHUNK_STATUS_FAILED = "failed"


def sha256_text(text: str) -> str:
    """Return the hex SHA-256 digest of ``text`` (UTF-8)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ChunkRecord:
    """Metadata for one translatable chunk of a chapter."""

    chunk_id: int
    content_hash: str
    status: str = CHUNK_STATUS_PENDING
    source_words: int = 0
    translated_words: int = 0
    translated_hash: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChunkRecord":
        return cls(
            chunk_id=int(data.get("chunk_id", 0)),
            content_hash=str(data.get("content_hash", "")),
            status=str(data.get("status", CHUNK_STATUS_PENDING)),
            source_words=int(data.get("source_words", 0)),
            translated_words=int(data.get("translated_words", 0)),
            translated_hash=str(data.get("translated_hash", "")),
            updated_at=str(data.get("updated_at", "")),
        )


@dataclass
class ChapterRecord:
    """Metadata for one chapter: ordered chunk records + word counts."""

    chapter_id: int
    title: str = ""
    chunks: List[ChunkRecord] = field(default_factory=list)
    source_words: int = 0
    translated_words: int = 0

    @property
    def status(self) -> str:
        if not self.chunks:
            return CHUNK_STATUS_PENDING
        if all(c.status == CHUNK_STATUS_TRANSLATED for c in self.chunks):
            return CHUNK_STATUS_TRANSLATED
        if any(c.status == CHUNK_STATUS_FAILED for c in self.chunks):
            return CHUNK_STATUS_FAILED
        return CHUNK_STATUS_PENDING

    @property
    def progress(self) -> float:
        if not self.chunks:
            return 0.0
        done = sum(1 for c in self.chunks if c.status == CHUNK_STATUS_TRANSLATED)
        return done / len(self.chunks)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_id": self.chapter_id,
            "title": self.title,
            "status": self.status,
            "source_words": self.source_words,
            "translated_words": self.translated_words,
            "chunks": [c.to_dict() for c in self.chunks],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChapterRecord":
        return cls(
            chapter_id=int(data.get("chapter_id", 0)),
            title=str(data.get("title", "")),
            chunks=[ChunkRecord.from_dict(c) for c in data.get("chunks", [])],
            source_words=int(data.get("source_words", 0)),
            translated_words=int(data.get("translated_words", 0)),
        )


class BookManifestManager:
    """
    SHA-256-based resumable manifest for book translation projects.

    Small interface: add chapters/chunks, mark translated, ask what is still
    pending (``pending_chunks`` skips hashes already translated), serialize.
    """

    def __init__(
        self,
        title: str = "",
        source_language: str = "en",
        target_language: str = "fa",
        manifest_path: Optional[Union[str, Path]] = None,
        _skip_load: bool = False,
    ) -> None:
        self.title = title
        self.source_language = source_language
        self.target_language = target_language
        self.manifest_path = Path(manifest_path) if manifest_path else None
        self.chapters: List[ChapterRecord] = []
        if self.manifest_path and self.manifest_path.exists() and not _skip_load:
            self.load(self.manifest_path)

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_chapter(self, chapter_id: int, title: str = "") -> ChapterRecord:
        existing = self.get_chapter(chapter_id)
        if existing is not None:
            if title:
                existing.title = title
            return existing
        chapter = ChapterRecord(chapter_id=chapter_id, title=title)
        self.chapters.append(chapter)
        self.chapters.sort(key=lambda c: c.chapter_id)
        return chapter

    def add_chunk(self, chapter_id: int, source_text: str) -> ChunkRecord:
        """Register a source chunk; identical content hashes deduplicate."""
        chapter = self.add_chapter(chapter_id)
        content_hash = sha256_text(source_text)
        for chunk in chapter.chunks:
            if chunk.content_hash == content_hash:
                return chunk
        chunk = ChunkRecord(
            chunk_id=len(chapter.chunks) + 1,
            content_hash=content_hash,
            source_words=len(source_text.split()),
            updated_at=_utcnow(),
        )
        chapter.chunks.append(chunk)
        chapter.source_words += chunk.source_words
        return chunk

    def is_translated(self, chapter_id: int, source_text: str) -> bool:
        """True when a chunk with this content hash is already translated."""
        chapter = self.get_chapter(chapter_id)
        if chapter is None:
            return False
        content_hash = sha256_text(source_text)
        return any(
            c.content_hash == content_hash and c.status == CHUNK_STATUS_TRANSLATED
            for c in chapter.chunks
        )

    def mark_translated(
        self, chapter_id: int, source_text: str, translated_text: str
    ) -> Optional[ChunkRecord]:
        """Mark the chunk matching ``source_text`` translated; cache its hash."""
        chapter = self.get_chapter(chapter_id)
        if chapter is None:
            return None
        content_hash = sha256_text(source_text)
        for chunk in chapter.chunks:
            if chunk.content_hash == content_hash:
                chunk.status = CHUNK_STATUS_TRANSLATED
                chunk.translated_text = translated_text  # type: ignore[attr-defined]
                chunk.translated_hash = sha256_text(translated_text)
                chunk.translated_words = len(translated_text.split())
                chunk.updated_at = _utcnow()
                chapter.translated_words = sum(
                    c.translated_words
                    for c in chapter.chunks
                    if c.status == CHUNK_STATUS_TRANSLATED
                )
                return chunk
        # Unknown chunk: register then mark.
        chunk = self.add_chunk(chapter_id, source_text)
        return self.mark_translated(chapter_id, source_text, translated_text)

    def mark_failed(self, chapter_id: int, source_text: str) -> Optional[ChunkRecord]:
        chapter = self.get_chapter(chapter_id)
        if chapter is None:
            return None
        content_hash = sha256_text(source_text)
        for chunk in chapter.chunks:
            if chunk.content_hash == content_hash:
                chunk.status = CHUNK_STATUS_FAILED
                chunk.updated_at = _utcnow()
                return chunk
        return None

    def pending_chunks(self, chapter_id: Optional[int] = None) -> List[tuple]:
        """List ``(chapter_id, ChunkRecord)`` still needing translation (resume)."""
        out: List[tuple] = []
        chapters = (
            [self.get_chapter(chapter_id)]
            if chapter_id is not None
            else self.chapters
        )
        for chapter in chapters:
            if chapter is None:
                continue
            for chunk in chapter.chunks:
                if chunk.status != CHUNK_STATUS_TRANSLATED:
                    out.append((chapter.chapter_id, chunk))
        return out

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_chapter(self, chapter_id: int) -> Optional[ChapterRecord]:
        for chapter in self.chapters:
            if chapter.chapter_id == chapter_id:
                return chapter
        return None

    def get_stats(self) -> Dict[str, Any]:
        total_chunks = sum(len(c.chunks) for c in self.chapters)
        done_chunks = sum(
            1 for c in self.chapters for ch in c.chunks if ch.status == CHUNK_STATUS_TRANSLATED
        )
        return {
            "title": self.title,
            "total_chapters": len(self.chapters),
            "total_chunks": total_chunks,
            "translated_chunks": done_chunks,
            "pending_chunks": total_chunks - done_chunks,
            "progress": (done_chunks / total_chunks) if total_chunks else 0.0,
            "source_words": sum(c.source_words for c in self.chapters),
            "translated_words": sum(c.translated_words for c in self.chapters),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "manifest_version": MANIFEST_VERSION,
            "title": self.title,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "chapters": [c.to_dict() for c in self.chapters],
        }

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], manifest_path: Optional[Union[str, Path]] = None
    ) -> "BookManifestManager":
        mgr = cls(
            title=str(data.get("title", "")),
            source_language=str(data.get("source_language", "en")),
            target_language=str(data.get("target_language", "fa")),
            manifest_path=manifest_path,
            _skip_load=True,
        )
        mgr.chapters = [ChapterRecord.from_dict(c) for c in data.get("chapters", [])]
        return mgr

    def save(self, path: Optional[Union[str, Path]] = None) -> Path:
        target = Path(path) if path else self.manifest_path
        if target is None:
            raise ValueError("No manifest path configured; pass `path` explicitly.")
        if target.parent and str(target.parent) not in ("", "."):
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.manifest_path = target
        return target

    def load(self, path: Union[str, Path]) -> "BookManifestManager":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        fresh = self.from_dict(data, manifest_path=path)
        self.title = fresh.title
        self.source_language = fresh.source_language
        self.target_language = fresh.target_language
        self.chapters = fresh.chapters
        self.manifest_path = Path(path)
        return self
