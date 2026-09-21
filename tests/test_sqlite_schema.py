"""
Comprehensive Test Suite for SQLite Schema 001, Migration Runner,
and Typed Repositories (FND-006).

Architecture Zero §4 (Canonical IR), §25.5 (Database rules),
§26 (Persistent Job Engine), and locked decisions:
  - D07: SQLite WAL production storage.
  - D19: Layer law & repository boundaries.
  - D20: No DB BLOBs (large binaries live in artifact store).
  - D22: SQLite-backed persistent job engine.
  - D36: Workspace persistence boundary.
  - D38: Locked status vocabulary (QUEUED, RUNNING, WAITING_REVIEW, SUCCEEDED, FAILED, CANCELLED).
"""
from __future__ import annotations

import sqlite3
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator

import pytest

from tarjoman.core.contracts import (
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
)
from tarjoman.core.errors import MigrationError
from tarjoman.storage import (
    ArtifactRepository,
    DatabaseManager,
    JobRecord,
    JobRepository,
    OperationRepository,
    ProjectRepository,
    SegmentRepository,
)


@pytest.fixture
def mem_db() -> Generator[DatabaseManager, None, None]:
    """Provide an in-memory DatabaseManager initialized with schema 001."""
    db = DatabaseManager(":memory:")
    db.apply_migrations()
    yield db
    db.close()


