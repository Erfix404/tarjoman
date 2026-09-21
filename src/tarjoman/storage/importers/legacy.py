"""
Legacy State Importer for Tarjoman Workspaces.

Converts legacy Tarjoman book projects, manifests (manifest.json),
termbases (terms.tsv), and translation caches (cache.json / tarjoman_cache.json)
into canonical SQLite database models and content-addressed artifact store records.

Conforms to:
- Architecture Zero §4 (Canonical Intermediate Representation)
- Architecture Zero §25 (Workspace & Storage Architecture)
- ROADMAP.md (Work Package FND-008: Legacy-state importer)
- Mandatory Invariant: Source files are NEVER deleted, moved, or truncated.
- Deterministic conflict resolution: SKIP (default), OVERWRITE, FAIL.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from pydantic import BaseModel, Field

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
from tarjoman.storage.artifact_store import ArtifactStore, StoredBlob
from tarjoman.storage.database import DatabaseManager
from tarjoman.storage.repositories import (
    ArtifactRepository,
    ProjectRepository,
    SegmentRepository,
)


class ConflictPolicy(str, Enum):
    """Deterministic conflict resolution policy (FND-008)."""

    SKIP = "SKIP"
    OVERWRITE = "OVERWRITE"
    FAIL = "FAIL"


class ImportSummary(BaseModel):
    """Structured report produced by legacy import operations."""

    projects_imported: int = 0
    artifacts_imported: int = 0
    segments_imported: int = 0
    versions_imported: int = 0
    terms_imported: int = 0
    conflicts_encountered: int = 0
    conflicts_resolved: List[Dict[str, Any]] = Field(default_factory=list)
    source_files_preserved: List[Path] = Field(default_factory=list)

    def merge(self, other: ImportSummary) -> ImportSummary:
        """Merge another ImportSummary into this one."""
        self.projects_imported += other.projects_imported
        self.artifacts_imported += other.artifacts_imported
        self.segments_imported += other.segments_imported
        self.versions_imported += other.versions_imported
        self.terms_imported += other.terms_imported
        self.conflicts_encountered += other.conflicts_encountered
        self.conflicts_resolved.extend(other.conflicts_resolved)
        for p in other.source_files_preserved:
            if p not in self.source_files_preserved:
                self.source_files_preserved.append(p)
        return self


def _parse_datetime(val: Any) -> datetime:
    """Safely parse datetime from ISO string or return UTC now."""
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if isinstance(val, str) and val.strip():
        try:
            clean = val.strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)


def _compute_sha256(path: Path) -> str:
    """Compute SHA-256 checksum of a file without modifying it."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class LegacyStateImporter:
    """
    Non-destructive importer for legacy Tarjoman book projects, manifests,
    termbases, and resumable caches.

    Architecture Zero §4, §25, and ROADMAP.md (FND-008).
    - Fixture conversions into canonical SQLite models and ArtifactStore blobs.
    - Deterministic conflict resolution (SKIP, OVERWRITE, FAIL).
    - Mandatory invariant: Source files are NEVER deleted, moved, or truncated.
    """

    def __init__(
        self,
        db: DatabaseManager,
        artifact_store: Optional[ArtifactStore] = None,
        workspace_root: Optional[Union[str, Path]] = None,
    ) -> None:
        self.db = db
        # Ensure schema 001 is applied
        self.db.apply_migrations()

        if artifact_store is not None:
            self.artifact_store = artifact_store
        elif workspace_root is not None:
            self.artifact_store = ArtifactStore(workspace_root)
        elif not db.is_memory and isinstance(db.db_path, Path):
            if db.db_path.parent.name == ".tarjoman":
                self.artifact_store = ArtifactStore(db.db_path.parent.parent)
            else:
                self.artifact_store = ArtifactStore(db.db_path.parent)
        else:
            self.artifact_store = None

        self.project_repo = ProjectRepository(db)
        self.artifact_repo = ArtifactRepository(db)
        self.segment_repo = SegmentRepository(db)

    def _normalize_conflict_policy(self, policy: Union[ConflictPolicy, str]) -> ConflictPolicy:
        if isinstance(policy, ConflictPolicy):
            return policy
        if isinstance(policy, str):
            try:
                return ConflictPolicy(policy.strip().upper())
            except ValueError:
                pass
        raise ValueError(f"Invalid ConflictPolicy: {policy}. Must be SKIP, OVERWRITE, or FAIL.")

    def import_book_project(
        self,
        project_dir: Union[str, Path],
        conflict_policy: Union[ConflictPolicy, str] = ConflictPolicy.SKIP,
        project_id: Optional[str] = None,
    ) -> ImportSummary:
        """
        Import a complete legacy book project directory.

        Reads:
        - manifest.json (BookManifest) -> canonical ProjectSpec
        - chapter_*.txt / *.txt -> ArtifactStore blobs and Artifact records
        - terms.tsv -> structured glossary and terminology entries in project metadata
        - cache.json / tarjoman_cache.json -> Segments and SegmentVersions
        """
        policy = self._normalize_conflict_policy(conflict_policy)
        pdir = Path(project_dir).resolve()
        if not pdir.exists() or not pdir.is_dir():
            raise ArtifactValidationError(
                f"Project directory does not exist or is not a directory: {pdir}",
                details={"project_dir": str(pdir)},
            )

        summary = ImportSummary()
        source_file_hashes: Dict[Path, str] = {}

        def _track_file(fp: Path) -> None:
            if fp.exists() and fp.is_file() and fp not in source_file_hashes:
                source_file_hashes[fp] = _compute_sha256(fp)

        manifest_path = pdir / "manifest.json"
        if not manifest_path.exists():
            raise ArtifactValidationError(
                f"Required manifest.json not found in project directory: {pdir}",
                details={"project_dir": str(pdir)},
            )
        _track_file(manifest_path)

        # 1. Parse manifest.json
        manifest_bytes = manifest_path.read_bytes()
        try:
            manifest_raw = json.loads(manifest_bytes.decode("utf-8"))
        except Exception as exc:
            raise ArtifactValidationError(
                f"Failed to parse manifest.json: {exc}",
                details={"path": str(manifest_path)},
            ) from exc

        title = manifest_raw.get("title", pdir.name)
        src_lang = manifest_raw.get("source_language", "en")
        tgt_lang = manifest_raw.get("target_language", "fa")
        meta = dict(manifest_raw.get("metadata", {}))

        pid = (
            project_id
            or manifest_raw.get("project_id")
            or meta.get("project_id")
            or manifest_raw.get("id")
            or meta.get("id")
            or pdir.name
        )

        domain_id = (
            manifest_raw.get("domain")
            or manifest_raw.get("domain_profile_id")
            or meta.get("domain")
            or meta.get("domain_profile_id")
        )
        style_id = (
            manifest_raw.get("style")
            or manifest_raw.get("style_profile_id")
            or meta.get("style")
            or meta.get("style_profile_id")
        )

        now = datetime.now(timezone.utc)
        project_metadata = {
            **meta,
            "legacy_manifest": {
                "title": title,
                "total_chapters": manifest_raw.get("total_chapters", 1),
                "current_chapter": manifest_raw.get("current_chapter", 0),
                "total_segments": manifest_raw.get("total_segments", 0),
                "translated_segments": manifest_raw.get("translated_segments", 0),
                "terms_count": manifest_raw.get("terms_count", 0),
            },
        }

        project_spec = ProjectSpec(
            project_id=pid,
            name=title,
            default_source_language=src_lang,
            default_target_language=tgt_lang,
            default_domain_profile_id=domain_id,
            default_style_profile_id=style_id,
            created_at=now,
            updated_at=now,
            metadata=project_metadata,
        )

        # Conflict resolution for Project
        existing_project = self.project_repo.get(pid)
        if existing_project is not None:
            summary.conflicts_encountered += 1
            if policy == ConflictPolicy.FAIL:
                raise ArtifactValidationError(
                    f"Project '{pid}' already exists in database and conflict policy is FAIL",
                    details={"project_id": pid},
                )
            elif policy == ConflictPolicy.SKIP:
                summary.conflicts_resolved.append({
                    "entity_type": "project",
                    "id": pid,
                    "action": "skipped",
                    "reason": "already exists",
                })
            elif policy == ConflictPolicy.OVERWRITE:
                summary.conflicts_resolved.append({
                    "entity_type": "project",
                    "id": pid,
                    "action": "overwritten",
                    "reason": "replaced existing project",
                })
                # Preserve existing glossary in metadata if present, then update
                if "glossary" in existing_project.metadata and "glossary" not in project_metadata:
                    project_metadata["glossary"] = existing_project.metadata["glossary"]
                if "terms" in existing_project.metadata and "terms" not in project_metadata:
                    project_metadata["terms"] = existing_project.metadata["terms"]
                if "terminology_map" in existing_project.metadata and "terminology_map" not in project_metadata:
                    project_metadata["terminology_map"] = existing_project.metadata["terminology_map"]
                self.project_repo.update(project_spec)
        else:
            self.project_repo.create(project_spec)
            summary.projects_imported += 1

        # 2. Ingest chapter/text files into ArtifactStore & Artifacts table
        text_files = sorted(
            [
                f for f in pdir.iterdir()
                if f.is_file()
                and f.suffix.lower() in (".txt", ".md")
                and f.name not in ("manifest.json", "terms.tsv", "cache.json", "tarjoman_cache.json")
                and not f.name.startswith(".")
            ],
            key=lambda x: x.name,
        )
        for tf in text_files:
            _track_file(tf)
            art_id = f"{pid}_{tf.stem}"
            file_bytes = tf.read_bytes()
            sha256 = hashlib.sha256(file_bytes).hexdigest()
            blob_path = None

            if self.artifact_store is not None:
                blob = self.artifact_store.store_file(tf)
                blob_path = str(blob.path)
                sha256 = blob.sha256

            existing_art = self.artifact_repo.get(art_id)
            if existing_art is not None:
                summary.conflicts_encountered += 1
                if policy == ConflictPolicy.FAIL:
                    raise ArtifactValidationError(
                        f"Artifact '{art_id}' already exists in database and conflict policy is FAIL",
                        details={"artifact_id": art_id},
                    )
                elif policy == ConflictPolicy.SKIP:
                    summary.conflicts_resolved.append({
                        "entity_type": "artifact",
                        "id": art_id,
                        "action": "skipped",
                        "reason": "already exists",
                    })
                elif policy == ConflictPolicy.OVERWRITE:
                    summary.conflicts_resolved.append({
                        "entity_type": "artifact",
                        "id": art_id,
                        "action": "overwritten",
                        "reason": "replaced existing artifact",
                    })
                    self.artifact_repo.delete(art_id)
                    new_art = Artifact(
                        artifact_id=art_id,
                        project_id=pid,
                        kind=ArtifactKind.SOURCE_DOCUMENT,
                        raw_sha256=sha256,
                        blob_path=blob_path,
                        source_uri=tf.name,
                        created_at=now,
                        metadata={"filename": tf.name, "size_bytes": len(file_bytes)},
                    )
                    self.artifact_repo.create(new_art)
            else:
                new_art = Artifact(
                    artifact_id=art_id,
                    project_id=pid,
                    kind=ArtifactKind.SOURCE_DOCUMENT,
                    raw_sha256=sha256,
                    blob_path=blob_path,
                    source_uri=tf.name,
                    created_at=now,
                    metadata={"filename": tf.name, "size_bytes": len(file_bytes)},
                )
                self.artifact_repo.create(new_art)
                summary.artifacts_imported += 1

        # 3. Ingest termbase if present
        terms_file = None
        for candidate in ("terms.tsv", "terms.txt", "terminology.tsv"):
            p = pdir / candidate
            if p.exists() and p.is_file():
                terms_file = p
                break
        if terms_file is not None:
            _track_file(terms_file)
            term_summary = self.import_termbase(terms_file, pid, conflict_policy=policy)
            summary.merge(term_summary)

        # 4. Ingest cache if present
        cache_file = None
        for candidate in ("cache.json", "tarjoman_cache.json"):
            p = pdir / candidate
            if p.exists() and p.is_file():
                cache_file = p
                break
        if cache_file is not None:
            _track_file(cache_file)
            cache_summary = self.import_cache_file(cache_file, pid, conflict_policy=policy)
            summary.merge(cache_summary)

        # 5. Mandatory invariant verification: Source files are NEVER modified or deleted
        for fp, original_sha in source_file_hashes.items():
            if not fp.exists():
                raise AssertionError(f"Source file was deleted during import: {fp}")
            current_sha = _compute_sha256(fp)
            if current_sha != original_sha:
                raise AssertionError(
                    f"Source file content changed during import: {fp} (expected {original_sha}, got {current_sha})"
                )
            if fp not in summary.source_files_preserved:
                summary.source_files_preserved.append(fp)

        return summary

    def import_termbase(
        self,
        termbase_tsv_path: Union[str, Path],
        project_id: str,
        conflict_policy: Union[ConflictPolicy, str] = ConflictPolicy.SKIP,
    ) -> ImportSummary:
        """
        Import a standalone termbase TSV file into project metadata.

        Architecture Zero §4.2: Structured glossary entries in ProjectSpec metadata.
        """
        policy = self._normalize_conflict_policy(conflict_policy)
        tsv_path = Path(termbase_tsv_path).resolve()
        if not tsv_path.exists() or not tsv_path.is_file():
            raise ArtifactValidationError(
                f"Termbase file does not exist or is not a file: {tsv_path}",
                details={"termbase_tsv_path": str(tsv_path)},
            )

        initial_sha = _compute_sha256(tsv_path)
        summary = ImportSummary()

        project = self.project_repo.get(project_id)
        now = datetime.now(timezone.utc)
        if project is None:
            project = ProjectSpec(
                project_id=project_id,
                name=project_id,
                created_at=now,
                updated_at=now,
                metadata={"imported_standalone": True},
            )
            self.project_repo.create(project)
            summary.projects_imported += 1

        content = tsv_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        metadata = dict(project.metadata)
        glossary: List[Dict[str, Any]] = list(metadata.get("glossary", []))
        terms_map: Dict[str, Dict[str, Any]] = dict(metadata.get("terms", {}))
        terminology_map: Dict[str, str] = dict(metadata.get("terminology_map", {}))

        def _find_glossary_idx(en_key: str) -> int:
            target = en_key.strip().lower()
            for idx, item in enumerate(glossary):
                if (
                    item.get("english_term", "").strip().lower() == target
                    or item.get("en", "").strip().lower() == target
                ):
                    return idx
            return -1

        for idx, line in enumerate(lines):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            first_col = parts[0].strip().lower()
            second_col = parts[1].strip().lower() if len(parts) > 1 else ""

            # Detect standard header row
            is_header = (
                idx == 0
                and (
                    first_col in ("english_term", "en_term", "english", "source_term")
                    or (
                        first_col in ("term", "terms")
                        and second_col in ("persian_translation", "translation", "persian", "fa", "target_term")
                    )
                )
            )
            if is_header:
                continue

            en = parts[0].strip()
            fa = parts[1].strip() if len(parts) > 1 else ""
            domain = parts[2].strip() if len(parts) > 2 else ""
            notes = parts[3].strip() if len(parts) > 3 else ""

            if not en or not fa:
                continue

            en_key = en
            term_exists = (en_key in terms_map) or (_find_glossary_idx(en_key) >= 0)

            if term_exists:
                summary.conflicts_encountered += 1
                if policy == ConflictPolicy.FAIL:
                    raise ArtifactValidationError(
                        f"Term '{en}' already exists in project '{project_id}' and conflict policy is FAIL",
                        details={"project_id": project_id, "term": en},
                    )
                elif policy == ConflictPolicy.SKIP:
                    summary.conflicts_resolved.append({
                        "entity_type": "term",
                        "id": en,
                        "action": "skipped",
                        "reason": "already exists",
                    })
                elif policy == ConflictPolicy.OVERWRITE:
                    summary.conflicts_resolved.append({
                        "entity_type": "term",
                        "id": en,
                        "action": "overwritten",
                        "reason": "replaced existing term",
                    })
                    terms_map[en_key] = {
                        "fa_term": fa,
                        "persian_translation": fa,
                        "fa": fa,
                        "domain": domain,
                        "notes": notes,
                    }
                    terminology_map[en_key] = fa
                    g_idx = _find_glossary_idx(en_key)
                    entry = {
                        "english_term": en,
                        "persian_translation": fa,
                        "en": en,
                        "fa": fa,
                        "domain": domain,
                        "notes": notes,
                    }
                    if g_idx >= 0:
                        glossary[g_idx] = entry
                    else:
                        glossary.append(entry)
            else:
                terms_map[en_key] = {
                    "fa_term": fa,
                    "persian_translation": fa,
                    "fa": fa,
                    "domain": domain,
                    "notes": notes,
                }
                terminology_map[en_key] = fa
                glossary.append({
                    "english_term": en,
                    "persian_translation": fa,
                    "en": en,
                    "fa": fa,
                    "domain": domain,
                    "notes": notes,
                })
                summary.terms_imported += 1

        metadata["glossary"] = glossary
        metadata["terms"] = terms_map
        metadata["terminology_map"] = terminology_map
        if "legacy_manifest" in metadata and isinstance(metadata["legacy_manifest"], dict):
            metadata["legacy_manifest"]["terms_count"] = len(glossary)

        project.metadata = metadata
        project.updated_at = now
        self.project_repo.update(project)

        # Invariant check
        if not tsv_path.exists():
            raise AssertionError(f"Source termbase file was deleted: {tsv_path}")
        if _compute_sha256(tsv_path) != initial_sha:
            raise AssertionError(f"Source termbase file was modified: {tsv_path}")
        if tsv_path not in summary.source_files_preserved:
            summary.source_files_preserved.append(tsv_path)

        return summary

    def _find_or_create_chapter_artifact(
        self,
        project_id: str,
        chapter_id: Optional[int],
        cache_file_name: str,
        conflict_policy: ConflictPolicy,
        summary: ImportSummary,
    ) -> str:
        """Find an existing artifact matching a chapter or create a virtual one."""
        existing_artifacts = self.artifact_repo.list_by_project(project_id)

        if chapter_id is not None:
            patterns = [
                f"chapter_{chapter_id}",
                f"chapter_{chapter_id:02d}",
                f"chapter{chapter_id}",
                f"ch_{chapter_id}",
                f"ch{chapter_id}",
            ]
            for art in existing_artifacts:
                art_id_lower = art.artifact_id.lower()
                if any(p in art_id_lower for p in patterns):
                    return art.artifact_id
                if art.metadata.get("chapter_id") == chapter_id:
                    return art.artifact_id

        if len(existing_artifacts) == 1 and (chapter_id is None or chapter_id in (0, 1)):
            return existing_artifacts[0].artifact_id

        if chapter_id is not None:
            target_art_id = f"{project_id}_chapter_{chapter_id}"
        else:
            target_art_id = f"{project_id}_document"

        existing_art = self.artifact_repo.get(target_art_id)
        if existing_art is not None:
            return existing_art.artifact_id

        now = datetime.now(timezone.utc)
        new_art = Artifact(
            artifact_id=target_art_id,
            project_id=project_id,
            kind=ArtifactKind.SOURCE_DOCUMENT,
            source_uri=f"legacy_cache:{cache_file_name}#chapter_{chapter_id if chapter_id is not None else 0}",
            created_at=now,
            metadata={"chapter_id": chapter_id, "imported_from_cache": cache_file_name},
        )
        self.artifact_repo.create(new_art)
        summary.artifacts_imported += 1
        return target_art_id

    def import_cache_file(
        self,
        cache_file_path: Union[str, Path],
        project_id: str,
        artifact_id: Optional[str] = None,
        conflict_policy: Union[ConflictPolicy, str] = ConflictPolicy.SKIP,
    ) -> ImportSummary:
        """
        Import a standalone translation cache JSON file (cache.json or tarjoman_cache.json).

        Converts cached segment entries into:
        - Artifact (document/chapter)
        - Segments (source text + structural locators)
        - SegmentVersions (DRAFT for translated_text, REVISED for polished_text)
        """
        policy = self._normalize_conflict_policy(conflict_policy)
        cache_path = Path(cache_file_path).resolve()
        if not cache_path.exists() or not cache_path.is_file():
            raise ArtifactValidationError(
                f"Cache file does not exist or is not a file: {cache_path}",
                details={"cache_file_path": str(cache_path)},
            )

        initial_sha = _compute_sha256(cache_path)
        summary = ImportSummary()

        project = self.project_repo.get(project_id)
        now = datetime.now(timezone.utc)
        if project is None:
            project = ProjectSpec(
                project_id=project_id,
                name=project_id,
                created_at=now,
                updated_at=now,
                metadata={"imported_standalone": True},
            )
            self.project_repo.create(project)
            summary.projects_imported += 1

        try:
            cache_data = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ArtifactValidationError(
                f"Failed to parse cache JSON file: {exc}",
                details={"path": str(cache_path)},
            ) from exc

        raw_entries: List[Dict[str, Any]] = []
        if isinstance(cache_data, dict):
            if "segments" in cache_data and isinstance(cache_data["segments"], list):
                raw_entries = cache_data["segments"]
            else:
                for k, v in cache_data.items():
                    if isinstance(v, dict) and ("source_text" in v or "translated_text" in v or "segment_id" in v):
                        item = dict(v)
                        item.setdefault("key", k)
                        raw_entries.append(item)
        elif isinstance(cache_data, list):
            raw_entries = [dict(x) for x in cache_data if isinstance(x, dict)]

        # Deterministic sort by (chapter_id, segment_id)
        raw_entries.sort(key=lambda x: (int(x.get("chapter_id", 0) or 0), int(x.get("segment_id", 0) or 0)))

        chapters: Dict[Optional[int], List[Dict[str, Any]]] = {}
        for entry in raw_entries:
            ch = entry.get("chapter_id")
            ch_key = int(ch) if ch is not None else None
            chapters.setdefault(ch_key, []).append(entry)

        for ch_key, entries in chapters.items():
            if artifact_id is not None:
                target_art_id = artifact_id
                existing_art = self.artifact_repo.get(target_art_id)
                if existing_art is None:
                    new_art = Artifact(
                        artifact_id=target_art_id,
                        project_id=project_id,
                        kind=ArtifactKind.SOURCE_DOCUMENT,
                        source_uri=f"legacy_cache:{cache_path.name}",
                        created_at=now,
                        metadata={"imported_from_cache": cache_path.name},
                    )
                    self.artifact_repo.create(new_art)
                    summary.artifacts_imported += 1
            else:
                target_art_id = self._find_or_create_chapter_artifact(
                    project_id=project_id,
                    chapter_id=ch_key,
                    cache_file_name=cache_path.name,
                    conflict_policy=policy,
                    summary=summary,
                )

            for entry in entries:
                seg_num = int(entry.get("segment_id", 0) or 0)
                source_text = entry.get("source_text", "")
                trans_text = entry.get("translated_text")
                polish_text = entry.get("polished_text")
                updated_at_dt = _parse_datetime(entry.get("updated_at"))

                locator = f"ch_{ch_key}:seg_{seg_num}" if ch_key is not None else f"seg_{seg_num}"
                segment_id = f"{target_art_id}:{locator}"
                source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()

                # Check if segment exists
                existing_seg = self.segment_repo.get(segment_id)
                if existing_seg is None:
                    with self.db.connection() as conn:
                        row = conn.execute(
                            "SELECT segment_id FROM segments WHERE artifact_id = ? AND structural_locator = ?;",
                            (target_art_id, locator),
                        ).fetchone()
                        if row:
                            existing_seg = self.segment_repo.get(row[0])

                if existing_seg is not None:
                    summary.conflicts_encountered += 1
                    if policy == ConflictPolicy.FAIL:
                        raise ArtifactValidationError(
                            f"Segment '{segment_id}' already exists in database and conflict policy is FAIL",
                            details={"segment_id": segment_id},
                        )
                    elif policy == ConflictPolicy.SKIP:
                        summary.conflicts_resolved.append({
                            "entity_type": "segment",
                            "id": segment_id,
                            "action": "skipped",
                            "reason": "already exists",
                        })
                        continue
                    elif policy == ConflictPolicy.OVERWRITE:
                        summary.conflicts_resolved.append({
                            "entity_type": "segment",
                            "id": segment_id,
                            "action": "overwritten",
                            "reason": "replaced existing segment",
                        })
                        self.segment_repo.delete(existing_seg.segment_id)

                # Create Segment
                segment = Segment(
                    segment_id=segment_id,
                    artifact_id=target_art_id,
                    structural_locator=locator,
                    source_text=source_text,
                    source_content_hash=source_hash,
                    translatable=True,
                    structural_context={
                        "chapter_id": ch_key,
                        "segment_id": seg_num,
                    },
                    metadata={"cache_key": entry.get("key", "")},
                )
                self.segment_repo.create(segment)
                summary.segments_imported += 1

                # Create SegmentVersions
                draft_version_id = None
                if trans_text:
                    draft_version_id = f"{segment_id}:draft"
                    ver_draft = SegmentVersion(
                        segment_version_id=draft_version_id,
                        segment_id=segment_id,
                        kind=SegmentVersionKind.DRAFT,
                        text=trans_text,
                        author=AuthorType.SYSTEM,
                        author_id="legacy_cache",
                        created_at=updated_at_dt,
                        provenance={"source": "legacy_cache", "status": "draft"},
                    )
                    self.segment_repo.add_version(ver_draft)
                    summary.versions_imported += 1

                if polish_text:
                    revised_version_id = f"{segment_id}:revised"
                    ver_revised = SegmentVersion(
                        segment_version_id=revised_version_id,
                        segment_id=segment_id,
                        kind=SegmentVersionKind.REVISED,
                        text=polish_text,
                        parent_version_id=draft_version_id,
                        author=AuthorType.SYSTEM,
                        author_id="legacy_cache",
                        created_at=updated_at_dt,
                        provenance={"source": "legacy_cache", "status": "revised"},
                    )
                    self.segment_repo.add_version(ver_revised)
                    summary.versions_imported += 1

        # Invariant check
        if not cache_path.exists():
            raise AssertionError(f"Source cache file was deleted: {cache_path}")
        if _compute_sha256(cache_path) != initial_sha:
            raise AssertionError(f"Source cache file was modified: {cache_path}")
        if cache_path not in summary.source_files_preserved:
            summary.source_files_preserved.append(cache_path)

        return summary
