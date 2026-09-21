"""
Typed Project repository for Tarjoman workspaces.

Architecture Zero §4.2 (ProjectSpec) & §25.5 (Repository layer owns SQL).
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from tarjoman.core.contracts import ProjectSpec
from tarjoman.storage.database import DatabaseManager


class ProjectRepository:
    """Repository managing ProjectSpec persistence."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def _row_to_spec(self, row: Any) -> ProjectSpec:
        metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        return ProjectSpec(
            project_id=row["project_id"],
            name=row["name"],
            default_source_language=row["default_source_language"],
            default_target_language=row["default_target_language"],
            default_domain_profile_id=row["default_domain_profile_id"],
            default_style_profile_id=row["default_style_profile_id"],
            default_workflow_profile_id=row["default_workflow_profile_id"],
            privacy_policy_id=row["privacy_policy_id"],
            provider_policy_id=row["provider_policy_id"],
            review_policy_id=row["review_policy_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            metadata=metadata,
        )

    def create(self, spec: ProjectSpec) -> ProjectSpec:
        """Persist a new ProjectSpec."""
        metadata_json = json.dumps(spec.metadata)
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO projects (
                    project_id,
                    name,
                    default_source_language,
                    default_target_language,
                    default_domain_profile_id,
                    default_style_profile_id,
                    default_workflow_profile_id,
                    privacy_policy_id,
                    provider_policy_id,
                    review_policy_id,
                    created_at,
                    updated_at,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    spec.project_id,
                    spec.name,
                    spec.default_source_language,
                    spec.default_target_language,
                    spec.default_domain_profile_id,
                    spec.default_style_profile_id,
                    spec.default_workflow_profile_id,
                    spec.privacy_policy_id,
                    spec.provider_policy_id,
                    spec.review_policy_id,
                    spec.created_at.isoformat(),
                    spec.updated_at.isoformat(),
                    metadata_json,
                ),
            )
        return spec

    def get(self, project_id: str) -> Optional[ProjectSpec]:
        """Retrieve a ProjectSpec by ID, or None if not found."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM projects WHERE project_id = ?;",
                (project_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_spec(row)

    def list(self, limit: int = 100, offset: int = 0) -> List[ProjectSpec]:
        """List projects ordered by creation time descending."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM projects ORDER BY created_at DESC LIMIT ? OFFSET ?;",
                (limit, offset),
            )
            return [self._row_to_spec(row) for row in cursor.fetchall()]

    def update(self, spec: ProjectSpec) -> ProjectSpec:
        """Update an existing ProjectSpec."""
        metadata_json = json.dumps(spec.metadata)
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE projects
                SET name = ?,
                    default_source_language = ?,
                    default_target_language = ?,
                    default_domain_profile_id = ?,
                    default_style_profile_id = ?,
                    default_workflow_profile_id = ?,
                    privacy_policy_id = ?,
                    provider_policy_id = ?,
                    review_policy_id = ?,
                    updated_at = ?,
                    metadata_json = ?
                WHERE project_id = ?;
                """,
                (
                    spec.name,
                    spec.default_source_language,
                    spec.default_target_language,
                    spec.default_domain_profile_id,
                    spec.default_style_profile_id,
                    spec.default_workflow_profile_id,
                    spec.privacy_policy_id,
                    spec.provider_policy_id,
                    spec.review_policy_id,
                    spec.updated_at.isoformat(),
                    metadata_json,
                    spec.project_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Project not found: {spec.project_id}")
        return spec

    def delete(self, project_id: str) -> bool:
        """Delete a project and cascade-remove all child entities.

        Returns True if deleted, False if project did not exist.
        """
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM projects WHERE project_id = ?;",
                (project_id,),
            )
            return cursor.rowcount > 0
