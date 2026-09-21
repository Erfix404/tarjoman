"""
SQLite database engine and migration runner for Tarjoman workspaces.

Architecture Zero §25.5 (Database rules) & §26 (Persistent Job Engine):
- Numbered immutable SQL migrations with SHA-256 checksums
- PRAGMA foreign_keys = ON
- PRAGMA journal_mode = WAL for local file workspaces
- Explicit busy timeout
- Atomic transaction context management with SAVEPOINT nesting
- Fail-closed migration verification (tampering and newer unsupported schema detection)
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

from tarjoman.core.errors import MigrationError

MIGRATION_FILE_RE = re.compile(r"^(\d+)_(.+)\.sql$")


class DatabaseManager:
    """Encapsulates SQLite connections, pragmas, transactions, and migrations."""

    def __init__(
        self,
        db_path: Union[str, Path] = ":memory:",
        busy_timeout_ms: int = 5000,
        migrations_dir: Optional[Union[str, Path]] = None,
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

        if self.is_memory:
            self._memory_conn = self._create_connection()
        else:
            if isinstance(self.db_path, Path):
                self.db_path.parent.mkdir(parents=True, exist_ok=True)

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

    def apply_migrations(self, target_version: Optional[int] = None) -> List[int]:
        """Apply pending migrations in sequential order.

        Verifies:
        1. All already applied migrations match their recorded SHA-256 checksums.
        2. Database schema version is not newer than known code migrations.
        3. Pending migrations execute atomically under BEGIN IMMEDIATE.
        """
        discovered = self._discover_migrations()
        max_known = max(discovered.keys()) if discovered else 0

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

            # 2. Read applied migrations
            cursor = conn.execute(
                "SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version ASC;"
            )
            applied_rows = cursor.fetchall()
            applied_map = {row["version"]: row for row in applied_rows}

            # 3. Verify integrity of existing applied migrations (§25.5)
            for ver, row in applied_map.items():
                if ver not in discovered:
                    raise MigrationError(
                        f"Database schema version {ver} is newer than maximum supported version {max_known}"
                    )
                expected_sum = discovered[ver]["checksum"]
                if row["checksum"] != expected_sum:
                    raise MigrationError(
                        f"Migration checksum mismatch for version {ver} ({row['name']}): "
                        f"database recorded {row['checksum']}, migration file has {expected_sum}"
                    )

            # 4. Determine pending migrations
            pending_versions = [
                v
                for v in sorted(discovered.keys())
                if v not in applied_map and (target_version is None or v <= target_version)
            ]

            applied_versions: List[int] = []
            for ver in pending_versions:
                m = discovered[ver]
                now_iso = datetime.now(timezone.utc).isoformat()
                sql = m["content"]

                try:
                    # Execute within explicit transaction
                    conn.executescript(f"BEGIN IMMEDIATE;\n{sql};\n")
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name, checksum, applied_at) VALUES (?, ?, ?, ?);",
                        (ver, m["name"], m["checksum"], now_iso),
                    )
                    conn.execute("COMMIT;")
                    applied_versions.append(ver)
                except Exception as exc:
                    try:
                        conn.execute("ROLLBACK;")
                    except Exception:
                        pass
                    raise MigrationError(
                        f"Failed to apply migration {ver} ({m['name']}): {exc}"
                    ) from exc

            return applied_versions

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
        """Close persistent resources (in-memory connection)."""
        if self._memory_conn is not None:
            try:
                self._memory_conn.close()
            except Exception:
                pass
            self._memory_conn = None

    def __enter__(self) -> DatabaseManager:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
