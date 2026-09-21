# Work Package FND-005: Artifact Store — Completion Report

## 1. Executive Summary
- **Package ID:** FND-005
- **Title:** Artifact store
- **Phase:** 1 (Foundation)
- **Status:** COMPLETED
- **Branch:** `feat/fnd-005-artifact-store`
- **Dependencies Verified:** FND-002 (DONE), FND-004 (DONE)
- **Next Ready Package:** FND-006 (SQLite schema 001, promoted from PLANNED to READY)
- **Architecture References:** `ARCHITECTURE_ZERO.md` §25.1 (Workspace layout), §25.2 (Managed source rule), §25.3 (Artifact blob lifecycle), §25.4 (Atomic writes), §4.4 (Artifact IR model), §19 (Locked decisions D19, D20, D43), §22.2 (Package ownership for `storage`).

---

## 2. Architecture & Design Principles (Codebase Design Skill)

Applying the **codebase-design** skill principles, the artifact storage engine was engineered as a **deep module**:
- **Small Ergonomic Interface:** Callers interact with a clean, cohesive public interface (`store_bytes`, `store_file`, `store_stream`, `get`, `read_bytes`, `open_blob`, `exists`, `verify_blob`, `delete_blob`, `collect_garbage`, `list_blobs`, `is_expired`, `collect_expired`). Complex internal machinery—two-phase atomic file writes, incremental hashing, quota enforcement, `fsync` flushing, SHA-256 sharded directories, atomic sidecar metadata serialization, symlink resolution, and fail-closed traversal detection—is completely hidden behind the interface.
- **Fail-Closed Path Traversal Guard:** Input hashes are strictly validated against `^[a-f0-9]{64}$`. Directory traversal sequences (`..`, `/`, `\`, null bytes) and escaping absolute paths are rejected immediately with `PolicyViolationError`. Canonical paths are verified using `.resolve()` and `.relative_to(self.artifacts_dir.resolve())`. Symlinks escaping the artifact directory are detected and blocked from read access.
- **Two-Phase Atomic Writes (§25.4):** Writes stream to a unique temporary file inside `<workspace_root>/.tarjoman/tmp/`, computing SHA-256 incrementally and enforcing maximum size quotas on the fly. After `flush()` and `os.fsync()`, the file is atomically renamed (`os.replace`) to `<workspace_root>/.tarjoman/artifacts/sha256/<first_2_hex>/<full_sha256>`. Any exception mid-write triggers immediate cleanup of the temporary file, guaranteeing that no partial or corrupt artifact ever exists in destination storage.
- **Workspace-Scoped Deduplication (§25.3):** Identical content hashes to the same SHA-256 path. If a blob already exists with identical size, the temporary file is unlinked and the existing `StoredBlob` is returned without data corruption or redundant storage.
- **Layer Law & Seam Discipline (D19, §22.2):** `tarjoman.storage` resides strictly in the Infrastructure/Adapters layer. It imports only `tarjoman.core.errors` (`ArtifactValidationError`, `PolicyViolationError`), standard library modules, and Pydantic. It contains zero references to HTTP frameworks, CLI commands, LLM providers, or UI components. Core modules never import storage.

---

## 3. Deliverables Implemented

### 3.1 `StoredBlob` Contract Model (`src/tarjoman/storage/artifact_store.py`)
- Pydantic v2 `BaseModel` representing an immutable content-addressed stored blob:
  - `sha256: str` (strictly validated to 64 lowercase hexadecimal characters)
  - `size_bytes: int` (non-negative integer byte count)
  - `path: Path` (canonical absolute path to the stored artifact on disk)
  - `mime_type: Optional[str] = None` (MIME media type)
  - `created_at: datetime` (UTC timestamp)
  - `metadata: Dict[str, Any]` (arbitrary provenance/producer metadata dictionary)
- Convenience methods:
  - `read_bytes() -> bytes`: Direct read of blob binary content.
  - `open(mode: str = "rb") -> BinaryIO`: Open blob as stream.

### 3.2 `ArtifactStore` Engine (`src/tarjoman/storage/artifact_store.py`)
- Workspace-scoped filesystem storage engine:
  - `__init__(workspace_root: Union[str, Path], max_blob_size_bytes: Optional[int] = None)`
  - `store_stream(stream: BinaryIO, mime_type: Optional[str] = None, expected_sha256: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> StoredBlob`
  - `store_bytes(data: bytes, mime_type: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> StoredBlob`
  - `store_file(source_path: Union[str, Path], mime_type: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> StoredBlob`
  - `get(sha256: str) -> Optional[StoredBlob]`
  - `read_bytes(sha256: str) -> bytes`
  - `open_blob(sha256: str) -> BinaryIO`
  - `exists(sha256: str) -> bool`
  - `verify_blob(sha256: str) -> bool`
  - `delete_blob(sha256: str) -> bool`
  - `collect_garbage(referenced_hashes: Set[str], min_age_seconds: Optional[Union[int, float]] = None) -> Tuple[int, int]`
  - `list_blobs() -> List[StoredBlob]`
  - `is_expired(sha256: str, max_age_seconds: Union[int, float], reference_time: Optional[datetime] = None) -> bool`
  - `collect_expired(max_age_seconds: Union[int, float], referenced_hashes: Optional[Set[str]] = None, reference_time: Optional[datetime] = None) -> Tuple[int, int]`
  - `total_size_bytes() -> int`
  - `count() -> int`
  - `clean_temp_files(max_age_seconds: float = 3600.0) -> int`

### 3.3 Target Directory Structure (§25.1)
```text
<workspace_root>/
  .tarjoman/
    artifacts/
      sha256/
        <first_2_hex>/
          <full_sha256>
          <full_sha256>.meta.json
    tmp/
      blob_<uuid>.tmp
```

### 3.4 Package Exports (`src/tarjoman/storage/__init__.py`)
- Publicly exports `ArtifactStore` and `StoredBlob`.

---

## 4. Verification & Test Evidence

### 4.1 New Test Suite (`tests/test_artifact_store.py`)
58 comprehensive unit and integration tests covering all requirements and edge cases:

1. **Atomic Writes & Interrupted Write Cleanup (5 tests):**
   - Standard write creates valid sharded path (`.tarjoman/artifacts/sha256/ab/<full_hash>`).
   - Simulated stream crash/disconnection mid-write cleans temp file; destination artifact does not exist.
   - Size quota exceeded mid-stream cleans temp file; destination artifact does not exist.
   - SHA-256 digest mismatch against `expected_sha256` cleans temp file; destination artifact does not exist.
   - Non-bytes stream chunk raises `ArtifactValidationError` and cleans temp file.

2. **Content-Addressed Deduplication (5 tests):**
   - Storing identical bytes produces same SHA-256, single on-disk file, deduplicated storage.
   - Storing identical stream produces deduplication.
   - Physical inspection verifies exactly one blob file on disk across repeated writes.
   - Distinct content creates distinct blobs.
   - 0-byte empty content is stored and deduplicated properly.

3. **Path Traversal & Security Escape Guards (23 tests):**
   - Relative traversal (`../../etc/passwd`, `../../../etc/shadow`, `../secrets.toml`, `../tarjoman.toml`) strictly rejected with `PolicyViolationError`.
   - Windows backslash traversal (`..\\..\\windows\\win.ini`) rejected with `PolicyViolationError`.
   - Subdirectory traversal (`subdir/../../escape`, `ab/../../etc/hosts`) rejected with `PolicyViolationError`.
   - Absolute paths (`/etc/passwd`, `C:\Windows\...`) rejected with `PolicyViolationError`.
   - Null bytes in hashes (`\x00...`) rejected with `PolicyViolationError`.
   - Malformed hash lengths and non-hex characters (too short, too long, uppercase, non-hex) rejected with `ArtifactValidationError`.
   - Non-string hashes rejected with `ArtifactValidationError`.
   - Escaping symlinks planted inside store are detected and blocked from read/open access with `PolicyViolationError`.
   - Deletion of escaping symlinks allows cleaning malicious store entries safely.

4. **Retention, Deletion, and Garbage Collection (8 tests):**
   - `delete_blob()` removes both data file and metadata sidecar, and removes empty shard directory.
   - Deleting non-existent blob returns `False`.
   - `collect_garbage()` with 3 stored blobs and 1 referenced removes 2 unreferenced blobs and reports freed bytes accurately.
   - `collect_garbage()` with all referenced removes 0 blobs.
   - `collect_garbage()` with empty reference set removes all unreferenced blobs.
   - `collect_garbage()` with `min_age_seconds` protects recently created uncommitted blobs.
   - `is_expired()` accurately evaluates blob age against retention thresholds.
   - `collect_expired()` purges expired blobs while honoring live references.

5. **Integrity & Verification (4 tests):**
   - `verify_blob()` returns `True` for intact, untampered blobs.
   - `verify_blob()` returns `False` for corrupted/modified on-disk bytes.
   - `verify_blob()` returns `False` when file size does not match sidecar metadata.
   - `verify_blob()` returns `False` for non-existent blobs.

6. **Retrieval, File & Stream Operations (10 tests):**
   - `store_bytes` and `read_bytes` full round-trip.
   - `open_blob` returns readable `BinaryIO` stream.
   - `store_file` imports external file, creates managed copy (§25.2), guesses MIME type, preserves filename.
   - `store_file` with missing path raises `FileNotFoundError`.
   - `store_file` with directory path raises `ArtifactValidationError`.
   - `read_bytes` / `open_blob` for missing blob raises `FileNotFoundError`.
   - 1.5 MiB multi-chunk streaming test verifies incremental hashing across 20+ chunks.
   - `count()` and `total_size_bytes()` accurately track workspace storage metrics.
   - `clean_temp_files()` unlinks expired temporary files.

7. **Model Contracts & Architecture Invariants (3 tests):**
   - `StoredBlob` convenience methods (`read_bytes()`, `open()`).
   - `StoredBlob` Pydantic v2 field validation.
   - Layer law compliance: `storage` imports no interfaces, providers, CLI, or server code.

### 4.2 Full Test Suite Results
```
collected 324 items
======================= 324 passed, 9 warnings in 2.69s ========================
```
- 266 baseline tests passed with zero regressions.
- 58 new artifact store tests passed.

### 4.3 10-Domain Benchmark Suite
Executed `benchmarks/run_benchmarks.py`:
```
[SUCCESS] All 10 Domain Verification Benchmarks PASSED (10/10) in 0.48s!
```

---

## 5. Acceptance Criteria Checklist

| Acceptance Criterion | Status | Evidence |
|---|:---:|---|
| **Interrupted write leaves no completed artifact** | PASSED | `TestAtomicWritesAndInterruptedWrites` (5 tests) verifies temporary files are cleaned up on exception, size quota violation, or hash mismatch, leaving zero destination artifacts. |
| **Dedup by SHA** | PASSED | `TestDeduplication` (5 tests) verifies SHA-256 sharded deduplication, single on-disk file preservation, and identical `StoredBlob` resolution. |
| **Filename cannot escape store** | PASSED | `TestPathTraversalAndSecurity` (23 tests) asserts strict rejection with `PolicyViolationError` on `..`, `/`, `\`, null bytes, absolute paths, and escaping symlinks, and `ArtifactValidationError` on non-conforming hashes. |
| **Retention/delete tests** | PASSED | `TestRetentionAndDeletion` (8 tests) verifies explicit single-blob deletion, live-reference garbage collection (`collect_garbage`), retention safety grace periods, and expiration purging. |
| **All 266 existing tests pass** | PASSED | All 324 tests (266 baseline + 58 new) pass cleanly. |
| **All 10 domain benchmarks pass** | PASSED | 10/10 domain verification benchmarks passed with 100% audit scores. |

---

## 6. Files Changed & Impact Analysis
- `src/tarjoman/storage/__init__.py` (New: 14 lines — exports `ArtifactStore`, `StoredBlob`)
- `src/tarjoman/storage/artifact_store.py` (New: 488 lines — content-addressed artifact engine, atomic writes, GC, traversal guards)
- `tests/test_artifact_store.py` (New: 442 lines — 58 comprehensive test cases)
- `WORKPACKAGES.json` (Modified: marked FND-005 DONE, promoted FND-006 to READY)
- `FND_005_REPORT.md` (New: comprehensive completion report)

### Architecture Decisions Impact
- **D19 (Layer Law):** Enforced. `storage` resides in Infrastructure/Adapters; imports `core.errors`, stdlib, and Pydantic. Core does not import storage.
- **D20 (No DB BLOBs):** Enforced. Large binary artifacts are stored as content-addressed files on the filesystem, not SQLite BLOBs.
- **D43 (Artifact Lifecycle & GC):** Enforced. Blobs are workspace-scoped, deduplicated by SHA-256, and managed by reachability garbage collection.

### Migration & Schema Impact
- None. FND-006 will implement SQLite schema 001 for transactional metadata.

### Dependency & License Impact
- Zero external runtime dependencies added. Uses Python standard library (`hashlib`, `io`, `json`, `mimetypes`, `os`, `re`, `tempfile`, `pathlib`) and existing `pydantic`.
