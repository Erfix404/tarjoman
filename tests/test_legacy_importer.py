"""
Comprehensive Test Suite for Legacy-State Importer (FND-008).

Architecture Zero §4 (Canonical IR), §25 (Storage Architecture), and ROADMAP.md:
  - Fixture conversions: legacy book manifests, caches, and termbases converted to canonical SQLite models.
  - Deterministic duplicate/conflict policies: SKIP (default), OVERWRITE, FAIL.
  - Mandatory invariant: Source files are NEVER deleted, moved, truncated, or modified.
  - Preserved source files are byte-identical (SHA-256 verified) before and after import.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Generator

import pytest

from tarjoman.core.contracts import (
    Artifact,
    ArtifactKind,
    AuthorType,
    BookManifest,
    ProjectSpec,
    Segment,
    SegmentVersion,
    SegmentVersionKind,
)
from tarjoman.core.errors import ArtifactValidationError, TarjomanError
from tarjoman.memory.cache import ResumableCache
from tarjoman.storage import (
    ArtifactRepository,
    ArtifactStore,
    ConflictPolicy,
    DatabaseManager,
    ImportSummary,
    LegacyStateImporter,
    ProjectRepository,
    SegmentRepository,
)


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 of file contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def workspace_dir() -> Generator[Path, None, None]:
    """Temporary workspace directory for DatabaseManager and ArtifactStore."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        yield ws


@pytest.fixture
def legacy_importer(workspace_dir: Path) -> Generator[LegacyStateImporter, None, None]:
    """Provide a configured LegacyStateImporter with SQLite DB and ArtifactStore."""
    db_path = workspace_dir / ".tarjoman" / "state.sqlite3"
    db = DatabaseManager(db_path)
    store = ArtifactStore(workspace_dir)
    importer = LegacyStateImporter(db=db, artifact_store=store)
    yield importer
    db.close()


