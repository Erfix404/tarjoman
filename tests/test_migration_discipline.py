"""
Comprehensive Migration Discipline Tests for Tarjoman Workspace (FND-007).

Architecture Zero §18 (Versioning and compatibility policy),
§24 (Error taxonomy & failure semantics: MigrationError with no automatic destructive repair),
and §25.5 (Database rules: numbered immutable SQL migrations with checksums,
migration lock before schema changes).

Acceptance criteria:
- migration idempotence check: repeated apply_migrations() calls are proven safe no-ops
- cannot edit applied migration unnoticed (checksum): modifying an applied SQL file fails loudly
- failure rolls back or leaves recoverable state: mid-script failure rolls back completely
- migration lock before schema changes implemented and tested
- status reporting: get_migration_status() accurate for applied, pending, tampered, missing
- downgrade / unsupported future version guard: schema version higher than code raises MigrationError
"""
from __future__ import annotations

import multiprocessing
import os
import shutil
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import Generator, List

import pytest

from tarjoman.core.errors import MigrationError
from tarjoman.storage import DatabaseManager


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def temp_workspace() -> Generator[Path, None, None]:
    """Provide a temporary directory structure mimicking a Tarjoman workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws_root = Path(tmpdir)
        tarjoman_dir = ws_root / ".tarjoman"
        tarjoman_dir.mkdir(parents=True)
        (tarjoman_dir / "locks").mkdir()
        (tarjoman_dir / "migrations").mkdir()
        yield ws_root


@pytest.fixture
def standard_migrations_dir(temp_workspace: Path) -> Path:
    """Provide a copy of the canonical migration 001 in a temporary migrations dir."""
    mig_dir = temp_workspace / ".tarjoman" / "migrations"
    canonical_001 = Path(__file__).parent.parent / "src" / "tarjoman" / "storage" / "migrations" / "001_initial_schema.sql"
    shutil.copy(canonical_001, mig_dir / "001_initial_schema.sql")
    return mig_dir


# ===========================================================================
# 1. Migration Idempotence Check (§25.5, FND-007 Acceptance)
# ===========================================================================

class TestMigrationIdempotence:
    """Repeated apply_migrations() calls must be safe, fast no-ops returning []."""

    def test_idempotence_in_memory_sequential(self) -> None:
        """Sequential invocations (5+) on an in-memory database are no-ops."""
        db = DatabaseManager(":memory:")
        first_applied = db.apply_migrations()
        assert first_applied == [1]
        assert db.get_current_version() == 1

        for iteration in range(5):
            subsequent = db.apply_migrations()
            assert subsequent == [], f"Iteration {iteration + 1} applied non-empty migrations: {subsequent}"
            assert db.get_current_version() == 1

        # Check table count remains stable
        with db.connection() as conn:
            cursor = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table';")
            count = cursor.fetchone()[0]
            assert count >= 6  # schema_migrations, projects, operations, artifacts, segments, jobs, etc.

        db.close()

    def test_idempotence_file_database_sequential(self, temp_workspace: Path) -> None:
        """Sequential invocations (5+) on a file database are no-ops with unchanging schema."""
        db_path = temp_workspace / ".tarjoman" / "state.sqlite3"
        db = DatabaseManager(db_path)
        first_applied = db.apply_migrations()
        assert first_applied == [1]
        assert db.get_current_version() == 1

        for iteration in range(5):
            subsequent = db.apply_migrations()
            assert subsequent == [], f"Iteration {iteration + 1} returned {subsequent}"
            assert db.get_current_version() == 1

        db.close()

    def test_idempotence_with_target_version(self) -> None:
        """Calling apply_migrations with explicit target_version repeatedly is safe."""
        db = DatabaseManager(":memory:")
        applied = db.apply_migrations(target_version=1)
        assert applied == [1]

        for _ in range(5):
            assert db.apply_migrations(target_version=1) == []
            assert db.get_current_version() == 1

        db.close()


# ===========================================================================
# 2. Tamper Detection & Checksum Integrity (§18, §25.5)
# ===========================================================================

class TestMigrationTamperDetection:
    """Cannot edit applied migration unnoticed; checksum mismatch raises MigrationError."""

    def test_tamper_detected_by_modifying_on_disk_file(self, standard_migrations_dir: Path) -> None:
        """Modifying SQL file content after application causes subsequent verify and apply to fail loudly."""
        sql_file = standard_migrations_dir / "001_initial_schema.sql"
        original_content = sql_file.read_text(encoding="utf-8")

        db = DatabaseManager(":memory:", migrations_dir=standard_migrations_dir)
        applied = db.apply_migrations()
        assert applied == [1]
        assert db.verify_migrations() is True

        # Tamper with on-disk migration file: append comment
        tampered_content = original_content + "\n-- Malicious or accidental modification\n"
        sql_file.write_text(tampered_content, encoding="utf-8")

        # 1. verify_migrations() must fail loudly with MigrationError
        with pytest.raises(MigrationError) as exc_info:
            db.verify_migrations()
        err_msg = str(exc_info.value)
        assert "checksum mismatch" in err_msg.lower()
        assert "001_initial_schema.sql" in err_msg
        assert "expected checksum" in err_msg
        assert "actual checksum" in err_msg

        # 2. apply_migrations() must also refuse to run
        with pytest.raises(MigrationError) as exc_info2:
            db.apply_migrations()
        assert "checksum mismatch" in str(exc_info2.value).lower()

        # 3. get_migration_status() must report 'tampered'
        status = db.get_migration_status()
        assert len(status) == 1
        assert status[0]["version"] == 1
        assert status[0]["status"] == "tampered"
        assert status[0]["recorded_checksum"] != status[0]["file_checksum"]

        db.close()

    def test_tamper_detected_by_modifying_database_record(self) -> None:
        """Modifying recorded checksum in database ledger triggers MigrationError."""
        db = DatabaseManager(":memory:")
        db.apply_migrations()

        with db.connection() as conn:
            conn.execute(
                "UPDATE schema_migrations SET checksum = '0000000000000000000000000000000000000000000000000000000000000000' WHERE version = 1;"
            )

        with pytest.raises(MigrationError) as exc_info:
            db.verify_migrations()
        assert "checksum mismatch" in str(exc_info.value).lower()

        with pytest.raises(MigrationError):
            db.apply_migrations()

        status = db.get_migration_status()
        assert status[0]["status"] == "tampered"

        db.close()


# ===========================================================================
# 3. Missing Migration File Detection (§18, §25.5)
# ===========================================================================

class TestMissingMigrationFile:
    """Missing applied migration file must be detected and raise MigrationError."""

    def test_missing_single_applied_migration(self, standard_migrations_dir: Path) -> None:
        """Deleting an applied migration file causes verify and apply to fail loudly."""
        sql_file = standard_migrations_dir / "001_initial_schema.sql"
        db = DatabaseManager(":memory:", migrations_dir=standard_migrations_dir)
        db.apply_migrations()
        assert db.verify_migrations() is True

        # Delete the file
        sql_file.unlink()

        # verify_migrations() must detect missing file
        with pytest.raises(MigrationError) as exc_info:
            db.verify_migrations()
        assert "missing from migrations directory" in str(exc_info.value)
        assert "001_initial_schema.sql" in str(exc_info.value)

        # apply_migrations() must refuse to run
        with pytest.raises(MigrationError):
            db.apply_migrations()

        # status reporting must show 'missing'
        status = db.get_migration_status()
        assert len(status) == 1
        assert status[0]["version"] == 1
        assert status[0]["status"] == "missing"
        assert status[0]["file_checksum"] is None

        db.close()

    def test_missing_intermediate_migration_file(self) -> None:
        """Deleting migration 001 while migration 002 exists on disk distinguishes missing file from future schema."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mig_dir = Path(tmpdir) / "migrations"
            mig_dir.mkdir()
            f1 = mig_dir / "001_init.sql"
            f2 = mig_dir / "002_next.sql"
            f1.write_text("CREATE TABLE t1 (id INT PRIMARY KEY);", encoding="utf-8")
            f2.write_text("CREATE TABLE t2 (id INT PRIMARY KEY);", encoding="utf-8")

            db = DatabaseManager(":memory:", migrations_dir=mig_dir)
            db.apply_migrations()
            assert db.get_current_version() == 2

            # Remove 001, leave 002 on disk (max_known is 2, ver is 1)
            f1.unlink()

            with pytest.raises(MigrationError) as exc_info:
                db.verify_migrations()
            assert "missing from migrations directory" in str(exc_info.value)

            status = db.get_migration_status()
            assert len(status) == 2
            assert status[0]["version"] == 1 and status[0]["status"] == "missing"
            assert status[1]["version"] == 2 and status[1]["status"] == "applied"

            db.close()


