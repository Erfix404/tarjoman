"""
Typed Job repository and persistent job engine for Tarjoman workspaces.

Architecture Zero §4.8 (RunRecord), §26 (Persistent job engine), and locked decisions:
  D22 — SQLite-backed single-node persistent job engine.
  D38 — Canonical public job status vocabulary is exactly
        QUEUED | RUNNING | WAITING_REVIEW | SUCCEEDED | FAILED | CANCELLED.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from tarjoman.core.contracts import JobStatus, RunRecord
from tarjoman.storage.database import DatabaseManager


class JobRecord(BaseModel):
    """Job record representing a schedulable execution unit in the persistent engine."""

    job_id: str
    operation_id: str
    project_id: str
    status: JobStatus = JobStatus.QUEUED
    priority: int = 0
    attempt: int = 0
    claim_token: Optional[str] = None
    lease_owner: Optional[str] = None
    lease_expires_at: Optional[datetime] = None
    idempotency_key: Optional[str] = None
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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_run_record(self, run_id: Optional[str] = None) -> RunRecord:
        """Convert this JobRecord to a canonical RunRecord contract."""
        return RunRecord(
            run_id=run_id or self.job_id,
            job_id=self.job_id,
            operation_id=self.operation_id,
            project_id=self.project_id,
            status=self.status,
            stage_checkpoints=self.stage_checkpoints,
            resolved_config_hash=self.resolved_config_hash,
            provider=self.provider,
            model=self.model,
            prompt_id=self.prompt_id,
            profile_id=self.profile_id,
            rule_ids=self.rule_ids,
            strategy_id=self.strategy_id,
            started_at=self.started_at,
            finished_at=self.finished_at,
            usage=self.usage,
            cost_usd=self.cost_usd,
            duration_ms=self.duration_ms,
            error_type=self.error_type,
            error_message=self.error_message,
            retry_count=self.retry_count,
            metadata=self.metadata,
        )

    @classmethod
    def from_run_record(
        cls,
        record: RunRecord,
        priority: int = 0,
        idempotency_key: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> JobRecord:
        """Create a JobRecord from a canonical RunRecord contract."""
        return cls(
            job_id=record.job_id,
            operation_id=record.operation_id,
            project_id=record.project_id,
            status=record.status,
            priority=priority,
            idempotency_key=idempotency_key,
            stage_checkpoints=record.stage_checkpoints,
            resolved_config_hash=record.resolved_config_hash,
            provider=record.provider,
            model=record.model,
            prompt_id=record.prompt_id,
            profile_id=record.profile_id,
            rule_ids=record.rule_ids,
            strategy_id=record.strategy_id,
            started_at=record.started_at,
            finished_at=record.finished_at,
            usage=record.usage,
            cost_usd=record.cost_usd,
            duration_ms=record.duration_ms,
            error_type=record.error_type,
            error_message=record.error_message,
            retry_count=record.retry_count,
            metadata=record.metadata,
            created_at=created_at or datetime.now(timezone.utc),
        )


class JobRepository:
    """Repository managing jobs, leases, heartbeats, and atomic claims."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def _row_to_job(self, row: Any) -> JobRecord:
        checkpoints = (
            json.loads(row["stage_checkpoints_json"])
            if row["stage_checkpoints_json"]
            else []
        )
        rule_ids = (
            json.loads(row["rule_ids_json"]) if row["rule_ids_json"] else []
        )
        usage = json.loads(row["usage_json"]) if row["usage_json"] else {}
        metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}

        lease_expires = (
            datetime.fromisoformat(row["lease_expires_at"])
            if row["lease_expires_at"]
            else None
        )
        started_at = (
            datetime.fromisoformat(row["started_at"])
            if row["started_at"]
            else None
        )
        finished_at = (
            datetime.fromisoformat(row["finished_at"])
            if row["finished_at"]
            else None
        )

        return JobRecord(
            job_id=row["job_id"],
            operation_id=row["operation_id"],
            project_id=row["project_id"],
            status=JobStatus(row["status"]),
            priority=row["priority"],
            attempt=row["attempt"],
            claim_token=row["claim_token"],
            lease_owner=row["lease_owner"],
            lease_expires_at=lease_expires,
            idempotency_key=row["idempotency_key"],
            stage_checkpoints=checkpoints,
            resolved_config_hash=row["resolved_config_hash"],
            provider=row["provider"],
            model=row["model"],
            prompt_id=row["prompt_id"],
            profile_id=row["profile_id"],
            rule_ids=rule_ids,
            strategy_id=row["strategy_id"],
            started_at=started_at,
            finished_at=finished_at,
            usage=usage,
            cost_usd=row["cost_usd"],
            duration_ms=row["duration_ms"],
            error_type=row["error_type"],
            error_message=row["error_message"],
            retry_count=row["retry_count"],
            metadata=metadata,
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def create(
        self,
        job: Union[JobRecord, RunRecord],
        priority: int = 0,
        idempotency_key: Optional[str] = None,
    ) -> JobRecord:
        """Create a new job entry."""
        if isinstance(job, RunRecord):
            record = JobRecord.from_run_record(
                job, priority=priority, idempotency_key=idempotency_key
            )
        else:
            record = job

        status_val = (
            record.status.value
            if isinstance(record.status, JobStatus)
            else str(record.status)
        )
        checkpoints_json = json.dumps(record.stage_checkpoints)
        rule_ids_json = json.dumps(record.rule_ids)
        usage_json = json.dumps(record.usage)
        metadata_json = json.dumps(record.metadata)
        lease_expires_str = (
            record.lease_expires_at.isoformat()
            if record.lease_expires_at
            else None
        )
        started_at_str = (
            record.started_at.isoformat() if record.started_at else None
        )
        finished_at_str = (
            record.finished_at.isoformat() if record.finished_at else None
        )

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id,
                    operation_id,
                    project_id,
                    status,
                    priority,
                    attempt,
                    claim_token,
                    lease_owner,
                    lease_expires_at,
                    idempotency_key,
                    stage_checkpoints_json,
                    resolved_config_hash,
                    provider,
                    model,
                    prompt_id,
                    profile_id,
                    rule_ids_json,
                    strategy_id,
                    started_at,
                    finished_at,
                    usage_json,
                    cost_usd,
                    duration_ms,
                    error_type,
                    error_message,
                    retry_count,
                    metadata_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    record.job_id,
                    record.operation_id,
                    record.project_id,
                    status_val,
                    record.priority,
                    record.attempt,
                    record.claim_token,
                    record.lease_owner,
                    lease_expires_str,
                    record.idempotency_key,
                    checkpoints_json,
                    record.resolved_config_hash,
                    record.provider,
                    record.model,
                    record.prompt_id,
                    record.profile_id,
                    rule_ids_json,
                    record.strategy_id,
                    started_at_str,
                    finished_at_str,
                    usage_json,
                    record.cost_usd,
                    record.duration_ms,
                    record.error_type,
                    record.error_message,
                    record.retry_count,
                    metadata_json,
                    record.created_at.isoformat(),
                ),
            )
        return record

    def get(self, job_id: str) -> Optional[JobRecord]:
        """Retrieve a JobRecord by ID."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?;",
                (job_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_job(row)

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[JobRecord]:
        """Retrieve a JobRecord by idempotency key (§26.5)."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM jobs WHERE idempotency_key = ?;",
                (idempotency_key,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_job(row)

    def claim_next_job(
        self, lease_owner: str, timeout_seconds: int = 300
    ) -> Optional[JobRecord]:
        """Atomically claim the highest-priority runnable job (§26.2).

        Finds either a QUEUED job or a RUNNING job whose lease has expired.
        Generates a fresh claim_token and sets status to RUNNING.
        """
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        lease_expires = now + timedelta(seconds=timeout_seconds)
        lease_expires_iso = lease_expires.isoformat()
        claim_token = uuid.uuid4().hex

        with self.db.transaction() as conn:
            # 1. Locate candidate eligible for claim
            cursor = conn.execute(
                """
                SELECT job_id, attempt FROM jobs
                WHERE status = 'QUEUED'
                   OR (status = 'RUNNING' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?)
                ORDER BY priority DESC, created_at ASC
                LIMIT 1;
                """,
                (now_iso,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            job_id = row["job_id"]
            new_attempt = row["attempt"] + 1

            # 2. Atomic Compare-And-Set claim
            update_cursor = conn.execute(
                """
                UPDATE jobs
                SET status = 'RUNNING',
                    lease_owner = ?,
                    claim_token = ?,
                    lease_expires_at = ?,
                    started_at = COALESCE(started_at, ?),
                    attempt = ?
                WHERE job_id = ?
                  AND (status = 'QUEUED' OR (status = 'RUNNING' AND lease_expires_at < ?));
                """,
                (
                    lease_owner,
                    claim_token,
                    lease_expires_iso,
                    now_iso,
                    new_attempt,
                    job_id,
                    now_iso,
                ),
            )
            if update_cursor.rowcount == 0:
                # Concurrent worker claimed it first
                return None

        return self.get(job_id)

    def heartbeat(
        self, job_id: str, claim_token: str, extend_seconds: int = 300
    ) -> bool:
        """Extend the lease of an actively running job (§26.2).

        Returns True if the lease was successfully extended, or False
        if the claim token is invalid, expired, or the job is no longer RUNNING.
        """
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        new_expires_iso = (now + timedelta(seconds=extend_seconds)).isoformat()

        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE jobs
                SET lease_expires_at = ?
                WHERE job_id = ?
                  AND claim_token = ?
                  AND status = 'RUNNING'
                  AND (lease_expires_at IS NULL OR lease_expires_at >= ?);
                """,
                (new_expires_iso, job_id, claim_token, now_iso),
            )
            return cursor.rowcount > 0

    def complete(
        self,
        job_id: str,
        claim_token: str,
        status: JobStatus = JobStatus.SUCCEEDED,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Mark a claimed job as finished (§26.1).

        Only the owner holding the active claim_token may complete the job.
        Status must be one of SUCCEEDED, FAILED, or WAITING_REVIEW.
        """
        allowed = (
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.WAITING_REVIEW,
        )
        if status not in allowed:
            raise ValueError(
                f"Complete requires terminal or review status ({allowed}), got: {status}"
            )

        now_iso = datetime.now(timezone.utc).isoformat()
        status_val = (
            status.value if isinstance(status, JobStatus) else str(status)
        )

        with self.db.transaction() as conn:
            # Check if job exists with valid token
            cursor = conn.execute(
                "SELECT metadata_json FROM jobs WHERE job_id = ? AND claim_token = ? AND status = 'RUNNING';",
                (job_id, claim_token),
            )
            row = cursor.fetchone()
            if not row:
                return False

            meta_json = row["metadata_json"]
            if metadata is not None:
                existing = json.loads(meta_json) if meta_json else {}
                existing.update(metadata)
                meta_json = json.dumps(existing)

            update_cursor = conn.execute(
                """
                UPDATE jobs
                SET status = ?,
                    finished_at = ?,
                    lease_expires_at = NULL,
                    claim_token = NULL,
                    error_type = COALESCE(?, error_type),
                    error_message = COALESCE(?, error_message),
                    metadata_json = ?
                WHERE job_id = ?
                  AND claim_token = ?
                  AND status = 'RUNNING';
                """,
                (
                    status_val,
                    now_iso,
                    error_type,
                    error_message,
                    meta_json,
                    job_id,
                    claim_token,
                ),
            )
            return update_cursor.rowcount > 0

    def cancel(self, job_id: str, reason: Optional[str] = None) -> bool:
        """Cooperatively cancel an active or queued job (§26.1).

        A job in QUEUED, RUNNING, or WAITING_REVIEW transitions to CANCELLED.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE jobs
                SET status = 'CANCELLED',
                    finished_at = ?,
                    lease_expires_at = NULL,
                    claim_token = NULL,
                    error_message = COALESCE(?, error_message)
                WHERE job_id = ?
                  AND status IN ('QUEUED', 'RUNNING', 'WAITING_REVIEW');
                """,
                (now_iso, reason, job_id),
            )
            return cursor.rowcount > 0

    def list_by_project(
        self, project_id: str, limit: int = 100, offset: int = 0
    ) -> List[JobRecord]:
        """List jobs for a project ordered by priority and creation time."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM jobs WHERE project_id = ? ORDER BY priority DESC, created_at ASC LIMIT ? OFFSET ?;",
                (project_id, limit, offset),
            )
            return [self._row_to_job(row) for row in cursor.fetchall()]

    def list_by_status(
        self, status: JobStatus, limit: int = 100, offset: int = 0
    ) -> List[JobRecord]:
        """List jobs with a specific status."""
        status_val = (
            status.value if isinstance(status, JobStatus) else str(status)
        )
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY priority DESC, created_at ASC LIMIT ? OFFSET ?;",
                (status_val, limit, offset),
            )
            return [self._row_to_job(row) for row in cursor.fetchall()]

    def delete(self, job_id: str) -> bool:
        """Delete a job by ID."""
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM jobs WHERE job_id = ?;",
                (job_id,),
            )
            return cursor.rowcount > 0
