"""
Base composer interface for Tarjoman publication generators.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
import re
from typing import Any, List


class BaseComposer(ABC):
    """Abstract base class for all output document composers."""

    @abstractmethod
    def compose(self, *args: Any, **kwargs: Any) -> str:
        """Compose output document content as a string."""
        pass

    @staticmethod
    def split_paragraphs(text: str) -> List[str]:
        """
        Split raw text into clean, non-empty paragraph blocks.
        Preserves block boundaries separated by one or more blank lines.
        """
        if not text or not text.strip():
            return []
        paragraphs = re.split(r"\n\s*\n", text.strip())
        return [p.strip() for p in paragraphs if p.strip()]