# ===========================================================================
# 4. Atomic Rollback on Mid-Script Failure (§24, §25.5)
# ===========================================================================

class TestAtomicRollbackOnFailure:
    """Mid-script failure rolls back completely, leaving previous version intact."""

    def test_atomic_rollback_on_syntax_error_mid_script(self) -> None:
        """Migration with syntax error at statement 3 rolls back statement 1 and 2."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mig_dir = Path(tmpdir) / "migrations"
            mig_dir.mkdir()

            (mig_dir / "001_valid.sql").write_text(
                "CREATE TABLE base_table (id INT PRIMARY KEY);", encoding="utf-8"
            )
            # Statement 1: CREATE TABLE partial_1
            # Statement 2: CREATE TABLE partial_2
            # Statement 3: INVALID SQL SYNTAX
            # Statement 4: CREATE TABLE partial_3
            bad_sql = (
                "CREATE TABLE partial_1 (id INT PRIMARY KEY);\n"
                "CREATE TABLE partial_2 (id INT PRIMARY KEY);\n"
                "MALFORMED_SQL_STATEMENT_HERE_CRASH;\n"
                "CREATE TABLE partial_3 (id INT PRIMARY KEY);\n"
            )
            (mig_dir / "002_bad.sql").write_text(bad_sql, encoding="utf-8")

            db = DatabaseManager(":memory:", migrations_dir=mig_dir)
            # Apply 001 first
            db.apply_migrations(target_version=1)
            assert db.get_current_version() == 1

            # Attempt to apply 002
            with pytest.raises(MigrationError) as exc_info:
                db.apply_migrations()
            assert "Failed to apply migration 2" in str(exc_info.value)

            # Assert database remained cleanly at version 1
            assert db.get_current_version() == 1
            with db.connection() as conn:
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [row[0] for row in cursor.fetchall()]
                assert "base_table" in tables
                assert "partial_1" not in tables
                assert "partial_2" not in tables
                assert "partial_3" not in tables

                # Assert schema_migrations only has version 1
                cursor = conn.execute("SELECT version FROM schema_migrations;")
                versions = [row[0] for row in cursor.fetchall()]
                assert versions == [1]

            db.close()

    def test_atomic_rollback_on_table_already_exists(self) -> None:
        """Pre-existing table collision rolls back all preceding statements in the migration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mig_dir = Path(tmpdir) / "migrations"
            mig_dir.mkdir()

            (mig_dir / "001_base.sql").write_text(
                "CREATE TABLE base (id INT PRIMARY KEY);", encoding="utf-8"
            )
            # Create a migration that attempts to create an already-existing table without IF NOT EXISTS
            (mig_dir / "002_collision.sql").write_text(
                "CREATE TABLE prefix_table (id INT);\n"
                "CREATE TABLE base (id INT);\n"  # Table base already exists!
                "CREATE TABLE postfix_table (id INT);\n",
                encoding="utf-8",
            )

            db = DatabaseManager(":memory:", migrations_dir=mig_dir)
            db.apply_migrations(target_version=1)
            assert db.get_current_version() == 1

            with pytest.raises(MigrationError) as exc_info:
                db.apply_migrations()
            assert "Failed to apply migration 2" in str(exc_info.value)

            # Assert prefix_table and postfix_table were not left behind
            with db.connection() as conn:
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [row[0] for row in cursor.fetchall()]
                assert "base" in tables
                assert "prefix_table" not in tables
                assert "postfix_table" not in tables

            assert db.get_current_version() == 1
            db.close()

    def test_atomic_rollback_on_constraint_violation(self) -> None:
        """Primary key constraint violation mid-script rolls back entire transaction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mig_dir = Path(tmpdir) / "migrations"
            mig_dir.mkdir()

            (mig_dir / "001_dupe.sql").write_text(
                "CREATE TABLE users (id INT PRIMARY KEY, name TEXT);\n"
                "INSERT INTO users VALUES (1, 'Alice');\n"
                "INSERT INTO users VALUES (1, 'Duplicate Alice');\n",  # Primary key violation
                encoding="utf-8",
            )

            db = DatabaseManager(":memory:", migrations_dir=mig_dir)
            with pytest.raises(MigrationError) as exc_info:
                db.apply_migrations()
            assert "Failed to apply migration 1" in str(exc_info.value)

            # Table users must NOT exist
            with db.connection() as conn:
                cursor = conn.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='users';"
                )
                assert cursor.fetchone()[0] == 0

            assert db.get_current_version() == 0
            db.close()

    def test_subsequent_valid_migration_succeeds_after_rollback(self) -> None:
        """After a failed migration rolls back, repairing the SQL script allows clean migration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mig_dir = Path(tmpdir) / "migrations"
            mig_dir.mkdir()

            (mig_dir / "001_base.sql").write_text(
                "CREATE TABLE base (id INT PRIMARY KEY);", encoding="utf-8"
            )
            mig2_path = mig_dir / "002_step.sql"
            mig2_path.write_text("INVALID SQL;", encoding="utf-8")

            db = DatabaseManager(":memory:", migrations_dir=mig_dir)
            db.apply_migrations(target_version=1)

            # Fails on 002
            with pytest.raises(MigrationError):
                db.apply_migrations()

            # Fix 002
            mig2_path.write_text("CREATE TABLE step2 (val TEXT);", encoding="utf-8")

            # Subsequent migration succeeds
            applied = db.apply_migrations()
            assert applied == [2]
            assert db.get_current_version() == 2

            with db.connection() as conn:
                cursor = conn.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='step2';"
                )
                assert cursor.fetchone()[0] == 1

            db.close()


