# Work Package FND-007: Migration Discipline — Completion Report

## 1. Executive Summary
- **Package ID:** FND-007
- **Title:** Migration discipline
- **Phase:** 1 (Foundation)
- **Status:** COMPLETED
- **Branch:** `phase/1-foundation`
- **Dependencies Verified:** FND-006 (DONE)
- **Next Ready Package:** FND-008 (Legacy-state importer, promoted from PLANNED to READY)
- **Architecture References:** `ARCHITECTURE_ZERO.md` §18 (Versioning and compatibility policy), §24 (Error taxonomy and failure semantics: `MigrationError`), §25.5 (Database rules: numbered immutable SQL migrations with checksums, migration lock before schema changes), and §19 (Locked decisions D07, D19, D36).

---

## 2. Architecture & Design Principles (Codebase Design Skill)

Applying the **codebase-design** principles, the migration engine in `DatabaseManager` was designed as a **deep module**:
- **Small Ergonomic Interface:** Callers interact with four high-level methods:
  1. `apply_migrations(target_version: Optional[int] = None) -> List[int]`
  2. `verify_migrations() -> bool`
  3. `get_migration_status() -> List[Dict[str, Any]]`
  4. `acquire_migration_lock(timeout: Optional[float] = None) -> Generator[None, None, None]`
- **Encapsulated Complexity:** The entire complexity of migration locking (OS-level `fcntl.flock` combined with in-process thread locking and thread re-entrancy), SHA-256 byte-for-byte checksum verification, missing file detection, unsupported future schema detection, and mid-script atomic rollback under `BEGIN IMMEDIATE` is sealed inside `DatabaseManager`.
- **Fail-Closed Verification (§18 & §24):** In accordance with Architecture Zero §18 ("Silent downgrade, silent destructive migration, and opening a newer unsupported schema for writing are forbidden") and §24 (`MigrationError`: no automatic destructive repair), any anomaly—checksum divergence, missing migration script, or database schema version ahead of known code—immediately halts execution and raises a typed `MigrationError` without mutating or attempting destructive repair on the database.
- **Migration Locking (§25.5):** Schema modifications must be protected by an exclusive migration lock. For file databases, an OS-level file lock (`fcntl.flock` on `<db_parent>/locks/migration.lock` or `<db_path>.migration.lock`) coordinates across processes, paired with an in-process thread lock registry to coordinate across concurrent threads. For in-memory databases, an in-memory lock guarantees mutual exclusion.
- **Atomic Rollback on Mid-Script Failure:** Every migration runs in an isolated transaction (`BEGIN IMMEDIATE`). A mid-script failure (syntax error, constraint failure, or table collision) executes a complete `ROLLBACK`, leaving zero partial DDL/DML state or orphaned entries in `schema_migrations`.
- **Idempotence (§25.5):** Running `apply_migrations()` on an up-to-date database executes a fast, safe verification and returns `[]` with no changes to the schema or ledger.

---

## 3. Deliverables Implemented

### 3.1 Migration Engine Hardening (`src/tarjoman/storage/database.py`)
1. **Migration Lock Context Manager (`acquire_migration_lock`)**:
   - For file databases, locks `<db_parent>/locks/migration.lock` (if workspace `locks/` directory exists) or `<db_path>.migration.lock` via non-blocking `fcntl.flock(LOCK_EX | LOCK_NB)` polled up to `timeout`.
   - Process-wide thread lock registry (`_FILE_LOCK_REGISTRY`) prevents inter-thread collisions in the same process.
   - For in-memory databases, acquires `self._memory_lock`.
   - Supports re-entrant acquisition on the holding thread via depth counting (`_lock_depth`).
   - Automatically cleans up file descriptors and releases locks on exit or exception.
2. **Fail-Closed Verification (`verify_migrations`)**:
   - Validates that every applied migration in `schema_migrations` matches the on-disk SQL file byte-for-byte using SHA-256.
   - Detects file content modification -> raises `MigrationError` with file name, expected checksum, and actual checksum.
   - Detects missing migration file -> raises `MigrationError` identifying the missing file.
   - Detects unsupported newer schema version -> raises `MigrationError` preventing silent downgrade.
3. **Structured Status Reporting (`get_migration_status`)**:
   - Discovers all migrations on disk and queries applied records from `schema_migrations`.
   - Categorizes each migration version into one of four states: `"applied"`, `"pending"`, `"tampered"`, `"missing"`.
   - Returns dictionaries containing `version`, `name`, `checksum`, `applied_at`, `status`, `recorded_checksum`, and `file_checksum`.
4. **Hardened Sequential Migration Runner (`apply_migrations`)**:
   - Automatically acquires the migration lock before performing schema modifications.
   - Enforces `verify_migrations()` before applying any pending migrations.
   - Executes pending migrations sequentially under `BEGIN IMMEDIATE`, rolling back completely on any statement failure.
   - Returns list of newly applied version numbers (or `[]` if up-to-date).

### 3.2 Re-exports (`src/tarjoman/storage/__init__.py`)
- Re-exported `MigrationError` alongside `DatabaseManager` and typed repositories for direct consumer access.

---

## 4. Verification & Testing Evidence

### 4.1 Migration Discipline Test Suite (`tests/test_migration_discipline.py`)
19 comprehensive tests were implemented covering all acceptance criteria:

1. **Migration Idempotence (`TestMigrationIdempotence`)**:
   - `test_idempotence_in_memory_sequential`: 5+ sequential runs return `[]` and keep schema version at 1.
   - `test_idempotence_file_database_sequential`: 5+ sequential runs on file database return `[]` without schema alterations.
   - `test_idempotence_with_target_version`: Repeated calls with explicit target version are safe no-ops.
