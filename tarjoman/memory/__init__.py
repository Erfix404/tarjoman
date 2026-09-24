"""
Memory and State Management Subsystem for Tarjoman (Super-Skill v2).

Provides:
- ResumableCache: JSON-backed persistent cache for chunk-by-chunk translation.
- StateManager: Project-wide state manager for dynamic termbase and character voices.
- BookManifestManager (+ ChunkRecord, ChapterRecord, sha256_text): SHA-256
  content-hash manifest for resumable long-form book translation.
- CharacterBible (+ CharacterProfile): character voice consistency ledger.
- Termbase (+ TermRecord, CascadeEvent): SQLite-backed domain-tagged
  terminology store with cascade re-translation tracking.
"""
from __future__ import annotations

from tarjoman.memory.cache import ResumableCache
from tarjoman.memory.character_bible import CharacterBible, CharacterProfile
from tarjoman.memory.scene_continuity import SceneContinuityTracker, SceneState
from tarjoman.memory.manifest import (
    CHUNK_STATUS_FAILED,
    CHUNK_STATUS_PENDING,
    CHUNK_STATUS_TRANSLATED,
    BookManifestManager,
    ChapterRecord,
    ChunkRecord,
    sha256_text,
)
from tarjoman.memory.state_manager import StateManager
from tarjoman.memory.termbase import CascadeEvent, Termbase, TermRecord

__all__ = [
    "ResumableCache",
    "StateManager",
    "BookManifestManager",
    "ChapterRecord",
    "ChunkRecord",
    "sha256_text",
    "CHUNK_STATUS_PENDING",
    "CHUNK_STATUS_TRANSLATED",
    "CHUNK_STATUS_FAILED",
    "CharacterBible",
    "CharacterProfile",
    "SceneContinuityTracker",
    "SceneState",
    "Termbase",
    "TermRecord",
    "CascadeEvent",
]
