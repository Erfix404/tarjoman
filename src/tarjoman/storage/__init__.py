"""
Tarjoman Storage Subsystem.

Architecture Zero §22.2, §25, §26:
- Content-addressed artifact blob storage
- SQLite transactional database engine and migration runner
- Typed repositories for Project, Operation, Artifact, Segment, and Job
"""
from tarjoman.storage.artifact_store import ArtifactStore, StoredBlob
from tarjoman.storage.database import DatabaseManager
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
    "DatabaseManager",
    "JobRecord",
    "JobRepository",
    "OperationRepository",
    "ProjectRepository",
    "SegmentRepository",
    "StoredBlob",
]
