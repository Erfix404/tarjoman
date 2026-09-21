"""
Typed Artifact repository for Tarjoman workspaces.

Architecture Zero §4.4 (Artifact), §25.5 (Repository layer owns SQL),
and locked decision D20 (No DB BLOBs: large binaries live in filesystem store).
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from tarjoman.core.contracts import (
    Artifact,
    ArtifactKind,
    IntegrityPolicy,
    ProtectedSpan,
    ProtectedSpanType,
    Segment,
)
from tarjoman.storage.database import DatabaseManager


class ArtifactRepository:
    """Repository managing Artifact persistence (without binary BLOBs)."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def _row_to_artifact(self, row: Any, segments: Optional[List[Segment]] = None) -> Artifact:
        language_tags = (
            json.loads(row["language_tags_json"])
            if row["language_tags_json"]
            else []
        )
        parent_artifact_ids = (
            json.loads(row["parent_artifact_ids_json"])
            if row["parent_artifact_ids_json"]
            else []
        )
        metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        return Artifact(
            artifact_id=row["artifact_id"],
            project_id=row["project_id"],
            kind=ArtifactKind(row["kind"]),
            raw_sha256=row["raw_sha256"],
            canonical_content_hash=row["canonical_content_hash"],
            language_tags=language_tags,
            source_uri=row["source_uri"],
            producer_name=row["producer_name"],
            producer_version=row["producer_version"],
            parent_artifact_ids=parent_artifact_ids,
            sensitivity=row["sensitivity"],
            retention_policy=row["retention_policy"],
            blob_path=row["blob_path"],
            segments=segments if segments is not None else [],
            created_at=datetime.fromisoformat(row["created_at"]),
            metadata=metadata,
        )

    def _row_to_segment(self, row: Any) -> Segment:
        lang_spans = (
            json.loads(row["language_spans_json"])
            if row["language_spans_json"]
            else []
        )
        raw_protected = (
            json.loads(row["protected_spans_json"])
            if row["protected_spans_json"]
            else []
        )
        protected_spans = [
            ProtectedSpan(
                span_id=p["span_id"],
                type=ProtectedSpanType(p["type"]),
                original_text=p["original_text"],
                integrity_policy=IntegrityPolicy(p.get("integrity_policy", "exact")),
                placeholder_token=p.get("placeholder_token"),
                metadata=p.get("metadata", {}),
            )
            for p in raw_protected
        ]
        context = (
            json.loads(row["structural_context_json"])
            if row["structural_context_json"]
            else {}
        )
        metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}

        return Segment(
            segment_id=row["segment_id"],
            artifact_id=row["artifact_id"],
            structural_locator=row["structural_locator"],
            source_text=row["source_text"],
            source_content_hash=row["source_content_hash"],
            language_spans=lang_spans,
            translatable=bool(row["translatable"]),
            protected_spans=protected_spans,
            structural_context=context,
            metadata=metadata,
        )

    def create(self, artifact: Artifact) -> Artifact:
        """Persist an Artifact record."""
        kind_val = (
            artifact.kind.value
            if isinstance(artifact.kind, ArtifactKind)
            else str(artifact.kind)
        )
        lang_tags_json = json.dumps(artifact.language_tags)
        parents_json = json.dumps(artifact.parent_artifact_ids)
        metadata_json = json.dumps(artifact.metadata)

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO artifacts (
                    artifact_id,
                    project_id,
                    kind,
                    raw_sha256,
                    canonical_content_hash,
                    language_tags_json,
                    source_uri,
                    producer_name,
                    producer_version,
                    parent_artifact_ids_json,
                    sensitivity,
                    retention_policy,
                    blob_path,
                    created_at,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    artifact.artifact_id,
                    artifact.project_id,
                    kind_val,
                    artifact.raw_sha256,
                    artifact.canonical_content_hash,
                    lang_tags_json,
                    artifact.source_uri,
                    artifact.producer_name,
                    artifact.producer_version,
                    parents_json,
                    artifact.sensitivity,
                    artifact.retention_policy,
                    artifact.blob_path,
                    artifact.created_at.isoformat(),
                    metadata_json,
                ),
            )
        return artifact

    def get(self, artifact_id: str, include_segments: bool = False) -> Optional[Artifact]:
        """Retrieve an Artifact by ID. Optionally populates segments."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM artifacts WHERE artifact_id = ?;",
                (artifact_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            segments = None
            if include_segments:
                seg_cursor = conn.execute(
                    "SELECT * FROM segments WHERE artifact_id = ? ORDER BY rowid ASC;",
                    (artifact_id,),
                )
                segments = [self._row_to_segment(s_row) for s_row in seg_cursor.fetchall()]

            return self._row_to_artifact(row, segments=segments)

    def list_by_project(
        self, project_id: str, limit: int = 100, offset: int = 0
    ) -> List[Artifact]:
        """List artifacts for a project ordered by creation time descending."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM artifacts WHERE project_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?;",
                (project_id, limit, offset),
            )
            return [self._row_to_artifact(row) for row in cursor.fetchall()]

    def delete(self, artifact_id: str) -> bool:
        """Delete an artifact and cascade-delete its segments and versions."""
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM artifacts WHERE artifact_id = ?;",
                (artifact_id,),
            )
            return cursor.rowcount > 0
