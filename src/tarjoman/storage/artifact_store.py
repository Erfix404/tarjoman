"""
Content-Addressed Artifact Blob Storage Engine.

Architecture Zero §25 (Storage Architecture) & §19 (Decisions D20, D43):
  - Workspace-scoped filesystem storage (<workspace_root>/.tarjoman/artifacts/sha256/<ab>/<sha256>).
  - Atomic two-phase writes using workspace temp directory (<workspace_root>/.tarjoman/tmp/).
  - Incremental SHA-256 calculation and size quota enforcement during streaming.
  - Flush and fsync (where supported) before atomic rename (os.replace).
  - Interrupted write handling: temp files are immediately cleaned up on failure,
    leaving no partial or corrupt artifact in destination storage.
  - Automatic deduplication by SHA-256 within the workspace (§25.3).
  - Fail-closed path traversal prevention: hashes must match ^[a-f0-9]{64}$, and all
    resolved paths must reside strictly within the artifact storage tree.
  - Retention policies, individual blob deletion, and live reference-set garbage collection (D43).
"""
from __future__ import annotations

import hashlib
import io
import json
import mimetypes
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Set, Tuple, Union

from pydantic import BaseModel, Field, field_validator

from tarjoman.core.errors import ArtifactValidationError, PolicyViolationError

_SHA256_HEX_REGEX = re.compile(r"^[a-f0-9]{64}$")
_TRAVERSAL_CHARS_REGEX = re.compile(r"(\.\.|/|\\|\x00)")


