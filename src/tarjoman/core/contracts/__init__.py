"""
Tarjoman Core Contracts — canonical IR and legacy data models.

All models are importable directly from ``tarjoman.core.contracts``:

    from tarjoman.core.contracts import JobStatus, Segment, DomainType

Legacy models (DomainType, TypographicRules, DomainProfile, TextSegment,
StageResult, AuditFinding, AuditReport, BookManifest) remain for
backward compatibility.
"""
from __future__ import annotations

# -- Legacy contracts (backward compatibility) --------------------------------
from tarjoman.core.contracts._legacy import (
    AuditFinding,
    AuditReport,
    BookManifest,
    DomainProfile,
    DomainType,
    EmDashPolicy,
    StageResult,
    TextSegment,
    TypographicRules,
)

# -- Canonical IR enums (Architecture Zero §4) --------------------------------
from tarjoman.core.contracts._canonical import (
    ArtifactKind,
    AuthorType,
    IntegrityPolicy,
    JobStatus,
    OperationType,
    ProtectedSpanType,
    SegmentVersionKind,
)

# -- Canonical IR models (Architecture Zero §4) --------------------------------
from tarjoman.core.contracts._canonical import (
    Artifact,
    OperationSpec,
    ProjectSpec,
    ProtectedSpan,
    RunRecord,
    Segment,
    SegmentVersion,
    Workspace,
)

# -- Stable ID and hashing helpers (§4.5, §42) --------------------------------
from tarjoman.core.contracts._hashing import (
    compute_content_hash,
    compute_placeholder,
    compute_segment_id,
)

# -- Schema snapshot utilities -------------------------------------------------
from tarjoman.core.contracts._schema import (
    CANONICAL_MODELS,
    export_schemas_json,
    get_all_schemas,
    get_model_schema,
)

__all__ = [
    # Legacy
    "DomainType",
    "EmDashPolicy",
    "TypographicRules",
    "DomainProfile",
    "TextSegment",
    "StageResult",
    "AuditFinding",
    "AuditReport",
    "BookManifest",
    # Canonical enums
    "JobStatus",
    "OperationType",
    "ArtifactKind",
    "SegmentVersionKind",
    "AuthorType",
    "ProtectedSpanType",
    "IntegrityPolicy",
    # Canonical models
    "Workspace",
    "ProjectSpec",
    "OperationSpec",
    "ProtectedSpan",
    "Segment",
    "SegmentVersion",
    "Artifact",
    "RunRecord",
    # Hashing helpers
    "compute_content_hash",
    "compute_segment_id",
    "compute_placeholder",
    # Schema utilities
    "CANONICAL_MODELS",
    "get_model_schema",
    "get_all_schemas",
    "export_schemas_json",
]
