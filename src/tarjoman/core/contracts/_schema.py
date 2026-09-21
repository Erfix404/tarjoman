"""
Schema snapshot export utility for canonical IR models.

Provides JSON Schema representations for all canonical models,
useful for schema versioning, compatibility checks, and documentation.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Type

from pydantic import BaseModel

from tarjoman.core.contracts._canonical import (
    Artifact,
    ArtifactKind,
    AuthorType,
    IntegrityPolicy,
    JobStatus,
    OperationSpec,
    OperationType,
    ProjectSpec,
    ProtectedSpan,
    ProtectedSpanType,
    RunRecord,
    Segment,
    SegmentVersion,
    SegmentVersionKind,
    Workspace,
)

# Ordered list of all canonical models for schema export.
CANONICAL_MODELS: List[Type[BaseModel]] = [
    Workspace,
    ProjectSpec,
    OperationSpec,
    ProtectedSpan,
    Segment,
    SegmentVersion,
    Artifact,
    RunRecord,
]


def get_model_schema(model: Type[BaseModel]) -> Dict[str, Any]:
    """Return the JSON Schema dict for a single Pydantic model."""
    return model.model_json_schema()


def get_all_schemas() -> Dict[str, Dict[str, Any]]:
    """Return a mapping of model name → JSON Schema for all canonical models."""
    return {model.__name__: get_model_schema(model) for model in CANONICAL_MODELS}


def export_schemas_json(*, indent: int = 2) -> str:
    """Export all canonical model schemas as a formatted JSON string."""
    return json.dumps(get_all_schemas(), indent=indent, sort_keys=True)
