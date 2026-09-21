"""
Memory and State Management Subsystem for Tarjoman.

Provides:
- ResumableCache: JSON-backed persistent cache for chunk-by-chunk translation.
- StateManager: Project-wide state manager for dynamic termbase and character voices.
"""
from __future__ import annotations

from tarjoman.memory.cache import ResumableCache
from tarjoman.memory.state_manager import StateManager

__all__ = [
    "ResumableCache",
    "StateManager",
]
