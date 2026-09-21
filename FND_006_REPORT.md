# Work Package FND-006: SQLite Schema 001 — Completion Report

## 1. Executive Summary
- **Package ID:** FND-006
- **Title:** SQLite schema 001
- **Phase:** 1 (Foundation)
- **Status:** COMPLETED
- **Branch:** `phase/1-foundation`
- **Dependencies Verified:** FND-002 (DONE), FND-005 (DONE)
- **Next Ready Package:** FND-007 (Migration discipline, promoted from PLANNED to READY)
- **Architecture References:** `ARCHITECTURE_ZERO.md` §4 (Canonical IR), §25.5 (Database rules), §26 (Persistent Job Engine), §19 (Locked decisions D07, D19, D20, D22, D36, D38), and §22.2 (Storage Subsystem).

---

## 2. Architecture & Design Principles (Codebase Design Skill)

Applying the **codebase-design** skill principles, the database and repository subsystem was engineered as a suite of **deep modules**:
- **Small Ergonomic Interfaces:** Repositories (`ProjectRepository`, `OperationRepository`, `ArtifactRepository`, `SegmentRepository`, `JobRepository`) expose concise, strongly typed domain interfaces taking and returning canonical IR Pydantic contracts (`ProjectSpec`, `OperationSpec`, `Artifact`, `Segment`, `SegmentVersion`, `RunRecord`, `JobRecord`).
- **Encapsulated Complexity:** All low-level SQLite mechanics—thread safety, connection lifecycle, PRAGMA enforcement (`foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000`), nested `SAVEPOINT` transactions, JSON column serialization/deserialization, SHA-256 migration checksum verification, and compare-and-set atomic job claims—are completely hidden behind the interface.
- **Strict Layer Law & Seam Discipline (D19):** `tarjoman.storage` resides firmly in the Infrastructure/Adapters layer. It depends exclusively on `tarjoman.core.contracts`, `tarjoman.core.errors`, standard libraries, and Pydantic. It contains zero references to HTTP frameworks, CLI commands, LLM providers, or UI components. Core modules never import storage.
- **Fail-Closed Migration Runner (§25.5):** Migrations are numbered immutable SQL files executed under `BEGIN IMMEDIATE`. Checksums are calculated via SHA-256 and compared against the ledger. Any file tampering or presence of unrecorded higher schema versions raises `MigrationError` fail-closed.
- **D20 Invariant (No DB BLOBs):** Transactional metadata is persisted in SQLite; large binary payloads are stored in the filesystem artifact store referenced by content hashes (`raw_sha256`) and paths (`blob_path`). Zero columns in the SQLite database have `BLOB` type.
- **D38 Status Vocabulary:** The `jobs` table enforces the exact canonical status vocabulary via SQL CHECK constraints: `status IN ('QUEUED', 'RUNNING', 'WAITING_REVIEW', 'SUCCEEDED', 'FAILED', 'CANCELLED')`.

---

## 3. Deliverables Implemented

### 3.1 Initial SQL Migration (`src/tarjoman/storage/migrations/001_initial_schema.sql`)
- `schema_migrations`: ledger tracking migration version (INT PK), filename (TEXT), SHA-256 checksum (TEXT), and ISO UTC timestamp `applied_at` (TEXT).
- `projects`: maps to `ProjectSpec` (§4.2). Enforces PK `project_id`, default language pairs, profile IDs, policy IDs, timestamps, and `metadata_json`.
- `operations`: maps to `OperationSpec` (§4.3). Enforces PK `operation_id`, FK `project_id` ON DELETE CASCADE, operation type, JSON arrays of input artifacts, resolved policies, strategy ID, config snapshot hash, and timestamps.
- `artifacts`: maps to `Artifact` (§4.4). Enforces PK `artifact_id`, FK `project_id` ON DELETE CASCADE, artifact kind, `raw_sha256`, `canonical_content_hash`, language tags, URI provenance, producer name/version, parent IDs, retention, blob path, and metadata. Invariant D20 enforced with no binary BLOB column.
- `segments`: maps to `Segment` (§4.5). Enforces PK `segment_id`, FK `artifact_id` ON DELETE CASCADE, structural locator, source text, source content hash, language spans, `translatable` boolean check constraint, protected spans, structural context, and `UNIQUE(artifact_id, structural_locator)`.
- `segment_versions`: maps to `SegmentVersion` (§4.6). Enforces PK `segment_version_id`, FK `segment_id` ON DELETE CASCADE, version kind, text, parent version self-reference ON DELETE SET NULL, strategy/provider/model/prompt metadata, hashes, author enum, author ID, timestamps, findings, and provenance.
- `jobs`: maps to `RunRecord` and persistent job engine (§4.8 & §26). Enforces PK `job_id`, FK `operation_id` ON DELETE CASCADE, FK `project_id` ON DELETE CASCADE, locked CHECK constraint on status (`QUEUED`, `RUNNING`, `WAITING_REVIEW`, `SUCCEEDED`, `FAILED`, `CANCELLED`), priority, attempt counter, claim token, lease owner, lease expiration timestamp, `idempotency_key UNIQUE`, checkpoints, provider, model, timestamps, usage, cost, error type/message, retry count, and metadata.
- Indexes: `idx_artifacts_project`, `idx_operations_project`, `idx_segments_artifact`, `idx_segment_versions_segment`, `idx_jobs_status_priority`, `idx_jobs_project`, `idx_jobs_operation`.

