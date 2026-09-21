# Work Package FND-008: Legacy-State Importer — Completion Report

## 1. Executive Summary
- **Package ID:** FND-008
- **Title:** Legacy-state importer
- **Phase:** 1 (Foundation)
- **Status:** COMPLETED
- **Branch:** `phase/1-foundation`
- **Dependencies Verified:** FND-006 (DONE), FND-007 (DONE)
- **Next Ready Packages:**
  - `FND-009` (Persian quality split, PLANNED)
  - `REL-003` (Migration upgrade fixtures, PLANNED, depends on FND-007 and FND-008)
- **Architecture References:**
  - `ARCHITECTURE_ZERO.md` §4 (Canonical intermediate representation: Workspace, Project, Artifact, Segment, SegmentVersion)
  - `ARCHITECTURE_ZERO.md` §25 (Workspace & storage architecture: Content-addressed artifact store, SQLite database, non-destructive managed source rule)
  - `ARCHITECTURE_ZERO.md` §19 (Locked decisions D04, D19, D20, D22, D36, D38)
  - `ROADMAP.md` (FND-008: "fixture conversions; duplicate/conflict policy deterministic; source files never deleted automatically")
  - `WORKPACKAGES.json` (FND-008: acceptance criteria verified)

---

## 2. Architecture & Design Principles (Codebase Design Skill)

In accordance with the **codebase-design** principles, the legacy-state importer is designed as a **deep module**:
- **Small Ergonomic Surface Area:**
  The caller interacts with a clean, concise interface on `LegacyStateImporter`:
  1. `import_book_project(project_dir, conflict_policy=ConflictPolicy.SKIP, project_id=None) -> ImportSummary`
  2. `import_cache_file(cache_file_path, project_id, artifact_id=None, conflict_policy=ConflictPolicy.SKIP) -> ImportSummary`
  3. `import_termbase(termbase_tsv_path, project_id, conflict_policy=ConflictPolicy.SKIP) -> ImportSummary`
- **Encapsulated Complexity:**
  All details of legacy file discovery, legacy schema normalization (`BookManifest`, TSV headers/columns, `ResumableCache` JSON key schemes), content-addressed hashing and storage via `ArtifactStore`, structural locator derivation, segment version lineage linking, and transaction management are hidden behind the public interface.
- **Mandatory Invariant — Source Files NEVER Deleted Automatically:**
  Under NO circumstances are legacy source files (`manifest.json`, `terms.tsv`, `cache.json`, `tarjoman_cache.json`, `chapter_*.txt`) deleted, unlinked, truncated, moved, or mutated. Source files are strictly read-only. Pre-import and post-import SHA-256 digests are tracked and verified to be 100% byte-identical. All preserved source file paths are recorded in `ImportSummary.source_files_preserved`.
- **Deterministic Conflict Resolution:**
  The policy is governed by `ConflictPolicy`:
  - `ConflictPolicy.SKIP` (Default): Preserves existing records in the database. Logs conflicts in `ImportSummary.conflicts_resolved` with action `"skipped"` and increments `conflicts_encountered`.
  - `ConflictPolicy.OVERWRITE`: Replaces existing records in the database (updating projects/terms, or deleting and recreating artifacts/segments/versions with full cascade integrity). Logs conflicts with action `"overwritten"`.
  - `ConflictPolicy.FAIL`: Fails closed immediately upon detecting an existing entity by raising a typed `ArtifactValidationError` (which inherits from `TarjomanError`), leaving existing records intact.
- **Canonical Model Mapping (§4):**
  - Legacy `BookManifest` -> Canonical `ProjectSpec` in `projects` table.
  - Legacy `terms.tsv` -> Structured glossary and terminology mappings inside `ProjectSpec.metadata`.
  - Legacy chapter `.txt` files -> Managed blobs in `ArtifactStore` and `Artifact` records in `artifacts` table.
  - Legacy `cache.json` / `tarjoman_cache.json` -> `Segment` records with structural locators (`ch_<id>:seg_<num>`), plus immutable `SegmentVersion` records (`kind=DRAFT` for `translated_text`, `kind=REVISED` for `polished_text` with `parent_version_id` pointing to the draft).

---

## 3. Deliverables Implemented

### 3.1 Importer Module (`src/tarjoman/storage/importers/legacy.py`)
1. **`ConflictPolicy` (Enum)**:
   - `SKIP = "SKIP"` (default)
   - `OVERWRITE = "OVERWRITE"`
   - `FAIL = "FAIL"`
   - Supports case-insensitive string coercion (`"skip"`, `"overwrite"`, `"fail"`).
2. **`ImportSummary` (Pydantic Model)**:
   - `projects_imported: int`
   - `artifacts_imported: int`
   - `segments_imported: int`
   - `versions_imported: int`
   - `terms_imported: int`
   - `conflicts_encountered: int`
   - `conflicts_resolved: List[Dict[str, Any]]`
   - `source_files_preserved: List[Path]`
   - Provides a `.merge(other)` helper for aggregating sub-import operations.
