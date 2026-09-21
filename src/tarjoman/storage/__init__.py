"""
Tarjoman Storage Subsystem.

Architecture Zero §22.2 & §25:
Content-addressed artifact blob storage and workspace persistence.
"""
from tarjoman.storage.artifact_store import ArtifactStore, StoredBlob

__all__ = [
    "ArtifactStore",
    "StoredBlob",
]