### 3.2 Database Engine & Migration Runner (`src/tarjoman/storage/database.py`)
- `DatabaseManager`:
  - Enforces `PRAGMA foreign_keys = ON;`, `PRAGMA journal_mode = WAL;`, `PRAGMA busy_timeout = <ms>;` on every connection.
  - Supports persistent in-memory (`:memory:`) and file-backed databases with automatic parent directory creation.
  - Connection context manager (`with db.connection() as conn:`).
  - Transaction context manager (`with db.transaction() as conn:`) with nested `SAVEPOINT` support for composable repository operations.
  - Sequential migration runner (`apply_migrations()`): discovers migrations matching `^(\d+)_(.+)\.sql$`, verifies SHA-256 checksums of applied migrations, rejects tampered or unsupported future schemas with `MigrationError`, and atomically applies pending migrations inside `BEGIN IMMEDIATE`.
  - Introspection utilities: `get_applied_migrations()`, `get_current_version()`.

### 3.3 Typed Repository Layer (`src/tarjoman/storage/repositories/`)
- `ProjectRepository` (`project_repository.py`):
  - `create(spec: ProjectSpec) -> ProjectSpec`
  - `get(project_id: str) -> Optional[ProjectSpec]`
  - `list(limit: int = 100, offset: int = 0) -> List[ProjectSpec]`
  - `update(spec: ProjectSpec) -> ProjectSpec`
  - `delete(project_id: str) -> bool` (triggers cascade deletion across all child entities)
- `OperationRepository` (`operation_repository.py`):
  - `create(spec: OperationSpec) -> OperationSpec`
  - `get(operation_id: str) -> Optional[OperationSpec]`
  - `list_by_project(project_id: str, limit: int = 100, offset: int = 0) -> List[OperationSpec]`
  - `delete(operation_id: str) -> bool`
- `ArtifactRepository` (`artifact_repository.py`):
  - `create(artifact: Artifact) -> Artifact`
  - `get(artifact_id: str, include_segments: bool = False) -> Optional[Artifact]`
  - `list_by_project(project_id: str, limit: int = 100, offset: int = 0) -> List[Artifact]`
  - `delete(artifact_id: str) -> bool`
- `SegmentRepository` (`segment_repository.py`):
  - `create(segment: Segment) -> Segment`
  - `create_batch(segments: List[Segment]) -> List[Segment]` (atomic multi-row insert)
  - `get(segment_id: str) -> Optional[Segment]`
  - `list_by_artifact(artifact_id: str, limit: int = 1000, offset: int = 0) -> List[Segment]`
  - `delete(segment_id: str) -> bool`
  - `add_version(version: SegmentVersion) -> SegmentVersion`
  - `get_version(version_id: str) -> Optional[SegmentVersion]`
  - `list_versions(segment_id: str) -> List[SegmentVersion]`
  - `get_latest_version(segment_id: str) -> Optional[SegmentVersion]`
- `JobRepository` & `JobRecord` (`job_repository.py`):
  - `JobRecord`: Pydantic model with bi-directional conversion to/from canonical `RunRecord`.
  - `create(job: Union[JobRecord, RunRecord], priority: int = 0, idempotency_key: Optional[str] = None) -> JobRecord`
  - `get(job_id: str) -> Optional[JobRecord]`
  - `get_by_idempotency_key(idempotency_key: str) -> Optional[JobRecord]`
  - `claim_next_job(lease_owner: str, timeout_seconds: int = 300) -> Optional[JobRecord]` (atomic CAS priority claim & expired lease recovery per §26.2)
  - `heartbeat(job_id: str, claim_token: str, extend_seconds: int = 300) -> bool`
  - `complete(job_id: str, claim_token: str, status: JobStatus = JobStatus.SUCCEEDED, error_type: Optional[str] = None, error_message: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> bool`
  - `cancel(job_id: str, reason: Optional[str] = None) -> bool`
  - `list_by_project(project_id: str, limit: int = 100, offset: int = 0) -> List[JobRecord]`
  - `list_by_status(status: JobStatus, limit: int = 100, offset: int = 0) -> List[JobRecord]`
  - `delete(job_id: str) -> bool`