@pytest.fixture
def legacy_project_fixture(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a realistic legacy Tarjoman book project fixture."""
    proj_dir = tmp_path_factory.mktemp("legacy_book_project")

    # 1. manifest.json
    manifest = BookManifest(
        title="تاریخ تمدن ویل دورانت",
        source_language="en",
        target_language="fa",
        total_chapters=2,
        current_chapter=1,
        total_segments=4,
        translated_segments=4,
        terms_count=3,
        metadata={"domain": "classical", "project_id": "durant_civilization"},
    )
    (proj_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    # 2. terms.tsv
    terms_tsv = (
        "english_term\tpersian_translation\tdomain\tnotes\n"
        "civilization\tتمدن\tclassical\tکلیدی\n"
        "renaissance\tرنسانس\tclassical\tعصر نوزایی\n"
        "enlightenment\tعصر روشنگری\tclassical\tقرن هجدهم\n"
    )
    (proj_dir / "terms.tsv").write_text(terms_tsv, encoding="utf-8")

    # 3. Chapter source text files
    (proj_dir / "chapter_01.txt").write_text(
        "Civilization is a stream with banks.\nThe stream is sometimes filled with blood.",
        encoding="utf-8",
    )
    (proj_dir / "chapter_02.txt").write_text(
        "The Renaissance was a fervent period of European cultural rebirth.\nIt paved the way for science.",
        encoding="utf-8",
    )

    # 4. tarjoman_cache.json (ResumableCache format)
    cache_path = proj_dir / "tarjoman_cache.json"
    cache = ResumableCache(cache_path)
    cache.record_segment(
        chapter_id=1,
        segment_id=0,
        source_text="Civilization is a stream with banks.",
        translated_text="تمدن جویباری است با کرانه‌ها.",
        polished_text="تمدن جویباری است با دو کرانه.",
    )
    cache.record_segment(
        chapter_id=1,
        segment_id=1,
        source_text="The stream is sometimes filled with blood.",
        translated_text="این جویبار گاه لبریز از خون است.",
        polished_text=None,  # Only draft
    )
    cache.record_segment(
        chapter_id=2,
        segment_id=0,
        source_text="The Renaissance was a fervent period of European cultural rebirth.",
        translated_text="رنسانس دوره‌ای پرحرارت از نوزایی فرهنگی اروپا بود.",
        polished_text="رنسانس برهه‌ای پرشور از تجدید حیات فرهنگی اروپا بود.",
    )
    cache.record_segment(
        chapter_id=2,
        segment_id=1,
        source_text="It paved the way for science.",
        translated_text="آن راه را برای علم هموار کرد.",
        polished_text="این دوران مسیر را برای پیشرفت دانش گشود.",
    )

    return proj_dir


# ===========================================================================
# 1. Fixture Conversions Tests
# ===========================================================================

class TestFixtureConversions:
    """Test conversions of legacy fixtures into canonical SQLite models."""

    def test_import_full_book_project(
        self, legacy_importer: LegacyStateImporter, legacy_project_fixture: Path
    ) -> None:
        """Verify full book project import creates ProjectSpec, Artifacts, Segments, and Versions."""
        summary = legacy_importer.import_book_project(legacy_project_fixture)

        assert summary.projects_imported == 1
        assert summary.artifacts_imported == 2  # chapter_01 and chapter_02
        assert summary.terms_imported == 3
        assert summary.segments_imported == 4
        # Segments 1:0 (draft+revised=2), 1:1 (draft=1), 2:0 (draft+revised=2), 2:1 (draft+revised=2) = 7
        assert summary.versions_imported == 7
        assert summary.conflicts_encountered == 0

        # Verify ProjectSpec in SQLite
        project_repo = ProjectRepository(legacy_importer.db)
        project = project_repo.get("durant_civilization")
        assert project is not None
        assert project.name == "تاریخ تمدن ویل دورانت"
        assert project.default_source_language == "en"
        assert project.default_target_language == "fa"
        assert project.default_domain_profile_id == "classical"

        # Verify terms in project metadata
        assert "glossary" in project.metadata
        assert len(project.metadata["glossary"]) == 3
        assert "terms" in project.metadata
        assert "civilization" in project.metadata["terms"]
        assert project.metadata["terms"]["civilization"]["persian_translation"] == "تمدن"
        assert project.metadata["terminology_map"]["renaissance"] == "رنسانس"
        assert project.metadata["legacy_manifest"]["terms_count"] == 3

        # Verify Artifacts in SQLite and ArtifactStore
        artifact_repo = ArtifactRepository(legacy_importer.db)
        artifacts = artifact_repo.list_by_project("durant_civilization")
        assert len(artifacts) == 2
        art_names = {a.metadata.get("filename") for a in artifacts}
        assert "chapter_01.txt" in art_names
        assert "chapter_02.txt" in art_names

        # Verify ArtifactStore content-addressed blobs
        assert legacy_importer.artifact_store is not None
        for art in artifacts:
            assert art.raw_sha256 is not None
            assert art.blob_path is not None
            assert legacy_importer.artifact_store.exists(art.raw_sha256)
            blob = legacy_importer.artifact_store.get(art.raw_sha256)
            assert blob is not None
            assert len(blob.read_bytes()) > 0

        # Verify Segments and Versions
        segment_repo = SegmentRepository(legacy_importer.db)
        for art in artifacts:
            segments = segment_repo.list_by_artifact(art.artifact_id)
            assert len(segments) == 2
            for seg in segments:
                assert seg.source_text is not None
                assert seg.source_content_hash == hashlib.sha256(seg.source_text.encode("utf-8")).hexdigest()
                assert seg.translatable is True
                versions = segment_repo.list_versions(seg.segment_id)
                assert len(versions) in (1, 2)
                # Draft version must exist
                drafts = [v for v in versions if v.kind == SegmentVersionKind.DRAFT]
                assert len(drafts) == 1
                assert drafts[0].author == AuthorType.SYSTEM

                # Revised version if polished_text existed
                revised = [v for v in versions if v.kind == SegmentVersionKind.REVISED]
                if "کرانه" in seg.source_text or "Renaissance" in seg.source_text or "science" in seg.source_text:
                    if len(revised) == 1:
                        assert revised[0].parent_version_id == drafts[0].segment_version_id

    def test_import_standalone_cache_file(
        self, legacy_importer: LegacyStateImporter, tmp_path: Path
    ) -> None:
        """Verify standalone import_cache_file creates artifacts, segments, and versions."""
        cache_file = tmp_path / "tarjoman_cache.json"
        cache = ResumableCache(cache_file)
        cache.record_segment(
            chapter_id=1,
            segment_id=0,
            source_text="Standalone test paragraph.",
            translated_text="بند آزمایشی مستقل.",
            polished_text="بند مستقل آزمایش شده.",
        )
        cache.record_segment(
            chapter_id=1,
            segment_id=1,
            source_text="Second test paragraph.",
            translated_text="بند دوم آزمایشی.",
            polished_text=None,
        )

        summary = legacy_importer.import_cache_file(
            cache_file_path=cache_file,
            project_id="standalone_proj",
        )

        assert summary.projects_imported == 1
        assert summary.artifacts_imported == 1
        assert summary.segments_imported == 2
        assert summary.versions_imported == 3  # (draft+revised) + (draft)
        assert summary.conflicts_encountered == 0

        # Verify segment repository
        segment_repo = SegmentRepository(legacy_importer.db)
        art_id = "standalone_proj_chapter_1"
        segments = segment_repo.list_by_artifact(art_id)
        assert len(segments) == 2
        seg0 = segments[0]
        versions = segment_repo.list_versions(seg0.segment_id)
        assert len(versions) == 2
        assert versions[0].kind == SegmentVersionKind.DRAFT
        assert versions[0].text == "بند آزمایشی مستقل."
        assert versions[1].kind == SegmentVersionKind.REVISED
        assert versions[1].text == "بند مستقل آزمایش شده."
        assert versions[1].parent_version_id == versions[0].segment_version_id

    def test_import_standalone_termbase(
        self, legacy_importer: LegacyStateImporter, tmp_path: Path
    ) -> None:
        """Verify standalone import_termbase parses TSV into project metadata."""
        tsv_file = tmp_path / "terms.tsv"
        tsv_file.write_text(
            "english_term\tpersian_translation\tdomain\tnotes\n"
            "quantum computing\tرایانش کوانتومی\tscientific\tفیزیک و محاسبات\n"
            "superposition\tبرهم‌نهی\tscientific\tاصل فیزیکی\n",
            encoding="utf-8",
        )

        summary = legacy_importer.import_termbase(
            termbase_tsv_path=tsv_file,
            project_id="quantum_project",
        )

        assert summary.projects_imported == 1
        assert summary.terms_imported == 2
        assert summary.conflicts_encountered == 0

        project_repo = ProjectRepository(legacy_importer.db)
        proj = project_repo.get("quantum_project")
        assert proj is not None
        assert proj.metadata["terms"]["quantum computing"]["persian_translation"] == "رایانش کوانتومی"
        assert proj.metadata["terminology_map"]["superposition"] == "برهم‌نهی"
        assert len(proj.metadata["glossary"]) == 2

    def test_import_project_without_cache(
        self, legacy_importer: LegacyStateImporter, tmp_path: Path
    ) -> None:
        """Verify project without cache imports manifest, terms, and text files."""
        proj_dir = tmp_path / "no_cache_book"
        proj_dir.mkdir()
        manifest = BookManifest(title="کتاب بدون حافظه", metadata={"project_id": "no_cache"})
        (proj_dir / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
        (proj_dir / "chapter_01.txt").write_text("Hello chapter 1.", encoding="utf-8")

        summary = legacy_importer.import_book_project(proj_dir)
        assert summary.projects_imported == 1
        assert summary.artifacts_imported == 1
        assert summary.segments_imported == 0
        assert summary.versions_imported == 0


# ===========================================================================
# 2. Deterministic Duplicate / Conflict Policy Tests
# ===========================================================================

class TestDeterministicConflictPolicies:
    """Test deterministic SKIP, OVERWRITE, and FAIL conflict policies."""

    def test_conflict_policy_skip_preserves_existing_records(
        self, legacy_importer: LegacyStateImporter, legacy_project_fixture: Path
    ) -> None:
        """Verify SKIP preserves existing DB records and tallies conflicts."""
        # 1. First import
        sum1 = legacy_importer.import_book_project(legacy_project_fixture, conflict_policy=ConflictPolicy.SKIP)
        assert sum1.projects_imported == 1
        assert sum1.conflicts_encountered == 0

        # Manually alter the project title in SQLite
        project_repo = ProjectRepository(legacy_importer.db)
        proj = project_repo.get("durant_civilization")
        assert proj is not None
        proj.name = "عنوان دستکاری شده"
        project_repo.update(proj)

        # 2. Re-import with SKIP
        sum2 = legacy_importer.import_book_project(legacy_project_fixture, conflict_policy=ConflictPolicy.SKIP)

        # No new entities imported; conflicts detected and resolved by skipping
        assert sum2.projects_imported == 0
        assert sum2.artifacts_imported == 0
        assert sum2.segments_imported == 0
        assert sum2.conflicts_encountered > 0

        actions = [c["action"] for c in sum2.conflicts_resolved]
        assert all(a == "skipped" for a in actions)

        # Existing record preserved
        proj_after = project_repo.get("durant_civilization")
        assert proj_after is not None
        assert proj_after.name == "عنوان دستکاری شده"

    def test_conflict_policy_overwrite_replaces_cleanly(
        self, legacy_importer: LegacyStateImporter, legacy_project_fixture: Path
    ) -> None:
        """Verify OVERWRITE cleanly replaces existing DB records."""
        # 1. First import
        legacy_importer.import_book_project(legacy_project_fixture, conflict_policy=ConflictPolicy.SKIP)

        # Manually alter project title and a term in SQLite
        project_repo = ProjectRepository(legacy_importer.db)
        proj = project_repo.get("durant_civilization")
        assert proj is not None
        proj.name = "عنوان موقت"
        proj.metadata["terms"]["civilization"]["persian_translation"] = "ترجمه اشتباه"
        proj.metadata["terminology_map"]["civilization"] = "ترجمه اشتباه"
        project_repo.update(proj)

        # 2. Re-import with OVERWRITE
        sum2 = legacy_importer.import_book_project(legacy_project_fixture, conflict_policy=ConflictPolicy.OVERWRITE)

        assert sum2.conflicts_encountered > 0
        actions = [c["action"] for c in sum2.conflicts_resolved]
        assert all(a == "overwritten" for a in actions)

        # Record overwritten with fixture's canonical data
        proj_after = project_repo.get("durant_civilization")
        assert proj_after is not None
        assert proj_after.name == "تاریخ تمدن ویل دورانت"
        assert proj_after.metadata["terms"]["civilization"]["persian_translation"] == "تمدن"
        assert proj_after.metadata["terminology_map"]["civilization"] == "تمدن"

    def test_conflict_policy_fail_raises_typed_error_on_project_conflict(
        self, legacy_importer: LegacyStateImporter, legacy_project_fixture: Path
    ) -> None:
        """Verify FAIL policy raises ArtifactValidationError (TarjomanError) on duplicate project."""
        legacy_importer.import_book_project(legacy_project_fixture, conflict_policy=ConflictPolicy.SKIP)

        with pytest.raises(ArtifactValidationError) as exc_info:
            legacy_importer.import_book_project(legacy_project_fixture, conflict_policy=ConflictPolicy.FAIL)

        err = exc_info.value
        assert isinstance(err, TarjomanError)
        assert err.code == "ARTIFACT_VALIDATION_ERROR"
        assert "already exists" in str(err)
        assert "durant_civilization" in str(err)

    def test_conflict_policy_fail_raises_on_cache_segment_conflict(
        self, legacy_importer: LegacyStateImporter, tmp_path: Path
    ) -> None:
        """Verify FAIL raises ArtifactValidationError when cache segment collides."""
        cache_file = tmp_path / "cache.json"
        cache = ResumableCache(cache_file)
        cache.record_segment(1, 0, "Hello", "سلام")

        # First import succeeds
        legacy_importer.import_cache_file(cache_file, project_id="test_cache_proj")

        # Second import fails under FAIL
        with pytest.raises(ArtifactValidationError) as exc_info:
            legacy_importer.import_cache_file(
                cache_file,
                project_id="test_cache_proj",
                conflict_policy=ConflictPolicy.FAIL,
            )
        assert "already exists" in str(exc_info.value)

    def test_conflict_policy_fail_raises_on_termbase_conflict(
        self, legacy_importer: LegacyStateImporter, tmp_path: Path
    ) -> None:
        """Verify FAIL raises ArtifactValidationError on duplicate term."""
        tsv_file = tmp_path / "terms.tsv"
        tsv_file.write_text("model\tمدل\n", encoding="utf-8")

        legacy_importer.import_termbase(tsv_file, project_id="term_proj")

        with pytest.raises(ArtifactValidationError) as exc_info:
            legacy_importer.import_termbase(
                tsv_file, project_id="term_proj", conflict_policy=ConflictPolicy.FAIL
            )
        assert "already exists" in str(exc_info.value)

    def test_conflict_policy_string_normalization(
        self, legacy_importer: LegacyStateImporter, tmp_path: Path
    ) -> None:
        """Verify string representations 'skip', 'overwrite', 'fail' are accepted."""
        tsv_file = tmp_path / "terms.tsv"
        tsv_file.write_text("term\tاصطلاح\n", encoding="utf-8")

        # Lowercase string "skip"
        sum1 = legacy_importer.import_termbase(tsv_file, project_id="str_policy_proj", conflict_policy="skip")
        assert sum1.terms_imported == 1

        # Lowercase string "overwrite"
        sum2 = legacy_importer.import_termbase(tsv_file, project_id="str_policy_proj", conflict_policy="overwrite")
        assert sum2.conflicts_encountered == 1

        # Lowercase string "fail"
        with pytest.raises(ArtifactValidationError):
            legacy_importer.import_termbase(tsv_file, project_id="str_policy_proj", conflict_policy="fail")


# ===========================================================================
# 3. Source Files Never Deleted or Modified Invariant Tests
# ===========================================================================

class TestSourceFilesNeverDeletedOrModified:
    """Verify Mandatory Invariant: Source files are NEVER deleted, unlinked, or modified."""

    def test_source_files_byte_identical_before_and_after_import(
        self, legacy_importer: LegacyStateImporter, legacy_project_fixture: Path
    ) -> None:
        """Verify all project files remain 100% byte-identical (SHA-256) across multiple imports."""
        files = [
            legacy_project_fixture / "manifest.json",
            legacy_project_fixture / "terms.tsv",
            legacy_project_fixture / "tarjoman_cache.json",
            legacy_project_fixture / "chapter_01.txt",
            legacy_project_fixture / "chapter_02.txt",
        ]

        # Record pre-import SHA-256 digests
        pre_hashes: Dict[Path, str] = {f: compute_sha256(f) for f in files}

        # 1. Run import under SKIP
        sum_skip = legacy_importer.import_book_project(legacy_project_fixture, conflict_policy=ConflictPolicy.SKIP)

        # Verify all files still exist and have unchanged SHA-256
        for f in files:
            assert f.exists(), f"Source file was deleted: {f}"
            assert compute_sha256(f) == pre_hashes[f], f"Source file was modified: {f}"

        assert len(sum_skip.source_files_preserved) == len(files)

        # 2. Run import under OVERWRITE
        sum_over = legacy_importer.import_book_project(legacy_project_fixture, conflict_policy=ConflictPolicy.OVERWRITE)

        for f in files:
            assert f.exists(), f"Source file was deleted: {f}"
            assert compute_sha256(f) == pre_hashes[f], f"Source file was modified: {f}"

        # 3. Run import under FAIL (which raises error)
        with pytest.raises(ArtifactValidationError):
            legacy_importer.import_book_project(legacy_project_fixture, conflict_policy=ConflictPolicy.FAIL)

        # Verify files are STILL intact after error rollback
        for f in files:
            assert f.exists(), f"Source file was deleted after error: {f}"
            assert compute_sha256(f) == pre_hashes[f], f"Source file was modified after error: {f}"

    def test_standalone_cache_preserved_byte_identical(
        self, legacy_importer: LegacyStateImporter, tmp_path: Path
    ) -> None:
        """Verify standalone cache file is preserved byte-identical."""
        cache_file = tmp_path / "tarjoman_cache.json"
        cache = ResumableCache(cache_file)
        cache.record_segment(1, 0, "Hello", "سلام")
        original_hash = compute_sha256(cache_file)

        summary = legacy_importer.import_cache_file(cache_file, project_id="cache_proj")

        assert cache_file.exists()
        assert compute_sha256(cache_file) == original_hash
        assert cache_file in summary.source_files_preserved

    def test_standalone_termbase_preserved_byte_identical(
        self, legacy_importer: LegacyStateImporter, tmp_path: Path
    ) -> None:
        """Verify standalone termbase file is preserved byte-identical."""
        tsv_file = tmp_path / "terms.tsv"
        tsv_file.write_text("word\tکلمه\n", encoding="utf-8")
        original_hash = compute_sha256(tsv_file)

        summary = legacy_importer.import_termbase(tsv_file, project_id="tb_proj")

        assert tsv_file.exists()
        assert compute_sha256(tsv_file) == original_hash
        assert tsv_file in summary.source_files_preserved


# ===========================================================================
# 4. Error Handling & Edge Cases Tests
# ===========================================================================

class TestErrorHandlingAndEdgeCases:
    """Test edge cases, missing files, corrupted fixtures, and Persian Unicode handling."""

    def test_nonexistent_project_directory_raises_error(
        self, legacy_importer: LegacyStateImporter, tmp_path: Path
    ) -> None:
        """Verify importing nonexistent directory raises ArtifactValidationError."""
        with pytest.raises(ArtifactValidationError) as exc_info:
            legacy_importer.import_book_project(tmp_path / "does_not_exist")
        assert "does not exist" in str(exc_info.value)

    def test_missing_manifest_raises_error(
        self, legacy_importer: LegacyStateImporter, tmp_path: Path
    ) -> None:
        """Verify missing manifest.json raises ArtifactValidationError."""
        empty_dir = tmp_path / "empty_proj"
        empty_dir.mkdir()
        with pytest.raises(ArtifactValidationError) as exc_info:
            legacy_importer.import_book_project(empty_dir)
        assert "manifest.json not found" in str(exc_info.value)

    def test_corrupted_manifest_json_raises_error(
        self, legacy_importer: LegacyStateImporter, tmp_path: Path
    ) -> None:
        """Verify corrupt JSON in manifest.json raises ArtifactValidationError."""
        corrupt_dir = tmp_path / "corrupt_proj"
        corrupt_dir.mkdir()
        (corrupt_dir / "manifest.json").write_text("{ unclosed json", encoding="utf-8")
        with pytest.raises(ArtifactValidationError) as exc_info:
            legacy_importer.import_book_project(corrupt_dir)
        assert "Failed to parse manifest.json" in str(exc_info.value)

    def test_corrupted_cache_json_raises_error(
        self, legacy_importer: LegacyStateImporter, tmp_path: Path
    ) -> None:
        """Verify corrupt cache file raises ArtifactValidationError."""
        bad_cache = tmp_path / "bad_cache.json"
        bad_cache.write_text("invalid json content", encoding="utf-8")
        with pytest.raises(ArtifactValidationError) as exc_info:
            legacy_importer.import_cache_file(bad_cache, project_id="bad_proj")
        assert "Failed to parse cache JSON file" in str(exc_info.value)

    def test_persian_unicode_and_zwnj_preservation(
        self, legacy_importer: LegacyStateImporter, tmp_path: Path
    ) -> None:
        """Verify Persian Unicode, half-space (ZWNJ), and quotation marks are faithfully preserved."""
        tsv_file = tmp_path / "unicode_terms.tsv"
        # Includes ZWNJ (‌) in 'می‌شود' and Persian quotes «»
        tsv_file.write_text(
            "written\tنوشته‌شده\tgrammar\tبا نیم‌فاصله\n"
            "quote\t«گیومه فارسی»\tliterary\tعلامت نقل قول\n",
            encoding="utf-8",
        )

        summary = legacy_importer.import_termbase(tsv_file, project_id="unicode_proj")
        assert summary.terms_imported == 2

        project_repo = ProjectRepository(legacy_importer.db)
        proj = project_repo.get("unicode_proj")
        assert proj is not None
        assert proj.metadata["terms"]["written"]["persian_translation"] == "نوشته‌شده"
        assert proj.metadata["terminology_map"]["quote"] == "«گیومه فارسی»"