3. **`LegacyStateImporter` (Class)**:
   - Accepts dependencies (`db: DatabaseManager`, optional `artifact_store: ArtifactStore`, optional `workspace_root: Path`).
   - Ensures latest SQLite migrations are applied on initialization.
   - Instantiates typed repositories (`ProjectRepository`, `ArtifactRepository`, `SegmentRepository`).
   - Implements `import_book_project`, `import_cache_file`, and `import_termbase`.
   - Invariant assertion: Computes pre-import and post-import SHA-256 for all scanned files, asserting byte-for-byte equality.

### 3.2 Package Re-exports
- `src/tarjoman/storage/importers/__init__.py`: Re-exports `ConflictPolicy`, `ImportSummary`, `LegacyStateImporter`.
- `src/tarjoman/storage/__init__.py`: Re-exports `ConflictPolicy`, `ImportSummary`, `LegacyStateImporter` for convenient top-level access.

### 3.3 Test Suite (`tests/test_legacy_importer.py`)
18 comprehensive tests covering:
- **Fixture Conversions:** Full book project import with manifests, terms, caches, and chapter text files; standalone cache imports; standalone termbase imports; cacheless book projects.
- **Deterministic Conflict Policy:** Verification of `SKIP`, `OVERWRITE`, and `FAIL` across projects, artifacts, segments, versions, and terminology.
- **Source File Preservation:** Byte-identical verification (SHA-256 matching) across multiple import iterations and after error rollbacks.
- **Edge Cases & Error Handling:** Missing directories, missing manifests, corrupted JSON files, Persian Unicode and ZWNJ (نیم‌فاصله) preservation.

### 3.4 Roadmap & Work Package Tracking
- Updated `WORKPACKAGES.json`: Promoted `FND-008` status from `READY` to `DONE`.

---

## 4. Verification & Testing Evidence

### 4.1 Pytest Execution
- **Command:** `.venv/bin/pytest -q`
- **Result:** **388 passed**, 9 warnings, 115 subtests passed in 4.80s.
- **New Tests:** 18 tests in `tests/test_legacy_importer.py` passed with 0 failures.
- **Zero Regressions:** All 370 prior tests pass with zero errors.

### 4.2 Universal 10-Domain Benchmark
- **Command:** `.venv/bin/python benchmarks/run_benchmarks.py`
- **Result:** **10/10 Domains PASSED** (literary, scientific, philosophy, legal, technical, medical, media, financial, classical, transcreation) with 100.0 audit scores in 0.49s.

### 4.3 Acceptance Criteria Checklist
- [x] `fixture conversions`: Legacy book manifests, translation caches, and termbases are accurately converted into canonical SQLite models and content-addressed blobs.
- [x] `duplicate/conflict policy deterministic`: `SKIP`, `OVERWRITE`, and `FAIL` policies tested and verified across all entity types.
- [x] `source files never deleted automatically`: Source files verified byte-identical before and after all import scenarios (including failures).
- [x] All 370 existing tests pass with zero regressions (total 388 tests passing).
- [x] All 10 domain benchmarks pass.

---

## 5. PR Evidence & Architectural Invariants

| Requirement | Evidence / Conformance |
|---|---|
| **Work Package ID** | `FND-008` |
| **Dependencies Verified** | `FND-006` (DONE), `FND-007` (DONE) |
| **Files Changed/Added** | `src/tarjoman/storage/importers/legacy.py`<br>`src/tarjoman/storage/importers/__init__.py`<br>`src/tarjoman/storage/__init__.py`<br>`tests/test_legacy_importer.py`<br>`WORKPACKAGES.json` |
| **Architecture Decisions** | **D04** (Canonical IR separates ingestion from translation logic)<br>**D19** (Layer law: core <- storage <- adapters)<br>**D20** (No DB BLOBs; text files live in `ArtifactStore`)<br>**D22** (SQLite persistence)<br>**D36** (Workspace persistence boundary)<br>**D38** (Canonical status vocabulary) |
| **Mandatory Invariants** | Source files are never deleted or modified; deterministic conflict resolution; fail-closed on FAIL policy. |
| **Schema/Migration Impact** | None; uses existing Schema 001. |
| **Dependency/License Impact** | Zero new external dependencies. |
| **Benchmark Impact** | 10/10 domain benchmarks pass in 0.49s. |
| **Known Limitations** | Standalone import of voice ledgers is deferred to literary profile work packages. |

---

## 6. Conclusion
Work Package FND-008 is fully implemented, verified, and complete in accordance with `ARCHITECTURE_ZERO.md` §4, §25, and `ROADMAP.md`. All acceptance criteria have passed with executable evidence.
