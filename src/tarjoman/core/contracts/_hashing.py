"""
Stable ID and content hashing helpers.

Architecture Zero §4.5 and §42 — deterministic, versioned, canonical
hashing for content, segment identity, and placeholder tokens.

Hash domains are distinct (§42): ``compute_content_hash`` is for
segment source content; ``compute_segment_id`` is for stable identity
based on artifact + structural locator; no code may substitute one
hash domain for another.
"""
from __future__ import annotations

import hashlib
import unicodedata


def compute_content_hash(text: str) -> str:
    """Canonical SHA-256 of NFC-normalized text.

    Normalization ensures that visually identical Unicode sequences
    (e.g. composed vs. decomposed Persian characters) produce the same
    hash.  The result is a lowercase hex digest prefixed with ``sha256:``
    for domain clarity.

    Args:
        text: The source text to hash.

    Returns:
        A string of the form ``sha256:<64-hex-chars>``.
    """
    normalized = unicodedata.normalize("NFC", text)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def compute_segment_id(artifact_id: str, structural_locator: str) -> str:
    """Deterministic stable segment ID from artifact identity + locator.

    Architecture §4.5: stable segment IDs are based on artifact identity
    + structural locator, **not text alone**, so repeated identical
    paragraphs remain distinct.

    The ID is a SHA-256 digest of the concatenation ``artifact_id``
    + ``\\x00`` + ``structural_locator``, prefixed with ``seg:`` for
    human readability.

    Args:
        artifact_id: The owning artifact's ID.
        structural_locator: The paragraph/cue/cell/run path locator.

    Returns:
        A string of the form ``seg:<64-hex-chars>``.
    """
    payload = f"{artifact_id}\x00{structural_locator}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"seg:{digest}"


def compute_placeholder(span_id: str, prefix: str = "__TRJ_") -> str:
    """Collision-resistant placeholder token for a protected span.

    Placeholder tokens are scoped to the operation/segment (§4.7).
    The token embeds a truncated SHA-256 of the ``span_id`` to resist
    accidental collisions with natural-language text.

    Args:
        span_id: The protected span's unique identifier.
        prefix: Token prefix (default ``__TRJ_``).

    Returns:
        A placeholder string like ``__TRJ_a1b2c3d4e5f6__``.
    """
    digest = hashlib.sha256(span_id.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}{digest}__"