# ===========================================================================
# 5. Migration Lock Concurrency (§25.5)
# ===========================================================================

class TestMigrationLockConcurrency:
    """Migration lock protects against concurrent overlapping migrations."""

    def test_in_memory_lock_reentrancy_on_same_thread(self) -> None:
        """Migration lock is cleanly re-entrant on the holding thread."""
        db = DatabaseManager(":memory:")
        with db.acquire_migration_lock():
            with db.acquire_migration_lock():
                # apply_migrations itself acquires the lock
                applied = db.apply_migrations()
                assert applied == [1]

        assert db.get_current_version() == 1
        db.close()

    def test_file_lock_reentrancy_on_same_thread(self, temp_workspace: Path) -> None:
        """File workspace migration lock is cleanly re-entrant on the holding thread."""
        db_path = temp_workspace / ".tarjoman" / "state.sqlite3"
        db = DatabaseManager(db_path)
        with db.acquire_migration_lock():
            with db.acquire_migration_lock():
                applied = db.apply_migrations()
                assert applied == [1]

        assert db.get_current_version() == 1
        db.close()

    def test_in_memory_lock_blocks_concurrent_thread(self) -> None:
        """In-memory lock prevents concurrent migration from another thread."""
        db = DatabaseManager(":memory:")
        lock_held_event = threading.Event()
        proceed_event = threading.Event()
        worker_outcome: List[str] = []

        def holding_worker() -> None:
            with db.acquire_migration_lock(timeout=2.0):
                lock_held_event.set()
                proceed_event.wait(timeout=3.0)

        def competing_worker() -> None:
            lock_held_event.wait(timeout=2.0)
            try:
                # Short timeout should fail with MigrationError
                with db.acquire_migration_lock(timeout=0.05):
                    worker_outcome.append("acquired")
            except MigrationError:
                worker_outcome.append("blocked_as_expected")

        t1 = threading.Thread(target=holding_worker)
        t2 = threading.Thread(target=competing_worker)

        t1.start()
        t2.start()
        t2.join(timeout=3.0)
        proceed_event.set()
        t1.join(timeout=3.0)

        assert worker_outcome == ["blocked_as_expected"]
        db.close()

    def test_file_lock_blocks_concurrent_thread(self, temp_workspace: Path) -> None:
        """File lock prevents concurrent migration from another thread on same workspace."""
        db_path = temp_workspace / ".tarjoman" / "state.sqlite3"
        db1 = DatabaseManager(db_path)
        db2 = DatabaseManager(db_path)

        lock_held_event = threading.Event()
        release_event = threading.Event()
        outcome: List[str] = []

        def holder() -> None:
            with db1.acquire_migration_lock(timeout=2.0):
                lock_held_event.set()
                release_event.wait(timeout=3.0)

        def contender() -> None:
            lock_held_event.wait(timeout=2.0)
            try:
                with db2.acquire_migration_lock(timeout=0.05):
                    outcome.append("acquired")
            except MigrationError:
                outcome.append("blocked")

        t1 = threading.Thread(target=holder)
        t2 = threading.Thread(target=contender)

        t1.start()
        t2.start()
        t2.join(timeout=3.0)
        release_event.set()
        t1.join(timeout=3.0)

        assert outcome == ["blocked"]
        db1.close()
        db2.close()

    def test_file_lock_blocks_concurrent_process(self, temp_workspace: Path) -> None:
        """File lock prevents concurrent process from acquiring lock simultaneously."""
        import subprocess
        import sys

        db_path = temp_workspace / ".tarjoman" / "state.sqlite3"

        worker_code = """import sys, time
from tarjoman.storage.database import DatabaseManager
db = DatabaseManager(sys.argv[1])
with db.acquire_migration_lock(timeout=5.0):
    print('LOCKED', flush=True)
    line = sys.stdin.readline()
"""

        proc = subprocess.Popen(
            [sys.executable, "-c", worker_code, str(db_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            assert proc.stdout is not None
            line = proc.stdout.readline().strip()
            assert line == "LOCKED", f"Expected LOCKED from subprocess, got {line}"

            # Main process attempts to acquire lock with short timeout
            main_db = DatabaseManager(db_path)
            with pytest.raises(MigrationError) as exc_info:
                with main_db.acquire_migration_lock(timeout=0.05):
                    pass
            assert "locked by another process" in str(exc_info.value) or "database is currently" in str(exc_info.value)

            # Signal subprocess to release lock and exit
            assert proc.stdin is not None
            proc.stdin.write("release\n")
            proc.stdin.flush()
            proc.wait(timeout=3.0)

            # Now main process can acquire lock cleanly
            with main_db.acquire_migration_lock(timeout=1.0):
                pass
            main_db.close()
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=1.0)


# ===========================================================================
# 6. Unsupported Future Version / Downgrade Guard (§18)
# ===========================================================================

class TestDowngradeAndFutureVersionGuard:
    """Opening or migrating a database with schema version newer than known code must fail read-only."""

    def test_future_schema_version_rejected(self) -> None:
        """Database with schema version 999 rejected with precise compatibility message."""
        db = DatabaseManager(":memory:")
        db.apply_migrations()

        with db.connection() as conn:
            conn.execute(
                "INSERT INTO schema_migrations (version, name, checksum, applied_at) VALUES (999, '999_future.sql', 'fakehash', '2026-09-21T00:00:00Z');"
            )

        with pytest.raises(MigrationError) as exc_info:
            db.verify_migrations()
        assert "newer than maximum supported version" in str(exc_info.value)
        assert "999" in str(exc_info.value)

        with pytest.raises(MigrationError) as exc_info2:
            db.apply_migrations()
        assert "newer than maximum supported version" in str(exc_info2.value)

        db.close()


# ===========================================================================
# 7. Migration Status Reporting (§18, §25.5)
# ===========================================================================

class TestMigrationStatusReporting:
    """get_migration_status() reports applied, pending, tampered, and missing."""

    def test_status_lifecycle_transitions(self) -> None:
        """Track migration status across pending -> applied -> tampered -> missing transitions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mig_dir = Path(tmpdir) / "migrations"
            mig_dir.mkdir()

            f1 = mig_dir / "001_init.sql"
            f2 = mig_dir / "002_extra.sql"
            f1.write_text("CREATE TABLE t1 (id INT PRIMARY KEY);", encoding="utf-8")
            f2.write_text("CREATE TABLE t2 (id INT PRIMARY KEY);", encoding="utf-8")

            db = DatabaseManager(":memory:", migrations_dir=mig_dir)

            # 1. Before apply: both should be pending
            st_pre = db.get_migration_status()
            assert len(st_pre) == 2
            assert st_pre[0]["version"] == 1 and st_pre[0]["status"] == "pending" and st_pre[0]["applied_at"] is None
            assert st_pre[1]["version"] == 2 and st_pre[1]["status"] == "pending" and st_pre[1]["applied_at"] is None

            # 2. Apply version 1 only
            db.apply_migrations(target_version=1)
            st_mid = db.get_migration_status()
            assert st_mid[0]["version"] == 1 and st_mid[0]["status"] == "applied" and st_mid[0]["applied_at"] is not None
            assert st_mid[1]["version"] == 2 and st_mid[1]["status"] == "pending"

            # 3. Tamper with version 1
            f1.write_text("CREATE TABLE t1 (id INT PRIMARY KEY); -- modified", encoding="utf-8")
            st_tampered = db.get_migration_status()
            assert st_tampered[0]["version"] == 1 and st_tampered[0]["status"] == "tampered"
            assert st_tampered[1]["version"] == 2 and st_tampered[1]["status"] == "pending"

            # 4. Remove version 1
            f1.unlink()
            st_missing = db.get_migration_status()
            assert st_missing[0]["version"] == 1 and st_missing[0]["status"] == "missing"
            assert st_missing[0]["file_checksum"] is None
            assert st_missing[1]["version"] == 2 and st_missing[1]["status"] == "pending"

            db.close()

    def test_status_empty_database_and_dir(self) -> None:
        """Empty directory and uninitialized database returns empty status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_mig_dir = Path(tmpdir) / "empty_migrations"
            empty_mig_dir.mkdir()
            db = DatabaseManager(":memory:", migrations_dir=empty_mig_dir)
            assert db.get_migration_status() == []
            assert db.verify_migrations() is True
            db.close()
