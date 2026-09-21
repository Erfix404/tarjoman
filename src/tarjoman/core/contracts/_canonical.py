"""
Canonical Intermediate Representation (IR) data contracts.

Architecture Zero §4 — all input formats normalize into one canonical
representation.  These models are the single source of truth for
Workspace, Project, Operation, Artifact, Segment, SegmentVersion,
ProtectedSpan, and RunRecord.

Locked decisions enforced here:
  D04  — Canonical IR separates ingestion/export from translation logic.
  D19  — Core contains no concrete provider/network/UI/server implementation.
  D38  — Public job status vocabulary is exactly
         QUEUED / RUNNING / WAITING_REVIEW / SUCCEEDED / FAILED / CANCELLED.
"""
from __future__ import annotations

import hashlib
import unicodedata
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums  (Architecture Zero §4.3, §4.4, §4.5, §4.6, §4.7, §4.8)
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    """Canonical public job status vocabulary (D38).

    No alternative public spellings such as ``completed`` are permitted.
    """
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_REVIEW = "WAITING_REVIEW"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class OperationType(str, Enum):
    """Every transformation declares its operation type (§4.3)."""
    TRANSLATE = "translate"
    REVIEW = "review"
    FORMALIZE = "formalize"
    SUMMARIZE = "summarize"
    TRANSCRIBE = "transcribe"
    SYNTHESIZE = "synthesize"
    EXPORT = "export"
    EVALUATE = "evaluate"


class ArtifactKind(str, Enum):
    """Artifact kind vocabulary (§4.4)."""
    SOURCE_DOCUMENT = "source_document"
    TRANSLATED_DOCUMENT = "translated_document"
    SUBTITLE = "subtitle"
    AUDIO = "audio"
    VIDEO = "video"
    TRANSCRIPT_RAW = "transcript_raw"
    TRANSCRIPT_CLEAN = "transcript_clean"
    NOTES = "notes"
    MINUTES = "minutes"
    SPEECH_PLAN = "speech_plan"
    SYNTHESIZED_AUDIO = "synthesized_audio"
    EVALUATION_REPORT = "evaluation_report"
    OTHER = "other"


class SegmentVersionKind(str, Enum):
    """Segment version kind vocabulary (§4.6)."""
    SOURCE = "source"
    DRAFT = "draft"
    REVISED = "revised"
    HUMAN_EDIT = "human_edit"
    APPROVED = "approved"


class AuthorType(str, Enum):
    """Author principal type (§4.6)."""
    SYSTEM = "system"
    MODEL = "model"
    HUMAN = "human"


class ProtectedSpanType(str, Enum):
    """Protected span type vocabulary (§4.7)."""
    CODE = "code"
    URL = "url"
    EMAIL = "email"
    MATH = "math"
    PLACEHOLDER = "placeholder"
    CITATION = "citation"
    TAG = "tag"
    TIMESTAMP = "timestamp"
    SPEAKER = "speaker"
    OTHER = "other"


class IntegrityPolicy(str, Enum):
    """Protected span integrity policy (§4.7)."""
    EXACT = "exact"
    NORMALIZED = "normalized"
    MAPPED = "mapped"


# ---------------------------------------------------------------------------
# Models  (Architecture Zero §4.1 – §4.8)
# ---------------------------------------------------------------------------