@pytest.fixture
def file_db() -> Generator[DatabaseManager, None, None]:
    """Provide a file-backed DatabaseManager in a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "workspace.db"
        db = DatabaseManager(db_path)
        db.apply_migrations()
        yield db
        db.close()


# ===========================================================================
# 1. Empty -> Latest Migration & Integrity Tests
# ===========================================================================

class TestMigrationEngine:
    """Acceptance: empty -> latest migration, checksum verification, tamper guard."""

    def test_empty_to_latest_migration_memory(self) -> None:
        db = DatabaseManager(":memory:")
        assert db.get_current_version() == 0

        applied = db.apply_migrations()
        assert applied == [1]
        assert db.get_current_version() == 1

        migrations = db.get_applied_migrations()
        assert len(migrations) == 1
        assert migrations[0]["version"] == 1
        assert migrations[0]["name"] == "001_initial_schema.sql"
        assert len(migrations[0]["checksum"]) == 64

        # Verify all tables created
        with db.connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
            )
            tables = [row[0] for row in cursor.fetchall()]
            for expected in [
                "artifacts",
                "jobs",
                "operations",
                "projects",
                "schema_migrations",
                "segment_versions",
                "segments",
            ]:
                assert expected in tables

            # Verify indexes created
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
            )
            indexes = [row[0] for row in cursor.fetchall()]
            for exp_idx in [
                "idx_artifacts_project",
                "idx_jobs_operation",
                "idx_jobs_project",
                "idx_jobs_status_priority",
                "idx_operations_project",
                "idx_segment_versions_segment",
                "idx_segments_artifact",
            ]:
                assert exp_idx in indexes

        db.close()

    def test_empty_to_latest_migration_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = DatabaseManager(db_path)
            applied = db.apply_migrations()
            assert applied == [1]
            assert db_path.exists()
            assert db.get_current_version() == 1
            db.close()

    def test_migration_is_idempotent(self, mem_db: DatabaseManager) -> None:
        # Second invocation should apply zero pending migrations
        second_applied = mem_db.apply_migrations()
        assert second_applied == []
        assert mem_db.get_current_version() == 1

    def test_migration_checksum_tamper_fails(self, mem_db: DatabaseManager) -> None:
        # Alter the recorded checksum
        with mem_db.connection() as conn:
            conn.execute(
                "UPDATE schema_migrations SET checksum = 'corrupted_hash' WHERE version = 1;"
            )

        with pytest.raises(MigrationError) as exc_info:
            mem_db.apply_migrations()
        assert "checksum mismatch" in str(exc_info.value).lower()

    def test_future_schema_version_fails(self, mem_db: DatabaseManager) -> None:
        with mem_db.connection() as conn:
            conn.execute(
                "INSERT INTO schema_migrations (version, name, checksum, applied_at) VALUES (999, '999_future.sql', 'hash', '2026-09-21');"
            )

        with pytest.raises(MigrationError) as exc_info:
            mem_db.apply_migrations()
        assert "newer than maximum supported version" in str(exc_info.value)

    def test_migration_atomic_rollback_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mig_dir = Path(tmpdir) / "migrations"
            mig_dir.mkdir()

            # Good migration 001
            (mig_dir / "001_good.sql").write_text(
                "CREATE TABLE t1 (id TEXT PRIMARY KEY);", encoding="utf-8"
            )
            # Broken migration 002 (violates unique in script)
            (mig_dir / "002_bad.sql").write_text(
                "CREATE TABLE t2 (x INT PRIMARY KEY); INSERT INTO t2 VALUES (1); INSERT INTO t2 VALUES (1);",
                encoding="utf-8",
            )

            db = DatabaseManager(":memory:", migrations_dir=mig_dir)
            with pytest.raises(MigrationError):
                db.apply_migrations()

            # Migration 1 succeeded, but Migration 2 rolled back completely
            assert db.get_current_version() == 1
            with db.connection() as conn:
                # Table t1 exists
                cursor = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='t1';")
                assert cursor.fetchone()[0] == 1
                # Table t2 was rolled back
                cursor = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='t2';")
                assert cursor.fetchone()[0] == 0

            db.close()


# ===========================================================================
# 2. PRAGMA Verification: Foreign Keys, WAL, and Busy Timeout
# ===========================================================================

class TestDatabasePragmas:
    """Acceptance: PRAGMA foreign_keys=ON, journal_mode=WAL/memory, busy_timeout."""

    def test_memory_db_pragmas(self, mem_db: DatabaseManager) -> None:
        with mem_db.connection() as conn:
            fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
            jm = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            bt = conn.execute("PRAGMA busy_timeout;").fetchone()[0]

            assert fk == 1, "Foreign keys must be ON"
            assert jm.lower() == "memory", "In-memory database journal mode is 'memory'"
            assert bt == 5000, "Default busy timeout must be 5000ms"

    def test_file_db_pragmas(self, file_db: DatabaseManager) -> None:
        with file_db.connection() as conn:
            fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
            jm = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            bt = conn.execute("PRAGMA busy_timeout;").fetchone()[0]

            assert fk == 1, "Foreign keys must be ON"
            assert jm.lower() == "wal", "File database journal mode must be WAL"
            assert bt == 5000, "Default busy timeout must be 5000ms"

    def test_custom_busy_timeout(self) -> None:
        db = DatabaseManager(":memory:", busy_timeout_ms=12345)
        with db.connection() as conn:
            bt = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
            assert bt == 12345
        db.close()


# ===========================================================================
# 3. Foreign Key Integrity and Cascade Deletion
# ===========================================================================

class TestForeignKeyIntegrity:
    """Acceptance: FK integrity enforced; cascade delete removes child entities; orphan rejected."""

    def test_orphan_artifact_rejected(self, mem_db: DatabaseManager) -> None:
        art_repo = ArtifactRepository(mem_db)
        art = Artifact(
            artifact_id="art_orphan",
            project_id="non_existent_project",
            kind=ArtifactKind.SOURCE_DOCUMENT,
            created_at=datetime.now(timezone.utc),
        )
        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            art_repo.create(art)
        assert "FOREIGN KEY constraint failed" in str(exc_info.value)

    def test_orphan_operation_rejected(self, mem_db: DatabaseManager) -> None:
        op_repo = OperationRepository(mem_db)
        op = OperationSpec(
            operation_id="op_orphan",
            project_id="non_existent_project",
            operation_type=OperationType.TRANSLATE,
            created_at=datetime.now(timezone.utc),
        )
        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            op_repo.create(op)
        assert "FOREIGN KEY constraint failed" in str(exc_info.value)

    def test_orphan_segment_rejected(self, mem_db: DatabaseManager) -> None:
        seg_repo = SegmentRepository(mem_db)
        seg = Segment(
            segment_id="seg_orphan",
            artifact_id="non_existent_artifact",
            structural_locator="p/1",
            source_text="Test",
            source_content_hash="hash",
        )
        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            seg_repo.create(seg)
        assert "FOREIGN KEY constraint failed" in str(exc_info.value)

    def test_orphan_segment_version_rejected(self, mem_db: DatabaseManager) -> None:
        seg_repo = SegmentRepository(mem_db)
        ver = SegmentVersion(
            segment_version_id="ver_orphan",
            segment_id="non_existent_segment",
            kind=SegmentVersionKind.DRAFT,
            text="Draft text",
            author=AuthorType.SYSTEM,
            created_at=datetime.now(timezone.utc),
        )
        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            seg_repo.add_version(ver)
        assert "FOREIGN KEY constraint failed" in str(exc_info.value)

    def test_orphan_job_rejected(self, mem_db: DatabaseManager) -> None:
        job_repo = JobRepository(mem_db)
        job = JobRecord(
            job_id="job_orphan",
            operation_id="non_existent_op",
            project_id="non_existent_project",
            status=JobStatus.QUEUED,
        )
        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            job_repo.create(job)
        assert "FOREIGN KEY constraint failed" in str(exc_info.value)

    def test_project_cascade_delete_removes_all_dependents(self, mem_db: DatabaseManager) -> None:
        proj_repo = ProjectRepository(mem_db)
        op_repo = OperationRepository(mem_db)
        art_repo = ArtifactRepository(mem_db)
        seg_repo = SegmentRepository(mem_db)
        job_repo = JobRepository(mem_db)

        now = datetime.now(timezone.utc)
        pid = "proj_cascade_test"

        # 1. Project
        proj_repo.create(ProjectSpec(project_id=pid, name="Cascade Project", created_at=now, updated_at=now))
        # 2. Operation
        op_repo.create(OperationSpec(operation_id="op_c", project_id=pid, operation_type=OperationType.TRANSLATE, created_at=now))
        # 3. Artifact
        art_repo.create(Artifact(artifact_id="art_c", project_id=pid, kind=ArtifactKind.SOURCE_DOCUMENT, created_at=now))
        # 4. Segment
        seg_repo.create(Segment(segment_id="seg_c", artifact_id="art_c", structural_locator="p/1", source_text="Sample", source_content_hash="h1"))
        # 5. SegmentVersion
        seg_repo.add_version(SegmentVersion(segment_version_id="ver_c", segment_id="seg_c", kind=SegmentVersionKind.DRAFT, text="نمونه", created_at=now))
        # 6. Job
        job_repo.create(JobRecord(job_id="job_c", operation_id="op_c", project_id=pid, status=JobStatus.QUEUED, created_at=now))

        # Verify all exist
        assert proj_repo.get(pid) is not None
        assert op_repo.get("op_c") is not None
        assert art_repo.get("art_c") is not None
        assert seg_repo.get("seg_c") is not None
        assert seg_repo.get_version("ver_c") is not None
        assert job_repo.get("job_c") is not None

        # Delete Project -> Cascades
        deleted = proj_repo.delete(pid)
        assert deleted is True

        # Verify all children were deleted
        assert proj_repo.get(pid) is None
        assert op_repo.get("op_c") is None
        assert art_repo.get("art_c") is None
        assert seg_repo.get("seg_c") is None
        assert seg_repo.get_version("ver_c") is None
        assert job_repo.get("job_c") is None

    def test_artifact_cascade_delete(self, mem_db: DatabaseManager) -> None:
        proj_repo = ProjectRepository(mem_db)
        art_repo = ArtifactRepository(mem_db)
        seg_repo = SegmentRepository(mem_db)
        now = datetime.now(timezone.utc)

        proj_repo.create(ProjectSpec(project_id="p_art_del", name="P", created_at=now, updated_at=now))
        art_repo.create(Artifact(artifact_id="a_del", project_id="p_art_del", kind=ArtifactKind.SOURCE_DOCUMENT, created_at=now))
        seg_repo.create(Segment(segment_id="s_del", artifact_id="a_del", structural_locator="p/1", source_text="Text", source_content_hash="h"))
        seg_repo.add_version(SegmentVersion(segment_version_id="v_del", segment_id="s_del", kind=SegmentVersionKind.DRAFT, text="T", created_at=now))

        assert art_repo.delete("a_del") is True
        assert art_repo.get("a_del") is None
        assert seg_repo.get("s_del") is None
        assert seg_repo.get_version("v_del") is None
        # Project remains
        assert proj_repo.get("p_art_del") is not None


# ===========================================================================
# 4. Invariant D20: No Large Binary BLOB Columns in SQLite
# ===========================================================================

class TestArchitectureInvariants:
    """Acceptance: D20 (No DB BLOBs). Large binaries live in artifact store."""

    def test_no_blob_columns_in_database(self, mem_db: DatabaseManager) -> None:
        with mem_db.connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
            )
            tables = [row[0] for row in cursor.fetchall()]

            for table in tables:
                col_cursor = conn.execute(f"PRAGMA table_info({table});")
                for col_info in col_cursor.fetchall():
                    col_name = col_info[1]
                    col_type = col_info[2].upper()
                    assert "BLOB" not in col_type, (
                        f"Invariant D20 violation: Table '{table}', Column '{col_name}' has type '{col_type}'. "
                        "Large binary artifacts must live in the filesystem store, not SQLite BLOBs."
                    )


# ===========================================================================
# 5. Strict Job Status CHECK Constraint (D38)
# ===========================================================================

class TestStrictJobStatusVocabulary:
    """Acceptance: Canonical status vocabulary is exactly QUEUED, RUNNING, WAITING_REVIEW, SUCCEEDED, FAILED, CANCELLED."""

    def test_valid_job_statuses(self, mem_db: DatabaseManager) -> None:
        proj_repo = ProjectRepository(mem_db)
        op_repo = OperationRepository(mem_db)
        now = datetime.now(timezone.utc)

        proj_repo.create(ProjectSpec(project_id="p_stat", name="P", created_at=now, updated_at=now))
        op_repo.create(OperationSpec(operation_id="op_stat", project_id="p_stat", operation_type=OperationType.TRANSLATE, created_at=now))

        valid_statuses = [
            "QUEUED",
            "RUNNING",
            "WAITING_REVIEW",
            "SUCCEEDED",
            "FAILED",
            "CANCELLED",
        ]
        with mem_db.connection() as conn:
            for i, st in enumerate(valid_statuses):
                conn.execute(
                    """
                    INSERT INTO jobs (job_id, operation_id, project_id, status, created_at)
                    VALUES (?, 'op_stat', 'p_stat', ?, '2026-09-21T00:00:00');
                    """,
                    (f"j_val_{i}", st),
                )

        job_repo = JobRepository(mem_db)
        for i, st in enumerate(valid_statuses):
            j = job_repo.get(f"j_val_{i}")
            assert j is not None
            assert j.status.value == st

    def test_invalid_job_statuses_rejected_by_check_constraint(self, mem_db: DatabaseManager) -> None:
        proj_repo = ProjectRepository(mem_db)
        op_repo = OperationRepository(mem_db)
        now = datetime.now(timezone.utc)

        proj_repo.create(ProjectSpec(project_id="p_bad_stat", name="P", created_at=now, updated_at=now))
        op_repo.create(OperationSpec(operation_id="op_bad_stat", project_id="p_bad_stat", operation_type=OperationType.TRANSLATE, created_at=now))

        invalid_spellings = [
            "completed",
            "done",
            "queued",
            "pending",
            "in_progress",
            "SUCCESS",
            "FAILURE",
            "finished",
        ]
        with mem_db.connection() as conn:
            for bad in invalid_spellings:
                with pytest.raises(sqlite3.IntegrityError) as exc_info:
                    conn.execute(
                        """
                        INSERT INTO jobs (job_id, operation_id, project_id, status, created_at)
                        VALUES (?, 'op_bad_stat', 'p_bad_stat', ?, '2026-09-21T00:00:00');
                        """,
                        (f"j_bad_{bad}", bad),
                    )
                assert "CHECK constraint failed" in str(exc_info.value)


# ===========================================================================
# 6. Repository CRUD & Lifecycle Tests
# ===========================================================================

class TestProjectRepositoryCRUD:
    """Acceptance: ProjectRepository create, get, list, update, delete."""

    def test_project_crud_lifecycle(self, mem_db: DatabaseManager) -> None:
        repo = ProjectRepository(mem_db)
        now = datetime.now(timezone.utc)

        # Create
        spec = ProjectSpec(
            project_id="proj_crud_1",
            name="Shahnameh Translation Project",
            default_source_language="fa",
            default_target_language="en",
            default_domain_profile_id="classical",
            default_style_profile_id="formal",
            default_workflow_profile_id="5pass",
            privacy_policy_id="priv_strict",
            provider_policy_id="prov_local_only",
            review_policy_id="rev_mqm",
            created_at=now,
            updated_at=now,
            metadata={"priority": "high", "translator": "Ferdowsi"},
        )
        created = repo.create(spec)
        assert created.project_id == "proj_crud_1"

        # Get
        fetched = repo.get("proj_crud_1")
        assert fetched is not None
        assert fetched.name == "Shahnameh Translation Project"
        assert fetched.default_source_language == "fa"
        assert fetched.default_target_language == "en"
        assert fetched.metadata["translator"] == "Ferdowsi"

        # List
        projects = repo.list()
        assert len(projects) == 1
        assert projects[0].project_id == "proj_crud_1"

        # Update
        updated_spec = fetched.model_copy()
        updated_spec.name = "Shahnameh Critical Edition"
        updated_spec.metadata["status"] = "in_review"
        repo.update(updated_spec)

        refetched = repo.get("proj_crud_1")
        assert refetched is not None
        assert refetched.name == "Shahnameh Critical Edition"
        assert refetched.metadata["status"] == "in_review"

        # Update non-existent raises KeyError
        phantom = spec.model_copy()
        phantom.project_id = "non_existent"
        with pytest.raises(KeyError):
            repo.update(phantom)

        # Delete
        assert repo.delete("proj_crud_1") is True
        assert repo.get("proj_crud_1") is None
        assert repo.delete("proj_crud_1") is False


class TestArtifactRepositoryCRUD:
    """Acceptance: ArtifactRepository create, get (with segments), list, delete."""

    def test_artifact_crud_lifecycle(self, mem_db: DatabaseManager) -> None:
        proj_repo = ProjectRepository(mem_db)
        art_repo = ArtifactRepository(mem_db)
        seg_repo = SegmentRepository(mem_db)
        now = datetime.now(timezone.utc)

        proj_repo.create(ProjectSpec(project_id="p_art", name="P", created_at=now, updated_at=now))

        art = Artifact(
            artifact_id="art_crud_1",
            project_id="p_art",
            kind=ArtifactKind.SOURCE_DOCUMENT,
            raw_sha256="abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234",
            canonical_content_hash="canonical_sha_123",
            language_tags=["fa", "en"],
            source_uri="file:///docs/sample.docx",
            producer_name="docx_parser",
            producer_version="1.0.0",
            parent_artifact_ids=["parent_1", "parent_2"],
            sensitivity="internal",
            retention_policy="30d",
            blob_path=".tarjoman/artifacts/sha256/ab/abcd1234...",
            created_at=now,
            metadata={"page_count": 42},
        )
        art_repo.create(art)

        # Get without segments
        fetched = art_repo.get("art_crud_1", include_segments=False)
        assert fetched is not None
        assert fetched.kind == ArtifactKind.SOURCE_DOCUMENT
        assert fetched.language_tags == ["fa", "en"]
        assert fetched.parent_artifact_ids == ["parent_1", "parent_2"]
        assert fetched.metadata["page_count"] == 42
        assert len(fetched.segments) == 0

        # Add segments
        seg_repo.create(Segment(segment_id="s1", artifact_id="art_crud_1", structural_locator="p/1", source_text="T1", source_content_hash="h1"))
        seg_repo.create(Segment(segment_id="s2", artifact_id="art_crud_1", structural_locator="p/2", source_text="T2", source_content_hash="h2"))

        # Get with segments
        fetched_with_segs = art_repo.get("art_crud_1", include_segments=True)
        assert fetched_with_segs is not None
        assert len(fetched_with_segs.segments) == 2
        assert fetched_with_segs.segments[0].segment_id == "s1"
        assert fetched_with_segs.segments[1].segment_id == "s2"

        # List by project
        arts = art_repo.list_by_project("p_art")
        assert len(arts) == 1
        assert arts[0].artifact_id == "art_crud_1"

        # Delete
        assert art_repo.delete("art_crud_1") is True
        assert art_repo.get("art_crud_1") is None


class TestSegmentRepositoryCRUD:
    """Acceptance: SegmentRepository create_batch, get, list_by_artifact, versions."""

    def test_segment_and_version_lifecycle(self, mem_db: DatabaseManager) -> None:
        proj_repo = ProjectRepository(mem_db)
        art_repo = ArtifactRepository(mem_db)
        seg_repo = SegmentRepository(mem_db)
        now = datetime.now(timezone.utc)

        proj_repo.create(ProjectSpec(project_id="p_seg", name="P", created_at=now, updated_at=now))
        art_repo.create(Artifact(artifact_id="a_seg", project_id="p_seg", kind=ArtifactKind.SOURCE_DOCUMENT, created_at=now))

        # Protected spans
        ps1 = ProtectedSpan(
            span_id="span_1",
            type=ProtectedSpanType.CODE,
            original_text="import os",
            integrity_policy=IntegrityPolicy.EXACT,
            placeholder_token="<SPAN_001>",
        )
        ps2 = ProtectedSpan(
            span_id="span_2",
            type=ProtectedSpanType.MATH,
            original_text="$E=mc^2$",
            integrity_policy=IntegrityPolicy.EXACT,
            placeholder_token="<SPAN_002>",
        )

        segments = [
            Segment(
                segment_id="seg_1",
                artifact_id="a_seg",
                structural_locator="sec/1/p/1",
                source_text="First paragraph with code: import os",
                source_content_hash="hash_p1",
                language_spans=[{"lang": "en", "start": 0, "end": 35}],
                translatable=True,
                protected_spans=[ps1],
                structural_context={"heading": "Chapter 1"},
                metadata={"tokens": 12},
            ),
            Segment(
                segment_id="seg_2",
                artifact_id="a_seg",
                structural_locator="sec/1/p/2",
                source_text="Second paragraph with math: $E=mc^2$",
                source_content_hash="hash_p2",
                translatable=True,
                protected_spans=[ps2],
            ),
        ]

        # Batch insert
        created = seg_repo.create_batch(segments)
        assert len(created) == 2

        # Get
        fetched_s1 = seg_repo.get("seg_1")
        assert fetched_s1 is not None
        assert fetched_s1.structural_locator == "sec/1/p/1"
        assert len(fetched_s1.protected_spans) == 1
        assert fetched_s1.protected_spans[0].placeholder_token == "<SPAN_001>"
        assert fetched_s1.structural_context["heading"] == "Chapter 1"

        # Unique constraint on (artifact_id, structural_locator)
        duplicate_locator = Segment(
            segment_id="seg_dup",
            artifact_id="a_seg",
            structural_locator="sec/1/p/1",  # duplicate!
            source_text="Duplicate text",
            source_content_hash="hash_dup",
        )
        with pytest.raises(sqlite3.IntegrityError):
            seg_repo.create(duplicate_locator)

        # Add versions to segment 1 (source -> draft -> approved)
        v1 = SegmentVersion(
            segment_version_id="v_src",
            segment_id="seg_1",
            kind=SegmentVersionKind.SOURCE,
            text="First paragraph with code: import os",
            author=AuthorType.HUMAN,
            created_at=now,
        )
        v2 = SegmentVersion(
            segment_version_id="v_draft",
            segment_id="seg_1",
            kind=SegmentVersionKind.DRAFT,
            text="بند اول همراه با کد: import os",
            parent_version_id="v_src",
            strategy_id="5pass_reflection",
            provider_id="anthropic",
            model_id="claude-opus-5",
            author=AuthorType.MODEL,
            created_at=now + timedelta(seconds=10),
            findings=[{"issue": "none"}],
            provenance={"cached": False},
        )
        v3 = SegmentVersion(
            segment_version_id="v_approved",
            segment_id="seg_1",
            kind=SegmentVersionKind.APPROVED,
            text="بند نخست همراه با کد: import os",
            parent_version_id="v_draft",
            author=AuthorType.HUMAN,
            author_id="lead_editor_1",
            created_at=now + timedelta(seconds=20),
        )

        seg_repo.add_version(v1)
        seg_repo.add_version(v2)
        seg_repo.add_version(v3)

        # Versions list order
        versions = seg_repo.list_versions("seg_1")
        assert len(versions) == 3
        assert versions[0].kind == SegmentVersionKind.SOURCE
        assert versions[1].kind == SegmentVersionKind.DRAFT
        assert versions[2].kind == SegmentVersionKind.APPROVED

        # Latest version
        latest = seg_repo.get_latest_version("seg_1")
        assert latest is not None
        assert latest.segment_version_id == "v_approved"
        assert latest.text == "بند نخست همراه با کد: import os"


class TestJobRepositoryAndPersistentEngine:
    """Acceptance: JobRepository atomic claim, lease expiration, heartbeat, complete, cancel."""

    def test_atomic_claim_and_lifecycle(self, mem_db: DatabaseManager) -> None:
        proj_repo = ProjectRepository(mem_db)
        op_repo = OperationRepository(mem_db)
        job_repo = JobRepository(mem_db)
        now = datetime.now(timezone.utc)

        proj_repo.create(ProjectSpec(project_id="p_job", name="P", created_at=now, updated_at=now))
        op_repo.create(OperationSpec(operation_id="op_job", project_id="p_job", operation_type=OperationType.TRANSLATE, created_at=now))

        # Create two jobs with different priorities
        job_low = JobRecord(
            job_id="job_low",
            operation_id="op_job",
            project_id="p_job",
            status=JobStatus.QUEUED,
            priority=10,
            created_at=now,
        )
        job_high = JobRecord(
            job_id="job_high",
            operation_id="op_job",
            project_id="p_job",
            status=JobStatus.QUEUED,
            priority=100,
            created_at=now + timedelta(seconds=1),
        )
        job_repo.create(job_low)
        job_repo.create(job_high)

        # Worker 1 claims next job -> should receive job_high (higher priority)
        claimed_1 = job_repo.claim_next_job(lease_owner="worker_node_1", timeout_seconds=120)
        assert claimed_1 is not None
        assert claimed_1.job_id == "job_high"
        assert claimed_1.status == JobStatus.RUNNING
        assert claimed_1.lease_owner == "worker_node_1"
        assert claimed_1.claim_token is not None
        assert claimed_1.attempt == 1
        assert claimed_1.lease_expires_at is not None

        # Worker 2 claims next job -> receives job_low
        claimed_2 = job_repo.claim_next_job(lease_owner="worker_node_2", timeout_seconds=120)
        assert claimed_2 is not None
        assert claimed_2.job_id == "job_low"

        # Worker 3 tries to claim -> None available
        assert job_repo.claim_next_job(lease_owner="worker_node_3") is None

        # Heartbeat test
        token_1 = claimed_1.claim_token
        assert token_1 is not None
        # Heartbeat with valid token succeeds
        assert job_repo.heartbeat(claimed_1.job_id, token_1, extend_seconds=300) is True
        # Heartbeat with invalid token fails
        assert job_repo.heartbeat(claimed_1.job_id, "invalid_token") is False

        # Completion test
        # Complete with invalid token fails
        assert (
            job_repo.complete(
                claimed_1.job_id,
                "wrong_token",
                status=JobStatus.SUCCEEDED,
            )
            is False
        )
        # Complete with valid token succeeds
        assert (
            job_repo.complete(
                claimed_1.job_id,
                token_1,
                status=JobStatus.SUCCEEDED,
                metadata={"final_score": 98.5},
            )
            is True
        )

        completed_job = job_repo.get(claimed_1.job_id)
        assert completed_job is not None
        assert completed_job.status == JobStatus.SUCCEEDED
        assert completed_job.claim_token is None
        assert completed_job.lease_expires_at is None
        assert completed_job.finished_at is not None
        assert completed_job.metadata["final_score"] == 98.5

    def test_lease_expiration_and_recovery(self, mem_db: DatabaseManager) -> None:
        """Architecture Zero §26.2: Expired RUNNING leases are reclaimed."""
        proj_repo = ProjectRepository(mem_db)
        op_repo = OperationRepository(mem_db)
        job_repo = JobRepository(mem_db)
        now = datetime.now(timezone.utc)

        proj_repo.create(ProjectSpec(project_id="p_exp", name="P", created_at=now, updated_at=now))
        op_repo.create(OperationSpec(operation_id="op_exp", project_id="p_exp", operation_type=OperationType.TRANSLATE, created_at=now))

        job = JobRecord(
            job_id="job_will_expire",
            operation_id="op_exp",
            project_id="p_exp",
            status=JobStatus.QUEUED,
            priority=50,
            created_at=now,
        )
        job_repo.create(job)

        # Worker 1 claims job with 0 second timeout (immediately expires)
        claimed_1 = job_repo.claim_next_job(lease_owner="worker_crashed", timeout_seconds=-1)
        assert claimed_1 is not None
        assert claimed_1.status == JobStatus.RUNNING
        assert claimed_1.attempt == 1

        # Worker 2 claims next job -> Reclaims the expired job!
        claimed_2 = job_repo.claim_next_job(lease_owner="worker_healthy", timeout_seconds=300)
        assert claimed_2 is not None
        assert claimed_2.job_id == "job_will_expire"
        assert claimed_2.lease_owner == "worker_healthy"
        assert claimed_2.attempt == 2  # incremented attempt counter
        assert claimed_2.claim_token != claimed_1.claim_token

    def test_job_cancellation(self, mem_db: DatabaseManager) -> None:
        """Architecture Zero §26.1: Cancellation is cooperative and persisted."""
        proj_repo = ProjectRepository(mem_db)
        op_repo = OperationRepository(mem_db)
        job_repo = JobRepository(mem_db)
        now = datetime.now(timezone.utc)

        proj_repo.create(ProjectSpec(project_id="p_canc", name="P", created_at=now, updated_at=now))
        op_repo.create(OperationSpec(operation_id="op_canc", project_id="p_canc", operation_type=OperationType.TRANSLATE, created_at=now))

        job = JobRecord(
            job_id="job_to_cancel",
            operation_id="op_canc",
            project_id="p_canc",
            status=JobStatus.QUEUED,
            created_at=now,
        )
        job_repo.create(job)

        # Cancel queued job
        assert job_repo.cancel("job_to_cancel", reason="User requested abort") is True
        cancelled = job_repo.get("job_to_cancel")
        assert cancelled is not None
        assert cancelled.status == JobStatus.CANCELLED
        assert cancelled.error_message == "User requested abort"

        # Cancel already cancelled job returns False (not in QUEUED/RUNNING/WAITING_REVIEW)
        assert job_repo.cancel("job_to_cancel") is False

    def test_idempotency_key(self, mem_db: DatabaseManager) -> None:
        """Architecture Zero §26.5: Idempotency identity enforcement."""
        proj_repo = ProjectRepository(mem_db)
        op_repo = OperationRepository(mem_db)
        job_repo = JobRepository(mem_db)
        now = datetime.now(timezone.utc)

        proj_repo.create(ProjectSpec(project_id="p_idem", name="P", created_at=now, updated_at=now))
        op_repo.create(OperationSpec(operation_id="op_idem", project_id="p_idem", operation_type=OperationType.TRANSLATE, created_at=now))

        key = "idemp_unique_hash_123"
        job1 = JobRecord(
            job_id="job_idemp_1",
            operation_id="op_idem",
            project_id="p_idem",
            status=JobStatus.QUEUED,
            idempotency_key=key,
            created_at=now,
        )
        job_repo.create(job1)

        # Fetch by key
        fetched = job_repo.get_by_idempotency_key(key)
        assert fetched is not None
        assert fetched.job_id == "job_idemp_1"

        # Attempt to insert duplicate key raises IntegrityError
        job2 = JobRecord(
            job_id="job_idemp_2",
            operation_id="op_idem",
            project_id="p_idem",
            status=JobStatus.QUEUED,
            idempotency_key=key,
            created_at=now,
        )
        with pytest.raises(sqlite3.IntegrityError):
            job_repo.create(job2)

    def test_run_record_conversion(self) -> None:
        """Test conversion between JobRecord and canonical RunRecord contract."""
        now = datetime.now(timezone.utc)
        record = RunRecord(
            run_id="run_123",
            job_id="job_123",
            operation_id="op_123",
            project_id="proj_123",
            status=JobStatus.RUNNING,
            provider="anthropic",
            model="claude-opus-5",
            cost_usd=0.015,
            started_at=now,
        )

        job_rec = JobRecord.from_run_record(record, priority=42, idempotency_key="key_123")
        assert job_rec.job_id == "job_123"
        assert job_rec.priority == 42
        assert job_rec.idempotency_key == "key_123"
        assert job_rec.status == JobStatus.RUNNING

        converted_back = job_rec.to_run_record(run_id="run_123")
        assert converted_back.run_id == "run_123"
        assert converted_back.job_id == "job_123"
        assert converted_back.status == JobStatus.RUNNING
        assert converted_back.cost_usd == 0.015
