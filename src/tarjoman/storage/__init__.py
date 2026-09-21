"""
Tarjoman Storage Subsystem.

Architecture Zero §22.2, §25, §26:
- Content-addressed artifact blob storage
- SQLite transactional database engine and migration runner
- Typed repositories for Project, Operation, Artifact, Segment, and Job
- Migration discipline and verification
- Legacy-state importer (FND-008)
"""
from tarjoman.core.errors import MigrationError
from tarjoman.storage.artifact_store import ArtifactStore, StoredBlob
from tarjoman.storage.database import DatabaseManager
from tarjoman.storage.importers import (
    ConflictPolicy,
    ImportSummary,
    LegacyStateImporter,
)
from tarjoman.storage.repositories import (
    ArtifactRepository,
    JobRecord,
    JobRepository,
    OperationRepository,
    ProjectRepository,
    SegmentRepository,
)

__all__ = [
    "ArtifactRepository",
    "ArtifactStore",
    "ConflictPolicy",
    "DatabaseManager",
    "ImportSummary",
    "JobRecord",
    "JobRepository",
    "LegacyStateImporter",
    "MigrationError",
    "OperationRepository",
    "ProjectRepository",
    "SegmentRepository",
    "StoredBlob",
]