class Workspace(BaseModel):
    """Workspace boundary model (§4.1).

    A Workspace is the persistence and trust boundary: one SQLite database,
    one content-addressed artifact store, one job queue/lease namespace,
    one set of projects, one network/license/security policy envelope.
    """
    workspace_id: str
    root_path: str
    created_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProjectSpec(BaseModel):
    """Durable project defaults (§4.2).

    Source/target language defaults are optional — a Persian meeting,
    a multilingual subtitle file, and a Persian TTS operation do not
    require a fake translation language pair.
    """
    project_id: str
    name: str
    default_source_language: Optional[str] = None
    default_target_language: Optional[str] = None
    default_domain_profile_id: Optional[str] = None
    default_style_profile_id: Optional[str] = None
    default_workflow_profile_id: Optional[str] = None
    privacy_policy_id: Optional[str] = None
    provider_policy_id: Optional[str] = None
    review_policy_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OperationSpec(BaseModel):
    """Immutable operation specification (§4.3).

    The OperationSpec is the semantic input to idempotency/cache/provenance.
    """
    operation_id: str
    project_id: str
    operation_type: OperationType
    input_artifact_ids: List[str] = Field(default_factory=list)
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    domain_profile_id: Optional[str] = None
    style_profile_id: Optional[str] = None
    workflow_profile_id: Optional[str] = None
    resolved_policy_ids: Dict[str, str] = Field(default_factory=dict)
    strategy_id: Optional[str] = None
    config_snapshot_hash: Optional[str] = None
    created_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProtectedSpan(BaseModel):
    """Protected span within a segment (§4.7).

    Placeholder tokens are collision-resistant and scoped to the
    operation/segment.  Finalization fails if a required placeholder is
    missing, duplicated unexpectedly, altered, or unresolved.  Silent
    "best effort" restoration is forbidden.
    """
    span_id: str
    type: ProtectedSpanType
    original_text: str
    integrity_policy: IntegrityPolicy = IntegrityPolicy.EXACT
    placeholder_token: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Segment(BaseModel):
    """Stable logical location in an artifact (§4.5).

    Stable segment IDs are based on artifact identity + structural locator,
    **not text alone**, so repeated identical paragraphs remain distinct.
    Content hashes are separate and used for cache/TM matching.
    """
    segment_id: str
    artifact_id: str
    structural_locator: str
    source_text: str
    source_content_hash: str
    language_spans: List[Dict[str, Any]] = Field(default_factory=list)
    translatable: bool = True
    protected_spans: List[ProtectedSpan] = Field(default_factory=list)
    structural_context: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SegmentVersion(BaseModel):
    """Immutable version of generated/reviewed text for a segment (§4.6).

    A new edit/version never overwrites historical text.
    """
    segment_version_id: str
    segment_id: str
    kind: SegmentVersionKind
    text: str
    parent_version_id: Optional[str] = None
    strategy_id: Optional[str] = None
    provider_id: Optional[str] = None
    model_id: Optional[str] = None
    prompt_id: Optional[str] = None
    profile_version: Optional[str] = None
    glossary_hash: Optional[str] = None
    context_hash: Optional[str] = None
    result_cache_hash: Optional[str] = None
    author: AuthorType = AuthorType.SYSTEM
    author_id: Optional[str] = None
    created_at: datetime
    findings: List[Dict[str, Any]] = Field(default_factory=list)
    provenance: Dict[str, Any] = Field(default_factory=dict)


class Artifact(BaseModel):
    """Immutable logical artifact version (§4.4).

    Imported source files are copied into the managed artifact store by
    default so a project remains reproducible if the original external
    path disappears.
    """
    artifact_id: str
    project_id: str
    kind: ArtifactKind
    raw_sha256: Optional[str] = None
    canonical_content_hash: Optional[str] = None
    language_tags: List[str] = Field(default_factory=list)
    source_uri: Optional[str] = None
    producer_name: Optional[str] = None
    producer_version: Optional[str] = None
    parent_artifact_ids: List[str] = Field(default_factory=list)
    sensitivity: Optional[str] = None
    retention_policy: Optional[str] = None
    blob_path: Optional[str] = None
    segments: List[Segment] = Field(default_factory=list)
    created_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RunRecord(BaseModel):
    """Run record with canonical status vocabulary (§4.8).

    All job/run interfaces use exactly:
    QUEUED | RUNNING | WAITING_REVIEW | SUCCEEDED | FAILED | CANCELLED

    No alternative public status spelling such as ``completed`` is permitted.
    """
    run_id: str
    job_id: str
    operation_id: str
    project_id: str
    status: JobStatus
    stage_checkpoints: List[Dict[str, Any]] = Field(default_factory=list)
    resolved_config_hash: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    prompt_id: Optional[str] = None
    profile_id: Optional[str] = None
    rule_ids: List[str] = Field(default_factory=list)
    strategy_id: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    usage: Dict[str, Any] = Field(default_factory=dict)
    cost_usd: Optional[float] = None
    duration_ms: Optional[int] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)