class StoredBlob(BaseModel):
    """Immutable representation of a content-addressed stored blob."""

    sha256: str = Field(description="64-character lowercase SHA-256 hexadecimal digest")
    size_bytes: int = Field(ge=0, description="Size of the stored blob in bytes")
    path: Path = Field(description="Canonical path to the stored blob file")
    mime_type: Optional[str] = Field(default=None, description="MIME media type of the stored blob")
    created_at: datetime = Field(description="Timestamp when the blob was first stored")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata dictionary")

    @field_validator("sha256")
    @classmethod
    def _validate_sha256_format(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("sha256 must be a string")
        clean = v.strip().lower()
        if clean.startswith("sha256:"):
            clean = clean[7:]
        if not _SHA256_HEX_REGEX.match(clean):
            raise ValueError(f"Invalid sha256: {v!r}. Must be 64 lowercase hexadecimal characters.")
        return clean

    def read_bytes(self) -> bytes:
        """Read and return all bytes from the blob file."""
        return self.path.read_bytes()

    def open(self, mode: str = "rb") -> BinaryIO:
        """Open the blob file as a stream."""
        return open(self.path, mode)  # type: ignore[return-value]


class ArtifactStore:
    """
    Content-addressed artifact blob storage engine.

    Architecture Zero §25 & Locked Decisions D20, D43.
    """

    CHUNK_SIZE: int = 65536  # 64 KiB streaming chunk size

    def __init__(
        self,
        workspace_root: Union[str, Path],
        max_blob_size_bytes: Optional[int] = None,
    ) -> None:
        """Initialize the artifact store for a workspace.

        Args:
            workspace_root: Root path of the Tarjoman workspace.
            max_blob_size_bytes: Optional hard quota limiting maximum stored blob size.

        Raises:
            ArtifactValidationError: If workspace_root is a regular file or max_blob_size_bytes < 0.
        """
        raw_root = Path(workspace_root)
        if raw_root.is_file():
            raise ArtifactValidationError(
                f"Workspace root must be a directory, but found an existing file: {raw_root}",
                details={"workspace_root": str(raw_root)},
            )

        if max_blob_size_bytes is not None and max_blob_size_bytes < 0:
            raise ArtifactValidationError(
                f"max_blob_size_bytes must be non-negative, got {max_blob_size_bytes}",
                details={"max_blob_size_bytes": max_blob_size_bytes},
            )

        self.workspace_root: Path = raw_root.resolve()
        self.artifacts_dir: Path = (self.workspace_root / ".tarjoman" / "artifacts" / "sha256").resolve()
        self.tmp_dir: Path = (self.workspace_root / ".tarjoman" / "tmp").resolve()
        self.max_blob_size_bytes: Optional[int] = max_blob_size_bytes

        # Ensure directory structure exists (§25.1)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------------
    # Hash & Path Traversal Guards
    # -----------------------------------------------------------------------

    def _validate_sha256(self, sha256: Any) -> str:
        """Validate and normalize a SHA-256 hexadecimal digest.

        Enforces Architecture Zero §25 & D43:
          - Input hashes must strictly match 64 lowercase hexadecimal characters.
          - Path traversal patterns ('..', '/', '\\', null bytes) are rejected immediately
            with PolicyViolationError.
          - Non-conforming or malformed hashes raise ArtifactValidationError.
        """
        if not isinstance(sha256, str):
            raise ArtifactValidationError(
                f"Artifact hash must be a string, got {type(sha256).__name__}",
                details={"sha256": str(sha256)},
            )

        raw = sha256.strip()
        if raw.startswith("sha256:"):
            raw = raw[7:]

        # Check for path traversal attacks or directory separators
        if _TRAVERSAL_CHARS_REGEX.search(sha256):
            raise PolicyViolationError(
                f"Path traversal sequence detected in artifact hash: {sha256!r}",
                details={"sha256": sha256},
            )

        raw_lower = raw.lower()
        if not _SHA256_HEX_REGEX.match(raw_lower):
            raise ArtifactValidationError(
                f"Invalid artifact hash: {sha256!r}. Expected 64-character hexadecimal digest.",
                details={"sha256": sha256},
            )

        return raw_lower

    def _get_blob_path(self, sha256: str, allow_escaping_symlink: bool = False) -> Path:
        """Resolve the canonical filesystem path for an artifact hash.

        Enforces:
          - Sharded storage layout: <artifacts_dir>/<first_2_hex>/<full_sha256>
          - Path traversal guard: canonical path must be strictly relative to artifacts_dir.
          - Symlink escape guard: symlinks pointing outside store are blocked unless
            allow_escaping_symlink is explicitly True (used only during deletion).
        """
        clean_hash = self._validate_sha256(sha256)
        shard = clean_hash[:2]
        dest_path = self.artifacts_dir / shard / clean_hash
        base = self.artifacts_dir.resolve()

        # Symlink traversal check
        if dest_path.is_symlink() and not allow_escaping_symlink:
            target = dest_path.resolve()
            try:
                target.relative_to(base)
            except ValueError:
                raise PolicyViolationError(
                    f"Symlink traversal detected: {sha256!r} points outside artifact store",
                    details={"sha256": sha256, "target": str(target)},
                )

        resolved = dest_path.resolve()
        try:
            resolved.relative_to(base)
        except ValueError:
            if not (allow_escaping_symlink and dest_path.is_symlink()):
                raise PolicyViolationError(
                    f"Path traversal detected: {sha256!r} escapes artifact store",
                    details={"sha256": sha256, "resolved_path": str(resolved)},
                )

        return dest_path

    # -----------------------------------------------------------------------
    # Metadata Sidecar Management
    # -----------------------------------------------------------------------

    def _write_metadata_sidecar(
        self,
        meta_path: Path,
        sha256: str,
        size_bytes: int,
        mime_type: Optional[str],
        metadata: Optional[Dict[str, Any]],
        created_at: Optional[datetime] = None,
    ) -> None:
        """Atomically write metadata sidecar JSON file."""
        if created_at is None:
            created_at = datetime.now(timezone.utc)

        # If meta_path already exists on disk, preserve its original created_at timestamp
        if meta_path.exists():
            try:
                old_data = json.loads(meta_path.read_text(encoding="utf-8"))
                if "created_at" in old_data:
                    created_at = datetime.fromisoformat(old_data["created_at"])
            except Exception:
                pass

        payload = {
            "sha256": sha256,
            "size_bytes": size_bytes,
            "mime_type": mime_type,
            "created_at": created_at.isoformat(),
            "metadata": metadata or {},
        }

        temp_meta = tempfile.NamedTemporaryFile(
            dir=self.tmp_dir,
            mode="w",
            encoding="utf-8",
            delete=False,
            prefix="meta_",
            suffix=".tmp",
        )
        temp_meta_path = Path(temp_meta.name).resolve()
        try:
            json.dump(payload, temp_meta, indent=2, ensure_ascii=False)
            temp_meta.flush()
            try:
                os.fsync(temp_meta.fileno())
            except OSError:
                pass
            temp_meta.close()
            os.replace(temp_meta_path, meta_path)
        except Exception:
            try:
                if not temp_meta.closed:
                    temp_meta.close()
            except Exception:
                pass
            try:
                temp_meta_path.unlink(missing_ok=True)
            except Exception:
                pass

    # -----------------------------------------------------------------------
    # Storage Operations (Atomic Writes & Deduplication)
    # -----------------------------------------------------------------------

    def store_stream(
        self,
        stream: BinaryIO,
        mime_type: Optional[str] = None,
        expected_sha256: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StoredBlob:
        """Store raw bytes from a binary stream into the artifact store.

        Enforces Architecture Zero §25.4 (Atomic writes):
          1. Create unique temporary file inside workspace temp store (<workspace_root>/.tarjoman/tmp/).
          2. Stream, enforce size quota, and compute SHA-256 incrementally.
          3. Flush and fsync (where supported).
          4. Validate expected_sha256 if provided.
          5. Enforce SHA-256 deduplication (§25.3).
          6. Atomically rename (os.replace) into content-addressed location.
          7. On any exception, clean up temporary file immediately; no destination artifact exists.
        """
        expected_clean: Optional[str] = None
        if expected_sha256 is not None:
            expected_clean = self._validate_sha256(expected_sha256)

        temp_file = tempfile.NamedTemporaryFile(
            dir=self.tmp_dir,
            delete=False,
            prefix="blob_",
            suffix=".tmp",
        )
        temp_path = Path(temp_file.name).resolve()

        try:
            hasher = hashlib.sha256()
            bytes_written = 0

            while True:
                chunk = stream.read(self.CHUNK_SIZE)
                if not chunk:
                    break
                if not isinstance(chunk, (bytes, bytearray, memoryview)):
                    raise ArtifactValidationError(
                        f"Stream yielded non-bytes chunk: {type(chunk).__name__}",
                        details={"chunk_type": type(chunk).__name__},
                    )

                bytes_written += len(chunk)
                if self.max_blob_size_bytes is not None and bytes_written > self.max_blob_size_bytes:
                    raise ArtifactValidationError(
                        f"Blob exceeds maximum size quota of {self.max_blob_size_bytes} bytes "
                        f"(received at least {bytes_written} bytes)",
                        details={
                            "max_blob_size_bytes": self.max_blob_size_bytes,
                            "bytes_written": bytes_written,
                        },
                    )

                hasher.update(chunk)
                temp_file.write(chunk)

            temp_file.flush()
            try:
                os.fsync(temp_file.fileno())
            except OSError:
                pass
            temp_file.close()

            computed_sha256 = hasher.hexdigest()

            if expected_clean is not None and computed_sha256 != expected_clean:
                raise ArtifactValidationError(
                    f"SHA-256 digest mismatch: expected {expected_clean}, computed {computed_sha256}",
                    details={
                        "expected_sha256": expected_clean,
                        "computed_sha256": computed_sha256,
                    },
                )

            final_path = self._get_blob_path(computed_sha256)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            meta_path = final_path.with_name(f"{computed_sha256}.meta.json")

            now = datetime.now(timezone.utc)

            # Deduplication handling (§25.3)
            if final_path.exists():
                existing_size = final_path.stat().st_size
                if existing_size == bytes_written:
                    # Deduplication hit: remove temporary file without clobbering existing blob
                    try:
                        temp_path.unlink(missing_ok=True)
                    except OSError:
                        pass

                    if metadata or mime_type or not meta_path.exists():
                        self._write_metadata_sidecar(
                            meta_path,
                            computed_sha256,
                            bytes_written,
                            mime_type,
                            metadata,
                        )
                    res = self.get(computed_sha256)
                    if res is not None:
                        return res
                else:
                    # Size mismatch indicates damaged destination file; overwrite atomically
                    os.replace(temp_path, final_path)
                    self._write_metadata_sidecar(
                        meta_path,
                        computed_sha256,
                        bytes_written,
                        mime_type,
                        metadata,
                        created_at=now,
                    )
                    res = self.get(computed_sha256)
                    if res is not None:
                        return res
            else:
                # Standard atomic move into destination location
                os.replace(temp_path, final_path)
                self._write_metadata_sidecar(
                    meta_path,
                    computed_sha256,
                    bytes_written,
                    mime_type,
                    metadata,
                    created_at=now,
                )
                res = self.get(computed_sha256)
                if res is not None:
                    return res

            return StoredBlob(
                sha256=computed_sha256,
                size_bytes=bytes_written,
                path=final_path,
                mime_type=mime_type,
                created_at=now,
                metadata=metadata or {},
            )

        except Exception:
            # Interrupted write cleanup (§25.4):
            # Close file handle and unlink temporary file immediately.
            # Destination path was not moved into, ensuring zero corrupt destination files.
            try:
                if not temp_file.closed:
                    temp_file.close()
            except Exception:
                pass
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise

    def store_bytes(
        self,
        data: bytes,
        mime_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StoredBlob:
        """Store in-memory raw bytes into the artifact store.

        Args:
            data: Binary payload.
            mime_type: Optional MIME media type.
            metadata: Optional arbitrary metadata dictionary.

        Returns:
            StoredBlob record.
        """
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise ArtifactValidationError(
                f"Expected bytes-like object, got {type(data).__name__}",
                details={"type": type(data).__name__},
            )
        stream = io.BytesIO(data)
        return self.store_stream(stream, mime_type=mime_type, metadata=metadata)

    def store_file(
        self,
        source_path: Union[str, Path],
        mime_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StoredBlob:
        """Copy external source file into the managed artifact store (§25.2).

        Args:
            source_path: Path to external file.
            mime_type: Optional MIME type (inferred if None).
            metadata: Optional metadata dictionary.

        Returns:
            StoredBlob record.
        """
        path = Path(source_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Source file does not exist: {source_path}")
        if not path.is_file():
            raise ArtifactValidationError(
                f"Source path is not a regular file: {source_path}",
                details={"source_path": str(source_path)},
            )

        if mime_type is None:
            guessed, _ = mimetypes.guess_type(str(path))
            mime_type = guessed

        meta = dict(metadata or {})
        if "original_filename" not in meta:
            meta["original_filename"] = path.name

        with open(path, "rb") as stream:
            return self.store_stream(stream, mime_type=mime_type, metadata=meta)

    # -----------------------------------------------------------------------
    # Retrieval & Inspection
    # -----------------------------------------------------------------------

    def get(self, sha256: str) -> Optional[StoredBlob]:
        """Retrieve metadata for a stored blob by SHA-256.

        Args:
            sha256: 64-character SHA-256 digest.

        Returns:
            StoredBlob if found on disk, None otherwise.

        Raises:
            ArtifactValidationError: If hash format is invalid.
            PolicyViolationError: If path traversal is attempted.
        """
        clean_hash = self._validate_sha256(sha256)
        blob_path = self._get_blob_path(clean_hash)

        if not blob_path.is_file():
            return None

        meta_path = blob_path.with_name(f"{clean_hash}.meta.json")
        mime_type: Optional[str] = None
        created_at: datetime = datetime.fromtimestamp(blob_path.stat().st_mtime, tz=timezone.utc)
        metadata: Dict[str, Any] = {}

        if meta_path.is_file():
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                mime_type = data.get("mime_type")
                if "created_at" in data:
                    created_at = datetime.fromisoformat(data["created_at"])
                metadata = data.get("metadata", {})
            except Exception:
                pass

        return StoredBlob(
            sha256=clean_hash,
            size_bytes=blob_path.stat().st_size,
            path=blob_path,
            mime_type=mime_type,
            created_at=created_at,
            metadata=metadata,
        )

    def read_bytes(self, sha256: str) -> bytes:
        """Read and return full byte content of a stored blob.

        Args:
            sha256: 64-character SHA-256 digest.

        Returns:
            Raw bytes of the artifact.

        Raises:
            FileNotFoundError: If the blob does not exist in storage.
            ArtifactValidationError: If hash format is invalid.
            PolicyViolationError: If path traversal is attempted.
        """
        clean_hash = self._validate_sha256(sha256)
        blob_path = self._get_blob_path(clean_hash)
        if not blob_path.is_file():
            raise FileNotFoundError(f"Artifact blob not found for hash: {clean_hash}")
        return blob_path.read_bytes()

    def open_blob(self, sha256: str) -> BinaryIO:
        """Open a stored blob as a binary read stream.

        Args:
            sha256: 64-character SHA-256 digest.

        Returns:
            Open BinaryIO stream in 'rb' mode.

        Raises:
            FileNotFoundError: If the blob does not exist in storage.
            ArtifactValidationError: If hash format is invalid.
            PolicyViolationError: If path traversal is attempted.
        """
        clean_hash = self._validate_sha256(sha256)
        blob_path = self._get_blob_path(clean_hash)
        if not blob_path.is_file():
            raise FileNotFoundError(f"Artifact blob not found for hash: {clean_hash}")
        return open(blob_path, "rb")  # type: ignore[return-value]

    def exists(self, sha256: str) -> bool:
        """Check whether a blob with the given SHA-256 exists in storage.

        Args:
            sha256: 64-character SHA-256 digest.

        Returns:
            True if present as a regular file, False otherwise.

        Raises:
            ArtifactValidationError: If hash format is invalid.
            PolicyViolationError: If path traversal is attempted.
        """
        clean_hash = self._validate_sha256(sha256)
        blob_path = self._get_blob_path(clean_hash)
        return blob_path.is_file()

    def verify_blob(self, sha256: str) -> bool:
        """Verify on-disk byte integrity and size of a stored blob against its hash.

        Args:
            sha256: 64-character SHA-256 digest.

        Returns:
            True if file exists, matches metadata size, and recomputed SHA-256 matches.
            False if file missing, size mismatched, or content tampered/corrupted.

        Raises:
            ArtifactValidationError: If hash format is invalid.
            PolicyViolationError: If path traversal is attempted.
        """
        clean_hash = self._validate_sha256(sha256)
        blob_path = self._get_blob_path(clean_hash)
        if not blob_path.is_file():
            return False

        meta_path = blob_path.with_name(f"{clean_hash}.meta.json")
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                expected_size = meta.get("size_bytes")
                if expected_size is not None and blob_path.stat().st_size != expected_size:
                    return False
            except Exception:
                pass

        hasher = hashlib.sha256()
        try:
            with open(blob_path, "rb") as f:
                while True:
                    chunk = f.read(self.CHUNK_SIZE)
                    if not chunk:
                        break
                    hasher.update(chunk)
        except OSError:
            return False

        return hasher.hexdigest() == clean_hash

    # -----------------------------------------------------------------------
    # Deletion, Retention, and Garbage Collection
    # -----------------------------------------------------------------------

    def delete_blob(self, sha256: str) -> bool:
        """Delete an individual blob and its metadata sidecar from storage.

        Args:
            sha256: 64-character SHA-256 digest.

        Returns:
            True if the blob was deleted, False if it did not exist.

        Raises:
            ArtifactValidationError: If hash format is invalid.
            PolicyViolationError: If path traversal is attempted.
        """
        clean_hash = self._validate_sha256(sha256)
        blob_path = self._get_blob_path(clean_hash, allow_escaping_symlink=True)

        if not blob_path.exists() and not blob_path.is_symlink():
            return False

        deleted = False
        try:
            blob_path.unlink(missing_ok=True)
            deleted = True
        except OSError:
            pass

        meta_path = blob_path.with_name(f"{clean_hash}.meta.json")
        try:
            meta_path.unlink(missing_ok=True)
        except OSError:
            pass

        # Remove parent shard directory if now empty
        try:
            shard_dir = blob_path.parent
            if shard_dir != self.artifacts_dir and not any(shard_dir.iterdir()):
                shard_dir.rmdir()
        except OSError:
            pass

        return deleted

    def collect_garbage(
        self,
        referenced_hashes: Set[str],
        min_age_seconds: Optional[Union[int, float]] = None,
    ) -> Tuple[int, int]:
        """Scan storage and remove any unreferenced blobs per D43.

        Args:
            referenced_hashes: Set of active SHA-256 digests referenced by workspace DB records.
            min_age_seconds: Optional retention safety grace period. Blobs modified more
                             recently than min_age_seconds are preserved to protect in-flight writes.

        Returns:
            Tuple of (blobs_removed, bytes_freed).
        """
        clean_refs: Set[str] = set()
        for h in referenced_hashes:
            try:
                clean_refs.add(self._validate_sha256(h))
            except (ArtifactValidationError, PolicyViolationError):
                pass

        now = datetime.now(timezone.utc).timestamp()
        blobs_removed = 0
        bytes_freed = 0

        if not self.artifacts_dir.exists():
            return (0, 0)

        for shard_dir in list(self.artifacts_dir.iterdir()):
            if not shard_dir.is_dir():
                continue

            for item in list(shard_dir.iterdir()):
                # Only process 64-hex blob files, skipping sidecars
                if not _SHA256_HEX_REGEX.match(item.name):
                    continue

                blob_hash = item.name
                if blob_hash in clean_refs:
                    continue

                # Enforce min_age_seconds retention safety grace period
                if min_age_seconds is not None:
                    try:
                        file_mtime = item.stat().st_mtime
                        if (now - file_mtime) < min_age_seconds:
                            continue
                    except OSError:
                        pass

                try:
                    size = os.lstat(item).st_size
                    item.unlink(missing_ok=True)
                    blobs_removed += 1
                    bytes_freed += size
                except OSError:
                    continue

                # Remove metadata sidecar
                meta_path = item.with_name(f"{blob_hash}.meta.json")
                try:
                    meta_path.unlink(missing_ok=True)
                except OSError:
                    pass

            # Clean empty shard directory
            try:
                if not any(shard_dir.iterdir()):
                    shard_dir.rmdir()
            except OSError:
                pass

        return (blobs_removed, bytes_freed)

    def list_blobs(self) -> List[StoredBlob]:
        """List all stored blobs in the workspace, sorted by hash.

        Returns:
            List of StoredBlob objects.
        """
        blobs: List[StoredBlob] = []
        if not self.artifacts_dir.exists():
            return blobs

        for shard_dir in sorted(self.artifacts_dir.iterdir()):
            if not shard_dir.is_dir():
                continue
            for item in sorted(shard_dir.iterdir()):
                if _SHA256_HEX_REGEX.match(item.name):
                    try:
                        blob = self.get(item.name)
                        if blob is not None:
                            blobs.append(blob)
                    except PolicyViolationError:
                        continue

        return blobs

    # -----------------------------------------------------------------------
    # Retention & Expiration Helpers
    # -----------------------------------------------------------------------

    def is_expired(
        self,
        sha256: str,
        max_age_seconds: Union[int, float],
        reference_time: Optional[datetime] = None,
    ) -> bool:
        """Check if a stored blob exceeds a retention age threshold.

        Args:
            sha256: 64-character SHA-256 digest.
            max_age_seconds: Maximum age in seconds before blob is considered expired.
            reference_time: Optional reference datetime (defaults to now UTC).

        Returns:
            True if blob age > max_age_seconds, False otherwise.

        Raises:
            FileNotFoundError: If blob does not exist in storage.
        """
        blob = self.get(sha256)
        if blob is None:
            raise FileNotFoundError(f"Artifact blob not found: {sha256}")
        ref = reference_time or datetime.now(timezone.utc)
        age = (ref - blob.created_at).total_seconds()
        return age > max_age_seconds

    def collect_expired(
        self,
        max_age_seconds: Union[int, float],
        referenced_hashes: Optional[Set[str]] = None,
        reference_time: Optional[datetime] = None,
    ) -> Tuple[int, int]:
        """Purge all blobs exceeding retention age threshold.

        Args:
            max_age_seconds: Expiration threshold in seconds.
            referenced_hashes: Optional set of live referenced hashes to protect.
            reference_time: Optional reference datetime (defaults to now UTC).

        Returns:
            Tuple of (blobs_removed, bytes_freed).
        """
        clean_refs: Set[str] = set()
        if referenced_hashes is not None:
            for h in referenced_hashes:
                try:
                    clean_refs.add(self._validate_sha256(h))
                except (ArtifactValidationError, PolicyViolationError):
                    pass

        blobs_removed = 0
        bytes_freed = 0
        ref = reference_time or datetime.now(timezone.utc)

        for blob in self.list_blobs():
            if referenced_hashes is not None and blob.sha256 in clean_refs:
                continue
            age = (ref - blob.created_at).total_seconds()
            if age > max_age_seconds:
                size = blob.size_bytes
                if self.delete_blob(blob.sha256):
                    blobs_removed += 1
                    bytes_freed += size

        return (blobs_removed, bytes_freed)

    # -----------------------------------------------------------------------
    # Workspace & Cleanliness Metrics
    # -----------------------------------------------------------------------

    def total_size_bytes(self) -> int:
        """Return total bytes occupied by all blobs in the store."""
        return sum(b.size_bytes for b in self.list_blobs())

    def count(self) -> int:
        """Return total number of blobs stored."""
        return len(self.list_blobs())

    def clean_temp_files(self, max_age_seconds: float = 3600.0) -> int:
        """Clean up orphaned temporary files older than max_age_seconds."""
        removed = 0
        if not self.tmp_dir.exists():
            return 0
        now = datetime.now(timezone.utc).timestamp()
        for item in self.tmp_dir.iterdir():
            if item.is_file():
                try:
                    if (now - item.stat().st_mtime) > max_age_seconds:
                        item.unlink(missing_ok=True)
                        removed += 1
                except OSError:
                    pass
        return removed
