"""
SQLite database engine and migration runner for Tarjoman workspaces.

Architecture Zero §18 (Versioning and compatibility), §24 (Error taxonomy),
§25.5 (Database rules), and §26 (Persistent Job Engine):
- Numbered immutable SQL migrations with SHA-256 checksums
- Migration locking before schema changes (flock for file DBs, thread lock for memory)
- PRAGMA foreign_keys = ON
- PRAGMA journal_mode = WAL for local file workspaces
- Explicit busy timeout
- Atomic transaction context management with SAVEPOINT nesting
- Fail-closed migration verification (tampering, missing files, and newer unsupported schema detection)
- Complete atomic rollback on migration script failure
- Structured migration status reporting
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment]

from tarjoman.core.errors import MigrationError

MIGRATION_FILE_RE = re.compile(r"^(\d+)_(.+)\.sql$")

# Process-wide registry for file lock synchronization across threads in the same process
_FILE_LOCK_REGISTRY: Dict[Path, threading.Lock] = {}
_REGISTRY_LOCK = threading.Lock()


def _get_process_lock_for_path(path: Path) -> threading.Lock:
    resolved = path.resolve()
    with _REGISTRY_LOCK:
        if resolved not in _FILE_LOCK_REGISTRY:
            _FILE_LOCK_REGISTRY[resolved] = threading.Lock()
        return _FILE_LOCK_REGISTRY[resolved]


class DatabaseManager:
    """Encapsulates SQLite connections, pragmas, transactions, migration locks, and migrations."""

    def __init__(
        self,
        db_path: Union[str, Path] = ":memory:",
        busy_timeout_ms: int = 5000,
        migrations_dir: Optional[Union[str, Path]] = None,
        lock_path: Optional[Union[str, Path]] = None,
    ) -> None:
        self.is_memory = str(db_path) == ":memory:"
        self.db_path = Path(db_path) if not self.is_memory else ":memory:"
        self.busy_timeout_ms = int(busy_timeout_ms)
        self.migrations_dir = (
            Path(migrations_dir)
            if migrations_dir is not None
            else Path(__file__).parent / "migrations"
        )
        self._memory_conn: Optional[sqlite3.Connection] = None
        self._memory_lock = threading.Lock()
        self._lock_holder_thread: Optional[int] = None
        self._lock_depth: int = 0

        if self.is_memory:
            self.lock_path: Optional[Path] = None
            self._memory_conn = self._create_connection()
        else:
            assert isinstance(self.db_path, Path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            if lock_path is not None:
                self.lock_path = Path(lock_path)
            else:
                locks_dir = self.db_path.parent / "locks"
                if locks_dir.is_dir() or self.db_path.parent.name == ".tarjoman":
                    locks_dir.mkdir(parents=True, exist_ok=True)
                    self.lock_path = locks_dir / "migration.lock"
                else:
                    self.lock_path = Path(f"{self.db_path}.migration.lock")

    def _init_pragmas(self, conn: sqlite3.Connection) -> None:
        """Apply mandatory SQLite PRAGMAs (D07, §25.5)."""
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms};")

    def _create_connection(self) -> sqlite3.Connection:
        """Create and configure a fresh SQLite connection."""
        conn_path = ":memory:" if self.is_memory else str(self.db_path)
        conn = sqlite3.connect(
            conn_path,
            timeout=float(self.busy_timeout_ms) / 1000.0,
            check_same_thread=False,
            isolation_level=None,  # Autocommit mode for explicit transaction control
        )
        conn.row_factory = sqlite3.Row
        self._init_pragmas(conn)
        return conn

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Provide a connection context.

        For in-memory databases, yields the persistent shared connection.
        For file databases, creates a connection and closes it upon exit.
        """
        if self.is_memory:
            if self._memory_conn is None:
                self._memory_conn = self._create_connection()
            yield self._memory_conn
        else:
            conn = self._create_connection()
            try:
                yield conn
            finally:
                conn.close()

    @contextmanager
    def transaction(
        self, conn: Optional[sqlite3.Connection] = None
    ) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for atomic database transactions.

        If a connection is provided, uses nested SAVEPOINTs to allow
        composable transactions. If none is provided, acquires a connection
        and initiates a BEGIN IMMEDIATE transaction.
        """
        if conn is not None:
            # Nested transaction via SAVEPOINT
            sp_name = f"sp_{uuid.uuid4().hex[:12]}"
            conn.execute(f"SAVEPOINT {sp_name};")
            try:
                yield conn
                conn.execute(f"RELEASE SAVEPOINT {sp_name};")
            except Exception:
                conn.execute(f"ROLLBACK TO SAVEPOINT {sp_name};")
                conn.execute(f"RELEASE SAVEPOINT {sp_name};")
                raise
        else:
            with self.connection() as new_conn:
                new_conn.execute("BEGIN IMMEDIATE;")
                try:
                    yield new_conn
                    new_conn.execute("COMMIT;")
                except Exception:
                    new_conn.execute("ROLLBACK;")
                    raise

    @contextmanager
    def acquire_migration_lock(
        self, timeout: Optional[float] = None
    ) -> Generator[None, None, None]:
        """Context manager to acquire an exclusive migration lock.

        Architecture Zero §25.5: Migration lock before schema changes.
        - For in-memory databases, uses an in-memory lock.
        - For file workspaces, uses an OS-level file lock (via fcntl.flock)
          combined with an in-process thread lock to prevent both inter-process
          and inter-thread migration races.
        - Fully re-entrant on the holding thread.
        - Times out and raises MigrationError if lock cannot be acquired.
        """
        lock_timeout = (
            float(self.busy_timeout_ms) / 1000.0 if timeout is None else max(0.0, float(timeout))
        )
        current_thread = threading.get_ident()

        # Re-entrant acquisition on the same thread
        if self._lock_holder_thread == current_thread:
            self._lock_depth += 1
            try:
                yield
            finally:
                self._lock_depth -= 1
                if self._lock_depth == 0:
                    self._lock_holder_thread = None
            return

        if self.is_memory:
            acquired = self._memory_lock.acquire(timeout=lock_timeout)
            if not acquired:
                raise MigrationError(
                    f"Failed to acquire in-memory migration lock within {lock_timeout:.3f}s: "
                    "migration already in progress in another thread"
                )
            try:
                self._lock_holder_thread = current_thread
                self._lock_depth = 1
                yield
            finally:
                self._lock_depth = 0
                self._lock_holder_thread = None
                self._memory_lock.release()
            return

        # File workspace lock
        assert self.lock_path is not None
        thread_lock = _get_process_lock_for_path(self.lock_path)
        deadline = time.monotonic() + lock_timeout

        thread_acquired = thread_lock.acquire(timeout=lock_timeout)
        if not thread_acquired:
            raise MigrationError(
                f"Failed to acquire migration lock on {self.lock_path} within {lock_timeout:.3f}s: "
                "migration already in progress in another thread"
            )

        fd: Optional[int] = None
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(self.lock_path), os.O_RDWR | os.O_CREAT, 0o644)

            file_locked = False
            while True:
                try:
                    if fcntl is not None:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    file_locked = True
                    break
                except (BlockingIOError, OSError):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    time.sleep(min(0.05, max(0.005, remaining)))

            if not file_locked:
                raise MigrationError(
                    f"Failed to acquire migration lock on {self.lock_path} within {lock_timeout:.3f}s: "
                    "database is currently being migrated by another process"
                )

            try:
                os.ftruncate(fd, 0)
                os.lseek(fd, 0, os.SEEK_SET)
                meta = (
                    f"pid={os.getpid()} "
                    f"thread={current_thread} "
                    f"time={datetime.now(timezone.utc).isoformat()}\n"
                )
                os.write(fd, meta.encode("utf-8"))
            except Exception:
                pass

            self._lock_holder_thread = current_thread
            self._lock_depth = 1

            try:
                yield
            finally:
                self._lock_depth = 0
                self._lock_holder_thread = None
                if fcntl is not None:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                    except Exception:
                        pass
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except Exception:
                    pass
            thread_lock.release()

    def _discover_migrations(self) -> Dict[int, Dict[str, Any]]:
        """Discover and validate migration files in the migrations directory."""
        if not self.migrations_dir.exists() or not self.migrations_dir.is_dir():
            return {}

        migrations: Dict[int, Dict[str, Any]] = {}
        for entry in sorted(self.migrations_dir.iterdir()):
            if not entry.is_file():
                continue
            match = MIGRATION_FILE_RE.match(entry.name)
            if not match:
                continue

            version = int(match.group(1))
            name = entry.name
            content = entry.read_text(encoding="utf-8")
            checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()

            if version in migrations:
                raise MigrationError(
                    f"Duplicate migration version {version} found: {name} and {migrations[version]['name']}"
                )

            migrations[version] = {
                "version": version,
                "name": name,
                "path": entry,
                "content": content,
                "checksum": checksum,
            }

        return migrations

    def verify_migrations(self) -> bool:
        """Validate integrity of all applied migrations against on-disk files.

        Architecture Zero §18 & §25.5:
        1. Validates that every migration recorded in schema_migrations matches
           the on-disk file checksum byte-for-byte.
        2. Detects modified file content (checksum mismatch) -> raises MigrationError
           with file name, expected checksum, and actual checksum.
        3. Detects missing applied migration file -> raises MigrationError.
        4. Detects schema version in DB newer than known code -> raises MigrationError.

        Returns:
            True if all applied migrations are valid.

        Raises:
            MigrationError: On tampering, missing files, or unsupported future schema version.
        """
        discovered = self._discover_migrations()
        max_known = max(discovered.keys()) if discovered else 0

        with self.connection() as conn:
            cursor = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='schema_migrations';"
            )
            if cursor.fetchone()[0] == 0:
                # Fresh, uninitialized database
                return True

            cursor = conn.execute(
                "SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version ASC;"
            )
            applied_rows = cursor.fetchall()
            if not applied_rows:
                return True

            for row in applied_rows:
                ver = row["version"]
                name = row["name"]
                recorded_checksum = row["checksum"]

                if len(discovered) > 0 and ver > max_known:
                    raise MigrationError(
                        f"Database schema version {ver} is newer than maximum supported version {max_known}"
                    )

                if ver not in discovered:
                    raise MigrationError(
                        f"Applied migration {ver} ({name}) file is missing from migrations directory: {self.migrations_dir}"
                    )

                actual_checksum = discovered[ver]["checksum"]
                if recorded_checksum != actual_checksum:
                    raise MigrationError(
                        f"Migration checksum mismatch for version {ver} ({name}): "
                        f"expected checksum {recorded_checksum}, actual checksum {actual_checksum}"
                    )

            return True

    def get_migration_status(self) -> List[Dict[str, Any]]:
        """Return structured status for all discovered and applied migrations.

        Returns a list of status dictionaries sorted by version ascending:
        - version: int
        - name: str
        - checksum: str (on-disk checksum if available, else database checksum)
        - applied_at: Optional[str] (ISO timestamp or None if pending)
        - status: "applied" | "pending" | "tampered" | "missing"
        - recorded_checksum: Optional[str] (checksum recorded in DB, or None)
        - file_checksum: Optional[str] (checksum from file on disk, or None)
        """
        discovered = self._discover_migrations()

        applied_map: Dict[int, Dict[str, Any]] = {}
        with self.connection() as conn:
            cursor = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='schema_migrations';"
            )
            if cursor.fetchone()[0] > 0:
                cursor = conn.execute(
                    "SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version ASC;"
                )
                for row in cursor.fetchall():
                    applied_map[row["version"]] = {
                        "version": row["version"],
                        "name": row["name"],
                        "checksum": row["checksum"],
                        "applied_at": row["applied_at"],
                    }

        all_versions = sorted(set(discovered.keys()) | set(applied_map.keys()))
        status_list: List[Dict[str, Any]] = []

        for v in all_versions:
            in_applied = v in applied_map
            in_discovered = v in discovered

            if in_applied and in_discovered:
                rec_sum = applied_map[v]["checksum"]
                disk_sum = discovered[v]["checksum"]
                status = "applied" if rec_sum == disk_sum else "tampered"
                status_list.append(
                    {
                        "version": v,
                        "name": discovered[v]["name"],
                        "checksum": disk_sum,
                        "applied_at": applied_map[v]["applied_at"],
                        "status": status,
                        "recorded_checksum": rec_sum,
                        "file_checksum": disk_sum,
                    }
                )
            elif in_applied and not in_discovered:
                status_list.append(
                    {
                        "version": v,
                        "name": applied_map[v]["name"],
                        "checksum": applied_map[v]["checksum"],
                        "applied_at": applied_map[v]["applied_at"],
                        "status": "missing",
                        "recorded_checksum": applied_map[v]["checksum"],
                        "file_checksum": None,
                    }
                )
            else:  # in_discovered and not in_applied
                disk_sum = discovered[v]["checksum"]
                status_list.append(
                    {
                        "version": v,
                        "name": discovered[v]["name"],
                        "checksum": disk_sum,
                        "applied_at": None,
                        "status": "pending",
                        "recorded_checksum": None,
                        "file_checksum": disk_sum,
                    }
                )

        return status_list

    def apply_migrations(self, target_version: Optional[int] = None) -> List[int]:
        """Apply pending migrations in sequential order under migration lock.

        Verifies:
        1. All already applied migrations match their recorded SHA-256 checksums.
        2. Database schema version is not newer than known code migrations.
        3. No applied migration files are missing from disk.
        4. Pending migrations execute atomically under BEGIN IMMEDIATE.
        """
        with self.acquire_migration_lock():
            with self.connection() as conn:
                # 1. Ensure schema_migrations table exists
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        checksum TEXT NOT NULL,
                        applied_at TEXT NOT NULL
                    );
                    """
                )

            # 2. Verify integrity of existing applied migrations (§18, §25.5)
            self.verify_migrations()

            # 3. Discover migrations on disk
            discovered = self._discover_migrations()

            # 4. Read applied versions
            with self.connection() as conn:
                cursor = conn.execute(
                    "SELECT version FROM schema_migrations ORDER BY version ASC;"
                )
                applied_versions_set = {row["version"] for row in cursor.fetchall()}

            # 5. Determine pending migrations
            pending_versions = [
                v
                for v in sorted(discovered.keys())
                if v not in applied_versions_set
                and (target_version is None or v <= target_version)
            ]

            if not pending_versions:
                return []

            # 6. Apply each pending migration in its own atomic transaction
            applied: List[int] = []
            with self.connection() as conn:
                for ver in pending_versions:
                    m = discovered[ver]
                    now_iso = datetime.now(timezone.utc).isoformat()
                    sql = m["content"]

                    try:
                        conn.executescript(f"BEGIN IMMEDIATE;\n{sql};\n")
                        conn.execute(
                            "INSERT INTO schema_migrations (version, name, checksum, applied_at) VALUES (?, ?, ?, ?);",
                            (ver, m["name"], m["checksum"], now_iso),
                        )
                        conn.execute("COMMIT;")
                        applied.append(ver)
                    except Exception as exc:
                        try:
                            if conn.in_transaction:
                                conn.execute("ROLLBACK;")
                        except Exception:
                            pass
                        raise MigrationError(
                            f"Failed to apply migration {ver} ({m['name']}): {exc}"
                        ) from exc

            return applied

    def get_applied_migrations(self) -> List[Dict[str, Any]]:
        """Return list of applied migrations recorded in the ledger."""
        with self.connection() as conn:
            cursor = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='schema_migrations';"
            )
            if cursor.fetchone()[0] == 0:
                return []
            cursor = conn.execute(
                "SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version ASC;"
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_current_version(self) -> int:
        """Return the highest applied schema version, or 0 if uninitialized."""
        applied = self.get_applied_migrations()
        if not applied:
            return 0
        return max(m["version"] for m in applied)

    def close(self) -> None:
        """Close persistent resources (in-memory connection and lock states)."""
        if self._memory_conn is not None:
            try:
                self._memory_conn.close()
            except Exception:
                pass
            self._memory_conn = None
        self._lock_depth = 0
        self._lock_holder_thread = None

    def __enter__(self) -> DatabaseManager:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