2. **Tamper Detection (`TestMigrationTamperDetection`)**:
   - `test_tamper_detected_by_modifying_on_disk_file`: Appending comments to an applied migration script raises `MigrationError` containing file name, expected checksum, and actual checksum; `get_migration_status()` marks status as `"tampered"`.
   - `test_tamper_detected_by_modifying_database_record`: Corrupting recorded checksum in DB ledger triggers `MigrationError`.
3. **Missing Migration File Detection (`TestMissingMigrationFile`)**:
   - `test_missing_single_applied_migration`: Deleting applied migration file triggers `MigrationError` and status `"missing"`.
   - `test_missing_intermediate_migration_file`: Deleting an intermediate applied migration while later ones exist distinguishes missing file from future schema version.
4. **Atomic Rollback on Mid-Script Failure (`TestAtomicRollbackOnFailure`)**:
   - `test_atomic_rollback_on_syntax_error_mid_script`: Multi-statement migration where statement 3 has invalid syntax rolls back statements 1 and 2 completely; zero partial tables exist; ledger remains unmutated.
   - `test_atomic_rollback_on_table_already_exists`: Table collision rolls back preceding created tables; database remains at prior version.
   - `test_atomic_rollback_on_constraint_violation`: Primary key violation mid-script rolls back entire transaction.
   - `test_subsequent_valid_migration_succeeds_after_rollback`: Repairing SQL script allows subsequent migration to succeed without residual corruption.
5. **Migration Lock Concurrency (`TestMigrationLockConcurrency`)**:
   - `test_in_memory_lock_reentrancy_on_same_thread`: In-memory lock is safely re-entrant.
   - `test_file_lock_reentrancy_on_same_thread`: File lock is safely re-entrant.
   - `test_in_memory_lock_blocks_concurrent_thread`: Competing thread fails to acquire lock and raises `MigrationError`.
   - `test_file_lock_blocks_concurrent_thread`: Competing thread on file database fails with `MigrationError`.
   - `test_file_lock_blocks_concurrent_process`: Independent Python subprocess holding file lock blocks main process from acquiring lock.
6. **Downgrade / Unsupported Future Version Guard (`TestDowngradeAndFutureVersionGuard`)**:
   - `test_future_schema_version_rejected`: Database containing version 999 rejected by `verify_migrations()` and `apply_migrations()`.
7. **Migration Status Reporting (`TestMigrationStatusReporting`)**:
   - `test_status_lifecycle_transitions`: Tracks status across `"pending"`, `"applied"`, `"tampered"`, and `"missing"` transitions.
   - `test_status_empty_database_and_dir`: Uninitialized database and empty directory cleanly report empty status list.

### 4.2 Full Test Suite Results
```text
collected 370 items
370 passed, 9 warnings in 3.00s
```
- 351 existing baseline tests passed with zero regressions.
- 19 new migration discipline tests passed with 100% success.

### 4.3 10-Domain Benchmark Suite
Executed `benchmarks/run_benchmarks.py`:
```text
[SUCCESS] All 10 Domain Verification Benchmarks PASSED (10/10) in 0.46s!
```

---

## 5. Acceptance Criteria Checklist

| Acceptance Criterion | Status | Evidence |
|---|:---:|---|
| **migration idempotence check** | PASSED | `TestMigrationIdempotence` verifies 5+ sequential `apply_migrations()` calls return `[]` and preserve schema version without side effects. |
| **cannot edit applied migration unnoticed (checksum)** | PASSED | `TestMigrationTamperDetection` verifies editing on-disk SQL raises `MigrationError` with file name, expected checksum, and actual checksum; status reported as `"tampered"`. |
| **failure rolls back or leaves recoverable state** | PASSED | `TestAtomicRollbackOnFailure` verifies syntax error, table collision, or constraint violation rolls back all preceding statements; zero partial state or orphaned ledger rows persist. |
| **migration lock before schema changes (§25.5)** | PASSED | `TestMigrationLockConcurrency` verifies `acquire_migration_lock()` enforces mutual exclusion across threads and processes, supports thread re-entrancy, and protects `apply_migrations()`. |
| **All 351 existing tests pass** | PASSED | 370/370 tests passed cleanly. |
| **All 10 domain benchmarks pass** | PASSED | 10/10 domain verification benchmarks passed with 100% audit scores. |

---

## 6. Files Changed & Impact Analysis
- `src/tarjoman/storage/database.py`:
  - Added `acquire_migration_lock()`, `verify_migrations()`, `get_migration_status()`.
  - Added process-wide lock registry `_FILE_LOCK_REGISTRY` and `_get_process_lock_for_path`.
  - Integrated `acquire_migration_lock()` and `verify_migrations()` into `apply_migrations()`.
  - Hardened rollback handling with explicit `ROLLBACK` on `conn.in_transaction`.
- `src/tarjoman/storage/__init__.py`:
  - Re-exported `MigrationError`.
- `WORKPACKAGES.json`:
  - Updated `FND-007` status to `DONE`.
  - Promoted `FND-008` status to `READY`.
- `tests/test_migration_discipline.py`:
  - Added 19 comprehensive migration discipline tests.

### Architecture Decisions Impact
- **§18 (Compatibility Policy):** Guaranteed fail-closed behavior on downgrade attempts, missing migrations, and tampered files.
- **§24 (Error Taxonomy):** Typed `MigrationError` raised across all migration failures without destructive automatic repair.
- **§25.5 (Database Rules):** Migration lock before schema changes implemented via `fcntl.flock` and in-memory locks; atomic transaction rollback enforced; immutable checksum verification enforced.
