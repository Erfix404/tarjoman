"""
Comprehensive Test Suite for Artifact Store (FND-005).

Architecture Zero §25 (Storage Architecture) & §19 (Decisions D20, D43):
  - Interrupted write tests (leaves no partial/completed artifact).
  - Deduplication by SHA-256 within workspace.
  - Strict path traversal prevention (filename cannot escape store).
  - Retention, explicit deletion, and live-reference garbage collection.
  - Integrity verification and tamper detection.
  - Layer law and architecture invariant compliance.
"""
from __future__ import annotations

import hashlib
import io
import os
import shutil
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Set

import pytest

from tarjoman.core.errors import ArtifactValidationError, PolicyViolationError
from tarjoman.storage.artifact_store import ArtifactStore, StoredBlob


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory for testing."""
    td = tempfile.mkdtemp(prefix="tarjoman_test_ws_")
    ws_path = Path(td).resolve()
    yield ws_path
    if ws_path.exists():
        shutil.rmtree(ws_path, ignore_errors=True)


@pytest.fixture
def store(temp_workspace):
    """Create an ArtifactStore instance in the temporary workspace."""
    return ArtifactStore(temp_workspace)


# ===========================================================================
# 1. Interrupted Write Tests (§25.4)
# ===========================================================================

class TestAtomicWritesAndInterruptedWrites:
    """Verify two-phase atomic writes and crash/interruption cleanup."""

    def test_atomic_write_creates_valid_blob_and_sharded_path(self, store, temp_workspace):
        """Standard store creates correct sharded directory and metadata."""
        data = b"Hello, Tarjoman storage engine!"
        expected_sha = hashlib.sha256(data).hexdigest()
        shard = expected_sha[:2]

        blob = store.store_bytes(data, mime_type="text/plain", metadata={"test_key": "val"})

        assert blob.sha256 == expected_sha
        assert blob.size_bytes == len(data)
        assert blob.mime_type == "text/plain"
        assert blob.metadata == {"test_key": "val"}

        # Verify on-disk file path conforms to §25.1
        expected_file = temp_workspace / ".tarjoman" / "artifacts" / "sha256" / shard / expected_sha
        assert blob.path == expected_file
        assert expected_file.is_file()
        assert expected_file.read_bytes() == data

        # Verify temp directory has no leftover files
        assert list(store.tmp_dir.iterdir()) == []

    def test_interrupted_write_stream_exception_cleans_temp_and_leaves_no_artifact(self, store):
        """When an exception occurs mid-stream, temp file is removed and no destination artifact exists."""
        class CrashMidStream(io.BytesIO):
            def __init__(self, buffer):
                super().__init__(buffer)
                self.calls = 0

            def read(self, size=-1):
                self.calls += 1
                if self.calls > 2:
                    raise IOError("Simulated network disconnection or power loss mid-stream")
                return super().read(size)

        payload = b"X" * (store.CHUNK_SIZE * 5)
        stream = CrashMidStream(payload)

        with pytest.raises(IOError, match="Simulated network disconnection"):
            store.store_stream(stream)

        # Assert zero files remain in temp directory
        temp_files = list(store.tmp_dir.iterdir())
        assert temp_files == [], f"Expected empty temp dir, found {temp_files}"

        # Assert no artifacts exist in destination store
        assert store.count() == 0
        assert store.list_blobs() == []

    def test_interrupted_write_quota_exceeded_cleans_temp_and_leaves_no_artifact(self, temp_workspace):
        """When max_blob_size_bytes quota is exceeded, temp file is deleted and no artifact is saved."""
        capped_store = ArtifactStore(temp_workspace, max_blob_size_bytes=500)
        oversized_data = b"A" * 1024

        with pytest.raises(ArtifactValidationError) as exc_info:
            capped_store.store_bytes(oversized_data)

        assert "exceeds maximum size quota" in str(exc_info.value)
        assert exc_info.value.code == "ARTIFACT_VALIDATION_ERROR"
        assert exc_info.value.details.get("max_blob_size_bytes") == 500

        # Assert temp directory is clean
        assert list(capped_store.tmp_dir.iterdir()) == []
        # Assert no artifact was stored
        assert capped_store.count() == 0

    def test_interrupted_write_sha_mismatch_cleans_temp_and_leaves_no_artifact(self, store):
        """When expected_sha256 does not match computed SHA, write aborts and cleans temp."""
        data = b"Sample data for hash mismatch test"
        wrong_sha = "0" * 64

        with pytest.raises(ArtifactValidationError) as exc_info:
            store.store_stream(io.BytesIO(data), expected_sha256=wrong_sha)

        assert "SHA-256 digest mismatch" in str(exc_info.value)
        assert exc_info.value.details.get("expected_sha256") == wrong_sha

        # Assert temp directory is clean
        assert list(store.tmp_dir.iterdir()) == []
        # Assert no artifact created
        assert store.count() == 0

    def test_non_bytes_stream_chunk_raises_validation_error_and_cleans_temp(self, store):
        """Passing stream yielding non-bytes raises ArtifactValidationError and cleans temp."""
        class BadStream:
            def read(self, size=-1):
                return "this is a string, not bytes"

        with pytest.raises(ArtifactValidationError) as exc_info:
            store.store_stream(BadStream())  # type: ignore[arg-type]

        assert "Stream yielded non-bytes" in str(exc_info.value)
        assert list(store.tmp_dir.iterdir()) == []
        assert store.count() == 0


# ===========================================================================
# 2. Deduplication Tests (§25.3)
# ===========================================================================

class TestDeduplication:
    """Verify SHA-256 content-addressed deduplication within the workspace."""

    def test_deduplication_identical_bytes(self, store):
        """Storing identical bytes twice yields identical StoredBlob without duplicating files."""
        content = b"Content to deduplicate strictly."
        expected_sha = hashlib.sha256(content).hexdigest()

        blob1 = store.store_bytes(content, mime_type="text/plain", metadata={"version": 1})
        blob2 = store.store_bytes(content, mime_type="text/plain", metadata={"version": 2})

        assert blob1.sha256 == expected_sha
        assert blob2.sha256 == expected_sha
        assert blob1.path == blob2.path
        assert blob1.size_bytes == blob2.size_bytes

        # Only one blob should exist in storage
        assert store.count() == 1
        all_blobs = store.list_blobs()
        assert len(all_blobs) == 1
        assert all_blobs[0].sha256 == expected_sha

    def test_deduplication_identical_stream(self, store):
        """Storing from streams produces deduplication."""
        content = b"Streamed content deduplication."
        b1 = store.store_stream(io.BytesIO(content))
        b2 = store.store_stream(io.BytesIO(content))

        assert b1.sha256 == b2.sha256
        assert store.count() == 1

    def test_deduplication_preserves_single_file_on_disk(self, store, temp_workspace):
        """Verify on-disk file system has exactly one physical blob file."""
        content = b"Physical file deduplication check."
        h = hashlib.sha256(content).hexdigest()
        shard = h[:2]

        store.store_bytes(content)
        store.store_bytes(content)
        store.store_bytes(content)

        shard_dir = temp_workspace / ".tarjoman" / "artifacts" / "sha256" / shard
        blob_files = [f for f in shard_dir.iterdir() if not f.name.endswith(".meta.json")]
        assert len(blob_files) == 1
        assert blob_files[0].name == h

    def test_distinct_content_stores_distinct_blobs(self, store):
        """Different content creates distinct blobs."""
        b1 = store.store_bytes(b"File Alpha")
        b2 = store.store_bytes(b"File Beta")

        assert b1.sha256 != b2.sha256
        assert store.count() == 2
        assert store.exists(b1.sha256)
        assert store.exists(b2.sha256)

    def test_empty_bytes_blob_stored_and_deduplicated(self, store):
        """0-byte empty content is stored and deduplicated properly."""
        empty_sha = hashlib.sha256(b"").hexdigest()
        b1 = store.store_bytes(b"")
        b2 = store.store_bytes(b"")

        assert b1.sha256 == empty_sha
        assert b1.size_bytes == 0
        assert b2.sha256 == empty_sha
        assert store.count() == 1
        assert store.read_bytes(empty_sha) == b""


# ===========================================================================
# 3. Path Traversal & Security Escape Tests (Fail-Closed)
# ===========================================================================

class TestPathTraversalAndSecurity:
    """Verify fail-closed rejection of path traversal and malformed hashes."""

    @pytest.mark.parametrize(
        "traversal_hash",
        [
            "../../etc/passwd",
            "../../../etc/shadow",
            "../secrets.toml",
            "../../../../var/log/syslog",
            "../tarjoman.toml",
            "..\\..\\windows\\win.ini",
            "subdir/../../escape",
            "ab/../../etc/hosts",
            "/etc/passwd",
            "C:\\Windows\\System32\\config\\SAM",
            "\x00" + ("a" * 63),
            ("a" * 63) + "\x00",
        ],
    )
    def test_traversal_attempts_rejected_with_policy_violation(self, store, traversal_hash):
        """Path traversal patterns are immediately rejected with PolicyViolationError."""
        with pytest.raises(PolicyViolationError) as exc_info:
            store.get(traversal_hash)
        assert exc_info.value.code == "POLICY_VIOLATION_ERROR"

        with pytest.raises(PolicyViolationError):
            store.read_bytes(traversal_hash)

        with pytest.raises(PolicyViolationError):
            store.open_blob(traversal_hash)

        with pytest.raises(PolicyViolationError):
            store.exists(traversal_hash)

        with pytest.raises(PolicyViolationError):
            store.verify_blob(traversal_hash)

        with pytest.raises(PolicyViolationError):
            store.delete_blob(traversal_hash)

        with pytest.raises(PolicyViolationError):
            store.is_expired(traversal_hash, 3600)

    @pytest.mark.parametrize(
        "malformed_hash",
        [
            "",
            "   ",
            "not_a_hash",
            "12345",
            "a" * 63,          # 63 chars (too short)
            "a" * 65,          # 65 chars (too long)
            "g" * 64,          # Non-hex characters
            "z" * 64,
            "A" * 60 + "ZZZZ",
        ],
    )
    def test_malformed_hash_syntax_rejected_with_validation_error(self, store, malformed_hash):
        """Hashes not matching ^[a-f0-9]{64}$ raise ArtifactValidationError."""
        with pytest.raises(ArtifactValidationError) as exc_info:
            store.get(malformed_hash)
        assert exc_info.value.code == "ARTIFACT_VALIDATION_ERROR"

        with pytest.raises(ArtifactValidationError):
            store.read_bytes(malformed_hash)

        with pytest.raises(ArtifactValidationError):
            store.exists(malformed_hash)

        with pytest.raises(ArtifactValidationError):
            store.verify_blob(malformed_hash)

    def test_non_string_hash_rejected_with_validation_error(self, store):
        """Non-string hash arguments raise ArtifactValidationError."""
        for invalid_arg in [None, 12345, ["hash"], {"hash": "val"}]:
            with pytest.raises(ArtifactValidationError):
                store.get(invalid_arg)  # type: ignore[arg-type]

    def test_symlink_pointing_outside_store_is_blocked_on_read(self, store):
        """Symlinks inside the store pointing outside raise PolicyViolationError on access."""
        outside_target = store.workspace_root / "outside_secret.txt"
        outside_target.write_text("classified data")

        fake_hash = "f" * 64
        shard = fake_hash[:2]
        shard_dir = store.artifacts_dir / shard
        shard_dir.mkdir(parents=True, exist_ok=True)
        symlink_file = shard_dir / fake_hash

        os.symlink(outside_target, symlink_file)

        # Accessing the escaping symlink must fail closed
        with pytest.raises(PolicyViolationError) as exc_info:
            store.get(fake_hash)
        assert "Symlink traversal detected" in str(exc_info.value)

        with pytest.raises(PolicyViolationError):
            store.read_bytes(fake_hash)

        with pytest.raises(PolicyViolationError):
            store.open_blob(fake_hash)

        # Deleting the symlink to clean the store is allowed and unlinks the symlink
        assert store.delete_blob(fake_hash) is True
        assert not symlink_file.exists()
        # Ensure outside secret was NOT deleted
        assert outside_target.exists()


# ===========================================================================
# 4. Retention & Deletion Tests
# ===========================================================================

class TestRetentionAndDeletion:
    """Verify explicit deletion, retention expiration, and garbage collection."""

    def test_delete_existing_blob_removes_file_and_meta(self, store, temp_workspace):
        """Deleting an existing blob removes both data file and sidecar, and cleans shard dir."""
        data = b"Content to be deleted"
        blob = store.store_bytes(data, mime_type="text/plain", metadata={"tag": "temporary"})
        sha = blob.sha256
        shard = sha[:2]
        shard_dir = temp_workspace / ".tarjoman" / "artifacts" / "sha256" / shard

        assert store.exists(sha) is True
        assert blob.path.exists() is True

        deleted = store.delete_blob(sha)
        assert deleted is True

        assert store.exists(sha) is False
        assert not blob.path.exists()
        assert not blob.path.with_name(f"{sha}.meta.json").exists()
        # Shard directory should be cleaned up if empty
        assert not shard_dir.exists()

    def test_delete_nonexistent_blob_returns_false(self, store):
        """Deleting a hash that does not exist returns False."""
        fake_sha = "e" * 64
        assert store.delete_blob(fake_sha) is False

    def test_garbage_collection_removes_unreferenced_blobs(self, store):
        """Store 3 blobs, mark 1 as referenced; GC removes 2 unreferenced and returns accurate freed bytes."""
        data1 = b"Blob 1: Persistent and referenced."
        data2 = b"Blob 2: Temporary, will be unreferenced."
        data3 = b"Blob 3: Also temporary, will be unreferenced."

        b1 = store.store_bytes(data1)
        b2 = store.store_bytes(data2)
        b3 = store.store_bytes(data3)

        assert store.count() == 3
        expected_freed_bytes = len(data2) + len(data3)

        # Reference only Blob 1
        referenced: Set[str] = {b1.sha256}
        removed_count, freed_bytes = store.collect_garbage(referenced)

        assert removed_count == 2
        assert freed_bytes == expected_freed_bytes

        # Check remaining state
        assert store.exists(b1.sha256) is True
        assert store.exists(b2.sha256) is False
        assert store.exists(b3.sha256) is False
        assert store.count() == 1

    def test_garbage_collection_with_all_referenced(self, store):
        """When all blobs are referenced, GC deletes nothing."""
        b1 = store.store_bytes(b"Data 1")
        b2 = store.store_bytes(b"Data 2")

        removed, freed = store.collect_garbage({b1.sha256, b2.sha256})
        assert removed == 0
        assert freed == 0
        assert store.count() == 2

    def test_garbage_collection_with_empty_references(self, store):
        """When referenced set is empty, GC removes all blobs."""
        store.store_bytes(b"Orphan 1")
        store.store_bytes(b"Orphan 2")

        removed, freed = store.collect_garbage(set())
        assert removed == 2
        assert store.count() == 0

    def test_garbage_collection_min_age_safety_grace_period(self, store):
        """min_age_seconds preserves recently modified blobs even if unreferenced."""
        b = store.store_bytes(b"Fresh uncommitted blob")
        # GC with 10-second grace period: fresh blob must be preserved
        removed, freed = store.collect_garbage(set(), min_age_seconds=10.0)
        assert removed == 0
        assert store.exists(b.sha256) is True

    def test_retention_is_expired(self, store):
        """is_expired correctly detects age against threshold."""
        b = store.store_bytes(b"Aging data")

        # In the future by 100 seconds
        future_ref = datetime.now(timezone.utc) + timedelta(seconds=100)
        assert store.is_expired(b.sha256, max_age_seconds=50, reference_time=future_ref) is True
        assert store.is_expired(b.sha256, max_age_seconds=200, reference_time=future_ref) is False

    def test_collect_expired_blobs(self, store):
        """collect_expired removes only blobs exceeding age threshold."""
        b1 = store.store_bytes(b"Old item")
        future_ref = datetime.now(timezone.utc) + timedelta(seconds=200)

        removed, freed = store.collect_expired(max_age_seconds=60, reference_time=future_ref)
        assert removed == 1
        assert freed == len(b"Old item")
        assert store.exists(b1.sha256) is False


# ===========================================================================
# 5. Integrity & Verification Tests
# ===========================================================================

class TestIntegrityAndVerification:
    """Verify on-disk byte integrity, tamper detection, and verify_blob."""

    def test_verify_blob_valid_blob_returns_true(self, store):
        """verify_blob returns True for an intact blob."""
        content = b"Intact verified content"
        blob = store.store_bytes(content)

        assert store.verify_blob(blob.sha256) is True

    def test_verify_blob_tampered_content_returns_false(self, store):
        """verify_blob returns False if on-disk bytes were modified or corrupted."""
        content = b"Original uncorrupted bytes"
        blob = store.store_bytes(content)

        # Simulate on-disk bit-rot or tampering
        blob.path.write_bytes(b"Tampered modified bytes!")

        assert store.verify_blob(blob.sha256) is False

    def test_verify_blob_mismatched_size_returns_false(self, store):
        """verify_blob returns False if file size does not match sidecar metadata."""
        content = b"Exact size check data"
        blob = store.store_bytes(content)

        # Truncate on disk
        blob.path.write_bytes(b"Truncated")

        assert store.verify_blob(blob.sha256) is False

    def test_verify_blob_missing_blob_returns_false(self, store):
        """verify_blob returns False if the blob does not exist."""
        fake_sha = "d" * 64
        assert store.verify_blob(fake_sha) is False


# ===========================================================================
# 6. Stream, File & Model Operations
# ===========================================================================

class TestRetrievalAndFileOperations:
    """Verify read_bytes, open_blob, store_file, and metadata sidecars."""

    def test_store_and_read_bytes(self, store):
        """store_bytes and read_bytes round-trip."""
        data = b"Direct byte round-trip test"
        blob = store.store_bytes(data)
        assert store.read_bytes(blob.sha256) == data

    def test_store_and_open_blob(self, store):
        """open_blob returns readable binary stream."""
        data = b"Binary stream reading test"
        blob = store.store_bytes(data)
        with store.open_blob(blob.sha256) as stream:
            assert stream.read() == data

    def test_store_file_with_metadata_and_mime_guessing(self, store, temp_workspace):
        """store_file correctly imports external file and guesses MIME type."""
        ext_file = temp_workspace / "sample_doc.json"
        ext_file.write_text('{"name": "test"}', encoding="utf-8")

        blob = store.store_file(ext_file, metadata={"source": "cli_import"})

        assert blob.mime_type == "application/json"
        assert blob.metadata.get("original_filename") == "sample_doc.json"
        assert blob.metadata.get("source") == "cli_import"
        assert store.read_bytes(blob.sha256) == b'{"name": "test"}'

    def test_store_file_missing_source_raises_file_not_found(self, store):
        """store_file with non-existent path raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            store.store_file("/non/existent/path/document.pdf")

    def test_store_file_directory_raises_validation_error(self, store, temp_workspace):
        """store_file with directory path raises ArtifactValidationError."""
        sub_dir = temp_workspace / "subdir"
        sub_dir.mkdir()
        with pytest.raises(ArtifactValidationError):
            store.store_file(sub_dir)

    def test_read_bytes_missing_blob_raises_file_not_found(self, store):
        """read_bytes for absent blob raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            store.read_bytes("c" * 64)

    def test_open_blob_missing_blob_raises_file_not_found(self, store):
        """open_blob for absent blob raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            store.open_blob("c" * 64)

    def test_large_file_streaming(self, store):
        """Large payload spanning multiple chunks is streamed and hashed accurately."""
        # 1.5 MiB payload (> 20 chunks of 64 KiB)
        large_data = b"0123456789ABCDEF" * (1024 * 96)
        expected_sha = hashlib.sha256(large_data).hexdigest()

        blob = store.store_bytes(large_data)
        assert blob.sha256 == expected_sha
        assert blob.size_bytes == len(large_data)
        assert store.verify_blob(blob.sha256) is True

    def test_count_and_total_size_bytes(self, store):
        """count and total_size_bytes accurately reflect stored blobs."""
        assert store.count() == 0
        assert store.total_size_bytes() == 0

        store.store_bytes(b"12345")
        store.store_bytes(b"67890")

        assert store.count() == 2
        assert store.total_size_bytes() == 10

    def test_clean_temp_files(self, store):
        """clean_temp_files unlinks expired temporary files."""
        # Create an orphaned temp file
        temp_file = store.tmp_dir / "orphaned.tmp"
        temp_file.write_text("orphaned data")

        # File is young; should not be cleaned with 3600s threshold
        assert store.clean_temp_files(max_age_seconds=3600) == 0

        # With 0s threshold, file is cleaned
        cleaned = store.clean_temp_files(max_age_seconds=-1.0)
        assert cleaned == 1
        assert not temp_file.exists()