### 3.4 Storage Subsystem Exports (`src/tarjoman/storage/__init__.py`)
- Re-exports `DatabaseManager`, `ProjectRepository`, `OperationRepository`, `ArtifactRepository`, `SegmentRepository`, `JobRepository`, `JobRecord`, along with `ArtifactStore` and `StoredBlob`.

---

## 4. Verification & Test Evidence

### 4.1 New Test Suite (`tests/test_sqlite_schema.py`)
27 comprehensive test cases verifying all acceptance criteria and edge cases:
1. **Migration Engine & Integrity (6 tests):**
   - Clean in-memory DB migrates to latest schema, records migration 001 with 64-char SHA-256 checksum, creates all 7 tables and 7 indexes.
   - Clean file DB migrates to latest schema and initializes WAL mode.
   - Idempotency: re-running `apply_migrations()` applies 0 pending migrations and preserves version 1.
   - Checksum tampering detection: altering recorded checksum raises `MigrationError`.
   - Unsupported future schema version detection: having DB version > max local version raises `MigrationError`.
   - Atomic rollback: simulated broken migration rolls back completely, leaving zero residual tables.
2. **PRAGMA Verification (3 tests):**
   - In-memory database verifies `foreign_keys=1`, `journal_mode=memory`, and `busy_timeout=5000`.
   - File database verifies `foreign_keys=1`, `journal_mode=wal`, and `busy_timeout=5000`.
   - Custom `busy_timeout_ms` properly configured and verified via PRAGMA.
3. **Foreign Key Integrity & Cascades (7 tests):**
   - Rejection of orphan artifact referencing non-existent project with `sqlite3.IntegrityError`.
   - Rejection of orphan operation with `sqlite3.IntegrityError`.
   - Rejection of orphan segment with `sqlite3.IntegrityError`.
   - Rejection of orphan segment version with `sqlite3.IntegrityError`.
   - Rejection of orphan job with `sqlite3.IntegrityError`.
   - Cascade deletion: deleting project cleanly removes associated operations, artifacts, segments, versions, and jobs.
   - Cascade deletion: deleting artifact cleanly removes associated segments and versions.
4. **Architecture Invariant D20 (1 test):**
   - Introspection of `PRAGMA table_info` across all tables asserts zero columns of type `BLOB`.
5. **Strict Job Status Vocabulary D38 (2 tests):**
   - Insertion of all 6 canonical statuses (`QUEUED`, `RUNNING`, `WAITING_REVIEW`, `SUCCEEDED`, `FAILED`, `CANCELLED`) succeeds.
   - Insertion of non-conforming statuses (`completed`, `done`, `queued`, `pending`, `SUCCESS`, etc.) fails SQLite CHECK constraint.
6. **Project Repository CRUD (1 test):**
   - Full lifecycle: create, get, list, update, and delete; non-existent get returns None; update on missing raises KeyError.
7. **Artifact Repository CRUD (1 test):**
   - Create, get (with and without `include_segments`), list by project, and delete.
8. **Segment & Version Repository CRUD (1 test):**
   - Batch insert segments, verify `ProtectedSpan` serialization, enforce `UNIQUE(artifact_id, structural_locator)`, append historical `SegmentVersion`s, verify chronological ordering and `get_latest_version`.
9. **Job Repository & Engine Lifecycle (5 tests):**
   - Priority-based atomic claiming (`claim_next_job`), valid/invalid heartbeat lease extension, valid/invalid token completion.
   - Expired lease recovery (§26.2): worker 1 crashed lease is recovered by worker 2 with incremented attempt counter.
   - Cooperative cancellation: queued or running jobs transition to `CANCELLED`; already cancelled jobs return False.
   - Idempotency key uniqueness and retrieval (`get_by_idempotency_key`); duplicate keys rejected.
   - Bi-directional conversion between `JobRecord` and canonical `RunRecord`.

