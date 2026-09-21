"""
Typed Segment and SegmentVersion repository for Tarjoman workspaces.

Architecture Zero §4.5 (Segment), §4.6 (SegmentVersion), and §25.5.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from tarjoman.core.contracts import (
    AuthorType,
    IntegrityPolicy,
    ProtectedSpan,
    ProtectedSpanType,
    Segment,
    SegmentVersion,
    SegmentVersionKind,
)
from tarjoman.storage.database import DatabaseManager


class SegmentRepository:
    """Repository managing Segments and immutable SegmentVersions."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

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

    def _row_to_version(self, row: Any) -> SegmentVersion:
        findings = (
            json.loads(row["findings_json"]) if row["findings_json"] else []
        )
        provenance = (
            json.loads(row["provenance_json"]) if row["provenance_json"] else {}
        )
        return SegmentVersion(
            segment_version_id=row["segment_version_id"],
            segment_id=row["segment_id"],
            kind=SegmentVersionKind(row["kind"]),
            text=row["text"],
            parent_version_id=row["parent_version_id"],
            strategy_id=row["strategy_id"],
            provider_id=row["provider_id"],
            model_id=row["model_id"],
            prompt_id=row["prompt_id"],
            profile_version=row["profile_version"],
            glossary_hash=row["glossary_hash"],
            context_hash=row["context_hash"],
            result_cache_hash=row["result_cache_hash"],
            author=AuthorType(row["author"]),
            author_id=row["author_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            findings=findings,
            provenance=provenance,
        )

    def create(self, segment: Segment) -> Segment:
        """Persist a single segment."""
        self.create_batch([segment])
        return segment

    def create_batch(self, segments: List[Segment]) -> List[Segment]:
        """Atomically persist a batch of segments."""
        if not segments:
            return []

        rows = []
        for s in segments:
            lang_spans_json = json.dumps(s.language_spans)
            protected_json = json.dumps(
                [span.model_dump(mode="json") for span in s.protected_spans]
            )
            context_json = json.dumps(s.structural_context)
            metadata_json = json.dumps(s.metadata)
            trans_int = 1 if s.translatable else 0
            rows.append(
                (
                    s.segment_id,
                    s.artifact_id,
                    s.structural_locator,
                    s.source_text,
                    s.source_content_hash,
                    lang_spans_json,
                    trans_int,
                    protected_json,
                    context_json,
                    metadata_json,
                )
            )

        with self.db.transaction() as conn:
            conn.executemany(
                """
                INSERT INTO segments (
                    segment_id,
                    artifact_id,
                    structural_locator,
                    source_text,
                    source_content_hash,
                    language_spans_json,
                    translatable,
                    protected_spans_json,
                    structural_context_json,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                rows,
            )
        return segments

    def get(self, segment_id: str) -> Optional[Segment]:
        """Retrieve a Segment by ID."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM segments WHERE segment_id = ?;",
                (segment_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_segment(row)

    def list_by_artifact(
        self, artifact_id: str, limit: int = 1000, offset: int = 0
    ) -> List[Segment]:
        """List segments for an artifact ordered by document sequence."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM segments WHERE artifact_id = ? ORDER BY rowid ASC LIMIT ? OFFSET ?;",
                (artifact_id, limit, offset),
            )
            return [self._row_to_segment(row) for row in cursor.fetchall()]

    def delete(self, segment_id: str) -> bool:
        """Delete a segment and its child versions."""
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM segments WHERE segment_id = ?;",
                (segment_id,),
            )
            return cursor.rowcount > 0

    def add_version(self, version: SegmentVersion) -> SegmentVersion:
        """Persist an immutable SegmentVersion record."""
        kind_val = (
            version.kind.value
            if isinstance(version.kind, SegmentVersionKind)
            else str(version.kind)
        )
        author_val = (
            version.author.value
            if isinstance(version.author, AuthorType)
            else str(version.author)
        )
        findings_json = json.dumps(version.findings)
        provenance_json = json.dumps(version.provenance)

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO segment_versions (
                    segment_version_id,
                    segment_id,
                    kind,
                    text,
                    parent_version_id,
                    strategy_id,
                    provider_id,
                    model_id,
                    prompt_id,
                    profile_version,
                    glossary_hash,
                    context_hash,
                    result_cache_hash,
                    author,
                    author_id,
                    created_at,
                    findings_json,
                    provenance_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    version.segment_version_id,
                    version.segment_id,
                    kind_val,
                    version.text,
                    version.parent_version_id,
                    version.strategy_id,
                    version.provider_id,
                    version.model_id,
                    version.prompt_id,
                    version.profile_version,
                    version.glossary_hash,
                    version.context_hash,
                    version.result_cache_hash,
                    author_val,
                    version.author_id,
                    version.created_at.isoformat(),
                    findings_json,
                    provenance_json,
                ),
            )
        return version

    def get_version(self, version_id: str) -> Optional[SegmentVersion]:
        """Retrieve a specific SegmentVersion by ID."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM segment_versions WHERE segment_version_id = ?;",
                (version_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_version(row)

    def list_versions(self, segment_id: str) -> List[SegmentVersion]:
        """List all historical versions of a segment in chronological order."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM segment_versions WHERE segment_id = ? ORDER BY created_at ASC, rowid ASC;",
                (segment_id,),
            )
            return [self._row_to_version(row) for row in cursor.fetchall()]

    def get_latest_version(self, segment_id: str) -> Optional[SegmentVersion]:
        """Retrieve the most recent version of a segment."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM segment_versions WHERE segment_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1;",
                (segment_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_version(row)