# ===========================================================================
# 7. StoredBlob Model & Architecture Invariants
# ===========================================================================

class TestStoredBlobModelAndArchitecture:
    """Verify StoredBlob model validation and architecture layer contracts."""

    def test_stored_blob_read_bytes_and_open_convenience(self, store):
        """StoredBlob instance provides direct read_bytes and open methods."""
        data = b"Convenience methods test"
        blob = store.store_bytes(data)

        assert blob.read_bytes() == data
        with blob.open() as f:
            assert f.read() == data

    def test_stored_blob_sha256_validation(self, temp_workspace):
        """StoredBlob validates that sha256 is 64 lowercase hex characters."""
        with pytest.raises(ValueError, match="Must be 64 lowercase hexadecimal characters"):
            StoredBlob(
                sha256="invalid",
                size_bytes=10,
                path=temp_workspace / "dummy",
                created_at=datetime.now(timezone.utc),
            )

    def test_layer_law_storage_module_boundaries(self):
        """Storage must not import interfaces or provider implementations (D19, §22.2)."""
        import tarjoman.storage.artifact_store as store_mod
        mod_file = Path(store_mod.__file__).read_text(encoding="utf-8")

        assert "interfaces" not in mod_file
        assert "providers" not in mod_file
        assert "cli" not in mod_file
        assert "fastapi" not in mod_file
        assert "shell=True" not in mod_file