### 4.2 Full Test Suite Results
```text
collected 351 items
351 passed, 9 warnings, 115 subtests passed in 1.92s
```
- 324 existing baseline tests passed with zero regressions.
- 27 new SQLite schema and repository tests passed with 100% success.

### 4.3 10-Domain Benchmark Suite
Executed `benchmarks/run_benchmarks.py`:
```text
[SUCCESS] All 10 Domain Verification Benchmarks PASSED (10/10) in 0.55s!
```

---

## 5. Acceptance Criteria Checklist

| Acceptance Criterion | Status | Evidence |
|---|:---:|---|
| **empty → latest migration** | PASSED | `TestMigrationEngine` verifies clean database applies `001_initial_schema.sql`, records checksum in `schema_migrations`, creates all tables/indexes, and verifies idempotency and atomic rollback. |
| **FK integrity** | PASSED | `TestForeignKeyIntegrity` asserts `PRAGMA foreign_keys=ON`, blocks orphan inserts across all child tables with `IntegrityError`, and verifies cascading deletion from projects and artifacts. |
| **WAL / busy timeout** | PASSED | `TestDatabasePragmas` verifies `PRAGMA foreign_keys=1`, `PRAGMA journal_mode=WAL` (on file DBs) / `memory` (on memory DBs), and explicit busy timeout. |
| **repository CRUD tests** | PASSED | `TestProjectRepositoryCRUD`, `TestArtifactRepositoryCRUD`, `TestSegmentRepositoryCRUD`, and `TestJobRepositoryAndPersistentEngine` verify complete CRUD, batch inserts, and versioning. |
| **No large binary BLOB columns (D20)** | PASSED | `TestArchitectureInvariants.test_no_blob_columns_in_database` verifies zero BLOB columns exist in any SQLite table. |
| **All 324 existing tests pass** | PASSED | 351/351 tests passed cleanly. |
| **All 10 domain benchmarks pass** | PASSED | 10/10 domain verification benchmarks passed with 100% audit scores. |

---

## 6. Files Changed & Impact Analysis
- `src/tarjoman/storage/migrations/001_initial_schema.sql` (New: 144 lines — DDL for migrations ledger, projects, operations, artifacts, segments, versions, jobs, and indexes)
- `src/tarjoman/storage/database.py` (New: 215 lines — `DatabaseManager` with connection pooling, pragmas, SAVEPOINT transactions, and migration runner)
- `src/tarjoman/storage/repositories/__init__.py` (New: 18 lines — exports repository classes)
- `src/tarjoman/storage/repositories/project_repository.py` (New: 140 lines — `ProjectRepository` CRUD)
- `src/tarjoman/storage/repositories/operation_repository.py` (New: 125 lines — `OperationRepository` CRUD)
- `src/tarjoman/storage/repositories/artifact_repository.py` (New: 185 lines — `ArtifactRepository` CRUD)
- `src/tarjoman/storage/repositories/segment_repository.py` (New: 235 lines — `SegmentRepository` and `SegmentVersion` persistence)
- `src/tarjoman/storage/repositories/job_repository.py` (New: 375 lines — `JobRepository` with atomic claim, heartbeat, lease recovery, and `JobRecord`)
- `src/tarjoman/storage/__init__.py` (Modified: re-exports `DatabaseManager` and all typed repositories)
- `pyproject.toml` (Modified: packaged `migrations/*.sql` data)
- `WORKPACKAGES.json` (Modified: marked FND-006 DONE, promoted FND-007 to READY)
- `tests/test_sqlite_schema.py` (New: 920 lines — 27 comprehensive tests)

### Architecture Decisions Impact
- **D07 (SQLite WAL):** Fully implemented and verified.
- **D19 (Layer Law):** Enforced. `tarjoman.storage` resides in Infrastructure/Adapters; imports only `core.contracts`, `core.errors`, stdlib, and Pydantic.
- **D20 (No DB BLOBs):** Enforced. No BLOB columns exist; binary data remains in content-addressed artifact store.
- **D22 (SQLite Persistent Job Engine):** Initialized with atomic claim, lease recovery, and status transitions.
- **D36 (Workspace Persistence Boundary):** Workspace DB houses all project and job metadata locally.
- **D38 (Canonical Status Vocabulary):** Enforced via SQLite CHECK constraints.

### Migration & Schema Impact
- Initial schema `001_initial_schema.sql` established with checksum ledger.

### Dependency & License Impact
- Zero external runtime dependencies added. Uses standard library `sqlite3` and existing project dependencies (`pydantic`).
