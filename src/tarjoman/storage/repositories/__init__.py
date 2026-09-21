"""
Typed repositories for Tarjoman workspaces.

Architecture Zero §25.5 (Repository layer owns SQL).
"""
from tarjoman.storage.repositories.artifact_repository import ArtifactRepository
from tarjoman.storage.repositories.job_repository import JobRecord, JobRepository
from tarjoman.storage.repositories.operation_repository import OperationRepository
from tarjoman.storage.repositories.project_repository import ProjectRepository
from tarjoman.storage.repositories.segment_repository import SegmentRepository

__all__ = [
    "ArtifactRepository",
    "JobRecord",
    "JobRepository",
    "OperationRepository",
    "ProjectRepository",
    "SegmentRepository",
]
