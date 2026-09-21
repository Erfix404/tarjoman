"""
Base stage interface for the Tarjoman translation pipeline.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from tarjoman.core.contracts import DomainProfile, StageResult, TextSegment


class BaseStage(ABC):
    """Abstract base class for all translation pipeline stages."""

    @abstractmethod
    def process(self, segments: List[TextSegment], profile: DomainProfile) -> StageResult:
        """
        Process a list of TextSegments according to the given DomainProfile.
        """
        pass
