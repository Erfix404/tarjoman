"""
Typed Operation repository for Tarjoman workspaces.

Architecture Zero §4.3 (OperationSpec) & §25.5 (Repository layer owns SQL).
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from tarjoman.core.contracts import OperationSpec, OperationType
from tarjoman.storage.database import DatabaseManager


class OperationRepository:
    """Repository managing OperationSpec persistence."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def _row_to_spec(self, row: Any) -> OperationSpec:
        input_artifact_ids = (
            json.loads(row["input_artifact_ids_json"])
            if row["input_artifact_ids_json"]
            else []
        )
        resolved_policy_ids = (
            json.loads(row["resolved_policy_ids_json"])
            if row["resolved_policy_ids_json"]
            else {}
        )
        metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        return OperationSpec(
            operation_id=row["operation_id"],
            project_id=row["project_id"],
            operation_type=OperationType(row["operation_type"]),
            input_artifact_ids=input_artifact_ids,
            source_language=row["source_language"],
            target_language=row["target_language"],
            domain_profile_id=row["domain_profile_id"],
            style_profile_id=row["style_profile_id"],
            workflow_profile_id=row["workflow_profile_id"],
            resolved_policy_ids=resolved_policy_ids,
            strategy_id=row["strategy_id"],
            config_snapshot_hash=row["config_snapshot_hash"],
            created_at=datetime.fromisoformat(row["created_at"]),
            metadata=metadata,
        )

    def create(self, spec: OperationSpec) -> OperationSpec:
        """Persist a new OperationSpec."""
        input_ids_json = json.dumps(spec.input_artifact_ids)
        policy_ids_json = json.dumps(spec.resolved_policy_ids)
        metadata_json = json.dumps(spec.metadata)
        op_type = (
            spec.operation_type.value
            if isinstance(spec.operation_type, OperationType)
            else str(spec.operation_type)
        )

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO operations (
                    operation_id,
                    project_id,
                    operation_type,
                    input_artifact_ids_json,
                    source_language,
                    target_language,
                    domain_profile_id,
                    style_profile_id,
                    workflow_profile_id,
                    resolved_policy_ids_json,
                    strategy_id,
                    config_snapshot_hash,
                    created_at,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    spec.operation_id,
                    spec.project_id,
                    op_type,
                    input_ids_json,
                    spec.source_language,
                    spec.target_language,
                    spec.domain_profile_id,
                    spec.style_profile_id,
                    spec.workflow_profile_id,
                    policy_ids_json,
                    spec.strategy_id,
                    spec.config_snapshot_hash,
                    spec.created_at.isoformat(),
                    metadata_json,
                ),
            )
        return spec

    def get(self, operation_id: str) -> Optional[OperationSpec]:
        """Retrieve an OperationSpec by ID, or None if not found."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM operations WHERE operation_id = ?;",
                (operation_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_spec(row)

    def list_by_project(
        self, project_id: str, limit: int = 100, offset: int = 0
    ) -> List[OperationSpec]:
        """List operations for a project ordered by creation time descending."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM operations WHERE project_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?;",
                (project_id, limit, offset),
            )
            return [self._row_to_spec(row) for row in cursor.fetchall()]

    def delete(self, operation_id: str) -> bool:
        """Delete an operation by ID. Returns True if deleted, False if not found."""
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM operations WHERE operation_id = ?;",
                (operation_id,),
            )
            return cursor.rowcount > 0
