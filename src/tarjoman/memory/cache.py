"""
Resumable Cache for Tarjoman Long-Form Book and Document Translation.

Provides persistent, thread-safe, atomic JSON-backed caching to support
pausing and resuming translation of large multi-chapter volumes.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class ResumableCache:
    """
    JSON-backed persistent cache for tracking chunk/segment translation progress.
    Thread-safe and atomic file writes prevent data corruption across interruptions.
    """

    def __init__(self, cache_path: Union[str, Path] = "tarjoman_cache.json") -> None:
        self.cache_path = Path(cache_path)
        self._lock = threading.Lock()
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._load_from_disk()

    @staticmethod
    def compute_key(chapter_id: int, segment_id: int, source_text: str) -> str:
        """
        Compute deterministic SHA-256 composite key for a segment.
        """
        raw = f"{chapter_id}:{segment_id}:{source_text}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _load_from_disk(self) -> None:
        if not self.cache_path.exists():
            return
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self._cache = data
        except Exception:
            # If cache file is empty or corrupted, start with clean state
            self._cache = {}

    def _save_to_disk(self) -> None:
        # Ensure directory exists
        parent = self.cache_path.parent
        if parent and not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)

        target_dir = str(parent) if str(parent) else "."
        # ponytail: JSON-backed single-file cache; upgrade to SQLite / LMDB if segments exceed 100k.
        fd, temp_path = tempfile.mkstemp(
            dir=target_dir, prefix=".cache_tmp_", suffix=".json"
        )
        try:
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, self.cache_path)
        except Exception:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise

    def record_segment(
        self,
        chapter_id: int,
        segment_id: int,
        source_text: str,
        translated_text: str,
        polished_text: Optional[str] = None,
    ) -> None:
        """
        Record translated segment in cache and persist atomically to disk.
        """
        key = self.compute_key(chapter_id, segment_id, source_text)
        entry: Dict[str, Any] = {
            "chapter_id": chapter_id,
            "segment_id": segment_id,
            "source_text": source_text,
            "translated_text": translated_text,
            "polished_text": polished_text,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._cache[key] = entry
            self._save_to_disk()

    def is_completed(self, chapter_id: int, segment_id: int, source_text: str) -> bool:
        """
        Check if segment translation is completed in cache.
        """
        key = self.compute_key(chapter_id, segment_id, source_text)
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return False
            return bool(entry.get("translated_text") or entry.get("polished_text"))

    def get_segment(
        self, chapter_id: int, segment_id: int, source_text: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached segment data if present.
        """
        key = self.compute_key(chapter_id, segment_id, source_text)
        with self._lock:
            entry = self._cache.get(key)
            return dict(entry) if entry is not None else None

    def get_stats(self) -> Dict[str, int]:
        """
        Return cache statistics: total segments cached and count of unique chapters.
        """
        with self._lock:
            chapters = {entry["chapter_id"] for entry in self._cache.values()}
            return {
                "total_cached": len(self._cache),
                "chapters_count": len(chapters),
            }

    def export_chapter(self, chapter_id: int) -> List[Dict[str, Any]]:
        """
        Export all cached segments for a given chapter, ordered by segment_id.
        """
        with self._lock:
            segments = [
                dict(entry)
                for entry in self._cache.values()
                if entry.get("chapter_id") == chapter_id
            ]
            return sorted(segments, key=lambda x: x.get("segment_id", 0))

    def clear(self) -> None:
        """
        Clear all cache entries in memory and on disk.
        """
        with self._lock:
            self._cache.clear()
            self._save_to_disk()
