"""
Tarjoman application package — use-case orchestration (Architecture Zero §22).

Exports application services that coordinate provider ports, policy
enforcement, and provenance tracking.  Application modules import from
``tarjoman.core`` only — never from concrete infrastructure packages
(``storage``, ``providers``, ``interfaces``, ``audio``).

Work Package: TRN-001 — Provider port/capabilities.
"""

from tarjoman.application.translation_service import TranslationService

__all__ = [
    "TranslationService",
]
